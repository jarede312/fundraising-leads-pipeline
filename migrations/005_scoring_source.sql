-- Phase 6 needs an ingest_runs.source value for a computed scoring pass - it's not an
-- external data source like the rest of this CHECK list, but the audit-trail principle
-- (every write traceable to a run) still applies to computed values, not just ingested
-- ones. TEXT+CHECK is meant to evolve; this is that evolution.
ALTER TABLE ingest_runs DROP CONSTRAINT ingest_runs_source_check;
ALTER TABLE ingest_runs ADD CONSTRAINT ingest_runs_source_check
    CHECK (source IN (
        'nces_ccd','nces_pss','nces_edge','state_doe',
        'irs_990','irs_990n','diocese_directory',
        'web_scrape','llm_extract','phone_pass',
        'manual','commercial_list','scoring'
    ));
