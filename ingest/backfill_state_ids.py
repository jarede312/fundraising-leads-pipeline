"""One-time backfill of districts.st_lea_id / schools.st_school_id from the CCD directory
CSVs already on disk (no new download). Needed before phase2_dpi.py can join DPI rows to
the schools/districts loaded in Phase 1.

Run: python -m ingest.backfill_state_ids
"""
import csv

from . import config, db

RAW = config.RAW_DIR


def main():
    conn = db.connect()

    with open(RAW / "ccd_lea_029_2425_directory/ccd_lea_029_2425_w_1a_073025.csv",
              newline="", encoding="utf-8-sig") as fh:
        lea_rows = [r for r in csv.DictReader(fh) if r["ST"] == "ND"]

    with open(RAW / "ccd_sch_029_2425_directory/ccd_sch_029_2425_w_1a_073025.csv",
              newline="", encoding="utf-8-sig") as fh:
        sch_rows = [r for r in csv.DictReader(fh) if r["ST"] == "ND"]

    with conn.cursor() as cur:
        for r in lea_rows:
            cur.execute(
                "UPDATE districts SET st_lea_id = %s WHERE nces_lea_id = %s",
                (r["ST_LEAID"] or None, r["LEAID"]),
            )
        for r in sch_rows:
            cur.execute(
                "UPDATE schools SET st_school_id = %s WHERE nces_school_id = %s",
                (r["ST_SCHID"] or None, r["NCESSCH"]),
            )
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM districts WHERE st_lea_id IS NOT NULL")
        d = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM schools WHERE st_school_id IS NOT NULL")
        s = cur.fetchone()[0]
    print(f"backfilled st_lea_id on {d} districts, st_school_id on {s} schools")
    conn.close()


if __name__ == "__main__":
    main()
