"""
Phase 7 sweep: the re-runnable "August refresh." Re-crawls every ND public district/school
site using the exact same logic as phase5_crawl (crawl_site()), then diffs the result
against the current *active*, *llm_extract*-sourced contacts instead of blindly
overwriting them.

Scope: only web-crawled (llm_extract) contacts are swept here. State-directory contacts
(ND DPI) refresh by re-running phase2_dpi against next year's file - a much simpler,
already-solved problem (DPI is authoritative and republished wholesale each year; there's
nothing to "diff" there the way there is for a scraped page).

Diffing rules, by role:
- Single-holder roles (principal, superintendent, office_manager, activities_director,
  athletic_director, band_director, choir_director, drama_director, and the four PTO/
  booster roles): a school normally has one. Same name found again -> confirmed. A
  DIFFERENT name found -> a real personnel change: the old contact is marked 'departed'
  with a contact_verifications row (outcome='changed', pointing at the new contact's id);
  the new one is inserted fresh. Nobody found this time -> 'suspected_stale' on the old
  contact (we lack positive confirmation they left, just that we didn't see them again -
  none of contact_verifications.outcome's five values cleanly fit that, so no verification
  row is written for it, just the status flip).
- Multi-holder roles (assistant_principal, music_teacher): a school can legitimately have
  several at once. There's no way to confidently pair "who replaced whom" when the roster
  changes size, so this is plain set reconciliation, not change-inference: names still
  present are confirmed, names no longer found are 'suspected_stale', brand-new names are
  inserted fresh.

A site that fails to fetch at all this run (robots.txt, timeout, 404 - see the gap list)
is left completely untouched: its existing contacts are neither confirmed nor marked
stale, since "not found" only means something for a (school, role) we actually got to
look at this time.

A `signals` row is written only for roles the schema's signal_type CHECK actually has a
slot for (new_principal, new_music_teacher, new_activities_director, pto_officer_change
for any of the four PTO/booster roles) - every other role still gets its contact status
and contact_verifications updated, it just doesn't get a signals row.

Run: python -m ingest.phase7_sweep
"""
import json
import sys

import httpx

from . import config, db
from .phase5_crawl import build_targets, crawl_site, load_district_email_info, write_gap_csv

MULTI_HOLDER_ROLES = {"assistant_principal", "music_teacher"}

SIGNAL_TYPE = {
    "principal": "new_principal",
    "music_teacher": "new_music_teacher",
    "activities_director": "new_activities_director",
    "pto_president": "pto_officer_change",
    "pto_fundraising_chair": "pto_officer_change",
    "pto_treasurer": "pto_officer_change",
    "booster_president": "pto_officer_change",
}

INSERT_CONTACT_SQL = """
    INSERT INTO contacts (
        school_id, role, role_detail, first_name, last_name,
        email, email_source, email_confidence, phone, source_url, ingest_run_id
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    RETURNING id
"""


def norm(first, last):
    return ((first or "").strip().lower(), (last or "").strip().lower())


def load_existing(conn):
    """(school_id, role) -> {(first,last)_normalized: contact_id} for active,
    llm_extract-sourced contacts only - the only ones this sweep is allowed to touch."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT c.id, c.school_id, c.role, c.first_name, c.last_name
        FROM contacts c
        JOIN ingest_runs ir ON ir.id = c.ingest_run_id
        WHERE c.status = 'active' AND ir.source = 'llm_extract'
        """
    )
    existing = {}
    for cid, school_id, role, first, last in cur.fetchall():
        existing.setdefault((school_id, role), {})[norm(first, last)] = cid
    return existing


def confirm(cur, contact_id):
    cur.execute(
        "UPDATE contacts SET last_verified_at = now(), last_verified_method = 'scrape' WHERE id = %s",
        (contact_id,),
    )
    cur.execute(
        "INSERT INTO contact_verifications (contact_id, method, outcome) VALUES (%s, 'scrape', 'confirmed')",
        (contact_id,),
    )


def insert_contact(cur, school_id, role, rec, run_id):
    first, last, role_detail, email, esrc, econf, phone, page_url = rec
    cur.execute(
        INSERT_CONTACT_SQL,
        (school_id, role, role_detail, first, last, email, esrc, econf, phone, page_url, run_id),
    )
    return cur.fetchone()[0]


