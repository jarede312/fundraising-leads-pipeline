# Prospect Engine Web App — Build Plan

Status: pre-Phase-0. Nothing built yet. This document is the plan only, per WEBAPP_BRIEF.md's own rules.

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
