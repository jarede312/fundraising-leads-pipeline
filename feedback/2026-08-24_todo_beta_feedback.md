# To-Do: Address Beta Feedback (2026-09-22)

Derived from `2026-09-22_beta_feedback_simulated_rep.md`. Excludes items already fixed in code
(keyboard shortcuts, snooze black hole — see note at bottom) and the district page request.

## Activity History (2026-08-24, direct user request, not from the feedback doc)

- [x] A "Total Activity History" page/nav link next to Guide: a running log of every
      human-initiated write on the site (not page loads, not the self-heal regen).
      *Done: new append-only `audit_log` table (`migrations/013_audit_log.sql`), written to by
      all nine mutating endpoints (log/correct/delete an activity, add/edit a contact, pipeline
      stage changes, decision-window edits, Today dismissals) via `queries.log_audit`. New
      `/activity-history` page, paginated, nav link next to Guide. Verified live: all nine write
      paths produce a correctly human-readable, correctly school/contact-linked entry, in the
      right order.*

## P0 — Trust bugs (days, not weeks)

- [x] **Fix inverted confidence labels** (§5). Relabel by *source*, not internal confidence
      tier: "State directory," "Found on school site," "Pattern guess — unverified," "Confirmed
      by me." Currently 986 state-directory addresses show as amber "Derived" while 86 guessed
      addresses show as green "High confidence" — reps are avoiding the best data in the system.
      `webapp/templates/macros.html` (`conf_badge` macro) is the place to start.
      *Done: badge now derives from `email_source`/`last_verified_method` (State directory /
      Found on school site / Added by you / Pattern guess — unverified / Invalid), wired through
      `queries.py` and both template call sites. Guide glossary updated to match. Verified live
      against school 2 (state-directory) and school 4 (pattern-guess).*
- [x] **Add undo/delete on a logged action** (§4.4). No way to remove a mis-logged call; a bad
      entry permanently resets that school's cadence clock and suppresses it from Today.
      *Done: `DELETE /actions/{action_id}` + `queries.delete_action`, "Delete" control on each
      activity row (`hx-confirm`). Cadence/last-activity recompute live from `rep_actions`, so no
      separate repair logic was needed. Verified end-to-end (log → delete → gone from DB), plus
      404 on double-delete and on a mismatched `school_id`.*
- [x] **Correct the Guide's "Done for now" wording** (§4.3). Guide currently says dismissal
      "clear[s] it permanently (until a new trigger fires)" — doesn't clearly explain that *Done
      for now* reappears on the ~10-day cadence timer while *Not interested* is truly permanent.
      `webapp/templates/guide.html`.
      *Done: wording now spells out that Done for now reappears on the cadence timer and only
      Not interested is permanent.*
- [x] **Build or remove the Signals feature** (§4.6). The Guide and every school page advertise
      signals, and `ingest/phase7_sweep.py` can generate them, but nothing schedules it to run —
      the table is effectively always empty in normal operation. Either wire it into the daily/
      periodic job so it actually fires, or pull the Signals section until it does.
      *Done (honesty fix, not automation): wiring `phase7_sweep.py` into the daily path would run
      real LLM-cost site crawls on every load, which is a bigger/riskier change than a P0 "days"
      fix and overlaps the P2 "automate the new-principal detector" item. Instead corrected the
      Guide, glossary, and the school-page Signals card to say plainly that detection isn't on a
      running schedule yet, so an empty list means "not checked," not "nothing changed." Full
      automation stays tracked under P2 item 13.*

## P1 — Build before rollout (weeks)

**Deployed 2026-08-24:** commit `1e6fd4e` pushed to `origin/master` (Render auto-deploys from
there); `migrations/011_opportunities.sql` applied to the production database beforehand, so the
new `opportunities` table existed before the code that queries it went live. Same commit also
carries the P0 fixes above, which had been sitting local-only until this push.

- [x] **Record a sale** (§9 item 1). No button anywhere writes "quoted / won / lost" or a dollar
      amount, even though the schema has slots for it. Without this there's no closed loop.
      *Done, bundled with the pipeline view below (user chose "both" over amount-only) — see
      `migrations/011_opportunities.sql`, `queries.upsert_opportunity`, and
      `POST /schools/{id}/opportunities` in `main.py`. Marking Won/Lost also writes a matching
      `rep_actions` row (action_type `won`/`lost`, already in the schema's CHECK but unused until
      now) so the Activity timeline and the pipeline never disagree. Verified live: full
      interested → proposal_out → closed_won($1,500) lifecycle, confirmed in the DB and reflected
      on `/pipeline`'s won-by-segment table.*
- [x] **Basic pipeline view** (§9 item 2). Four stages would do: Contacted → Interested →
      Proposal Out → Closed.
      *Done: a Pipeline card on each school's page (one row per buying entity ever contacted or
      tracked), plus a new `/pipeline` nav page listing every open deal territory-wide. "Contacted"
      is left implicit (no row) rather than a real stage - see the migration's header comment for
      why. Guide updated with a new Pipeline section + glossary entries.*