def reconcile_site(cur, school_id, role, found_people, existing, run_id, counts):
    key = (school_id, role)
    old_by_name = dict(existing.get(key, {}))
    found_by_name = {norm(f, l): (f, l, rd, e, es, ec, p, u) for (f, l, rd, e, es, ec, p, u) in found_people}

    if role in MULTI_HOLDER_ROLES:
        for name_key, rec in found_by_name.items():
            if name_key in old_by_name:
                confirm(cur, old_by_name.pop(name_key))
            else:
                insert_contact(cur, school_id, role, rec, run_id)
                counts["written"] += 1
        for stale_cid in old_by_name.values():
            cur.execute("UPDATE contacts SET status = 'suspected_stale' WHERE id = %s", (stale_cid,))
        return

    # Single-holder: at most one found person to reason about.
    rec = next(iter(found_by_name.values()), None)
    if rec is None:
        for cid in old_by_name.values():
            cur.execute("UPDATE contacts SET status = 'suspected_stale' WHERE id = %s", (cid,))
        return

    name_key = norm(rec[0], rec[1])
    if name_key in old_by_name:
        confirm(cur, old_by_name[name_key])
        return

    new_cid = insert_contact(cur, school_id, role, rec, run_id)
    counts["written"] += 1
    for old_name, old_cid in old_by_name.items():
        cur.execute("UPDATE contacts SET status = 'departed' WHERE id = %s", (old_cid,))
        cur.execute(
            "INSERT INTO contact_verifications (contact_id, method, outcome, replacement_contact_id) "
            "VALUES (%s, 'scrape', 'changed', %s)",
            (old_cid, new_cid),
        )
    if role in SIGNAL_TYPE:
        first, last, _rd, _e, _es, _ec, _p, page_url = rec
        cur.execute(
            "INSERT INTO signals (school_id, signal_type, source_url, payload) VALUES (%s, %s, %s, %s)",
            (school_id, SIGNAL_TYPE[role], page_url,
             json.dumps({"role": role, "new_name": f"{first} {last}",
                         "previous_names": [f"{n[0]} {n[1]}" for n in old_by_name] or None})),
        )


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    conn = db.connect()
    targets = build_targets(conn)
    if limit:
        targets = targets[:limit]
    email_info = load_district_email_info(conn)
    existing = load_existing(conn)
    print(f"{len(targets)} site targets to re-crawl. "
          f"{sum(len(v) for v in existing.values())} existing web-sourced contacts to diff against.")

    client = httpx.Client(headers={"User-Agent": config.USER_AGENT})
    gap_rows = []
    gap_path = config.OUT_DIR / "phase7_sweep_gap_list.csv"

    with db.ingest_run(
        conn, "llm_extract", "August refresh sweep - re-crawl + diff against current contacts", "ND",
    ) as (run_id, counts):
        with conn.cursor() as cur:
            for i, target in enumerate(targets, 1):
                counts["in"] += 1
                site_contacts, site_gaps, site_cost = crawl_site(client, target, email_info)
                gap_rows.extend(site_gaps)
                counts["cost_usd"] += site_cost

                by_role = {}
                for (school_id, role, role_detail, first_name, last_name, email_source,
                     email_confidence, phone, page_url, email) in site_contacts.values():
                    by_role.setdefault((school_id, role), []).append(
                        (first_name, last_name, role_detail, email, email_source,
                         email_confidence, phone, page_url)
                    )
                for (school_id, role), found_people in by_role.items():
                    reconcile_site(cur, school_id, role, found_people, existing, run_id, counts)

                conn.commit()
                write_gap_csv(gap_rows, gap_path)
                if i % 10 == 0 or i == len(targets):
                    print(f"[{i}/{len(targets)}] written={counts['written']} cost=${counts['cost_usd']:.4f}", flush=True)

    conn.close()
    print(f"Swept {len(targets)} sites. {counts['written']} new/changed contacts written. "
          f"Cost: ${counts['cost_usd']:.4f}. Gaps: {len(gap_rows)}")


if __name__ == "__main__":
    main()
