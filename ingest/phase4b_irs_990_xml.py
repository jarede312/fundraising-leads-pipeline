"""
Phase 4 follow-up: parse the real Form 990/990-EZ XML filings downloaded for the ~38
orgs (of the 123 found in Phase 4) that are too large for the 990-N e-Postcard and so had
no principal officer or verified revenue figure from BMF alone.

Source files were located via IRS's per-year 990-series e-file index
(apps.irs.gov/pub/epostcard/990/xml/{year}/index_{year}.csv, 2022-2026), matched by EIN
against the 123 orgs from Phase 4, then fetched — via partial HTTP range reads
(`remotezip`) where the batch used ordinary Deflate, or a full download + `unzip` where it
used Deflate64 (Python's zipfile can't decompress Deflate64; `unzip` can) — into
data/raw/irs_990_xml/. 3 of the 38 index entries pointed at an object that turned out not
to actually be in the batch file the index named (checked the two adjacent month-batches
too, genuinely absent) — a small, accepted residual gap, not chased further:
Blue Hawk Booster Club, Legacy Bismarck Girls Hockey Booster, St Marys School Foundation.

Run: python -m ingest.phase4b_irs_990_xml
"""
import xml.etree.ElementTree as ET
from pathlib import Path

from . import config, db

NS = {"e": "http://www.irs.gov/efile"}
XML_DIR = config.RAW_DIR / "irs_990_xml"


def parse_one(path):
    tree = ET.parse(path)
    root = tree.getroot()
    ein = root.findtext(".//e:ReturnHeader/e:Filer/e:EIN", namespaces=NS)
    tax_yr = root.findtext(".//e:ReturnHeader/e:TaxYr", namespaces=NS)

    irs990 = root.find(".//e:IRS990", NS)
    irs990ez = root.find(".//e:IRS990EZ", NS)

    if irs990 is not None:
        filing_type = "990"
        gross_receipts = irs990.findtext("e:GrossReceiptsAmt", namespaces=NS)
        total_revenue = irs990.findtext("e:CYTotalRevenueAmt", namespaces=NS)
        officer_groups = irs990.findall(".//e:Form990PartVIISectionAGrp", NS)
    elif irs990ez is not None:
        filing_type = "990EZ"
        gross_receipts = irs990ez.findtext("e:GrossReceiptsAmt", namespaces=NS)
        total_revenue = irs990ez.findtext("e:TotalRevenueAmt", namespaces=NS)
        officer_groups = irs990ez.findall(".//e:OfficerDirectorTrusteeEmplGrp", NS)
    else:
        return None

    officers = []
    for grp in officer_groups:
        name = grp.findtext("e:PersonNm", default="", namespaces=NS)
        title = (grp.findtext("e:TitleTxt", default="", namespaces=NS) or "").upper()
        if name:
            officers.append((name, title))

    principal = None
    for pref in ("PRESIDENT", "TREASURER", "SECRETARY", "VICE"):
        for name, title in officers:
            if pref in title:
                principal = name
                break
        if principal:
            break
    if principal is None and officers:
        principal = officers[0][0]

    def to_float(s):
        try:
            return float(s) if s not in (None, "") else None
        except ValueError:
            return None

    return {
        "ein": ein,
        "fiscal_year": int(tax_yr) if tax_yr else None,
        "filing_type": filing_type,
        "gross_receipts": to_float(gross_receipts),
        "total_revenue": to_float(total_revenue),
        "principal_officer_name": principal,
    }


def main():
    conn = db.connect()
    files = sorted(XML_DIR.glob("*_public.xml"))
    parsed = []
    for f in files:
        try:
            r = parse_one(f)
            if r and r["ein"]:
                parsed.append(r)
        except ET.ParseError as e:
            print(f"  skip {f.name}: parse error {e}")

    with db.ingest_run(conn, "irs_990", "IRS 990/990-EZ e-file XML, individually located and parsed for the ~38 orgs BMF+e-Postcard didn't cover with a principal officer", "ND") as (run_id, counts):
        with conn.cursor() as cur:
            for r in parsed:
                counts["in"] += 1
                cur.execute(
                    """
                    INSERT INTO nonprofit_orgs (
                        ein, fiscal_year, name, org_type, filing_type,
                        gross_receipts, total_revenue, principal_officer_name,
                        state_code, ingest_run_id
                    )
                    SELECT %s, %s, name, org_type, %s, %s, %s, %s, 'ND', %s
                    FROM nonprofit_orgs WHERE ein = %s LIMIT 1
                    ON CONFLICT (ein, fiscal_year) DO UPDATE SET
                        filing_type = EXCLUDED.filing_type,
                        gross_receipts = EXCLUDED.gross_receipts,
                        total_revenue = EXCLUDED.total_revenue,
                        principal_officer_name = COALESCE(EXCLUDED.principal_officer_name, nonprofit_orgs.principal_officer_name)
                    """,
                    (
                        r["ein"], r["fiscal_year"], r["filing_type"],
                        r["gross_receipts"], r["total_revenue"], r["principal_officer_name"], run_id,
                        r["ein"],
                    ),
                )
                counts["written"] += cur.rowcount
        conn.commit()
    conn.close()

    with_officer = sum(1 for r in parsed if r["principal_officer_name"])
    print(f"Parsed {len(parsed)} XML filings ({with_officer} with a principal officer name).")


if __name__ == "__main__":
    main()
