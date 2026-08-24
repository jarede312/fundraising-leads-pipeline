"""
Phase 1: load the ND public + private school universe from NCES CCD (2024-25) and
PSS (2021-22, the most recent available) into the schema.

Run: python -m ingest.phase1_nces
"""
import csv

from . import config, db

RAW = config.RAW_DIR

# PSS LOGR2022/HIGR2022 grade codes -> CCD-style grade text, per NCES PSS Public-Use
# Data File User's Manual for SY 2021-22, Appendix C (pp. C-60/C-61). Confirmed by
# reading the actual codebook, not inferred from the numbers.
PSS_GRADE_CODE = {
    "1": None,   # All Ungraded
    "2": "PK",
    "3": "KG",
    "4": "KG",   # transitional kindergarten -> treat as KG for grade-span purposes
    "5": "01",   # transitional first grade -> treat as 1st
    "6": "01",
    "7": "02",
    "8": "03",
    "9": "04",
    "10": "05",
    "11": "06",
    "12": "07",
    "13": "08",
    "14": "09",
    "15": "10",
    "16": "11",
    "17": "12",
}

# ordering for segment classification (PK < KG < 01 < ... < 12)
GRADE_ORDER = {"PK": -1, "KG": 0}
for i in range(1, 13):
    GRADE_ORDER[f"{i:02d}"] = i


def grade_rank(code):
    if code is None:
        return None
    return GRADE_ORDER.get(code)


def classify_segment(grade_low, grade_high):
    """Grade-span buckets tuned to actual ND configurations, not just the textbook
    K-5/6-8/9-12 split. K-6 and PK-8 buildings (called "elementary" by their own
    districts) and 7-12 "junior-senior high" buildings are both extremely common
    here and were falling through to "other" under a stricter hi<=5/lo>=9 rule -
    caught because "other" turned out to be the single largest segment (268 of 557
    open schools) once this became a Phase 6 scoring input and got a second look."""
    lo, hi = grade_rank(grade_low), grade_rank(grade_high)
    if lo is None or hi is None:
        return "other"
    if lo <= 1 and hi <= 8:
        return "elementary"
    if lo <= 1 and hi >= 9:
        return "combined"
    if lo >= 5 and hi <= 8:
        return "middle"
    if lo >= 5 and hi >= 9:
        return "high"
    return "other"


def load_csv(relpath, encoding="utf-8-sig"):
    with open(RAW / relpath, newline="", encoding=encoding) as fh:
        return list(csv.DictReader(fh))


def load_pipe_delimited(relpath, encoding="latin-1"):
    rows = []
    with open(RAW / relpath, encoding=encoding) as fh:
        for line in fh:
            f = line.rstrip("\n").split("|")
            rows.append(f)
    return rows


def build_edge_geocode():
    """NCESSCH -> (lat, lon, locale_code) from the EDGE public school geocode file.

    Column layout confirmed directly against the raw file (NCESSCH, short ID, name,
    state FIPS, street, city, state, ZIP, state FIPS again, county FIPS, COUNTY NAME,
    LOCALE, LAT, LON, CBSA, ...). An earlier version of this parser read county name
    as locale, locale code as latitude, and true latitude as longitude - true
    longitude was never captured at all. It went undetected because two schools in
    the same small town still landed "close together" in the bogus coordinate space
    (same real latitude, same locale code by coincidence), so v_combined_sites kept
    producing plausible-looking output despite being computed on nonsense geometry.
    Caught when Phase 6 needed a real, usable locale code and this column turned out
    to hold county names instead."""
    out = {}
    rows = load_pipe_delimited("edge_geocode/EDGE_GEOCODE_PUBLICSCH_2425.TXT")
    for f in rows:
        ncessch = f[0]
        locale = f[11]
        try:
            lat, lon = float(f[12]), float(f[13])
        except (ValueError, IndexError):
            continue
        out[ncessch] = (lat, lon, locale if locale not in ("N", "") else None)
    return out


def build_frl_and_basis(nd_char):
    """NCESSCH -> (frl_count, frl_pct placeholder, frl_basis) from lunch + characteristics."""
    frl_count = {}
    rows = load_csv("ccd_sch_033_2425_lunch/ccd_sch_033_2425_l_2a_073025.csv")
    for r in rows:
        if r["ST"] != "ND":
            continue
        if r["DATA_GROUP"] == "Free and Reduced-price Lunch Table" and r["LUNCH_PROGRAM"] == "No Category Codes":
            try:
                frl_count[r["NCESSCH"]] = int(r["STUDENT_COUNT"])
            except ValueError:
                pass

    basis = {}
    for ncessch, c in nd_char.items():
        status = c.get("NSLP_STATUS_TEXT", "")
        if status.startswith("Yes under Community"):
            basis[ncessch] = "cep"
        elif status == "Yes under Provision 2":
            basis[ncessch] = "provision_2"
        elif status.startswith("Yes"):
            basis[ncessch] = "applications"
        else:
            basis[ncessch] = "unknown"
    return frl_count, basis


