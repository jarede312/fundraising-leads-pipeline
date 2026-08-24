# Phase 1 Reconciliation Report — ND Universe

Sources: NCES CCD 2024-25 (school directory, LEA directory, school characteristics, lunch
program eligibility, membership) + NCES PSS 2021-22 (private schools) + NCES EDGE 2024-25
(public school geocodes). All downloaded live today, not from memory. Raw files in
`data/raw/`, per-file provenance below.

**Loaded to Postgres.** `fundraising_nd` database, migrations 001 (schema.sql, minus PostGIS
per your call), 002 (frl_basis, virtual_status, v_school_reach, v_combined_sites), and 003
(routing/drive-time infrastructure removed — this is a remote phone/email sales strategy,
not in-person visits, per your instruction). Loader: `ingest/phase1_nces.py`. Every number
below is a live query result, not a CSV scan. `data/out/districts_ranked.csv` (168 rows)
is generated and matches the table in §4 exactly.

---

## 1. Actual counts

| | Count |
|---|---|
| ND public school districts (LEAID with >=1 open/new school) | **169** |
| ND regular public school districts, any status (matches brief's "168") | 171 (170 open/new) |
| ND open + new public schools | **514** |
| ND private schools (PSS 2021-22, most recent available) | **43** |
| Statewide public enrollment (sum of school-level totals) | **119,656** |

Brief said "~168 districts / ~540 public schools / ~48 private / ~116,000 students." All
four land close to the brief's estimates — district count matches almost exactly, school
and enrollment counts are a few percent higher (current year plus New-status schools not
yet in "Open"), private school count is 5 lower than estimated. None of this is a
surprise worth stopping for.

## 2. Elementary-serving buildings

Using **"serves any elementary grade" = grade_low <= 5** (i.e., PK/KG through 5 is present
somewhere in the building's span, regardless of what else it also serves):

**298 of 514 open schools (58%) serve at least one elementary grade.**

Using the narrower "elementary segment" definition below (building's *entire* span is
elementary, high <= 5): **136 schools (26%).** These are two different questions and the
brief's Open Question 4 asks which one you want — see Checkpoint 1 questions.

## 3. Combined K-12 buildings

**Zero.** Using the schema's own segment rule (grade_low <= 5 AND grade_high >= 9), no
open ND school qualifies. This is the surprise — see the callout below.

## 4. Districts by enrollment, ranked, with cumulative %

Top 20 of 168 ranked districts (full list will be generated as `data/out/districts_ranked.csv`
once the DB is up):

| Rank | District | Enrollment | Schools | Cumulative % |
|---|---|---|---|---|
| 1 | Bismarck 1 | 14,086 | 29 | 11.8% |
| 2 | West Fargo 6 | 13,175 | 26 | 22.8% |
| 3 | Fargo 1 | 11,443 | 26 | 32.3% |
| 4 | Grand Forks 1 | 7,811 | 18 | 38.9% |
| 5 | Minot 1 | 7,668 | 21 | 45.3% |
| 6 | Williston Basin 7 | 5,413 | 11 | 49.8% |
| 7 | Mandan 1 | 4,451 | 12 | 53.5% |
| 8 | Dickinson 1 | 4,177 | 12 | 57.0% |
| 9 | McKenzie Co 1 | 2,349 | 7 | 59.0% |
| 10 | Jamestown 1 | 2,032 | 7 | 60.7% |
| 11 | Devils Lake 1 | 1,786 | 5 | 62.2% |
| 12 | Belcourt 7 | 1,518 | 4 | 63.4% |
| 13 | Wahpeton 37 | 1,221 | 4 | 64.5% |
| 14 | Central Cass 17 | 1,026 | 3 | 65.3% |
| 15 | Grafton 18 | 953 | 3 | 66.1% |
| 16 | Valley City 2 | 943 | 4 | 66.9% |
| 17 | New Town 1 | 931 | 3 | 67.7% |
| 18 | Kindred 2 | 874 | 3 | 68.4% |
| 19 | Stanley 2 | 783 | 2 | 69.1% |
| 20 | Beulah 27 | 748 | 3 | 69.7% |

**The top 7 districts (4% of all 168) hold 50% of statewide enrollment.** Those 7 are
Bismarck, West Fargo, Fargo, Grand Forks, Minot, Williston, Mandan — that's 7 of your 8
named districts exactly; Dickinson lands at #8, just past the 50% line, holding 57%
cumulative with it included. The brief's "eight districts hold about half the students"
claim is confirmed almost exactly as stated.

The remaining 160 districts split the other ~43% of enrollment across a long tail —
by district 100 of 168 you're past 95% cumulative. This is the number that should drive
Open Question 2 (full treatment for the small-district tail vs. free-NCES-record-only).

---

## 5. CCD field list — kept vs. dropped

### Kept (loading into schema in Phase 1)

| Schema column | CCD source field | File |
|---|---|---|
| `schools.name` | SCH_NAME | Directory |
| `schools.street/city/zip` | LSTREET1, LCITY, LZIP | Directory |
| `schools.phone` | PHONE | Directory |
| `schools.website_url` | WEBSITE | Directory |
| `schools.grade_low/high` | GSLO, GSHI | Directory |
| `schools.status` | SY_STATUS_TEXT | Directory |
| `schools.enrollment` | STUDENT_COUNT where TOTAL_INDICATOR='Education Unit Total' | Membership |
| `schools.frl_count` | STUDENT_COUNT where DATA_GROUP='Free and Reduced-price Lunch Table' and LUNCH_PROGRAM='No Category Codes' | Lunch Program |
| `schools.lat/lon` | LATITUDE, LONGITUDE | EDGE geocode (separate file — CCD Directory carries **no coordinates**, correcting my own plan) |
| `schools.locale_code` | LOCALE | EDGE geocode |
| `districts.name/address/phone/website` | LEA_NAME, address fields, PHONE, WEBSITE | LEA Directory |
| `districts.enrollment_total` | sum of school enrollments per LEAID | derived |
| `districts.school_count` | OPERATIONAL_SCHOOLS | LEA Directory |

### New field worth adding (not in your original list): `schools.nslp_status`

The Lunch Program Eligibility component doesn't just give a count — School Characteristics
carries `NSLP_STATUS_TEXT`, which directly flags Community Eligibility Provision (CEP) and
Provision 2 schools. This *is* the fix for the FRL problem I raised in the plan (see
callout below) and it's a clean one: no smell-testing needed, NCES tells us directly which
schools have a formula-based FRL count instead of an application-based one. Proposing to
add a `frl_basis` text column (`'applications'` / `'cep'` / `'provision_2'`) alongside the
existing `frl_pct` — small schema addition, your call at Checkpoint 1.

### Dropped, with reasons

| Field | Why dropped |
|---|---|
| `schools.title_i` | **Not available.** The 2024-25 CCD School Characteristics file does not carry a Title I flag — checked the actual header, it's not there. This appears to have been discontinued from CCD's basic release (may live in EDFacts, which NCES doesn't bundle into these files). Column stays in the schema and stays null unless you want me to chase EDFacts specifically — extra scope, ask before I do it. |
| CHARTER_TEXT, CHARTAUTH1/2 | ND has zero charter schools in this file (`CHARTER_TEXT` = "Not applicable" for all 530 rows) — dead weight for this state. |
| Race/ethnicity/sex breakdowns in Membership | Only the "Education Unit Total" row is used; the ~47,000 ND rows broken out by race/sex/grade are not needed for a fundraising-prioritization score and would 50x the row count for no benefit. |
| MSTREET (mailing address) | Kept LSTREET (physical/location address) only — mailing address is frequently a district PO box, physical address is what a rep drives to. |
| VIRTUAL_TEXT | Not a schema column, but flagging it: **29 open ND schools are "Exclusively virtual"** (Bismarck/Fargo/Williston virtual academies, etc.) — no physical building, no traditional PTO. Raising as a Checkpoint 1 question rather than silently including or excluding them. |

---

## 6a. Combined K-12 resolved — town/district co-location, not single buildings

Per your Checkpoint 1 answer (Q1 = b), "combined K-12" means a district where an
elementary-serving building and a secondary-serving building sit close enough together
that one relationship plausibly reaches both a PTO and a booster program — not one building
spanning every grade.

Built as `v_combined_sites`: a self-join on `district_id` between elementary-serving and
secondary-serving open, non-virtual buildings, distance via `earthdistance`/`cube` (no
PostGIS). First pass used a 10-mile threshold and produced a misleading result — it caught
Fargo and West Fargo elementaries paired with a same-city high school 7-9 miles away, which
is just ordinary big-district geography, not a small-town single-relationship pattern (a
26-school district has no one relationship spanning a specific elementary's PTO and a
specific high school's booster club). Tightened to 2 miles, which keeps the genuine cases
and drops the metro false positives:

**9 districts, 18 elementary/secondary building pairs** — Belcourt, Bowman Co, Dickinson,
Ft Totten, Mandan, Minnewaukan, New Town, Selfridge, St John. Mostly small towns and two
reservation communities where the whole district is one physical site (distances of
0.0-0.4 miles); Dickinson is the one larger case, where 4 elementaries and the high school
all sit within 1.4 miles of each other. Threshold is exposed as a column, not baked into a
boolean, so it's tunable without a schema change if 2 miles turns out wrong in the other
direction once you look at these 9 by name.

## 6. Segment classification — the surprise (brief's Rule 7: flag immediately)

**North Dakota has zero schools that are combined K-12 in one building**, using the schema's
own rule (`grade_low <= 5 AND grade_high >= 9`). I checked every distinct grade span among
the 514 open schools; the widest single-building span is 06-12 (10 schools) and 07-12
(89 schools) — none starts at PK/KG.

This directly contradicts a load-bearing claim in the brief: *"Many rural buildings are
combined K-12. Those are high-value: one visit reaches a PTO and a booster program."*
Phase 6 also explicitly proposes weighting "combined K-12" up as a scoring input.

What the data actually shows: 89 buildings span grades 7-12 (junior-senior high — reaches
a PTO/booster-adjacent population but not elementary PTO) and 10 span 06-12. Genuine
K-through-12-in-one-building is rare to nonexistent in the current CCD snapshot for ND —
possibly it existed in the "grant-funded prospect tool" you built before (different state,
or an older CCD year with different building configurations), or possibly "combined K-12"
in your mental model means *same district* rather than *same building* (e.g., a one-school-
town district where the elementary and the high school are physically separate buildings
half a mile apart, but a single visit to the town covers both). That second reading would
change the answer completely, since it's about route efficiency, not building segment — and
it's checkable in this same data (co-located or same-town elementary+secondary school pairs
by district). I did not build that check without asking, since it reframes what "combined"
means in your scoring model. See Checkpoint 1, Q1.

## 7. FRL / CEP finding (validates a concern I raised in the plan, refines the fix)

**47 of 514 open schools (9%) are under CEP or Provision 2** — meaning their FRL count is a
formula-derived eligibility estimate, not household applications. I'd guessed I would need
a "% at exactly 100%" smell test to find these; that would have failed, because CEP schools'
reported counts range anywhere from ~40% to ~80%+ depending on the CEP multiplier, not a
flat 100%. The real fix is simpler than I planned: NCES already labels this
(`NSLP_STATUS_TEXT`), so it's a clean flag rather than an inference problem. Proposed
`frl_basis` column above handles it. Confirms the underlying concern from PLAN.md §1.3 was
right, refines the mechanism.

---

## CHECKPOINT 1 — resolved

1. **"Combined K-12" = district/town co-location (b).** Built as `v_combined_sites`, see §6a.
2. **Elementary definition — kept both.** `schools.segment` stays the strict building-level
   classification (`elementary` = grade_high <= 5, 136 schools). `v_school_reach` adds
   `serves_elementary` (grade_low <= 5, 298 schools) as a separate view-computed flag for
   "has an elementary PTO target inside it" — no schema column added, since it's a derived
   fact, not a new source fact.
3. **`frl_basis` column added** (migration 002) — `applications`/`cep`/`provision_2`/`unknown`.
   409 applications-based, 40 CEP, 7 Provision 2, 101 unknown (private schools + the small
   number of public schools CCD didn't report an NSLP status for).
4. **`title_i` stays null.** Not chasing EDFacts for the pilot.
5. **29 exclusively-virtual schools kept**, `virtual_status` column added and populated
   (`none`/`supplemental`/`exclusive`). Excluded from `v_combined_sites` — a virtual academy
   has no physical site — and flagged for Phase 6/7 to decide export treatment.

**Also resolved outside this checkpoint:** this pilot is a remote (phone/email) sales
strategy, not in-person visits. `CLAUDE_CODE_BRIEF.md` updated to remove all drive-time and
routing language, and migration 003 dropped `route_clusters`, `school_clusters`, and
`territories.base_lat`/`base_lon` from the live schema (both tables were still empty, so
this was a clean removal, not a migration off real data). Phase 6's scoring inputs no longer
include drive time.

Nothing else in this phase's data materially disagrees with the brief. **Phase 1 is loaded
and complete.** Ready for Phase 2 (ND DPI directory) on your go-ahead.
