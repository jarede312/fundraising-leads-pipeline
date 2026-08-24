"""
Phase 4: load ND-domiciled IRS-exempt PTO/PTA/booster/school-foundation organizations,
match them to schools, and populate school_org_links with a score.

Sources: IRS Exempt Organizations Business Master File (state extract, eo_nd.csv - name,
address, NTEE code, most-recent-return revenue) and the Form 990-N e-Postcard bulk file
(national, filtered to ND - principal officer name, the smallest orgs only).

Scope cut, stated plainly: Form 990/990-EZ full return data (gross receipts + principal
officer for organizations too large to file the e-Postcard) requires parsing IRS's e-file
XML archive, a materially bigger effort than this pilot's BMF+e-Postcard approach. ~27% of
the plausible orgs found here (33/123) have no e-Postcard record and so get no principal
officer name from this phase - flagged at Checkpoint 4, not silently absorbed.

Matching: name-first (pg_trgm), scoped to the org's own city, not address-first as the
original brief specified - see PLAN.md 1.2 and the Checkpoint 4 report for why (PTO mailing
addresses are frequently a volunteer officer's home, which turns over every 1-2 years;
school address matching would silently miss the active PTOs at exactly the schools where
officers rotate). Address/ZIP agreement is folded in as a score booster, not the primary
signal.

Run: python -m ingest.phase4_irs
"""
import re
from collections import defaultdict

from . import config, db

RAW = config.RAW_DIR

KEYWORD_RE = re.compile(
    r"\b(PTO|PTA|BOOSTER|PARENT TEACHER|FFA|FBLA|SCHOOL FOUNDATION|SCHOOL FUND|"
    r"ROBOTICS TEAM|SPEECH TEAM|DEBATE TEAM|CHOIR|BAND PARENTS|MUSIC BOOSTERS)\b",
    re.I,
)
EXCLUDE_RE = re.compile(
    r"\b(BGS|OSS|AFB|AIR FORCE|SQUADRON|WING|BASE|FIRE DEPARTMENT|VOLUNTEER FIRE|CITY CHOIR)\b",
    re.I,
)

# Generic org-type words stripped off to recover the likely school/mascot-identifying
# fragment of the name, used as the matching key against schools.name.
STRIP_WORDS_RE = re.compile(
    r"\b(BOOSTER CLUB|BOOSTERS|BOOSTER|PARENT TEACHER ORGANIZATION|PARENT TEACHER "
    r"ASSOCIATION|PTO|PTA|SCHOOL FOUNDATION|FOUNDATION|ALUMNI CHAPTER|ALUMNI AND "
    r"SUPPORTERS|ALUMNI|FFA|FBLA|ATHLETIC|INC\.?|INCORPORATED|CLUB)\b",
    re.I,
)


def classify_org_type(name):
    n = name.upper()
    if "PTO" in n or "PARENT TEACHER" in n:
        return "pto"
    if "PTA" in n:
        return "pta"
    if "BOOSTER" in n:
        return "booster"
    if "FOUNDATION" in n:
        return "foundation"
    return "other"


def core_name(name):
    n = STRIP_WORDS_RE.sub(" ", name)
    n = re.sub(r"\s+", " ", n).strip()
    return n or name


def load_bmf():
    import csv

    with open(RAW / "irs_eo_nd.csv", newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    hits = [
        r for r in rows
        if KEYWORD_RE.search(r["NAME"]) and not EXCLUDE_RE.search(r["NAME"]) and r["CITY"] != "MINOT AFB"
    ]
    return hits


def load_epostcard_officers(eins):
    """EIN -> (tax_year, principal_officer_name), most recent year only."""
    out = {}
    with open(RAW / "epostcard_nd.txt", encoding="utf-8") as fh:
        for line in fh:
            p = line.rstrip("\n").split("|")
            if len(p) < 9:
                continue
            ein, year, officer = p[0], p[1], p[8].strip()
            if ein in eins:
                prev = out.get(ein)
                if prev is None or year > prev[0]:
                    out[ein] = (year, officer or None)
    return out


def main():
    conn = db.connect()
    bmf_rows = load_bmf()
    eins = {r["EIN"] for r in bmf_rows}
    officers = load_epostcard_officers(eins)

    with db.ingest_run(conn, "irs_990", "IRS EO BMF (eo_nd.csv) + 990-N e-Postcard bulk file, filtered to ND PTO/PTA/booster/school-foundation orgs", "ND") as (run_id, counts):
        with conn.cursor() as cur:
            for r in bmf_rows:
                counts["in"] += 1
                ein = r["EIN"]
                year, officer = officers.get(ein, (None, None))
                if year is None:
                    # fall back to the BMF's own most-recent-return period (YYYYMM)
                    tp = r.get("TAX_PERIOD") or ""
                    year = tp[:4] if len(tp) >= 4 and tp[:4].isdigit() else "2025"
                revenue = None
                try:
                    revenue = float(r["REVENUE_AMT"]) if r["REVENUE_AMT"] not in (None, "") else None
                except ValueError:
                    pass

                cur.execute(
                    """
                    INSERT INTO nonprofit_orgs (
                        ein, fiscal_year, name, org_type, filing_type,
                        gross_receipts, total_revenue, principal_officer_name,
                        street, city, state_code, zip, ingest_run_id
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, 'ND', %s, %s
                    )
                    ON CONFLICT (ein, fiscal_year) DO UPDATE SET
                        name = EXCLUDED.name, principal_officer_name = EXCLUDED.principal_officer_name
                    """,
                    (
                        ein, int(year) if year else 0, r["NAME"], classify_org_type(r["NAME"]),
                        "990N" if officer is not None or ein in officers else None,
                        revenue, revenue, officer,
                        r["STREET"], r["CITY"], r["ZIP"][:5] if r["ZIP"] else None, run_id,
                    ),
                )
                counts["written"] += 1
        conn.commit()

    # matching: name-first (pg_trgm), scoped to the org's city; ZIP agreement as a booster.
    with conn.cursor() as cur:
        cur.execute("SELECT ein, name, city, zip FROM nonprofit_orgs WHERE state_code = 'ND'")
        orgs = cur.fetchall()

    matched = 0
    with conn.cursor() as cur:
        for ein, name, city, zipc in orgs:
            key = core_name(name)
            cur.execute(
                """
                SELECT id, name, city, zip, similarity(name, %s) AS sim
                FROM schools
                WHERE state_code = 'ND' AND status = 'open'
                  AND (city = %s OR similarity(city, %s) > 0.6)
                ORDER BY sim DESC
                LIMIT 3
                """,
                (key, city, city),
            )
            candidates = cur.fetchall()
            if not candidates:
                continue
            best = candidates[0]
            school_id, school_name, school_city, school_zip, sim = best

            score = float(sim)
            method = "name_trgm"
            if zipc and school_zip and zipc[:5] == school_zip[:5]:
                score = min(1.0, score + 0.15)
                method = "name_and_zip"

            if score < 0.15:
                continue  # not even a plausible candidate; don't force a row

            cur.execute(
                """
                INSERT INTO school_org_links (school_id, ein, match_method, match_score)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (school_id, ein) DO UPDATE SET
                    match_method = EXCLUDED.match_method, match_score = EXCLUDED.match_score
                """,
                (school_id, ein, method, round(score, 3)),
            )
            matched += 1
    conn.commit()
    conn.close()

    print(f"Loaded {len(bmf_rows)} orgs ({len(officers)} with an e-Postcard principal officer).")
    print(f"Matched {matched} of {len(orgs)} orgs to a candidate school.")


if __name__ == "__main__":
    main()
