# Prospect Engine: Web App Build Brief

Paste as the opening message in Claude Code. Assumes the ND ingest pipeline and `schema.sql` are already in the repo.

---

## GROUND RULES: READ AND FOLLOW LITERALLY

I am one person building this in spare time for a family business. The primary user is my father-in-law, who sells school fundraising programs. **My scarcest resource is attention, and the most expensive failure is you building something correct that I did not need.**

1. **Stop at every CHECKPOINT.** Wait for my answer. Do not proceed on your own judgment even when the next step seems obvious.
2. **Batch questions.** 3 to 8 at a time, numbered, each with your recommended answer and a one-line reason. Format so I can reply "1a, 2b, 3 your call, 4 skip."
3. **Ask when the answer changes more than 30 minutes of work.** Cheap and reversible: just do it and tell me. Expensive or hard to undo: ask.
4. **Prototype on 3 records before running 500.** Show me output, wait for go.
5. **Say what you are about to build** in one or two sentences before anything over ~20 lines.
6. **Tell me when you think I am wrong.** I want blind spots, caveats, and consequences I have not considered. If a spec here is bad, say so before implementing it.
7. **Flag surprises immediately** rather than coding around them.

---

## SCOPE CONSTRAINTS

**This is a remote sales motion.** No in-person visits, ever. Channels are phone, email, video call, and physical mail. Consequences:

- Delete or ignore `route_clusters` and `school_clusters`
- Remove any drive-time component from scoring
- No `in_person` channel value, no maps, no route views, no geographic clustering
- Geography is no longer a scoring input at all

**Desktop only.** Single-user at a desk with keyboard and mouse. No mobile layout, no responsive breakpoints below ~1024px, no touch targets, no offline handling, no PWA. Assume reliable connection.

**Do NOT build** unless I explicitly ask: custom fields, workflow builders, permission matrices, report builders, deal stages with weighted probabilities, email sending or sequencing, a public API, multi-org onboarding, dark mode, or anything national in scope.

---

## STACK

Server-rendered. FastAPI + Jinja + HTMX, or Django. One process, one deploy, no separate frontend build step and no SPA. Plain CSS or a minimal utility layer. Postgres as already configured. Numbered `.sql` files in `migrations/`, no migration framework.

---

## PHASE 0: Schema migration

Write migration `002_crm_layer.sql`.

**Add:**

- `rep_actions.outcome` — text with CHECK in (`no_answer`, `left_voicemail`, `gatekept`, `spoke`, `email_sent`, `email_replied`, `email_bounced`, `meeting_set`, `no_response`)
- `rep_actions.buying_entity` — nullable text with CHECK in (`pto`, `pta`, `boosters_band`, `boosters_choir`, `boosters_drama`, `boosters_athletic`, `school_admin`, `unknown`)
- `follow_ups` — id, school_id, buying_entity, due_date, reason_type (`window`/`signal`/`cadence`/`manual`), reason_text, status (`open`/`done`/`dismissed`/`snoozed`), snoozed_until, created_at, created_by, completed_at
- `buying_windows` — id, school_id nullable, district_id nullable, season (`fall`/`spring`), decision_start (month/day), decision_end, source (`assumed`/`observed`/`stated`), confidence, notes, updated_at
- `daily_priority` — a table regenerated nightly, not a view: school_id, buying_entity, rank, score, reason_text, generated_for_date

**Change:**

- `rep_actions.channel` CHECK becomes (`email`, `phone`, `video`, `mail`, `other`). Drop `in_person`.

**Seed:** every open ND school gets a default `buying_windows` row, season `fall`, decision window roughly April 1 to June 15, source `assumed`. A wrong default that gets corrected beats an empty field nobody fills.

> **CHECKPOINT 0.** Show me the migration before applying. Ask about anything in the enum values that seems wrong for this business.

---

## PHASE 1: Read-only app

Ship this alone and give it to my father-in-law for two weeks before building anything that writes. If he does not open it unprompted, the rest of this is dead and I want to know cheaply.

**Screens:**

1. **School list.** Sortable, filterable table. Columns: school name, district, city, segment, enrollment, score, best-known contact, last activity date. Filters: state, segment, enrollment range, score range, has-PTO-contact, has-verified-email, decision window status.
2. **School detail.** Header with school facts and score plus its rationale text. Contacts grouped by role, each showing email confidence tier, last verified date, and verification method. Linked nonprofit org with gross receipts if matched. Signals timeline. Empty activity section.
3. **Saved views.** Let me name and re-open a filter set. This is the cheapest feature here and the one that gets used most.

**Requirements:**

- Every contact displays its provenance visibly. A derived-unverified email must look different from a phone-verified one at a glance. If the user cannot tell good data from guesses, they will distrust all of it.
- Server-side pagination and sorting. Do not load 600 rows into the browser and sort client-side.
- Keyboard navigation on the list: j/k to move, Enter to open, Esc back.

