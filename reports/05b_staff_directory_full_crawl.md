# Phase 5 Full Crawl — Staff Directory Extraction

Ran the full crawl after the prototype was approved. Two things changed from the prototype
based on feedback mid-build, both already reflected in [ingest/phase5_crawl.py](ingest/phase5_crawl.py):

- **Model switched from Opus 5 to Sonnet 5** (`.env`'s `LLM_MODEL`) — same extraction quality
  on spot checks, ~30% cheaper per page. Cost accounting in `extract_contacts.py` now looks up
  the right per-token rate for whichever model is configured, instead of hardcoding Opus's.
- **Only sales-relevant roles get written to `contacts`.** The extractor can still tag a real
  title as `other` when it doesn't fit the schema's role list (per its own rules — never forcing
  a wrong specific role), but `other` never makes it into the database. Without this, the table
  would have filled with cooks, librarians, dorm counselors, and IT staff alongside the
  principals and PTO officers a fundraiser sale actually needs to reach.

## Two more bugs caught before the real run, on top of the one in the prototype report

1. **JSON truncation on dense pages.** `max_tokens=8000` covers the model's thinking *and* the
   JSON output combined; a long staff list left too little room to finish the JSON on one
   district page. Doubled to 16000, confirmed fixed on the exact page that had failed. Still
   recurs on 2 of 257 sites with unusually large staff lists — a small accepted residual, not
   chased further (same call as the IRS 990 index gap in Phase 4).
2. **Same person appearing twice from one site.** A superintendent's name showed up on both a
   site's homepage and its own staff page, producing duplicate rows. Fixed by deduping within
   each site before insert (keyed on name + role), preferring whichever version had a real
   found email over a derived one.

Both were caught by inspecting real dry-run output before scaling, not assumed away.

## Result

**257 site targets crawled, 243 contacts written, across 78 distinct schools.**

| | |
|---|---|
| Email coverage | 241 of 243 (99%) — 79 found directly on the page, 162 derived from Phase 3's district email patterns, 2 unresolved |
| Cost | **$6.42** total (well under the $20-60 estimated in the prototype report — Sonnet 5 plus the role filter did most of that) |
| Targets with nothing found | 105 (101 schools, 4 districts) — real sites, no staff content on any candidate page tried |
| Other gaps logged | 61 HTTP errors (404s, a couple of 522s), 15 fetch timeouts, 2 JSON-truncation residuals |

### Role distribution written

| Role | Count |
|---|---|
| principal | 95 |
| superintendent | 49 |
| music_teacher | 43 |
| assistant_principal | 19 |
| athletic_director | 11 |
| activities_director | 9 |
| band_director | 7 |
| office_manager | 4 |
| drama_director | 3 |
| choir_director | 2 |
| pto_president | 1 |

Almost no PTO/booster officers turned up here — expected, not a gap. School websites publish
institutional staff, not PTO rosters; that's exactly what Phase 2 (state directory) and Phase 4
(IRS filings) exist to cover instead. This crawl's real contribution is principals,
superintendents, and the arts/activities staff who don't appear in either of those sources.

## Known gaps, stated plainly

- **Private schools are not covered at all.** All 43 ND private schools (Phase 1's PSS source)
  have no `website_url` on file — PSS doesn't publish one, so there was nothing to crawl. Not
  silently absorbed into this run's numbers; needs its own small follow-up (manual lookup, or an
  explicitly-scoped search pass) before private schools have any web-sourced contacts.
- **Site discovery is depth-1 only** (homepage → up to 3 keyword-scored links). A staff page
  buried two clicks deep, or gated behind a search box instead of a direct link, won't be found.
  Consistent with the brief's own 20-30% expected-failure tolerance — not chased further.
- **Superintendent/central-office contacts on multi-school districts** are anchored to the
  district's largest-enrollment open school (`contacts.school_id` has no district-level option in
  the schema). Reversible later via `source_url` if a different anchor is wanted.
- **Re-running this phase will create duplicate rows** for anyone still listed next time — there's
  no natural key to `ON CONFLICT` against yet. Fine for a first pass; worth a dedup/reconciliation
  step before this becomes a recurring refresh.

Full per-URL gap detail: [data/out/phase5_gap_list.csv](data/out/phase5_gap_list.csv).
