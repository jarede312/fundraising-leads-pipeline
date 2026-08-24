-- migrations/011 keyed an opportunity by (school, buying_entity) alone, which put
-- every non-PTO/booster contact - principal, music teacher, athletic director,
-- superintendent, office manager - into the same 'school_admin' bucket (see
-- queries.buying_entity_for_contact). That meant only one deal could ever be tracked
-- per school for all of those people combined, and a music-teacher-driven deal showed
-- up mislabeled as "School Admin" with no way to tell who it was actually with.
--
-- Key an opportunity by the specific contact instead, when one exists. Two separate
-- partial unique indexes replace the single one from 011: one open deal per *named
-- contact* (whoever the relationship is really with), and separately one open deal per
-- buying_entity when logged with no specific person attached (the General/Front Office
-- card's entity picker, for a PTO/booster relationship not yet tied to a name).
ALTER TABLE opportunities ADD COLUMN contact_id bigint REFERENCES contacts(id) ON DELETE SET NULL;

DROP INDEX opportunities_one_open_per_entity;

CREATE UNIQUE INDEX opportunities_one_open_per_contact
    ON opportunities (school_id, contact_id)
    WHERE stage NOT IN ('closed_won', 'closed_lost') AND contact_id IS NOT NULL;

CREATE UNIQUE INDEX opportunities_one_open_per_entity_no_contact
    ON opportunities (school_id, buying_entity)
    WHERE stage NOT IN ('closed_won', 'closed_lost') AND contact_id IS NULL;