def build_enrollment():
    enr = {}
    with open(RAW / "ccd_sch_052_2425_membership/ccd_sch_052_2425_l_1a_073025.csv",
              newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            if row["ST"] == "ND" and row["TOTAL_INDICATOR"] == "Education Unit Total":
                try:
                    enr[row["NCESSCH"]] = int(row["STUDENT_COUNT"])
                except ValueError:
                    pass
    return enr


def virtual_status_of(text):
    if text == "Exclusively virtual":
        return "exclusive"
    if text == "Supplemental Virtual":
        return "supplemental"
    return "none"


def main():
    conn = db.connect()
    conn.execute(
        """
        INSERT INTO states (code, name)
        VALUES ('ND', 'North Dakota')
        ON CONFLICT (code) DO NOTHING
        """
    )
    conn.commit()

    sch_dir = [r for r in load_csv("ccd_sch_029_2425_directory/ccd_sch_029_2425_w_1a_073025.csv") if r["ST"] == "ND"]
    lea_dir = [r for r in load_csv("ccd_lea_029_2425_directory/ccd_lea_029_2425_w_1a_073025.csv") if r["ST"] == "ND"]
    nd_char = {
        r["NCESSCH"]: r
        for r in load_csv("ccd_sch_129_2425_characteristics/ccd_sch_129_2425_w_1a_073025.csv")
        if r["ST"] == "ND"
    }
    geocode = build_edge_geocode()
    frl_count, frl_basis = build_frl_and_basis(nd_char)
    enr = build_enrollment()

    with db.ingest_run(conn, "nces_ccd", "CCD 2024-25 LEA directory", "ND") as (run_id, counts):
        with conn.cursor() as cur:
            for r in lea_dir:
                counts["in"] += 1
                if r["SY_STATUS_TEXT"] not in ("Open", "New"):
                    continue
                cur.execute(
                    """
                    INSERT INTO districts (
                        nces_lea_id, name, state_code, website_url, phone,
                        district_type, ingest_run_id, last_seen_in_source
                    ) VALUES (%s, %s, 'ND', %s, %s, 'public', %s, now())
                    ON CONFLICT (nces_lea_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        website_url = EXCLUDED.website_url,
                        phone = EXCLUDED.phone,
                        last_seen_in_source = now(),
                        updated_at = now()
                    """,
                    (r["LEAID"], r["LEA_NAME"], r["WEBSITE"] or None, r["PHONE"] or None, run_id),
                )
                counts["written"] += 1
        conn.commit()

    district_id_by_leaid = {}
    with conn.cursor() as cur:
        cur.execute("SELECT id, nces_lea_id FROM districts WHERE state_code = 'ND'")
        for id_, leaid in cur.fetchall():
            district_id_by_leaid[leaid] = id_

    with db.ingest_run(conn, "nces_ccd", "CCD 2024-25 school directory + characteristics + lunch + membership + EDGE geocode", "ND") as (run_id, counts):
        with conn.cursor() as cur:
            for r in sch_dir:
                counts["in"] += 1
                if r["SY_STATUS_TEXT"] not in ("Open", "New"):
                    status = "closed" if r["SY_STATUS_TEXT"] == "Closed" else "unknown"
                else:
                    status = "open"

                ncessch = r["NCESSCH"]
                leaid = r["LEAID"]
                district_id = district_id_by_leaid.get(leaid)

                grade_low = r["GSLO"] or None
                grade_high = r["GSHI"] or None
                segment = classify_segment(grade_low, grade_high)

                lat = lon = locale_code = None
                if ncessch in geocode:
                    lat, lon, locale_code = geocode[ncessch]

                char = nd_char.get(ncessch, {})
                v_status = virtual_status_of(char.get("VIRTUAL_TEXT", ""))
                basis = frl_basis.get(ncessch, "unknown")

                enrollment = enr.get(ncessch)
                frl = frl_count.get(ncessch)
                frl_pct = round(100.0 * frl / enrollment, 2) if (frl is not None and enrollment) else None

                cur.execute(
                    """
                    INSERT INTO schools (
                        nces_school_id, district_id, name, school_type,
                        street, city, state_code, zip, lat, lon, phone, website_url,
                        grade_low, grade_high, segment,
                        enrollment, enrollment_year, frl_count, frl_pct, frl_basis,
                        locale_code, status, virtual_status,
                        ingest_run_id, last_seen_in_source
                    ) VALUES (
                        %s, %s, %s, 'public',
                        %s, %s, 'ND', %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, now()
                    )
                    ON CONFLICT (nces_school_id) DO UPDATE SET
                        district_id = EXCLUDED.district_id,
                        name = EXCLUDED.name,
                        street = EXCLUDED.street, city = EXCLUDED.city, zip = EXCLUDED.zip,
                        lat = EXCLUDED.lat, lon = EXCLUDED.lon,
                        phone = EXCLUDED.phone, website_url = EXCLUDED.website_url,
                        grade_low = EXCLUDED.grade_low, grade_high = EXCLUDED.grade_high,
                        segment = EXCLUDED.segment,
                        enrollment = EXCLUDED.enrollment, enrollment_year = EXCLUDED.enrollment_year,
                        frl_count = EXCLUDED.frl_count, frl_pct = EXCLUDED.frl_pct,
                        frl_basis = EXCLUDED.frl_basis,
                        locale_code = EXCLUDED.locale_code, status = EXCLUDED.status,
                        virtual_status = EXCLUDED.virtual_status,
                        last_seen_in_source = now(), updated_at = now()
                    """,
                    (
                        ncessch, district_id, r["SCH_NAME"],
                        r["LSTREET1"] or None, r["LCITY"] or None, r["LZIP"] or None,
                        lat, lon, r["PHONE"] or None, r["WEBSITE"] or None,
                        grade_low, grade_high, segment,
                        enrollment, "2024-2025" if enrollment is not None else None,
                        frl, frl_pct, basis,
                        locale_code, status, v_status,
                        run_id,
                    ),
                )
                counts["written"] += 1
        conn.commit()

    # District enrollment_total / school_count, computed from what we just loaded.
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE districts d SET
                enrollment_total = s.total_enr,
                school_count = s.n
            FROM (
                SELECT district_id, SUM(enrollment) AS total_enr, COUNT(*) AS n
                FROM schools
                WHERE state_code = 'ND' AND status = 'open'
                GROUP BY district_id
            ) s
            WHERE d.id = s.district_id
            """
        )
    conn.commit()

    # Private schools from PSS 2021-22 (most recent available; three years stale, see report).
    pss_rows = [r for r in load_csv("pss2122/pss2122_pu.csv", encoding="latin-1") if r.get("PSTABB") == "ND"]
    with db.ingest_run(conn, "nces_pss", "PSS 2021-22 public-use file", "ND") as (run_id, counts):
        with conn.cursor() as cur:
            for r in pss_rows:
                counts["in"] += 1
                grade_low = PSS_GRADE_CODE.get(r.get("LOGR2022"))
                grade_high = PSS_GRADE_CODE.get(r.get("HIGR2022"))
                segment = classify_segment(grade_low, grade_high)
                try:
                    lat = float(r["LATITUDE22"])
                    lon = float(r["LONGITUDE22"])
                except (ValueError, KeyError):
                    lat = lon = None
                try:
                    enrollment = int(r["NUMSTUDS"])
                except (ValueError, KeyError):
                    enrollment = None
                relig_map = {"1": "catholic", "2": "other_religious", "3": "nonsectarian"}
                affiliation = relig_map.get(r.get("RELIG"))

                cur.execute(
                    """
                    INSERT INTO schools (
                        pss_id, name, school_type, affiliation,
                        street, city, state_code, zip, lat, lon, phone,
                        grade_low, grade_high, segment,
                        enrollment, enrollment_year,
                        status, ingest_run_id, last_seen_in_source
                    ) VALUES (
                        %s, %s, 'private', %s,
                        %s, %s, 'ND', %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, '2021-2022',
                        'open', %s, now()
                    )
                    ON CONFLICT (pss_id) DO UPDATE SET
                        name = EXCLUDED.name, affiliation = EXCLUDED.affiliation,
                        street = EXCLUDED.street, city = EXCLUDED.city, zip = EXCLUDED.zip,
                        lat = EXCLUDED.lat, lon = EXCLUDED.lon, phone = EXCLUDED.phone,
                        grade_low = EXCLUDED.grade_low, grade_high = EXCLUDED.grade_high,
                        segment = EXCLUDED.segment, enrollment = EXCLUDED.enrollment,
                        last_seen_in_source = now(), updated_at = now()
                    """,
                    (
                        r["PPIN"], r["PINST"], affiliation,
                        r["PADDRS"] or None, r["PCITY"] or None, r["PZIP"] or None, lat, lon,
                        r.get("PPHONE") or None,
                        grade_low, grade_high, segment,
                        enrollment,
                        run_id,
                    ),
                )
                counts["written"] += 1
        conn.commit()

    conn.close()
    print("Phase 1 load complete.")


if __name__ == "__main__":
    main()
