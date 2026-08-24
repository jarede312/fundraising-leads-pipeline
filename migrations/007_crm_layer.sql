-- Migration 006 — CRM layer (WEBAPP_BRIEF Phase 0)
--
-- rep_actions.channel: 'in_person' was already meaningless (this is a remote-only sales
-- motion, migration 003 already dropped the routing tables that depended on it) but the
-- CHECK itself was never updated. Replaced with 'video' per the brief.
--
-- outcome adds 'declined' beyond the brief's list: without it, a firm no and a dead line
-- both land in 'no_response', and they should behave differently for follow-up
-- suppression (WEBAPP_PLAN.md Checkpoint 0, Q2).
--
-- Seed org/user are placeholders (WEBAPP_PLAN.md Checkpoint 0, Q3) — rename before this
-- goes in front of anyone. Needed because rep_actions.org_id/user_id are NOT NULL and
-- both tables are currently empty; nothing else can log an action without this.
--
-- buying_windows.decision_start/decision_end are stored as (month, day) smallint pairs
-- rather than a real date, since a decision window recurs every year with no fixed year
-- attached to it.

ALTER TABLE rep_actions DROP CONSTRAINT rep_actions_channel_check;
ALTER TABLE rep_actions ADD CONSTRAINT rep_actions_channel_check
    CHECK (channel IN ('email','phone','video','mail','other'));

ALTER TABLE rep_actions ADD COLUMN outcome text
    CHECK (outcome IN (
        'no_answer','left_voicemail','gatekept','spoke','declined',
        'email_sent','email_replied','email_bounced',
        'meeting_set','no_response'
    ));

ALTER TABLE rep_actions ADD COLUMN buying_entity text
    CHECK (buying_entity IN (
        'pto','pta','boosters_band','boosters_choir','boosters_drama',
        'boosters_athletic','school_admin','unknown'
    ));

CREATE TABLE follow_ups (
    id              bigserial PRIMARY KEY,
    school_id       bigint NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
    buying_entity   text
                    CHECK (buying_entity IN (
                        'pto','pta','boosters_band','boosters_choir','boosters_drama',
                        'boosters_athletic','school_admin','unknown'
                    )),
    due_date        date NOT NULL,
    reason_type     text NOT NULL
                    CHECK (reason_type IN ('window','signal','cadence','manual')),
    reason_text     text NOT NULL,
    status          text NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open','done','dismissed','snoozed')),
    snoozed_until   date,
    created_at      timestamptz NOT NULL DEFAULT now(),
    created_by      bigint REFERENCES users(id),
    completed_at    timestamptz
);

CREATE INDEX ON follow_ups (school_id, status);
CREATE INDEX ON follow_ups (due_date) WHERE status = 'open';

CREATE TABLE buying_windows (
    id                  bigserial PRIMARY KEY,
    school_id           bigint REFERENCES schools(id) ON DELETE CASCADE,
    district_id         bigint REFERENCES districts(id) ON DELETE CASCADE,
    season              text NOT NULL CHECK (season IN ('fall','spring')),
    decision_start_month smallint NOT NULL CHECK (decision_start_month BETWEEN 1 AND 12),
    decision_start_day   smallint NOT NULL CHECK (decision_start_day BETWEEN 1 AND 31),
    decision_end_month   smallint NOT NULL CHECK (decision_end_month BETWEEN 1 AND 12),
    decision_end_day     smallint NOT NULL CHECK (decision_end_day BETWEEN 1 AND 31),
    source              text NOT NULL DEFAULT 'assumed'
                        CHECK (source IN ('assumed','observed','stated')),
    confidence          text NOT NULL DEFAULT 'low'
                        CHECK (confidence IN ('low','medium','high')),
    notes               text,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (school_id IS NOT NULL OR district_id IS NOT NULL)
);

CREATE INDEX ON buying_windows (school_id);
CREATE INDEX ON buying_windows (district_id);

-- Regenerated nightly, not a view — the brief is explicit this should be a real table
-- so a rank/reason can be snapshotted for the date it was shown, not recomputed live.
CREATE TABLE daily_priority (
    id                  bigserial PRIMARY KEY,
    school_id           bigint NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
    buying_entity        text
                        CHECK (buying_entity IN (
                            'pto','pta','boosters_band','boosters_choir','boosters_drama',
                            'boosters_athletic','school_admin','unknown'
                        )),
    rank                integer NOT NULL,
    score               numeric(5,2) NOT NULL,
    reason_text         text NOT NULL,
    generated_for_date  date NOT NULL
);

CREATE INDEX ON daily_priority (generated_for_date, rank);

-- Seed org/user — placeholders, see header note.
INSERT INTO orgs (name) VALUES ('Placeholder Org');
INSERT INTO users (org_id, display_name, role)
    SELECT id, 'Placeholder Rep', 'rep' FROM orgs WHERE name = 'Placeholder Org';

-- Every open school gets a default fall window. A wrong default that gets corrected
-- beats an empty field nobody fills (brief's own words).
INSERT INTO buying_windows (school_id, season, decision_start_month, decision_start_day,
                             decision_end_month, decision_end_day, source, confidence)
SELECT id, 'fall', 4, 1, 6, 15, 'assumed', 'low'
FROM schools
WHERE status = 'open';
