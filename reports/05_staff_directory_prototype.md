# Phase 5 Prototype — Staff Directory Extraction

Per the brief: prototype on 3 sites (one large metro district, one small rural district, one
private school), show the JSON, then stop for approval before any full crawl.

## Sites tested

| Site | Type | Result |
|---|---|---|
| Fargo Public Schools staff directory | Large metro district | No staff content found (expected — see below) |
| Hettinger Public School, 2 pages (teacher / ancillary staff) | Small rural district | 28 + 20 names, no roles/emails |
| Grace Lutheran School, Fargo | Private school | 26 people, roles for most |

## A build problem I hit and fixed before trusting any of this

My first version of the extractor used a plain-text system prompt ("respond with ONLY a JSON
object") plus manual `json.loads()`. It failed on 2 of 4 prototype pages — the Fargo response
was pure prose describing the page instead of JSON, and the Grace Lutheran response had a chunk
of echoed page text before the real JSON. `json.loads()` correctly rejected both rather than
silently accepting garbage, which is how I caught it. I rewrote the extractor
([ingest/extract_contacts.py](ingest/extract_contacts.py)) to use structured outputs — Pydantic
models + `client.messages.parse(..., output_format=ExtractionResult)` — which constrains the API
response to the schema directly rather than hoping the model's prose contains valid JSON. Re-ran
all 4 pages after the fix: clean structured output on every one, no prose leakage, no parse
errors.

## Results

**Fargo** — `page_had_staff_content: false`, 0 contacts. This is the JS-rendered-directory
failure mode the brief anticipated (Fargo's site runs on Finalsite, which renders staff listings
client-side; the plain-text HTML fetch never sees the names). Correct behavior, not a bug — the
model was shown a page with no staff text and correctly said so instead of inventing anything.
Not worth working around with a headless browser; that's outside the brief's stack and this
class of failure is the expected 20-30% tail.

**Hettinger** (teacher + ancillary-staff pages) — 48 names total, real people, but **zero roles
or emails**, because the source pages are bare name lists with no titles, no role headers, and no
email/phone info in the text at all. The model followed rule 3 correctly (null role when no
title info exists) rather than guessing a role from which page a name appeared on. This is a
genuine gap in what's crawlable from this site, not an extraction failure — there's nothing here
to derive a role or contact method from without guessing, which the brief forbids.

**Grace Lutheran** — 26 people, most with real roles: principal (Susan Jahnke), office manager
(Amy Hirsch), librarian, cook, music teacher, several classroom teachers by grade
("Kindergarten", "3rd Grade", etc. — used verbatim in `role_detail` since no separate "teacher"
schema role exists), plus an 11-person governing board with titles like President, Secretary,
Treasurer, Vice President. One real structural finding: several board members are listed with
their *home church* affiliation (e.g. "President | Beautiful Savior Lutheran Church") — Grace
Lutheran is apparently governed by a multi-congregation board rather than a single-parish PTO
structure, which is useful context for how a sales approach to this school would need to route
through multiple churches, not just the school office. No emails or phones were present in the
source text for anyone.

## Cost

| Page | Input tokens | Output tokens | Cost |
|---|---|---|---|
| Fargo (empty) | 1,394 | 6,681 | $0.174 |
| Hettinger teacher | 1,649 | 1,383 | $0.043 |
| Hettinger ancillary | 1,653 | 1,187 | $0.038 |
| Grace Lutheran | 1,874 | 1,400 | $0.044 |
| **Total (4 pages)** | | | **$0.299** |

**Worth flagging:** the empty Fargo page cost more than the three real ones combined — 6,681
output tokens to conclude "no staff content," vs. ~1,200-1,400 for pages with 20-26 real
contacts. That's the model's adaptive thinking working through a confusing/large page before
giving up, not a bug, but it means a full crawl's cost won't scale cleanly with contacts-found;
JS-rendered dead ends could be some of the more expensive pages, not the cheapest.

## Scale estimate for a full crawl

207 of 221 districts and 508 of 573 schools have a `website_url` on file; deduplicated, that's
**307 distinct site URLs**. Real sites need more than one page each on average (Hettinger alone
needed 2), so call it 400-600 LLM extraction calls for a full pass. At $0.04-0.17/page, that's
roughly **$20-60 total** — cheap regardless of which end of that range it lands on.

## What full crawl still needs to be built (not done yet, listed so the scope is clear)

- A site → staff-page URL discovery step (this prototype used hand-picked URLs; the full crawl
  needs to find the actual directory page per site, e.g. by checking common paths or following
  in-page links from the homepage).
- robots.txt-gated, rate-limited fetching across all 307 sites (the actual crawler; the prototype
  only fetched 4 pages by hand).
- Writing extracted contacts into the `contacts` table with `source_url`, `ingest_run_id`, and a
  gap-list CSV for pages that fail (no staff content, fetch error, or a parse exception).
- Accumulating `cost_usd` into `ingest_runs` per run (the `extract()` function returns per-call
  cost; nothing persists it yet).

Per the brief, stopping here for approval before building or running any of that.