- [x] **Back-date an activity** (§4.5). Every logged action stamps the click time; add an
      editable date/time field defaulted to now.
      *Done: collapsible "Logged just now - back-date?" field on every logging control
      (`macros.html`), pre-fills to the current moment when opened so a rep only has to nudge it
      back. Server rejects a future timestamp. Verified live: a call logged with an explicit past
      date stored and displayed with that date, not click-time; future dates correctly 400.*
- [ ] **Real users, login, ownership/territory model** (§10). One placeholder account today;
      two reps calling the same principal is a real risk the moment a second person opens it.
      **Deferred — explicit user decision (2026-08-24):** more reps are much further out; build
      for it later without a rewrite, but keep the placeholder rep for now. Nothing in this pass
      hardcoded around the single-user assumption any more than the codebase already did (every
      new write still goes through the existing `get_default_org_user()` placeholder and carries
      real `org_id`/`user_id`/`buying_entity` columns), so adding real auth later is additive, not
      a rewrite. Revisit when a second rep is actually imminent.
- [x] **Basic activity reporting** (§10). Dials/week, contact rate, conversion by segment, which
      reps are working their lists — currently unanswerable for anyone.
      *Done, folded into `/pipeline` rather than a separate page: last-7-days calls/contact
      rate/attempts/schools-touched, plus all-time won/lost totals by segment. "Which reps are
      working their lists" is explicitly out of scope until real per-rep users exist (see above).*
- [x] **Show tiers, not decimals** (§6, partial). Two-decimal score reads as false precision on a
      number that barely discriminates in the middle of its range.
      *Done: Hot/Warm/Cool tier is now the primary display everywhere the score appears (Today,
      school page, queue, All Schools), with the raw number demoted to a small caption. Cutoffs
      (7.3 / 4.6) taken directly from the rep's own measured p90/p10 on the live score
      distribution.*
      **Not done — the weight-rebalancing half of §6/§11 item 10** (de-emphasize enrollment,
      weight in named PTO/booster contact and prior-fundraiser 990 history, same-district warmth).
      That's a live change to which schools every rep sees first, requires an ingest-side change
      to `ingest/phase6_scoring.py` and re-running scoring across all 557 schools, and I have no
      way to backtest a new weighting against real outcomes yet (no wins existed until this
      session). Flagging for a deliberate follow-up rather than guessing at new weights.
- [ ] **Audit trail across users** (§10). Every action currently stamps to the same placeholder
      user — depends on the login work above. **Deferred along with it**, same 2026-08-24 decision.
- [ ] **Data-loss/backup story** (§10). Confirm and document that the database is actually
      backed up.
      **Checked, not fixed:** `render.yaml`'s `fundraising-db` has no `plan:` set, which on Render
      means the free Postgres tier - no automatic backups, and the database is deleted after 30
      days regardless of activity. Fixing this means picking a paid Render Postgres plan (billing
      decision), so it isn't something to change unasked. Recommend: add a `plan:` to the
      `fundraising-db` database in `render.yaml` (check Render's current Postgres plan names/
      pricing before picking one) before any other rep's month of call notes goes into it.

## P2 — Next quarter

- [ ] **Surface IRS principal officers as contacts** (§5.1, §11). 143 nonprofit orgs already
      have a named principal officer sitting unused in the IRS layer — turning those into
      contact records (even name-only) would multiply PTO coverage for near-zero new data
      acquisition.
- [ ] **Seasonal awareness in Today** (§7). Fall-fundraiser decisions get made April–June,
      spring decisions in Oct–Nov; the tool currently hands out the same list year-round.
      Decision windows exist in the schema but were disabled as meaningless placeholders —
      make them real per-segment windows instead of one shared placeholder.
- [ ] **"Competitive takeaway" saved filter** (§11). Schools whose PTO files a 990/990-EZ with
      real revenue that we've never sold — 33 schools today, one-click saved filter.
- [ ] **Automate the new-principal detector** (§11, §4.6). `ingest/phase7_sweep.py` already
      diffs directory names and can write signal rows; schedule it (e.g. annual summer
      re-scrape) instead of leaving it as a manual, un-run script.
- [ ] **Saved views** (§11). Filters currently live in the URL as a happy accident (bookmarks
      only); make "save this view" a real one-click feature.
- [ ] **Email address validation pass** (§5.2). 986 unvalidated addresses — validate before any
      email-sending feature ships, to protect the sending domain.
- [ ] **"Verify this contact" one-click flow** (§11). Let a rep confirm a name/number as a
      by-product of calling, cheaply improving data quality over time.
- [ ] **Referral/relationship field** (§11). Nowhere to record "Jennifer moved from Roosevelt to
      Lincoln."
- [ ] **Competitor field** (§9 item 4). Currently only exists as unsearchable free-text in notes.
- [ ] **Account history across seasons** (§9 item 3). No memory of prior business with a school —
      whether we sold them before, what they bought, who ran it.
- [ ] **Email templates (copy-to-clipboard)** (§9 item 5). Merge school/contact name into a
      reusable intro template; not a sequencer, no actual sending (see validation item above).
