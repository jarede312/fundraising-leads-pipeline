"""
Phase 2: load ND DPI directory contacts (falldir25-26.xlsx) into `contacts`.

Loaded under NDDPI's noncommercial-use disclaimer (see states.directory_license_notes) per
your explicit decision to load-and-flag rather than skip or wait on permission. Every row
written here carries source_url + an ingest_runs note pointing back to that decision so it
stays visible, not buried.

Matching: DPI's StateIssuedID (e.g. '02-002-8954') and CCD's ST_SCHID (e.g.
'ND-02002-89543') are the same state ID system, but DPI's code doesn't uniquely determine
which CCD building when one physical site holds multiple grade-span buildings (a Jr High
and a Sr High sharing base code 8954). So: prefix-match on the base code within the
district, then disambiguate by grade-span reach implied by which DPI sheet the row came
from. Rows that are still ambiguous, or whose site has no lat/lon-having match at all, are
never guessed — they go to data/out/phase2_gap_list.csv.

Run: python -m ingest.phase2_dpi
"""
import csv

import openpyxl

from . import config, db

XLSX_PATH = config.RAW_DIR / "nd_dpi_falldir25-26.xlsx"
GAP_CSV = config.OUT_DIR / "phase2_gap_list.csv"
SOURCE_URL = "https://www.nd.gov/dpi/sites/www/files/documents/Data/falldir25-26.xlsx"

# sheet name -> (contacts.role, role_detail, which segment-reach filter to apply when a
# DPI base code matches more than one CCD building at the same site)
PRINCIPAL_SHEETS = {
    "Elementary Principal": ("principal", "Elementary Principal", "elementary"),
    "Secondary Principal": ("principal", "Secondary Principal", "secondary"),
    "Jr-Middle Principal": ("principal", "Junior High/Middle Principal", "middle"),
    "Assistant Principals": ("assistant_principal", None, None),
}


def read_sheet(wb, name):
    """Row 10 (0-indexed) is the header. Below the real data table, several sheets carry
    a second, unrelated block of rows (a trailing district-website reference list) that
    have no FirstName and would otherwise be miscounted as unmatched people. FirstName
    is the actual "this is a real person row" signal, not "any cell is non-None"."""
    ws = wb[name]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[10]
    idx_first = header.index("FirstName")
    data = [r for r in rows[11:] if r[idx_first] is not None]
    return header, data


def match_private_school_by_name(conn, name):
    """Fallback for schools with no CCD state ID (private/tribal schools, which DPI's
    directory covers but CCD/PSS don't always share a joinable ID with). Conservative:
    only accept a clear best match, never guess between close candidates."""
    if not name:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, similarity(name, %s) AS sim
            FROM schools
            WHERE state_code = 'ND' AND school_type = 'private' AND status = 'open'
            ORDER BY sim DESC
            LIMIT 2
            """,
            (name,),
        )
        rows = cur.fetchall()
    if not rows or rows[0][2] < 0.5:
        return None
    if len(rows) > 1 and rows[1][2] >= rows[0][2] - 0.05:
        return None  # too close to call, don't guess
    return rows[0][0]


def build_school_index(conn):
    """st_lea_id -> list of (school_id, segment, serves_elementary, serves_secondary)."""
    idx = {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT d.st_lea_id, s.id, s.st_school_id, s.segment,
                   (s.grade_low IN ('PK','KG','01','02','03','04','05')) AS serves_elem,
                   (s.grade_high IN ('09','10','11','12','13')) AS serves_sec
            FROM schools s
            JOIN districts d ON d.id = s.district_id
            WHERE s.state_code = 'ND' AND s.status = 'open' AND s.st_school_id IS NOT NULL
            """
        )
        for st_lea_id, school_id, st_school_id, segment, serves_elem, serves_sec in cur.fetchall():
            idx.setdefault(st_lea_id, []).append(
                {"school_id": school_id, "st_school_id": st_school_id, "segment": segment,
                 "serves_elem": serves_elem, "serves_sec": serves_sec}
            )
    return idx


def base_code_to_st_lea_id(county, lea):
    return f"ND-{county}{lea}"


def match_school(school_index, county, lea, dpi_school_code, reach):
    st_lea_id = base_code_to_st_lea_id(county, lea)
    candidates = school_index.get(st_lea_id, [])
    prefix = f"ND-{county}{lea}-{dpi_school_code}"
    site_matches = [c for c in candidates if c["st_school_id"] and c["st_school_id"].startswith(prefix)]

    if len(site_matches) == 1:
        return site_matches[0]["school_id"], None
    if not site_matches:
        return None, "no_school_at_site"

    if reach == "elementary":
        filtered = [c for c in site_matches if c["serves_elem"]]
    elif reach == "secondary":
        filtered = [c for c in site_matches if c["serves_sec"] and c["segment"] != "middle"]
    elif reach == "middle":
        filtered = [c for c in site_matches if c["segment"] == "middle"]
    else:
        filtered = site_matches

    if len(filtered) == 1:
        return filtered[0]["school_id"], None
    return None, "ambiguous_site"