> **CHECKPOINT 1.** Show me the school list and detail page with real ND data, then stop. Do not start Phase 2 until I have given it to my father-in-law and reported back.

---

## PHASE 2: Activity logging

The whole reminder engine is worthless if the activity log is empty, so logging speed is the entire design goal here.

- Primary action on the school detail page is a single row of buttons: **Called / Left message / Emailed / Video call / Mailed**. One click logs it with the current timestamp. Notes are optional and secondary.
- Outcome is a second click, defaulting to the most common outcome for that channel. Never a required modal.
- **Keyboard shortcuts for everything.** This is a desktop tool used in focused sessions, so a keyboard-driven flow matters more than button size. `c` = called, `e` = emailed, `n` = note, `Enter` = save and advance to next school in the current list.
- Log against a `buying_entity` when known, defaulting to the last one used for that school.
- Activity timeline on the school page, reverse chronological, grouped by entity.

**Also build the work-the-queue view.** Given any filtered list, let me enter a focused mode that shows one school at a time with its contacts, phone numbers, last activity, and the logging buttons, with a next/previous control. This is how the tool will actually get used: sessions of thirty calls, not one-off lookups.

> **CHECKPOINT 2.** Build the logging buttons and timeline first. Show me. Ask before building the queue view whether the interaction model I described is what I meant.

---

## PHASE 3: Buying windows and follow-ups

**Buying window editing.** On the school page, let me set or correct the decision window and flip source from `assumed` to `observed` or `stated`. Show current window status prominently: "Decision window opens in 6 weeks" or "In window now, closes June 15."

**Follow-up generation.** A nightly job creates `follow_ups` rows from three sources, in this priority order:

1. **Window-anchored.** School enters its decision window and has no activity in the last 60 days. Highest priority.
2. **Signal-driven.** A new row in `signals` for new principal, new music teacher, or PTO officer change. Fires immediately regardless of cadence.
3. **Cadence.** Elapsed time since last *connection*. **Suppress entirely when the school is outside its decision window.** A cadence reminder firing in October, when nobody can buy, teaches the user to ignore reminders.

**Critical: cadence resets on connection, not on attempt.** Three voicemails is not three touches. An outcome of `no_answer`, `left_voicemail`, or `gatekept` should *raise* urgency, not reset the clock. Outcomes of `spoke`, `email_replied`, or `meeting_set` reset it.

> **CHECKPOINT 3.** Propose the exact cadence intervals and the window-anchored lead time with your reasoning before implementing. Show me a dry run listing what would have fired over the past 90 days against real data.

---

## PHASE 4: Daily priority list

The home screen. Regenerated nightly into `daily_priority`.

**Hard design rules, these matter more than the ranking logic:**

- **Never display an overdue count.** No red badge with a growing number.
- **Show a bounded list.** Today's 12 to 15, that is all. Not a queue.
- Items not worked roll forward silently and re-rank. Nothing is ever labeled "late." It just competes for a slot tomorrow.
- The list is **recomputed** each night, never **accumulated** from unfinished tasks.
- Every row carries a one-line reason: "Decision window opens in 3 weeks, last spoke in November." Without the why, the list is noise.

Include a "Show more" that reveals the next 15, and a dismiss action that suppresses a school for a chosen period.

> **CHECKPOINT 4.** Propose the ranking formula and defend it. Show me a generated list for a real date so I can judge whether it matches what my father-in-law would actually do that morning.

---

## PHASE 5: Rescoring

The `scores` model in the ingest pipeline included a drive-time component. That component is now dead. Rebalance the remaining inputs and bump `score_version`.

Remaining inputs: enrollment, PTO gross receipts from the IRS layer, free/reduced lunch percentage, segment (combined K-12 weighted up, since one relationship reaches multiple buying entities), contactability (does this school have a verified email or a known PTO officer at all).

**Contactability is a new input and it matters more in a remote motion than it would in a field motion.** A large school with no reachable contact is worth less than a mid-size school with a verified PTO president's email.

> **CHECKPOINT 5.** Propose the new weighting with reasoning. Show me the top 25 and bottom 25 before regenerating everything.

---

## Open questions to raise when relevant

1. Should a school with three buying entities appear three times in the daily list, or once with the highest-priority entity surfaced?
2. What is the right cadence interval inside a decision window versus outside it?
3. Should dismissing a follow-up suppress the school entirely or just that entity?
4. Do I need a lost/dead status that removes a school from generation permanently?
5. Should email deliverability risk gate anything? Sending to derived-unverified addresses at volume risks the sender domain.

---

## Definition of done

Desktop web app, single user, running against the ND database. School list with saved views, school detail with nested contacts and activity, one-click logging with keyboard shortcuts, a queue mode, a nightly priority list with reasons, and follow-up generation that respects decision windows. No email sending. No mobile. No maps.
