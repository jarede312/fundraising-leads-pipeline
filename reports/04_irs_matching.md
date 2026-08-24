# Phase 4 Report — IRS Nonprofit Matching

Sources: IRS Exempt Organizations Business Master File, ND state extract (`eo_nd.csv`,
6,766 ND-domiciled exempt orgs) + Form 990-N e-Postcard bulk file (national, filtered to
ND's 5,593 filing-years).

## Scope cut, stated plainly

**Form 990/990-EZ full return data is not loaded.** Getting gross receipts and a principal
officer name for organizations too large to file the e-Postcard requires parsing IRS's
e-file XML archive (per-year ZIPs of individual return XML) — a materially bigger effort
than filtering the BMF and joining the e-Postcard file. 90 of the 123 plausible orgs found
(73%) have e-Postcard data; the other 33 are real orgs (BMF confirms they exist and are
active) but this phase has no principal officer or revenue figure for them. If you want
full 990/990-EZ coverage, say so and I'll scope that as its own piece of work rather than
quietly bolting it on here — worth naming since your father-in-law's biggest-dollar PTOs
are more likely to be in this uncovered 27% (bigger PTOs are the ones that outgrow the
$50k e-Postcard threshold).

## Universe found

**123 plausible PTO/PTA/booster/school-foundation orgs**, filtered from 6,766 ND exempt
orgs by name keyword (PTO, PTA, booster, parent-teacher, school foundation, FFA/FBLA
alumni, choir/band-parent groups), with obvious non-school false positives removed by hand
(three Minot AFB squadron "booster clubs," a volunteer fire department booster club, a
community adult choir).

## Matching approach — name-first, not address-first as the brief specified

I flagged this in the plan before building anything (PLAN.md §1.2) and you didn't object,
so I went with it: matched by trigram similarity between the org's name (generic words like
"Booster Club," "PTO," "Foundation," "Inc" stripped off) and `schools.name`, scoped to the
org's own city — not address-first. Reason, now with real evidence behind it: a PTO's IRS
mailing address is frequently a volunteer officer's home, and that address turns over every
1-2 years with the volunteer, unlike a school's fixed address. Address/ZIP agreement is
folded in as a score *booster* (+0.15) rather than the primary signal.

**108 of 123 orgs (88%) matched to a candidate school** at some confidence level.

## Score distribution

| Score range | Count |
|---|---|
| 0.9 – 1.0 | 15 |
| 0.7 – 0.9 | 21 |
| 0.5 – 0.7 | 32 |
| 0.3 – 0.5 | 22 |
| 0.15 – 0.3 | 17 |
| below 0.15 (not linked at all) | 15 |

## 15 samples spanning high / medium / low

| Tier | Org | Matched school | Score | Assessment |
|---|---|---|---|---|
| high | Kindred High School Booster Club | Kindred High School | 1.00 | Correct |
| high | Eastwood Elementary PTO | Eastwood Elementary School | 0.88 | Correct |
| high | Phoenix Elementary PTO | Phoenix Elementary School | 0.88 | Correct |
| high | Harwood Elementary Parent Teacher Organization | Harwood Elementary School | 0.88 | Correct |
| high | Fargo Longfellow Elementary PTO | Longfellow Elementary School | 0.78 | Correct |
| medium | South Heart Booster Club | South Heart High School | 0.70 | Correct |
| medium | May-Port CG School Foundation | May-Port CG High School | 0.65 | Correct |
| medium | Jamestown Public Schools Music Boosters | Jamestown Middle School | 0.61 | **Likely wrong scope** — this reads as district-wide, not middle-school-specific; matched to one building because Jamestown has 7 schools and the trigram score had to land somewhere |
| medium | Bowbells PTO | Bowbells High School | 0.58 | Plausible for a single-site town, worth a human glance |
| medium | Mandan Tennis Booster Club | Mandan High School | 0.42 | Plausible (tennis is a HS sport) |
| low | Legacy Bismarck Girls Hockey Booster Club | **Bismarck High School** | 0.25 | **Wrong.** Bismarck has two high schools — Bismarck High and Legacy High. "Legacy" in the org's own name should have pointed to Legacy High; it matched Bismarck High instead because "BISMARCK" is in both the org name and the (wrong) school's city, and city-name overlap outweighed the actual identifying word. Concrete case for why low-confidence rows need a human, not a lower cutoff. |
| low | MCDC Booster Club | Minot High School | 0.195 | Unrecognized acronym, correctly uncertain |
| low | FFA Alumni Association | Lisbon High School | 0.183 | Generic name, correctly uncertain |
| low | Raider Booster Club | Taylor-Richardton Elementary | 0.174 | Mascot name, not verified against the actual building's mascot |
| low | Parent Booster USA Inc | Des Lacs-Burlington High School | 0.150 | **Structurally wrong to match 1:1 at all** — see below |

## A structural finding, not just a scoring edge case: "Parent Booster USA Inc"

This exact legal name appears **twice** in the ND BMF with two different principal
officers (Kay Quam; Jami Eklund) — because Parent Booster USA is a real national umbrella
nonprofit that many individual local booster clubs affiliate under instead of incorporating
separately. One EIN can represent an entirely different local group in a different town
each time it appears. Matching this name to a single school by any scoring method is the
wrong granularity, not a threshold problem — flagging so you know this category exists in
the data rather than trusting a link that happens to score above whatever cutoff you pick.

## Question

**Where should the auto-accept cutoff go?** Everything ≥0.7 in this sample checked out
correctly; the concrete Bismarck/Legacy miss sits at 0.25, well below that. Based on this
sample, I'd set the line around **0.6-0.65** and route everything below it to manual
review (`confirmed = false`, which is already the default), but this is a genuinely small
sample (15 of 108) and it's your calibration to make, not mine. Recommend picking a number,
then spend 10 minutes skimming the schools that land just above and below it before
treating it as final.
