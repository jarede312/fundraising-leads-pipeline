# School Fundraising Prospect Engine: Build Brief

Paste this as your opening message in Claude Code. Keep `schema.sql` in the repo root.

---

## READ THIS SECTION FIRST AND FOLLOW IT LITERALLY

You are helping me build a sales prospecting database for school fundraising. I am one person building this in spare time for a family business. **My scarcest resource is my attention, and the most expensive failure mode is you building something correct that I did not need.**

Therefore:

### The question protocol

1. **Stop at every CHECKPOINT.** The plan below has numbered checkpoints. At each one, stop and wait for my answer. Do not proceed past a checkpoint on your own judgment, even if the next step seems obvious.

2. **Batch your questions.** When you need decisions, give me a numbered list of 3 to 8 questions at once with your recommended answer for each and a one-line reason. Do not drip-feed one question at a time. Format them so I can reply "1a, 2b, 3 your call, 4 skip it."

3. **Default to asking when the answer changes more than 30 minutes of work.** Cheap and reversible: just do it and tell me. Expensive or hard to undo: ask.

4. **Prototype on 3 records before running 500.** Any extraction, scrape, or transform gets built against a handful of hand-picked examples first. Show me the output. Only scale after I say go. This rule has saved more time than anything else on this list.

5. **Say what you are about to build before you build it,** in one or two sentences, if it will take more than about 20 lines of code.

6. **Tell me when you think I am wrong.** I want the blind spots, the caveats, and the consequences I have not considered. If a spec I gave you is bad, say so before implementing it. Do not silently work around my mistakes.

7. **Flag surprises immediately.** If real data contradicts an assumption in this brief (record counts are way off, a source is unusable, a format changed), stop and tell me rather than coding around it. The assumptions here came from web research, not from the actual files.

### Do NOT build any of the following unless I explicitly ask

- Any web UI, front end, React app, or dashboard
- User authentication or login
- A CRM, deal pipeline, or opportunity tracking
- Email sending, sequencing, or campaign management
- Tests beyond what is needed to trust an ingest step
- Docker, CI, or deployment configuration
- An ORM layer or a repository/service abstraction over the SQL
- Retry/queue/worker infrastructure
- Anything national in scope

The scope for now is **North Dakota only**, **data ingest only**, **no interface**. My interface for the pilot is `psql` and CSV exports. That is deliberate and sufficient.

---

## Context

My father-in-law sells product fundraising programs (catalog sales, spirit wear, holiday shops) to schools. His buyers are principals, school office managers, PTO and PTA officers, and at secondary schools band, choir, and drama directors. Fundraisers run once or twice a year, so timing is everything and the decision windows are narrow.

The goal of this system is **prioritization, not contact storage**. Nobody works 128,000 schools. A rep works about 300. The job is: given a rep, a territory, and a month, which schools should they contact, and in what order. This is a remote sales strategy — phone and email, no in-person visits — so there is no routing or drive-time component anywhere in this system.

I have built something structurally similar before (a grant-funded prospect tool with scoring, weekly batches, and contacted/acknowledged flags), so assume I can read SQL and Python comfortably. Do not over-explain basics.

### Known facts about the pilot state

- North Dakota has roughly 168 public school districts operating roughly 540 public schools, plus roughly 48 private schools
- About 116,000 students statewide, and enrollment just declined for the first time in 16 years
- Roughly 3.2 schools per district, which is unusually low. The "scrape the district site instead of each school site" shortcut has much less leverage here than in most states. Expect to hit individual school sites often.
- A handful of districts (Bismarck, Fargo, West Fargo, Grand Forks, Minot, Mandan, Williston, Dickinson) hold roughly half the state's students. The other 160 districts are a long, shrinking tail.
- Many rural buildings are combined K-12. Those are high-value: one relationship reaches a PTO and a booster program.

**Treat all of the above as unverified.** Phase 1 exists partly to check it.

---

## Tech stack

- **Postgres.** Local Postgres 16 for development. I will decide on hosting later, so do not add hosting config.
- **Python 3.11+.** Plain scripts in `ingest/`. `psycopg`, `httpx`, `pandas` or `polars`, `selectolax` or `beautifulsoup4`. Add dependencies only when needed and tell me why.
- **Anthropic API** for structured extraction from staff directory pages. Make the model name a config variable, not a literal, so I can swap to a cheaper model. Log token counts and estimated cost per run into `ingest_runs.cost_usd`.
- Migrations: plain numbered `.sql` files in `migrations/`. No migration framework.

Apply `schema.sql` as migration `001`. Read the comments in it before writing any code, they explain the design constraints.

---

## Build plan

### Phase 1: Universe from NCES

Load the public school universe for ND.

- NCES Common Core of Data: schools and districts (school ID, LEA ID, name, address, phone, grade span, enrollment, free/reduced lunch counts, Title I, locale code)
- NCES Private School Universe Survey: the private schools
- Populate `states` with a stub row for ND

