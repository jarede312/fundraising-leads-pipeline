-- Beta feedback P1 item 6/7 (feedback/2026-09-22_beta_feedback_simulated_rep.md §9): the
-- app could log thirty calls and had no way to say whether any of them turned into a
-- program. rep_actions.action_type already had slots for 'quoted'/'won'/'lost' but no
-- dollar amount and nothing wrote them. This adds a real pipeline, deliberately small -
-- four stages, per (school, buying_entity), matching what the rep asked for rather than
-- a fourteen-stage enterprise model.
--
-- 'contacted' is left implicit (no row) rather than a real stage value: creating a row
-- for every relationship that's ever been called would make the pipeline view just be
-- the follow_ups list again. A row only exists once a rep has judged the relationship
-- worth tracking as a deal (Interested or further).
CREATE TABLE opportunities (
    id                  bigserial PRIMARY KEY,
    org_id              bigint NOT NULL REFERENCES orgs(id),
    school_id           bigint NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
    buying_entity       text NOT NULL
                        CHECK (buying_entity IN (
                            'pto','pta','boosters_band','boosters_choir','boosters_drama',
                            'boosters_athletic','school_admin','unknown'
                        )),
    stage               text NOT NULL DEFAULT 'interested'
                        CHECK (stage IN ('interested','proposal_out','closed_won','closed_lost')),
    amount              numeric(10,2),
    notes               text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    closed_at           timestamptz,
    created_by          bigint REFERENCES users(id),
    CHECK (amount IS NULL OR amount >= 0)
);

CREATE INDEX ON opportunities (school_id, buying_entity);
CREATE INDEX ON opportunities (stage) WHERE stage NOT IN ('closed_won', 'closed_lost');

-- One live deal per (school, entity) at a time - same "one open item per relationship"
-- rule follow_ups already follows. A school can start a fresh opportunity with the same
-- entity again once the previous one closes (renewal business), so this only blocks
-- two *open* rows, not two ever.
CREATE UNIQUE INDEX opportunities_one_open_per_entity
    ON opportunities (school_id, buying_entity)
    WHERE stage NOT IN ('closed_won', 'closed_lost');
