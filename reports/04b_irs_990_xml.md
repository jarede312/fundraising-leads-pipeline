# Phase 4 Addendum — Full 990/990-EZ Filings

Following up on the scope cut named in the original Phase 4 report: located and parsed the
actual Form 990/990-EZ XML for the larger orgs the e-Postcard doesn't cover.

## How this was done

IRS publishes a monthly index (`index_{year}.csv`, 2022-2026) mapping EIN → which ZIP batch
holds that filing's XML, and the batches themselves (`apps.irs.gov/pub/epostcard/990/xml/
{year}/{batch}.zip`) are enormous — a single batch runs 300MB-1GB and holds 40,000-150,000
organizations nationwide, for all of maybe 1-9 you actually need. Downloading full batches
for 38 target orgs would have meant several GB for a few hundred KB of useful XML, so I
checked whether the server supports HTTP range requests (it does — `Accept-Ranges: bytes`)
and used `remotezip` to read just the ZIP central directory plus the specific entries
needed, without pulling the whole archive. Where a batch used the older Deflate64
compression method (Python's `zipfile` can't decompress that, `remotezip` depends on
`zipfile`), I fell back to a full download + system `unzip` for just those few batches.

**38 EINs (of 123) had a 990/990-EZ filing; 33 were successfully retrieved and parsed.**
3 stayed unresolved — the index pointed at a batch file that, once actually opened, didn't
contain the object (checked the adjacent months' batches too; genuinely not there, not a
naming-convention guess gone wrong): Blue Hawk Booster Club, Legacy Bismarck Girls Hockey
Booster, St Marys School Foundation. Their BMF-level data (name, address, an approximate
revenue figure) still stands; they just don't have a verified principal officer from this
pass. Small, accepted residual — not chased further.

## Result

**Principal officer coverage across all 123 orgs: 107 (87%), up from 86** (the e-Postcard-
only figure from the original Phase 4 report). Filing type is now known and accurate for
every org that has one on file, not inferred:

| Filing type | Orgs |
|---|---|
| 990N (e-Postcard) | 89 |
| 990 | 17 |
| 990EZ | 16 |
| none on file / unresolved | ~16 |

## A real finding for Phase 6: use `total_revenue`, not `gross_receipts`

IRS's "Gross Receipts" is a specific technical term — total revenue plus certain gross
inflows before netting out cost of goods sold and pass-through activity — and it can be
wildly larger than what a PTO actually has to spend. Checked directly against the raw XML,
not a parsing artifact:

| Org | Gross receipts | Total revenue |
|---|---|---|
| Jamestown Hockey Booster Club | $10,070,472 | $646,715 |
| Bison Boosters Club of Milnor | $4,450,331 | $283,480 |
| Richland #44 School Foundation | $6,038,560 | $6,036,881 |

Booster clubs running concessions, facility rentals, or tournament pass-throughs show a
huge gap between the two figures; foundations that mostly just hold and disburse donations
show almost none (Richland's two numbers essentially match). Both fields are stored
separately in `nonprofit_orgs` (the schema already anticipated this), but **`gross_receipts`
would badly overstate PTO capacity as a scoring input** — a $10M "gross receipts" club
isn't 30x the size of a $300k one; `total_revenue` is the honest capacity signal for
Phase 6, and that's the recommendation going in when scoring weights get proposed.
