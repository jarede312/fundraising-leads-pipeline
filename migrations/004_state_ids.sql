-- Migration 004 — state-issued IDs for joining CCD (NCES) records to the ND DPI directory.
--
-- CCD's ST_LEAID/ST_SCHID and DPI's StateIssuedID are the same underlying ND state ID
-- system in different formats (e.g. CCD 'ND-02002-89543' vs DPI '02-002-8954'), but the
-- DPI code's last segment doesn't uniquely determine which CCD building it is when one
-- physical site holds multiple grade-span buildings (a Jr High and a Sr High sharing base
-- code 8954, distinguished only by a CCD-assigned sequence digit). Storing the real CCD
-- state ID lets Phase 2's loader do a prefix match + grade-span disambiguation instead of
-- guessing the sequence digit.

ALTER TABLE districts ADD COLUMN st_lea_id text;
ALTER TABLE schools ADD COLUMN st_school_id text;

CREATE INDEX ON districts (st_lea_id);
CREATE INDEX ON schools (st_school_id);