def main():
    conn = db.connect()
    school_index = build_school_index(conn)
    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)

    gaps = []
    LICENSE_NOTE = (
        "Loaded under NDDPI's noncommercial-use disclaimer "
        "(nd.gov/dpi/copyright-website-use-and-disclaimer) per explicit user decision "
        "at Checkpoint 2 to load-and-flag rather than skip or wait on permission. "
        "See states.directory_license_notes for verbatim text."
    )

    with db.ingest_run(conn, "state_doe", "ND DPI Fall 2025-26 directory (falldir25-26.xlsx) - principals", "ND") as (run_id, counts):
        with conn.cursor() as cur:
            cur.execute("UPDATE ingest_runs SET notes = %s WHERE id = %s", (LICENSE_NOTE, run_id))
            for sheet_name, (role, role_detail, reach) in PRINCIPAL_SHEETS.items():
                header, data = read_sheet(wb, sheet_name)
                idx_county = header.index("County")
                idx_lea = header.index("LEA")
                idx_school = header.index("School")
                idx_first = header.index("FirstName")
                idx_last = header.index("LastName")
                idx_email = header.index("EmailAddress")
                idx_phone = header.index("Phone")
                idx_ext = header.index("Phone Ext.")
                idx_position = header.index("Position") if "Position" in header else header.index("MajorPositionName")
                idx_name = header.index("District/School Name")

                for r in data:
                    counts["in"] += 1
                    county = str(r[idx_county]).zfill(2)
                    lea = str(r[idx_lea]).zfill(3)
                    sch_code = str(r[idx_school]) if r[idx_school] is not None else None
                    if not sch_code:
                        gaps.append({"sheet": sheet_name, "county": county, "lea": lea, "school_code": "",
                                     "name": r[idx_name], "person": f"{r[idx_first]} {r[idx_last]}",
                                     "reason": "no_school_code_on_row"})
                        continue

                    school_id, reason = match_school(school_index, county, lea, sch_code, reach)
                    if school_id is None and reason == "no_school_at_site":
                        school_id = match_private_school_by_name(conn, r[idx_name])
                        if school_id is not None:
                            reason = None
                    if school_id is None:
                        gaps.append({"sheet": sheet_name, "county": county, "lea": lea, "school_code": sch_code,
                                     "name": r[idx_name], "person": f"{r[idx_first]} {r[idx_last]}",
                                     "reason": reason})
                        continue

                    detail = role_detail or (r[idx_position] if idx_position < len(r) else None)
                    email = r[idx_email] or None
                    cur.execute(
                        """
                        INSERT INTO contacts (
                            school_id, role, role_detail, first_name, last_name,
                            email, email_source, email_confidence,
                            phone, phone_ext,
                            confidence, source_url, ingest_run_id,
                            last_verified_at, last_verified_method
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s,
                            'medium', %s, %s,
                            now(), 'state_directory'
                        )
                        """,
                        (
                            school_id, role, detail, r[idx_first], r[idx_last],
                            email, "found" if email else "unknown", "medium" if email else "unknown",
                            r[idx_phone], r[idx_ext],
                            SOURCE_URL, run_id,
                        ),
                    )
                    counts["written"] += 1
        conn.commit()

    # music teachers, filtered from the Teachers sheet
    with db.ingest_run(conn, "state_doe", "ND DPI Fall 2025-26 directory (falldir25-26.xlsx) - music specialists", "ND") as (run_id, counts):
        with conn.cursor() as cur:
            cur.execute("UPDATE ingest_runs SET notes = %s WHERE id = %s", (LICENSE_NOTE, run_id))
            header, data = read_sheet(wb, "Teachers")
            idx_area = header.index("MajorAreaofResponsibilityName")
            idx_county = header.index("County")
            idx_lea = header.index("LEA")
            idx_school = header.index("School")
            idx_first = header.index("FirstName")
            idx_last = header.index("LastName")
            idx_email = header.index("EmailAddress")
            idx_phone = header.index("Phone")
            idx_ext = header.index("Phone Ext.")
            idx_name = header.index("District/School Name")

            for r in data:
                if (r[idx_area] or "").strip() != "Specialist:  Music":
                    continue
                counts["in"] += 1
                county = str(r[idx_county]).zfill(2)
                lea = str(r[idx_lea]).zfill(3)
                sch_code = str(r[idx_school]) if r[idx_school] is not None else None
                if not sch_code:
                    gaps.append({"sheet": "Teachers:Music", "county": county, "lea": lea, "school_code": "",
                                 "name": r[idx_name], "person": f"{r[idx_first]} {r[idx_last]}",
                                 "reason": "no_school_code_on_row"})
                    continue

                school_id, reason = match_school(school_index, county, lea, sch_code, None)
                if school_id is None and reason == "no_school_at_site":
                    school_id = match_private_school_by_name(conn, r[idx_name])
                    if school_id is not None:
                        reason = None
                if school_id is None:
                    gaps.append({"sheet": "Teachers:Music", "county": county, "lea": lea, "school_code": sch_code,
                                 "name": r[idx_name], "person": f"{r[idx_first]} {r[idx_last]}",
                                 "reason": reason})
                    continue

                email = r[idx_email] or None
                cur.execute(
                    """
                    INSERT INTO contacts (
                        school_id, role, role_detail, first_name, last_name,
                        email, email_source, email_confidence,
                        phone, phone_ext,
                        confidence, source_url, ingest_run_id,
                        last_verified_at, last_verified_method
                    ) VALUES (
                        %s, 'music_teacher',
                        'DPI staff assignment category "Specialist: Music" - may be band, choir, or general music; not distinguished in this source',
                        %s, %s, %s, %s, %s, %s, %s, 'medium', %s, %s, now(), 'state_directory'
                    )
                    """,
                    (
                        school_id, r[idx_first], r[idx_last],
                        email, "found" if email else "unknown", "medium" if email else "unknown",
                        r[idx_phone], r[idx_ext],
                        SOURCE_URL, run_id,
                    ),
                )
                counts["written"] += 1
        conn.commit()

    conn.close()

    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(GAP_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["sheet", "county", "lea", "school_code", "name", "person", "reason"])
        w.writeheader()
        w.writerows(gaps)

    print(f"Phase 2 DPI load complete. {len(gaps)} rows unmatched -> {GAP_CSV}")


if __name__ == "__main__":
    main()
