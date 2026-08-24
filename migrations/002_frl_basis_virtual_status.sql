-- Migration 002 — Checkpoint 1 follow-ups
--
-- 1. frl_basis: CEP/Provision 2 schools report a formula-derived FRL count, not one from
--    household applications. NCES flags this directly (NSLP_STATUS_TEXT) so this is a clean
--    fact to store, not an inference. ~9% of ND open schools affected.
--
-- 2. virtual_status: 29 open ND schools are exclusively-virtual (no physical building).
--    Kept in the universe per your answer to Checkpoint 1 Q5, flagged so Phase 6/7 can
--    special-case them (no PTO/booster program in the traditional sense).
--
-- 3. cube + earthdistance: lightweight contrib extensions (not PostGIS) that give real
--    lat/lon distance in miles via earth_distance(ll_to_earth(...), ll_to_earth(...)).
--    Needed for the "combined site" view below — Checkpoint 1 Q1 clarified that "combined
--    K-12" means a town/district where separate elementary and secondary buildings sit close
--    enough that one relationship reaches both, not one building spanning every grade (which
--    the CCD data shows essentially does not exist in ND).

CREATE EXTENSION IF NOT EXISTS cube;
CREATE EXTENSION IF NOT EXISTS earthdistance;

ALTER TABLE schools ADD COLUMN frl_basis text NOT NULL DEFAULT 'unknown'
    CHECK (frl_basis IN ('applications','cep','provision_2','unknown'));

ALTER TABLE schools ADD COLUMN virtual_status text NOT NULL DEFAULT 'none'
    CHECK (virtual_status IN ('none','supplemental','exclusive'));

-- Per-school "serves an elementary population" flag, distinct from the strict `segment`
-- column. A PK-8 building has an elementary PTO target; a 6-8 middle school does not; the
-- existing `segment` enum can't tell them apart for this purpose. View-computed, no storage.
CREATE OR REPLACE VIEW v_school_reach AS
SELECT
    id AS school_id,
    (grade_low IN ('PK','KG','01','02','03','04','05')) AS serves_elementary,
    (grade_high IN ('09','10','11','12','13')) AS serves_secondary
FROM schools;

-- Districts where an elementary-serving building and a secondary-serving building sit
-- close enough together that one relationship plausibly reaches both an elementary PTO
-- and a secondary booster program (the Checkpoint 1 Q1 concept: "combined K-12" at the
-- town/district level, not one building spanning every grade).
--
-- Threshold: 2 miles, not 10. Checked against real output before settling on this —
-- at 10 miles, Fargo/West Fargo elementaries paired with a same-city high school 7-9
-- miles away, which is a large metro district's ordinary geography, not a small-town
-- single-site pattern; those are organizationally unrelated communities (a district
-- with 26 schools has no single relationship spanning one elementary's PTO and one
-- specific high school's booster club). 2 miles keeps the genuine cases (Belcourt
-- 0.2mi, Watford City/McKenzie Co 0.1-0.4mi) and drops the metro false positives.
-- Distance is still exposed, not hardcoded into a boolean, so this can be retuned
-- without a schema change if it turns out wrong in the other direction.
--
-- Virtual-only schools (virtual_status <> 'none' on either side) are excluded — a
-- virtual academy has no physical site to be "close" to anything.
CREATE OR REPLACE VIEW v_combined_sites AS
SELECT
    e.district_id,
    e.id AS elementary_school_id,
    e.name AS elementary_name,
    h.id AS secondary_school_id,
    h.name AS secondary_name,
    round((earth_distance(ll_to_earth(e.lat, e.lon), ll_to_earth(h.lat, h.lon)) / 1609.34)::numeric, 1)
        AS distance_miles
FROM schools e
JOIN v_school_reach ver ON ver.school_id = e.id AND ver.serves_elementary
JOIN schools h ON h.district_id = e.district_id AND h.id <> e.id
JOIN v_school_reach vhr ON vhr.school_id = h.id AND vhr.serves_secondary
WHERE e.status = 'open' AND h.status = 'open'
  AND e.virtual_status = 'none' AND h.virtual_status = 'none'
  AND e.lat IS NOT NULL AND e.lon IS NOT NULL
  AND h.lat IS NOT NULL AND h.lon IS NOT NULL
  AND earth_distance(ll_to_earth(e.lat, e.lon), ll_to_earth(h.lat, h.lon)) / 1609.34 <= 2;
