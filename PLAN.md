# ND Pilot — Build Plan

Status: pre-Phase-1. Nothing built yet. This document is the plan only.

---

## 0. Environment findings (checked, not assumed)

| Thing | State |
|---|---|
| Python | 3.14.6 present (brief asked 3.11+; 3.14 is fine, watch for lagging wheels) |
| Postgres | **not installed** — no `psql`, no `pg_config`, no service, nothing in Program Files |
| Docker | not installed |
| PostGIS | n/a (no PG) |
| Repo | not a git repo |

**This is the blocker.** Nothing in Phase 1 can land until Postgres 16 exists locally. See Q1.

---

## 1. Four things I would change about the brief

### 1.1 Phase 3 as written cannot run after Phase 2. Insert a cheap step.

Phase 3 derives each district's email convention "from known addresses." But the known addresses
are supposed to come from Phase 5 (staff crawl), which is scheduled *after* Phase 3. If the ND DPI
file has no emails, Phase 3 has zero input and stalls.

Proposed fix: a **Phase 3a domain harvest** — for each of ~168 districts, fetch only the district
homepage plus a contact/staff landing page and pull every `mailto:` and bare email on it. That is
~168 cheap fetches, no LLM, and it typically yields 3-10 addresses per district — exactly what the
pattern detector needs. Phase 3b (detection) then runs with real input, and Phase 5 gets to *derive*
emails for everyone it names instead of scraping them.

This also flips the economics of Phase 5: once the pattern is known, a name is worth an address, so
extraction only has to get names and roles right.

### 1.2 IRS matching should be name-first, not address-first

The brief says "match on address first, then name similarity." In practice a PTO's IRS address is
frequently the **treasurer's home**, and it changes every year or two as officers turn over. School
address matching therefore has a low hit rate and a nasty failure mode: it silently misses the
active PTOs at exactly the schools where officers rotate.

Names are the stronger signal — "Lincoln Elementary PTO", "Century High Booster Club" encode the
school. Proposed: `name_trgm` scoped to same city/ZIP as the primary pass, address as a score
booster and tiebreaker rather than the first pass. Same `school_org_links.match_method` values,
different priority. I will show both rates at Checkpoint 4 so this is checkable, not just asserted.

Related: ND has many one-school towns, where the district name and the school name and the town name
are all the same word. Expect false positives there; the score distribution at Checkpoint 4 is where
we set the cutoff.

### 1.3 FRL percentage is a degraded signal and will mislead the score

Community Eligibility Provision districts report every student as free-eligible regardless of actual
household income. Where CEP is in force, `frl_pct` is 100 and means nothing. If Phase 6 weights FRL
without accounting for this, CEP schools get systematically mis-scored — and CEP uptake is high in
rural and tribal districts, which is a meaningful slice of ND.

I will quantify CEP prevalence during Phase 1 (the count of schools sitting at exactly 100 percent
FRL is a usable smell test) and bring a proposal to Checkpoint 6. Likely alternative: Census SAIPE
district-level child poverty, which is a real estimate rather than a program artifact.

### 1.4 The per-school LLM rationale is probably not worth an API call

