-- Migration 009 — Phase 3 follow-up generation (WEBAPP_PLAN.md, approved 2026-08-23)
--
-- signal-driven follow-ups need an exact way to check "have I already generated a
-- follow-up for this specific signal" rather than a fuzzy text/date match against
-- reason_text. Nullable: only signal-driven follow_ups rows set it.

ALTER TABLE follow_ups ADD COLUMN source_signal_id bigint REFERENCES signals(id);
CREATE INDEX ON follow_ups (source_signal_id);