- [ ] **Call script / talk track panel** (§9 item 6). Small collapsible opener + objection
      responses next to the dial button, mainly to cut new-rep ramp time.
- [ ] **Standalone tasks/reminders not tied to a school** (§9 item 7).
- [ ] **Scale check beyond one state** (§10, §11). Current pages re-query/re-count on every
      request — fine at 557 schools, worth load-testing before expanding past ND.

## Smaller UI/usability fixes (§8)

**Not deployed yet** — built and verified locally 2026-08-24, not yet pushed/migrated to
production (see the pipeline rework note below; wants to go out together).

- [x] Today reason text should be larger than (or match) the school name, not smaller.
      *Done: `.priority-reason` bumped from 13px muted to 15px/600-weight, at least as prominent
      as the school name now.*
- [x] Make dismiss/snooze inline buttons instead of hidden behind a disclosure triangle.
      *Done: removed the `<details>`/`<summary>` wrapper in `_priority_list.html`; the four
      dismiss buttons render directly under the reason line.*
- [x] Collapse contact cards below the top two roles by default on schools with many contacts.
      *Done: role-group rendering factored into a `role_group` macro, top 2 roles (by
      ROLE_PRIORITY) shown expanded, the rest collapsed under one "+N more contact groups"
      disclosure.*
- [ ] Replace per-contact logging button clusters with a single bottom-pinned logging bar plus a
      "who did you talk to?" selector.
      **Not attempted.** The collapse-above mitigates the actual complaint (visual clutter on
      schools with many contacts) more cheaply. A full redesign risks the keyboard-shortcut
      workflow (shortcuts currently target specific per-card buttons by `data-scope`) - the
      rep called that the tool's best feature. Revisit deliberately if the collapse isn't enough.
- [x] Add a global search box in the top nav (currently only exists on All Schools).
      *Done: plain (non-htmx) search form in `base.html`'s nav, GETs to `/schools?q=...` from
      any page.*
- [x] Fix queue-mode "Next" navigating by list position instead of by school, which can skip or
      repeat a school when the sort reorders after a logged action.
      *Done: Next/Previous now pass the currently-viewed school's id as an anchor
      (`queries.school_position`); the server resolves that school's *current* position fresh on
      every click instead of trusting a position number computed before the action that just
      reordered the list. Falls back to the old position if the anchor school drops out of the
      filtered set entirely.*
- [x] Add CSV print/export for call sheets, without requiring a script.
      *Done: `GET /schools/export.csv`, same filters/sort as the current All Schools view, "Export
      CSV" button next to "Work this list".*
- [x] Show a visible "Directory data as of [date]" freshness indicator.
      *Done: latest successful `state_doe` ingest date shown on the All Schools header, from
      `ingest_runs`.*

---

## Pipeline rework (2026-08-24, user-reported after initial P1 build)

The Pipeline feature shipped in the P1 pass keyed an opportunity by `buying_entity` alone, which
put every non-PTO/booster contact - principal, music teacher, athletic director, superintendent,
office manager - into one 'school_admin' bucket (that's `queries.buying_entity_for_contact`'s
existing behavior, not something this pass introduced, but Pipeline made the coarseness
consequential for the first time). User feedback: a music-teacher-driven deal showed up
mislabeled "School Admin" with no way to tell who it was actually with, and only one deal could
ever be tracked per school across all of those roles combined.

- [x] Tie a pipeline item to the specific contact it's actually with, not just the coarse
      buying-entity bucket.
- [x] Support multiple concurrent pipeline items per school (one per contact, e.g. a principal
      deal and a music-teacher deal open at the same time).
- [x] Show a date and the contact's name on each pipeline item.
- [x] Move Decision Window to the bottom of the school page (and queue mode, which was missing
      the Pipeline card entirely until this pass).

*Done: `migrations/012_opportunities_per_contact.sql` adds `opportunities.contact_id` and
replaces the single unique index with two - one open deal per named contact, one open deal per
buying_entity when no contact is attached (the General/Front Office card's entity picker, for a
relationship not yet tied to a name). Each contact card gained a "+ Track as opportunity" starter
(hidden once that contact has an open deal, and showing an inline stage badge once tracked); the
Pipeline card now lists every tracked relationship with the contact's name + role, stage, amount,
and start date. Verified live: two concurrent opportunities on one school (principal + music
teacher), correctly independent through to Won: one closed at $2,200 while the other stayed at
Interested untouched; the Activity timeline entry for the close is now attributed to the specific
contact by name, which it never was before. Applied to local dev DB only so far - not yet
migrated/pushed to production.*

---

**Already fixed, excluded above:**
- Keyboard shortcuts not firing (§4.1) — `webapp/static/app.js` now targets the real
  `.log-btn[data-shortcut]` / `#notes-office` elements instead of the nonexistent
  `.primary-log` / `#notes-default`.
- Snooze never returning (§4.2) — `reopen_due_snoozes()` is now called from the daily self-heal
  path in `webapp/main.py` before follow-ups regenerate.

**Excluded per request:** district page / district rollup view (§8, §11).
