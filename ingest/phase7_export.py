"""
Phase 7: the CSV export - one row per school, the best contact for each sales-relevant
role, and the school's Phase 6 score. Nothing else in Phase 7 (verification queue,
August sweep) lives here; see phase7_verification_queue.sql and the Checkpoint 7 report
for those.

"Best" contact per (school, role) is: highest email_confidence (high > medium > low >
unknown), then an email present over none, then most recently seen - a plain SQL
DISTINCT ON, not a judgment call worth a whole module.

Run: python -m ingest.phase7_export
Writes: data/out/schools_export_<date>.csv
"""
import csv
from datetime import date

from . import config, db

ROLES = [
    "principal", "assistant_principal", "office_manager", "superintendent",
    "music_teacher", "band_director", "choir_director", "drama_director",
    "activities_director", "athletic_director",
    "pto_president", "pto_fundraising_chair", "pto_treasurer", "booster_president",
]

CONFIDENCE_RANK = "CASE email_confidence " \
    "WHEN 'high' THEN 4 WHEN 'medium' THEN 3 WHEN 'low' THEN 2 WHEN 'verified' THEN 5 " \
    "ELSE 1 END"

BEST_CONTACT_SQL = f"""
    SELECT DISTINCT ON (school_id, role)
        school_id, role, first_name, last_name, email, email_confidence, phone
    FROM contacts
    ORDER BY school_id, role,
             {CONFIDENCE_RANK} DESC,
             (email IS NOT NULL) DESC,
             first_seen DESC
"""


def main():
    conn = db.connect()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT s.id, s.name, s.city, d.name, s.segment, s.enrollment, s.school_type,
               sc.score, sc.rationale
        FROM schools s
        LEFT JOIN districts d ON d.id = s.district_id
        LEFT JOIN scores sc ON sc.school_id = s.id AND sc.score_version = 'v1'
        WHERE s.status = 'open'
        ORDER BY sc.score DESC NULLS LAST
        """
    )
    school_rows = cur.fetchall()

    cur.execute(BEST_CONTACT_SQL)
    contacts_by_school = {}
    for school_id, role, first, last, email, econf, phone in cur.fetchall():
        contacts_by_school.setdefault(school_id, {})[role] = (first, last, email, econf, phone)

    headers = [
        "school_name", "city", "district", "segment", "enrollment", "school_type",
        "score", "score_rationale",
    ]
    for role in ROLES:
        headers += [f"{role}_name", f"{role}_email", f"{role}_email_confidence", f"{role}_phone"]

    out_path = config.OUT_DIR / f"schools_export_{date.today().isoformat()}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for school_id, name, city, district, segment, enrollment, school_type, score, rationale in school_rows:
            row = [name, city, district, segment, enrollment, school_type, score, rationale]
            role_contacts = contacts_by_school.get(school_id, {})
            for role in ROLES:
                c = role_contacts.get(role)
                if c:
                    first, last, email, econf, phone = c
                    full_name = " ".join(p for p in (first, last) if p) or None
                    row += [full_name, email, econf, phone]
                else:
                    row += [None, None, None, None]
            writer.writerow(row)

    conn.close()
    print(f"Wrote {len(school_rows)} schools to {out_path}")


if __name__ == "__main__":
    main()
