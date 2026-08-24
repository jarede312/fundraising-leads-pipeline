-- Migration 003 — remove routing/drive-time infrastructure
--
-- This is a remote (phone/email) sales strategy, not in-person visits, so drive time and
-- geographic routing have no role anywhere in the pilot. schema.sql's Section 8 (ROUTING)
-- and territories.base_lat/base_lon existed only to support that. Both tables are still
-- empty (no seed data loaded yet) so this is a clean, reversible removal, not a migration
-- off real data. schema.sql itself is left untouched as the original reference document;
-- this migration is the applied, current state of the actual database.

DROP TABLE IF EXISTS school_clusters;
DROP TABLE IF EXISTS route_clusters;

ALTER TABLE territories DROP COLUMN IF EXISTS base_lat;
ALTER TABLE territories DROP COLUMN IF EXISTS base_lon;
