# Prospect Engine Web App — Build Plan

Status: Phases 0-2 built and running (schema, read-only app, logging + queue mode). Phase 3 below is a proposal only — nothing in this section is built yet, per WEBAPP_BRIEF.md Checkpoint 3's explicit instruction to propose before implementing.

---

## 0. Environment findings (checked, not assumed)

| Thing | State |
|---|---|
| Postgres | reachable via `PG_DSN` in `.env`. Real ND data loaded. |
| `schools` | 573 rows (557 `status='open'`) |
| `districts` | 221 |
| `contacts` | 1,229 |
| `nonprofit_orgs` | 143 |
| `school_org_links` | 108 (43 confirmed, 65 unconfirmed) |
| `signals` | 0 |
| `scores` | **0** |
| `rep_actions` | 0 |
| `orgs` / `users` / `territories` | **0 / 0 / 0** |
| `ingest_runs` | 8 |
| Repo | still not a git repo |
| DB driver installed | `psycopg2-binary` (used by `ingest/db.py`); no async driver |
| Webapp code | none exists — clean slate |

Contact quality, since this is the load-bearing fact for the whole UX:

| email_confidence | count |
|---|---|
| medium | 1,060 |
| high | 167 |
| unknown | 2 |

| role | count |
|---|---|
| principal | 634 |
| music_teacher | 356 |
| assistant_principal | 153 |
| superintendent | 49 |
| athletic_director | 11 |
| activities_director | 9 |
| band_director | 7 |
| **office_manager** | **4** |
| drama_director | 3 |
| choir_director | 2 |
| **pto_president** | **1** |
| pta / booster_* / other | **0** |

25 open schools have zero contacts of any kind.

---

## 1. Things the brief gets wrong about the current state — flagged, not worked around

### 1.1 Migration number collision
The brief says write `002_crm_layer.sql`. `002`, `003`, `004` are already used by the ingest pipeline (FRL/virtual-status, routing removal, state IDs). Next number is **`005`**.

### 1.2 Phase 0's "remove routing" is already done
`migrations/003_remove_routing.sql` already dropped `route_clusters`, `school_clusters`, and `territories.base_lat/base_lon`. The only real Phase 0 schema debt left from the routing note is `rep_actions.channel`'s CHECK, which in the live schema still lists `in_person` — that part of Phase 0 is still needed, the rest isn't.

### 1.3 Scores don't exist yet — this breaks the brief's own phase order
`scores` has zero rows. The ingest side's Phase 6 (scoring) was never run. But WEBAPP_BRIEF's **Phase 1** (read-only school list/detail) has "score" and "rationale" as load-bearing columns, and **Phase 5** ("Rescoring") — which is where the brief expects the drive-time-removed weighting to get proposed — is scheduled *last*, after the whole CRM is built.

There is nothing to "rescore" — there is no prior score to rebalance. This needs to become a first scoring run, moved *before* Phase 1, using Phase 5's already-drive-time-free input list (enrollment, PTO gross receipts, FRL%, segment, contactability). Otherwise Phase 1 either ships with a blank score column or I fabricate a placeholder — both worse than doing the real thing first.

### 1.4 rep_actions needs a seed org/user that doesn't exist
`rep_actions.org_id` and `rep_actions.user_id` are `NOT NULL` FKs. All three tenancy tables are empty. Phase 2 (logging) cannot insert a row until one `orgs` row and one `users` row exist. Cheap, but has to happen somewhere, and the brief never mentions it.

### 1.5 "Saved views" (Phase 1) duplicates existing `territories` infrastructure
`schema.sql`'s own comment on `territories`: *"a saved filter, not a hardcoded list... store the rule so it re-evaluates."* That is exactly Phase 1's "Saved views" spec. Building a new table would duplicate something already designed for this, in a schema whose stated design principle is not denormalizing/duplicating by decay layer. Worth a deliberate decision rather than silently picking one.

### 1.6 The PTO/booster contact layer the schema was built for barely exists yet
Phase 0 adds `rep_actions.buying_entity` with values like `pto`, `boosters_band`, etc. — but there is exactly **one** PTO contact and **zero** PTA/booster contacts in the entire state. `office_manager`, which the schema's own comment calls "the real gatekeeper," has 4 rows. The IRS layer *does* know PTO principal-officer names (via `nonprofit_orgs.principal_officer_name`, reachable through `school_org_links`) but that's a bare name string on a different table — not a `contacts` row, no email, no phone, nothing `rep_actions.contact_id` can point at.

This isn't a blocker — `rep_actions.contact_id` is nullable and `buying_entity` doesn't require one — but it means the school-detail page's "contacts grouped by role" will, for most schools, show a principal and maybe a music teacher, not the PTO officer the whole buying-entity model is designed around. I'd rather say this now than have it be a surprise on day one of the two-week trial.

---

## 2. UX position — this has to be the thing he opens first, not a thing he remembers to check

He is a working salesperson, not a data analyst. If this doesn't save him time in the first five minutes of every session, it dies quietly and I won't find out why. Three commitments drive every screen decision below:

**Trust is the actual product.** The data underneath is a deliberate mix of phone-verified, scraped, and pattern-derived guesses (schema.sql design principle 5). If a derived-unverified email is indistinguishable from a verified one anywhere in the UI, he loses confidence in *all* of it after the first bad call — and the brief already says this explicitly. Provenance can't be a detail-page tooltip; it has to be a consistent, glanceable visual language (small tier marker + color, not a paragraph) that shows up everywhere a contact appears: list, detail, queue mode. One icon system, defined once, reused everywhere — not redesigned per screen.

**The morning ritual is the whole product.** He opens the app, sees today's ~12–15, works down the list, closes the laptop. No inbox-zero anxiety, no growing red number (the brief already bans overdue counts — right instinct, and it extends further: no unread-style badges anywhere, no "N items need attention" banners). A bounded list that's always achievable beats a complete one that never is.

**Hands stay on the keyboard for the entire session.** Thirty calls in a sitting means every logging action needs a shortcut with a visible hint, and mouse-only actions should be the exception, not the rule — this is true on the list, the detail page, and especially queue mode, where a rep is moving school-to-school every 60–90 seconds.

One more thing worth designing for deliberately, given 1.6: **the empty state is a workflow instruction, not a blank space.** "No PTO contact on file — the office (555-0123) can tell you who runs it" is more useful to him than an empty "PTO" section header. I'll write real empty-state copy per contact role, not a generic "no data."

---

## 3. Proposed phase order (amended)

```
Phase 0   — schema migration 005_crm_layer.sql (brief's Phase 0, renumbered,
             minus the already-done routing removal)
Phase 0.5 — NEW: seed one org + one user; run first scoring pass
             (brief's Phase 5 content, moved here, framed as v1 not a rescore)
Phase 1   — read-only app (school list, detail, saved views)
Phase 2   — activity logging + queue mode
Phase 3   — buying windows + follow-up generation
Phase 4   — daily priority list
```

Brief's original Phase 5 is absorbed into the new Phase 0.5 — there's no prior `score_version` to bump from, so this ships as `'v1'`.

---

## 4. CHECKPOINT 0 — questions, batched

Reply in the "1a, 2b, 3 your call" format.

1. **Migration file name.** `005_crm_layer.sql`, folding in just the `rep_actions.channel` CHECK fix (drop `in_person`) since routing itself is already gone (1.1, 1.2).
   *(a) yes, 005, channel-fix only — (b) your call on naming, just don't touch routing again — (c) other.*

2. **Insert Phase 0.5 (seed + first scoring) before Phase 1.** Recommend yes — Phase 1's screens need a real score column, and there's nothing to rescore yet (1.3).
   *(a) yes, insert it — (b) skip scoring for now, ship Phase 1 with score column hidden/blank — (c) other.*

3. **Seed org/user.** What should the `orgs.name` and `users.display_name` be? I'll default to something like `"[Business Name]"` / his real name with `role='rep'` unless you tell me otherwise — this is a one-row throwaway, not user-facing copy, so low stakes either way.
   *(a) give me the two strings — (b) use placeholders, we'll rename later — (c) other.*

4. **Saved views vs. `territories`.** Recommend reusing `territories` (already shaped as a named, re-evaluating filter) instead of a new table, per 1.5.
   *(a) reuse territories — (b) new dedicated `saved_views` table, territories feels like the wrong mental model for a one-user tool — (c) other.*

5. **Thin PTO/booster contact data (1.6).** Recommend shipping Phase 1 as-is for the two-week trial — he can supplement by phone and the brief already frames this trial as cheap-to-fail. A one-time PTO enrichment pass is real, non-trivial work I'd rather not do speculatively.
   *(a) ship as-is, revisit after the trial — (b) do a PTO enrichment pass first — (c) other.*

6. **Schools with zero contacts (25 of them).** Recommend always showing them in the list (never silently hidden), consistent with "never label anything as failure, never drop a record."
   *(a) show them, flagged — (b) hide until they have a contact — (c) other.*

7. **DB access for the web app.** `psycopg2-binary` is already installed and used by `ingest/db.py`. Recommend sync `psycopg2` behind FastAPI's threadpool — single user, low request volume, no reason to add async complexity or a second driver.
   *(a) sync psycopg2, no new dependency — (b) move to psycopg3 — (c) other.*

8. **Git.** This still isn't a git repo. Recommend `git init` now, before any webapp code lands, so each checkpoint's diff is reviewable the way the brief's "show me the migration before applying" implies.
   *(a) git init now — (b) later — (c) skip, you don't need it.*

---

## PHASE 3 PROPOSAL — buying windows and follow-up generation

Not built. This is the proposal WEBAPP_BRIEF's Checkpoint 3 asks for before any of it gets implemented.

### Reality check on the "90-day dry run"

