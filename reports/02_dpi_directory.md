# Phase 2 Report — ND DPI Directory

Source: `falldir25-26.xlsx`, current 2025-26 school year, updated 2025-11-25.
`https://www.nd.gov/dpi/sites/www/files/documents/Data/falldir25-26.xlsx`

## License

Verbatim, from `nd.gov/dpi/copyright-website-use-and-disclaimer` (site-wide, applies to
every NDDPI-hosted file, no separate per-file terms):

> "All web pages and other files on the North Dakota Department of Public Instruction
> (NDDPI) website are copyrighted by NDDPI. **The material is for the noncommercial use
> of the education communities and general public.** The fair use guidelines of the U.S.
> copyright statutes apply to all material on the NDDPI website."

Stored in `states.directory_license_notes`, `commercial_use_permitted = 'restricted'`.

**Your decision: load it, flagged as restricted.** Every contact row's `ingest_runs.notes`
carries the disclaimer text and a pointer back to this decision, so it stays visible rather
than buried in a one-time chat message. Nothing here substitutes for actually resolving the
commercial-use question with NDDPI before this data drives real outreach — that's still
open, on you, whenever you're ready to raise it with them.

## What the file actually contains

30 sheets. Far richer than the brief anticipated — real named people with direct emails
across principal roles, assistant principals, business managers, board presidents, school
counselors, and compliance-coordinator roles (Title IX, 504, EL, homeless/foster-care
liaisons, etc.). Only the roles that map to your named buyer personas or existing schema
roles were loaded:

| DPI sheet | Schema role | Rows loaded |
|---|---|---|
| Elementary Principal | `principal` | (see below, combined) |
| Secondary Principal | `principal` | |
| Jr-Middle Principal | `principal` | |
| Assistant Principals | `assistant_principal` | 134 |
| Teachers, filtered to `MajorAreaofResponsibilityName = 'Specialist: Music'` | `music_teacher` | 313 |

**539 principal + 313 music_teacher + 134 assistant_principal = 986 contacts loaded,
100% with an email address.**

Not loaded, and why: Business Managers (a district-level financial role, not the same job
as the schema's `office_manager`/school-secretary persona — conflating them would be a
modeling error, not a shortcut), Board Presidents and County Sups (not a buyer persona, and
County Sups is a different state office structure that doesn't map to your districts at
all), and the compliance-coordinator sheets (Title IX, 504, EL, homeless/foster-care
liaisons, technology coordinators) — not relevant to a fundraising sales pitch.

## Correction to what I told you earlier this session

My first read of email coverage (41% Elementary Principal, 29% Secondary, 8.5% Jr-Middle)
was wrong — a parsing bug, not a real gap. Several sheets carry a second, unrelated block
of rows below the real data table (a trailing district-website reference list with only a
URL and every other column blank), and my first pass counted "any cell non-null" as a real
row, so those counted as principals with no email. Filtering on `FirstName IS NOT NULL`
(the actual "this is a person" signal) fixed it. **The real number is 100% email coverage
among genuine principal/assistant-principal/music-teacher rows** — better than the brief
expected ("usually carries principal names and sometimes emails"), not worse. Flagging this
plainly since it changes the picture I gave you, even though the corrected news is good.

## Matching: DPI records to the schools already loaded in Phase 1

DPI's `StateIssuedID` and CCD's `ST_SCHID` are the same underlying ND state ID system in
different formats, but DPI's short code doesn't always uniquely identify a CCD building —
one physical site can hold multiple grade-span buildings under one DPI site code (a Jr High
and a Sr High sharing a base code, distinguished only by a CCD-assigned sequence digit).
Added `districts.st_lea_id` / `schools.st_school_id` (migration 004) and matched by state-ID
prefix within the district, disambiguating multi-building sites by which DPI sheet a row
came from (Elementary Principal → the building serving elementary grades, etc). Schools
with no CCD state ID at all — mostly Catholic/private and one tribal (BIE-funded) school,
which aren't part of the state's public LEA structure — got a conservative name-similarity
fallback against the private schools already loaded from PSS (`pg_trgm`, only auto-accepted
when one candidate is clearly the best match; ties are left unmatched rather than guessed).

**177 rows (out of ~1,163 processed) stayed unmatched** → `data/out/phase2_gap_list.csv`.
Breakdown: 96 "ambiguous site" (a real building match exists but more than one candidate
still ties after segment disambiguation — mostly the Teachers:Music sheet, where there's no
segment signal to disambiguate with at all), 81 "no school at site" (private/tribal schools
the name-fallback still couldn't confidently place). Not chasing this tail further — same
"do not try to fix the tail" rule as Phase 5.

**Coverage: 528 of 557 open ND schools (public + private) have a named principal — 94.8%.**
529 schools have at least one contact of any role.

## What's still missing (expected, not a gap in this phase)

Office managers, PTO/PTA officers, and band/choir/drama directors specifically — none of
DPI's sheets carry these. `music_teacher` here is a DPI staff-assignment category
("Specialist: Music") that doesn't distinguish band vs. choir vs. general music; noted in
each row's `role_detail`. These remain Phase 4 (IRS/PTO) and Phase 5 (site crawl) work.