`scores.rationale` plus `scores.model` implies model-written rationale for every school. For 540
schools a **template** built from the component values ("Large combined K-12, 412 students, PTO
grossed $38k in FY24, 35 min from base") is deterministic, free, diffable across score versions, and
reads about as well. I would write the template and leave `scores.model` null. Cheap to revisit if
the templated text turns out flat. Raising it as a question rather than deciding, since it touches a
schema column you deliberately added.

---

## 2. Layout and conventions

```
migrations/001_init.sql        schema.sql, applied verbatim except the postgis line (Q2)
migrations/002_*.sql           anything later; numbered, forward-only, no framework
ingest/
  config.py                    env-driven: PG_DSN, ANTHROPIC_API_KEY, LLM_MODEL, USER_AGENT
  db.py                        psycopg connection, ingest_run open/close, cost accumulator
  phase1_nces.py
  phase2_nd_dpi.py
  phase3a_domains.py           mailto harvest (new, see 1.1)
  phase3b_patterns.py          pattern detection and confidence tiering
  phase4_irs.py
  phase5_extract.py
  phase6_score.py
  phase7_export.py
data/raw/                      downloaded source files, kept verbatim for reproducibility
data/out/                      CSV exports and gap lists
reports/                       reconciliation and checkpoint reports
run_pilot.py                   the single command from the definition of done
```

Rules I will hold myself to, from the brief:

- Every write goes through an `ingest_runs` row. No orphan facts.
- Raw source files are saved before parsing, so a re-run is reproducible without re-downloading.
- Any script that hits the network takes `--limit N` and defaults to a small N. Full runs are explicit.
- Nothing is deleted. Schools that vanish from a source get `status` changed, not a DELETE.

Seed data: one `orgs` row, one `users` row, one `territories` row. That is the minimum needed to make
territory-scoped scores have a foreign key to point at. Not building auth, not building a rep UI —
just enough for the joins to resolve.

**2026-08-22 update: this is a remote sales strategy (phone/email), not in-person visits.** No
drive-time component, no routing, no `base_lat`/`base_lon`, no route clusters anywhere in the
pilot. See the schema note below — Section 8 of `schema.sql` (ROUTING) is now dead weight.

---

## 3. Phases

### Phase 1 — NCES universe

Sources (all to be verified live, not trusted from memory):

- CCD school level: Directory, Membership (enrollment), School Characteristics (Title I), Lunch
  Program (NSLP/FRL), plus the EDGE geocode file for lat/lon
- CCD LEA level: directory and membership, for the districts table
- PSS: private schools, most recent collection

Notes:

- CCD is split across several files per year and they must be joined on NCES school ID. The
  directory file alone has no enrollment.
- CCD directory carries lat/lon already, so **no geocoding step and no geocoding API is needed** for
  public schools. PSS likewise. That removes a dependency the brief did not budget for.
- CCD and PSS release on different cadences and PSS is biennial, so the two halves of the universe
  will be from different years. I will record `enrollment_year` per row rather than pretend otherwise.

Provisional segment rule (open to revision at Checkpoint 1):
`grade_high <= 05` elementary; `grade_low >= 09` high; `grade_low >= 05 and grade_high <= 08` middle;
a span crossing 05 to 09 is combined; else other. `serves_elementary` and `serves_secondary` are
computed in a view from grade_low/grade_high rather than stored, so Open Question 3 needs no schema
change and can be answered later.

Deliverable: `reports/01_reconciliation.md` with the four required tables, the kept-field list, the
dropped-field list with reasons, and the CEP smell test. Then stop at **Checkpoint 1**.

### Phase 2 — ND DPI directory

Locate the directory, record its format, read the actual terms-of-use page, fill `states` with
verbatim license text and a `commercial_use_permitted` value. **If the terms restrict commercial
use, I load nothing and stop.** Report principal-name coverage as a percentage of open public schools.

Stop at **Checkpoint 2**.

### Phase 3a — district domain and address harvest (new)

~168 districts. Homepage plus one or two obvious contact pages each. robots.txt respected, honest
user agent, polite rate limit. No LLM. Output: `districts.email_domain` populated, plus a raw
evidence trail of found addresses.

### Phase 3b — pattern detection

Classify each district's addresses against the pattern set in the schema (`first.last`, `flast`,
`lastf`, `first_last`, `firstl`, `first`, `custom`). Tiering per the schema comment: 3+ consistent is
high, 1-2 is medium, inferred from a sibling district or shared platform is low.

A real caveat: a district can run more than one convention (staff vs admin, or a legacy domain kept
after a consolidation). When the evidence splits, the honest answer is `custom` with the evidence
retained, not a majority-vote guess. Better to under-claim than to derive 40 bad addresses.

Deliverable: pattern distribution, tier counts, 20 sample derived addresses, `v_email_pattern_gaps`
ranked. Stop at **Checkpoint 3**.