The brief's Checkpoint 3 asks for a dry run of what would have fired over the past 90 days. Checked: `rep_actions` has 15 rows, all from today's Phase 2 testing session; `signals` has 0 rows. There is no real history to dry-run against yet — Phase 2 only went live today. Proposing instead: run the generation logic once, read-only, against the database **as it stands right now**, and show what it would create tonight. That's a real test of the logic, just not a 90-day retrospective — there's nothing to retrospect over yet. A genuine 90-day dry run becomes possible once the two-week (or longer) trial has produced real activity.

### 1. Buying window editing

Small addition to the school detail page: an "Edit window" toggle on the existing window-inline display, revealing season / start month-day / end month-day / source (`observed` or `stated` — `assumed` is only ever the seed default, never a value a rep chooses) / an optional note. Saves via the same pattern as logging (a small POST). No new migration needed — `buying_windows` already has every column this touches.

### 2. Follow-up generation algorithm

**Window-anchored** (highest priority) — brief already specifies this one concretely: fires when a school is currently inside its decision window and has had no activity (any outcome) in 60+ days, or never. Proposing this fires **once per window occurrence**, not nightly for the whole ~75-day window — dedup by checking whether a window-type follow-up already exists with `created_at` inside the current window's date range, regardless of its status (open, done, or dismissed). A dismissed one doesn't get re-created three days later; a new one only appears next year's window.

I'm proposing **no pre-window lead time** (i.e., it fires at window entry, not two weeks before) — "window opens soon" is something the daily priority list (Phase 4) can surface directly from `buying_windows` by ranking, without needing a `follow_ups` row to exist. Keeping follow-up generation to "the window is actually open" keeps this phase's logic simple and matches the brief's literal wording. Flagging this as a real choice, not an obvious one — if you want a "coming up" nudge before the window opens, that's a small addition here.

**Signal-driven** — fires immediately on a new `signals` row (new principal, new music teacher, PTO officer change), regardless of cadence, per the brief. Dedup problem: `follow_ups` has no column linking back to the `signals` row that caused it, so there's no clean way to check "have I already generated a follow-up for this exact signal." Proposing a small schema addition: `follow_ups.source_signal_id bigint REFERENCES signals(id)`, nullable — makes the dedup check exact (`NOT EXISTS follow_ups WHERE source_signal_id = signal.id`) instead of a fuzzy text/date match. This is the one piece of this proposal that touches the schema; wanted to flag it explicitly rather than fold it in silently.

**Cadence** — the brief gives the behavior (suppressed outside the window, resets only on a real connection — `spoke`, `email_replied`, `meeting_set` — not on an attempt) but not the numbers. Proposing:

- **Base interval: 10 calendar days** since the last connection (or since the first attempt, if there's never been a connection) while the school is in-window.
- **Escalation: 5 calendar days** once 2 or more non-connect outcomes (`no_answer`, `left_voicemail`, `gatekept`, `declined`) have stacked up since the last connection — this is the "raise urgency" behavior the brief asks for, expressed as a shorter interval rather than a bigger badge or number (consistent with Phase 4's "never show a growing count" rule).
- **Dedup: skip entirely if an open (or snoozed) cadence follow-up already exists** for that school+entity. The interval only controls when the *next* one gets created after the current one is resolved — this avoids ever stacking duplicate cadence nudges for the same relationship.

Reasoning on the numbers: the fall window is ~75 days (Apr 1 - Jun 15) and Phase 4 caps the daily list at 12-15 items. A tighter interval than 10 days risks a handful of unreachable schools permanently crowding out everything else on the list; much looser than 10 and a school can go most of the window without a second nudge. Open to being wrong here — this is a guess calibrated on the shape of the window, not on any real usage data yet (there isn't any).

### 3. Suppression / lost schools (brief's open question 4)

No new column needed. Proposing: if the most recent `rep_actions.action_type` for a school (or a specific buying_entity, once actions are entity-scoped — they already are, per Phase 2) is `lost` or `do_not_contact`, suppress all follow-up generation for that school/entity. Reversible the moment a new action gets logged against it — matches the "cheap and reversible" bar without adding a `status` column that could drift out of sync with the activity log itself.

### 4. Dismissal semantics (brief's open question 3)

Proposing dismissal is **per buying_entity, not per school** — consistent with Phase 2's whole redesign around multiple independent entities per school. Dismissing the PTO follow-up shouldn't silence a live booster-club signal at the same school.

### 5. Questions

1. **Signal linkage schema change** — add `follow_ups.source_signal_id` (nullable FK to `signals`) for clean dedup. *(a) yes, small migration — (b) find another way to dedupe without a schema change — (c) your call.*
2. **Cadence numbers** — 10 days base / 5 days after 2+ non-connects, in-window only. *(a) use these — (b) different numbers (say what) — (c) show the dry run first, then decide.*
3. **No pre-window lead time** for window-anchored follow-ups — that signal comes from Phase 4's ranking instead. *(a) agreed — (b) I do want a lead-time nudge here, propose one — (c) your call.*
4. **Lost/do-not-contact suppression** via `rep_actions.action_type`, no new column. *(a) yes — (b) other.*
5. **Dismissal scope** — per buying_entity, not per school. *(a) yes — (b) per school instead — (c) your call.*
