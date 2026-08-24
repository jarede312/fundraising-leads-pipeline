-- A running, append-only record of every human-initiated write on the site (not page
-- loads, not the nightly/self-heal regen) - for a full activity-history page next to
-- the Guide. rep_actions/opportunities/follow_ups each hold current or call-specific
-- state and get corrected/deleted in place; this table is never edited, only appended
-- to, so it can answer "what actually happened, in order" even for things that don't
-- otherwise keep history (a contact's email getting edited, a decision window getting
-- corrected).
CREATE TABLE audit_log (
    id          bigserial PRIMARY KEY,
    org_id      bigint NOT NULL REFERENCES orgs(id),
    user_id     bigint NOT NULL REFERENCES users(id),
    occurred_at timestamptz NOT NULL DEFAULT now(),
    action      text NOT NULL,          -- short label, e.g. 'Logged activity', 'Edited contact'
    school_id   bigint REFERENCES schools(id) ON DELETE SET NULL,
    contact_id  bigint REFERENCES contacts(id) ON DELETE SET NULL,
    detail      text                    -- human-readable specifics
);

CREATE INDEX ON audit_log (occurred_at DESC);
CREATE INDEX ON audit_log (school_id);