### Phase 4 — IRS

Plan: pull the IRS Exempt Organizations Business Master File filtered to ND, use NTEE codes plus a
name regex to isolate PTO/PTA/booster/education-foundation orgs, then join the 990-N e-postcard bulk
data (principal officer name and address, gross receipts) and the 990/990-EZ extracts for the larger
filers. Match to schools per 1.2.

One flag worth raising now: the 990-N principal officer address is often a **home address**. It is
public and legal to use, but reaching a volunteer PTO president at their house has a different feel
from reaching a principal at a district address, and it is worth deciding deliberately whether those
go into the export or stay in the database.

Deliverable: match rate, score distribution, 15 samples spanning the confidence range. Stop at
**Checkpoint 4**.

### Phase 5 — staff extraction

Prototype on exactly 3 sites (one large metro district, one small rural district, one private
school), show the JSON, stop. Only then scale.

- Default model `claude-opus-5`, set in `config.py` as `LLM_MODEL`, swappable per the brief.
- Cost is not a constraint at this scale. After stripping HTML to text with selectolax, expect
  roughly 3-8k input tokens per page across ~700 pages. Ballpark $20-40 on Opus 5, and the full
  crawl is a natural fit for the Message Batches API (not latency sensitive, 50 percent off), which
  puts it near $15. Haiku 4.5 would be around $5. The gap is not worth optimizing; extraction
  quality is.
- Never invent a contact. Absent role means write nothing.
- Failures go to `data/out/gap_list.csv` with a reason code. The tail does not get fixed.

Stop at **Checkpoint 5** after the 3-site prototype.

### Phase 6 — scoring

The weighting proposal comes to **Checkpoint 6** as an argument before any code. One thing I already
expect to argue: FRL gets replaced or heavily discounted (1.3). No drive-time component — this is a
remote (phone/email) sales strategy, so distance from a base location has no bearing on the score.

### Phase 7 — export and refresh

CSV: one row per school, best contact per role, score, cluster, and a provenance column per contact
field. The verification queue view already exists in the schema. The August sweep re-extracts and
writes diffs to `signals` and `contact_verifications` rather than overwriting. Format shown at
**Checkpoint 7** before bulk generation.

---

## 4. Risk register

| Risk | Impact | Handling |
|---|---|---|
| ND DPI license restricts commercial use | Kills Phase 2, weakens Phase 3 input | Checked before any load; hard stop |
| DPI directory has names but no emails | Phase 3 loses its best input | Phase 3a covers it independently |
| CEP makes FRL meaningless | Score is quietly wrong | Quantified in Phase 1, resolved at Checkpoint 6 |
| PTO IRS address is a home address | Match rate and outreach appropriateness | Name-first matching; export decision at Checkpoint 4 |
| 20-30 percent of sites unparseable | Expected, not a problem | Gap list, no tail-chasing |
| PSS is biennial and stale | Private enrollment is 1-3 years old | `enrollment_year` recorded honestly |
| Python 3.14 wheel gaps | Setup friction | Fall back to 3.12 if a pin fights us |

---

## 5. Open questions from the brief — disposition

| # | Question | When it gets answered |
|---|---|---|
| 1 | Private schools in the pilot? | Now — Checkpoint 0, it changes Phase 1 scope |
| 2 | Full treatment for the ~130 smallest districts? | After Checkpoint 1 — the cumulative enrollment table *is* the answer |
| 3 | How to segment combined K-12 | Checkpoint 1; no schema change needed either way (view-computed flags) |
| 4 | What counts as "elementary" | Checkpoint 1; provisional rule above |
| 5 | Delete vs retain closed schools | **Decided: retain with `status`.** Cheap, reversible, matches your lean, and a school that closes is itself a signal worth keeping. Say the word if you disagree. |
| 6 | Drive time stored or computed at query time | **Moot — remote sales strategy, no drive-time component at all (2026-08-22).** |

---

## 6. CHECKPOINT 0

Questions are in chat. Nothing gets built until they are answered.