Then produce a reconciliation report answering:
1. Actual count of ND districts, public schools, private schools
2. How many buildings serve elementary grades
3. How many are combined K-12
4. Districts ranked by enrollment, with a cumulative percentage column

That last table decides the entire cost model, so it is the real deliverable of this phase.

> **CHECKPOINT 1.** Show me the reconciliation report and the CCD field list you chose to keep, plus fields you considered and dropped. Ask me about anything ambiguous in the segment classification logic. Wait for my answer.

### Phase 2: North Dakota DPI directory

The ND Department of Public Instruction publishes a school directory that usually carries principal names and sometimes emails. Find it, determine its format, and load it into `contacts`.

Also fill in `states` with the license terms verbatim and set `commercial_use_permitted`. Several states restrict commercial use of their published directories. Read the actual terms of use page, do not guess.

> **CHECKPOINT 2.** Tell me what the DPI file actually contains, what the license says, and what percentage of schools got a principal name. If the license restricts commercial use, stop entirely and tell me before loading anything.

### Phase 3: Email pattern derivation

For each district, determine the email convention from known addresses and store it in `districts.email_pattern` with an evidence trail and a confidence tier.

This is the highest-leverage step in the project. School districts are centrally IT-managed with one convention across every building, unlike universities. Solve the pattern once per district and you can derive an address for every named person in it.

Build the pattern detector, run it, then show me `v_email_pattern_gaps` ranked.

> **CHECKPOINT 3.** Show me the pattern distribution, how many districts resolved at each confidence tier, and a sample of 20 derived addresses. Ask me whether to buy email verification before or after I test deliverability manually on a few.

### Phase 4: IRS nonprofit data

Load 990, 990-EZ, and 990-N filings for ND, filter to plausible PTO/PTA/booster organizations, and fuzzy-match them to schools.

This is the only self-refreshing source in the system: these organizations refile annually and the filing names a principal officer. Match on address first, then name similarity, and populate `school_org_links` with a score. Leave `confirmed` false.

> **CHECKPOINT 4.** Show me match rate, the score distribution, and 15 sample matches spanning high, medium, and low confidence so I can calibrate the threshold. Ask me where to set the auto-accept cutoff.

### Phase 5: Staff directory extraction

Crawl school and district sites, extract contacts with the LLM, write to `contacts` with provenance.

Prototype on 3 sites first: one large metro district, one small rural district, one private school. Show me the extracted JSON before scaling.

Requirements:
- Respect `robots.txt`, rate limit politely, identify the user agent honestly
- Store `source_url` on every contact
- Never invent a contact. If the page has no music teacher listed, write nothing rather than guessing.
- Record cost per run

Expect roughly 20 to 30 percent of sites to fail to parse (PDFs, JavaScript-rendered directories, no staff page). **Do not try to fix the tail.** Write failures to a gap-list CSV for manual handling and move on.

> **CHECKPOINT 5.** Show me the 3-site prototype output, then stop. After I approve, run the full crawl and report yield, failure reasons, and cost.

### Phase 6: Scoring

Compute a fundraising potential score per school. Generate once, store in `scores` with the component breakdown and a short written rationale. Never call the model at read time.

Suggested inputs, but propose your own weighting and argue for it:
- Enrollment (raw dollar potential)
- PTO gross receipts from the IRS layer (capacity signal)
- Free/reduced lunch percentage (affects expected net per student)
- Segment, with combined K-12 weighted up
- Locale code

No drive-time or geographic-routing component. This is a remote sales strategy — outreach is phone and email — so distance from a base location has no bearing on the score.

> **CHECKPOINT 6.** Propose the weighting with your reasoning before implementing. Then show me the top 25 and bottom 25 scored schools so I can sanity check whether the ranking matches intuition.

### Phase 7: Exports and the refresh loop

- CSV export: one row per school with the best contact per role and score
- The verification queue view, tiered
- A re-runnable August sweep script that re-extracts and diffs against current contacts, writing changes to `signals` and `contact_verifications` rather than silently overwriting

> **CHECKPOINT 7.** Show me the export format before generating it in bulk.

---

## Open questions I already know exist

Raise these when they become relevant rather than deciding silently:

1. Do I want private schools in the pilot at all, or defer them? They are 48 schools with no central contact source and disproportionate manual cost.
2. Should the long tail (the roughly 130 smallest districts) get full treatment or just the free NCES record?
3. How should combined K-12 buildings be segmented, given they are both an elementary PTO target and a secondary booster target?
4. What counts as "elementary" for filtering: grade_low <= 05, or presence of any grade K-5?
5. Should closed and consolidated schools be deleted or retained with a status flag? (I lean retained, but confirm.)

---

## Definition of done for the pilot

A single command loads North Dakota from scratch and produces a CSV of ND schools with score, best-known contacts, and provenance on every field. No UI. No deployment. A gap list of what needs human work, with an honest count.

If at any point you think a phase is not worth doing, say so. I would rather cut a phase than build one I do not use.
