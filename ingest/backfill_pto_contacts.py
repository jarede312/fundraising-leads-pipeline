"""One-time backfill: promote the IRS-filed principal officer of each *confirmed*
school_org_links match into a `contacts` row.

Why: WEBAPP_PLAN.md Checkpoint 0 flagged that PTO/booster contacts are almost entirely
absent from `contacts` (1 pto_president in the whole state) even though the IRS layer
already names an officer for 38 confirmed matches. No new scraping - this just surfaces
data already in the database. There is no email or phone on a 990/990-N filing, so these
rows are name-only, `email_source='unknown'`, never verified - visibly a different tier
of contact than a scraped or phone-verified one, per the schema's provenance principle.

contacts.role has no generic "IRS-filed officer" value, so org_type maps to the closest
fit ('pto'/'pta' -> pto_president, 'booster' -> booster_president); foundation/other/
unclassified have no fit at all and fall back to 'other'. The real org name and filing
year go in role_detail so the imprecision is visible, not hidden.

One org can file under multiple fiscal years; only the most recent confirmed filing per
(school, EIN) is used, so a re-run of Phase 4 doesn't produce multiple officer rows for
the same organization.

Re-running this script will duplicate rows - there's no natural key to check against yet
(same accepted gap as Phase 5's staff crawl). Fine for a one-time pass.

Run: python -m ingest.backfill_pto_contacts
"""
from . import db

ROLE_BY_ORG_TYPE = {
    "pto": "pto_president",
    "pta": "pto_president",
    "booster": "booster_president",
}


def split_name(raw: str) -> tuple[str, str]:
    name = raw.strip()
    if name == name.upper():
        name = name.title()
    parts = name.split()
    if len(parts) == 1:
        return parts[0], ""
    return " ".join(parts[:-1]), parts[-1]


def main():
    conn = db.connect()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (l.school_id, l.ein)
                l.school_id, n.name, n.org_type, n.ein, n.fiscal_year,
                n.principal_officer_name
            FROM school_org_links l
            JOIN nonprofit_orgs n ON n.ein = l.ein
            WHERE l.confirmed = true AND n.principal_officer_name IS NOT NULL
            ORDER BY l.school_id, l.ein, n.fiscal_year DESC
            """
        )
        candidates = cur.fetchall()

    with db.ingest_run(
        conn, "irs_990",
        "Backfill: promote confirmed school_org_links.principal_officer_name into contacts "
        "(no email/phone available from a 990 filing)",
        "ND",
    ) as (run_id, counts):
        with conn.cursor() as cur:
            for school_id, org_name, org_type, ein, fiscal_year, officer_name in candidates:
                counts["in"] += 1
                first_name, last_name = split_name(officer_name)

                cur.execute(
                    """
                    SELECT 1 FROM contacts
                    WHERE school_id = %s AND first_name = %s AND last_name = %s
                    """,
                    (school_id, first_name, last_name),
                )
                if cur.fetchone():
                    continue

                role = ROLE_BY_ORG_TYPE.get(org_type, "other")
                role_detail = (
                    f"IRS Form 990 principal officer, {org_name} "
                    f"(EIN {ein}, FY{fiscal_year}) — no email or phone on file"
                )
                cur.execute(
                    """
                    INSERT INTO contacts
                        (school_id, role, role_detail, first_name, last_name,
                         email_source, email_confidence, status, confidence, ingest_run_id)
                    VALUES (%s, %s, %s, %s, %s, 'unknown', 'unknown', 'active', 'low', %s)
                    """,
                    (school_id, role, role_detail, first_name, last_name, run_id),
                )
                counts["written"] += cur.rowcount
        conn.commit()

    conn.close()
    print(f"Backfilled {counts['written']} PTO/booster contacts "
          f"from {counts['in']} confirmed IRS matches.")


if __name__ == "__main__":
    main()
