-- =============================================================================
-- SCHOOL FUNDRAISING PROSPECT ENGINE
-- Postgres schema, v0.1
--
-- DESIGN PRINCIPLES (read before changing anything)
--
-- 1. LAYERS BY DECAY RATE. Universe data (schools, districts) changes ~1%/yr.
--    Contact data changes 15-25%/yr. Scores are regenerated on demand.
--    These are separate tables on purpose. Do not denormalize them together.
--
-- 2. SHARED UNIVERSE, TENANT-SCOPED ACTIVITY. A principal's name is a public
--    fact and is shared across all tenants. A rep's notes, outreach, and
--    batches are private to their org. Tables carrying org_id are tenant data;
--    tables without it are shared reference data.
--
-- 3. APPEND, DON'T OVERWRITE. Verification history and email events are
--    append-only. The contacts table holds current best-known state; the
--    history tables hold how we got there.
--
-- 4. EVERY FACT CARRIES PROVENANCE. source, ingest_run_id, first_seen,
--    last_verified_at, confidence. A record with no provenance is a guess.
--
-- 5. VERIFICATION METHOD IS A FIRST-CLASS FIELD. Phone verification does not
--    scale nationally (~128k schools x 5 min = ~10,600 hours). So the database
--    will always contain a mix of phone-verified, scrape-derived, and
--    pattern-inferred records. You must be able to tell them apart.
--
-- 6. TEXT + CHECK RATHER THAN ENUMS. Easier to evolve on a solo project.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- fuzzy name matching for IRS joins
-- postgis dropped for the pilot: no routing service planned, haversine is enough for
-- ranking-only drive-time. Revisit only if real routing distances become necessary.


-- =============================================================================
-- SECTION 1: TENANCY
-- =============================================================================

CREATE TABLE orgs (
    id              bigserial PRIMARY KEY,
    name            text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id              bigserial PRIMARY KEY,
    org_id          bigint NOT NULL REFERENCES orgs(id),
    display_name    text NOT NULL,
    email           text UNIQUE,
    role            text NOT NULL DEFAULT 'rep'
                    CHECK (role IN ('rep','manager','admin')),
    active          boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- A territory is a saved filter, not a hardcoded list. Store the rule so it
-- re-evaluates as the universe changes (new schools appear, schools close).
CREATE TABLE territories (
    id              bigserial PRIMARY KEY,
    org_id          bigint NOT NULL REFERENCES orgs(id),
    name            text NOT NULL,
    definition      jsonb NOT NULL,
        -- e.g. {"states":["ND"],"segments":["elementary","combined"]}
        -- or   {"district_ids":[123,456]}
        -- or   {"states":["ND","SD"],"exclude_district_ids":[789]}
    base_lat        double precision,   -- rep's home base, for drive-time scoring
    base_lon        double precision,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE territory_assignments (
    territory_id    bigint NOT NULL REFERENCES territories(id) ON DELETE CASCADE,
    user_id         bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (territory_id, user_id)
);


-- =============================================================================
-- SECTION 2: PROVENANCE
-- Every ingested row points back to the run that produced it.
-- =============================================================================

CREATE TABLE ingest_runs (
    id              bigserial PRIMARY KEY,
    source          text NOT NULL
                    CHECK (source IN (
                        'nces_ccd','nces_pss','nces_edge','state_doe',
                        'irs_990','irs_990n','diocese_directory',
                        'web_scrape','llm_extract','phone_pass',
                        'manual','commercial_list'
                    )),
    source_detail   text,               -- e.g. 'ND DPI 2026-27 directory'
    scope           text,               -- e.g. 'ND', 'national', 'Bismarck 1'
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    records_in      integer,
    records_written integer,
    status          text NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running','ok','partial','failed')),
    cost_usd        numeric(10,4),      -- track LLM/API spend per run
    notes           text
);


-- =============================================================================
-- SECTION 3: UNIVERSE (slow decay, shared across tenants)
-- =============================================================================

-- State-level compliance and source metadata. This table is small and boring
-- and will save you from a legal problem later.
CREATE TABLE states (
    code                        char(2) PRIMARY KEY,
    name                        text NOT NULL,
    doe_directory_url           text,
    doe_directory_format        text,   -- 'csv','xlsx','pdf','html','none'
    directory_license_notes     text,   -- verbatim terms of use
    commercial_use_permitted    text NOT NULL DEFAULT 'unreviewed'
                                CHECK (commercial_use_permitted IN
                                    ('yes','no','restricted','unreviewed')),
    solicitation_restrictions   text,
    license_last_reviewed_at    date,
    license_reviewed_by         text
);

CREATE TABLE districts (
    id                      bigserial PRIMARY KEY,
    nces_lea_id             text UNIQUE,        -- null for private "districts"
    name                    text NOT NULL,
    state_code              char(2) NOT NULL REFERENCES states(code),
    county                  text,
    district_type           text NOT NULL DEFAULT 'public'
                            CHECK (district_type IN
                                ('public','charter_lea','diocese','independent')),
    website_url             text,
    phone                   text,
    enrollment_total        integer,
    school_count            integer,

    -- EMAIL PATTERN. The highest-leverage field in this schema.
    -- Districts are centrally IT-managed with one convention across every
    -- building. Determine once, derive addresses for anyone you have a name for.
    email_domain            text,
    email_pattern           text,   -- 'first.last','flast','lastf','first_last',
                                    -- 'firstl','first','custom'
    email_pattern_confidence text NOT NULL DEFAULT 'unknown'
                            CHECK (email_pattern_confidence IN
                                ('unknown','low','medium','high')),
        -- high   = confirmed by 3+ known addresses in this district
        -- medium = confirmed by 1-2
        -- low    = inferred from a sibling district or shared platform
    email_pattern_evidence  jsonb,  -- the known addresses used to derive it
    email_pattern_set_at    timestamptz,

    -- Deal-killers discovered late are expensive. Capture them early.
    vendor_registration_required boolean,
    solicitation_policy_notes    text,
    policy_last_checked_at       date,

    ingest_run_id           bigint REFERENCES ingest_runs(id),
    first_seen              timestamptz NOT NULL DEFAULT now(),
    last_seen_in_source     timestamptz,
    updated_at              timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ON districts (state_code);
CREATE INDEX ON districts (email_pattern_confidence);

CREATE TABLE schools (
    id                      bigserial PRIMARY KEY,
    nces_school_id          text UNIQUE,    -- null for private schools not in PSS
    pss_id                  text UNIQUE,    -- NCES Private School Universe Survey
    district_id             bigint REFERENCES districts(id),
    name                    text NOT NULL,

    school_type             text NOT NULL
                            CHECK (school_type IN ('public','charter','private')),
    affiliation             text,   -- 'catholic','lutheran','acsi','independent',...
    diocese                 text,   -- for Catholic schools, the routing key

    street                  text,
    city                    text,
    state_code              char(2) NOT NULL REFERENCES states(code),
    zip                     text,
    lat                     double precision,
    lon                     double precision,
    phone                   text,
    website_url             text,

    grade_low               text,   -- 'PK','KG','01'..'12'
    grade_high              text,
    -- Derived, but stored because every query filters on it.
    -- In rural states a large share of buildings are combined K-12, and those
    -- are the highest-value targets: one visit reaches a PTO and a booster club.
    segment                 text
                            CHECK (segment IN
                                ('elementary','middle','high','combined','other')),

    enrollment              integer,
    enrollment_year         text,
    frl_count               integer,
    frl_pct                 numeric(5,2),
    title_i                 boolean,
    locale_code             text,   -- NCES: 11-13 city, 21-23 suburb, 31-33 town,
                                    -- 41-43 rural

    status                  text NOT NULL DEFAULT 'open'
                            CHECK (status IN
                                ('open','closed','consolidated','unknown')),
    closed_detected_at      date,

    ingest_run_id           bigint REFERENCES ingest_runs(id),
    first_seen              timestamptz NOT NULL DEFAULT now(),
    last_seen_in_source     timestamptz,
    updated_at              timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ON schools (state_code, segment);
CREATE INDEX ON schools (district_id);
CREATE INDEX ON schools (enrollment DESC NULLS LAST);
CREATE INDEX ON schools (status);
CREATE INDEX ON schools USING gin (name gin_trgm_ops);


-- =============================================================================
-- SECTION 4: CONTACTS (fast decay, shared across tenants)
-- =============================================================================

CREATE TABLE contacts (
    id                  bigserial PRIMARY KEY,
    school_id           bigint NOT NULL REFERENCES schools(id) ON DELETE CASCADE,

    role                text NOT NULL
                        CHECK (role IN (
                            'principal',
                            'assistant_principal',
                            'office_manager',      -- the real gatekeeper.
                                                   -- longer tenure than the
                                                   -- principal. do not treat
                                                   -- this as a fallback field.
                            'music_teacher',       -- elementary: usually one
                                                   -- person, often shared
                                                   -- across buildings
                            'band_director',       -- secondary only
                            'choir_director',      -- secondary only
                            'drama_director',      -- secondary only
                            'activities_director',
                            'athletic_director',
                            'pto_president',       -- exists in no public dataset.
                            'pto_fundraising_chair',
                            'pto_treasurer',
                            'booster_president',
                            'superintendent',
                            'other'
                        )),
    role_detail         text,   -- e.g. 'K-5 general music, also serves Lincoln'

    first_name          text,
    last_name           text,
    title_text          text,   -- as printed on the source page

    email               text,
    email_source        text NOT NULL DEFAULT 'unknown'
                        CHECK (email_source IN
                            ('found','derived','provided','unknown')),
        -- found   = literally scraped or published
        -- derived = generated from district email_pattern + name
    email_confidence    text NOT NULL DEFAULT 'unknown'
                        CHECK (email_confidence IN
                            ('unknown','low','medium','high','verified','invalid')),
    email_verified_at   timestamptz,

    phone               text,
    phone_ext           text,

    -- Current best-known state. History lives in contact_verifications.
    status              text NOT NULL DEFAULT 'active'
                        CHECK (status IN
                            ('active','suspected_stale','bounced','departed','unknown')),
    confidence          text NOT NULL DEFAULT 'medium'
                        CHECK (confidence IN ('low','medium','high')),

    source_url          text,
    ingest_run_id       bigint REFERENCES ingest_runs(id),
    first_seen          timestamptz NOT NULL DEFAULT now(),
    last_verified_at    timestamptz,
    last_verified_method text
                        CHECK (last_verified_method IN
                            ('scrape','state_directory','phone','email_reply',
                             'auto_reply','referral','manual','commercial_list')),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ON contacts (school_id, role);
CREATE INDEX ON contacts (status);
CREATE INDEX ON contacts (last_verified_at NULLS FIRST);
CREATE INDEX ON contacts (email) WHERE email IS NOT NULL;

-- Append-only. Never update a row here.
CREATE TABLE contact_verifications (
    id              bigserial PRIMARY KEY,
    contact_id      bigint NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    verified_at     timestamptz NOT NULL DEFAULT now(),
    method          text NOT NULL
                    CHECK (method IN
                        ('scrape','state_directory','phone','email_reply',
                         'auto_reply','referral','manual','commercial_list')),
    outcome         text NOT NULL
                    CHECK (outcome IN
                        ('confirmed','changed','departed','unreachable','no_answer')),
    replacement_contact_id bigint REFERENCES contacts(id),
        -- when an auto-reply says "please contact X", link the successor
    verified_by     bigint REFERENCES users(id),
    notes           text
);

CREATE INDEX ON contact_verifications (contact_id, verified_at DESC);


-- =============================================================================
-- SECTION 5: NONPROFIT CAPACITY (IRS data)
-- PTOs and PTAs above the threshold file 990/990-EZ. Below it they file the
-- 990-N e-postcard, which still names a principal officer. All public, all
-- bulk-downloadable, and it REFILES ANNUALLY ON ITS OWN. This is the only
-- self-refreshing contact source in the entire system.
-- =============================================================================

CREATE TABLE nonprofit_orgs (
    id                      bigserial PRIMARY KEY,
    ein                     text NOT NULL,
    fiscal_year             integer NOT NULL,
    name                    text NOT NULL,
    org_type                text
                            CHECK (org_type IN
                                ('pto','pta','booster','foundation','other','unclassified')),
    filing_type             text
                            CHECK (filing_type IN ('990','990EZ','990N','990PF')),
    gross_receipts          numeric(14,2),
    total_revenue           numeric(14,2),
    principal_officer_name  text,
    street                  text,
    city                    text,
    state_code              char(2),
    zip                     text,
    ingest_run_id           bigint REFERENCES ingest_runs(id),
    UNIQUE (ein, fiscal_year)
);

CREATE INDEX ON nonprofit_orgs (state_code);
CREATE INDEX ON nonprofit_orgs USING gin (name gin_trgm_ops);

-- Fuzzy match, so the link needs its own confidence and a human confirmation path.
CREATE TABLE school_org_links (
    id                  bigserial PRIMARY KEY,
    school_id           bigint NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
    ein                 text NOT NULL,
    match_method        text NOT NULL
                        CHECK (match_method IN
                            ('address','name_trgm','name_and_zip','manual')),
    match_score         numeric(4,3),
    confirmed           boolean NOT NULL DEFAULT false,
    confirmed_by        bigint REFERENCES users(id),
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (school_id, ein)
);


-- =============================================================================
-- SECTION 6: SIGNALS
-- Timing beats messaging in this market. A new principal or a new music
-- teacher is the K-12 equivalent of a newly hired PI: no vendor loyalty,
-- no institutional memory, actively making decisions.
-- =============================================================================

CREATE TABLE signals (
    id              bigserial PRIMARY KEY,
    school_id       bigint REFERENCES schools(id) ON DELETE CASCADE,
    district_id     bigint REFERENCES districts(id) ON DELETE CASCADE,
    signal_type     text NOT NULL
                    CHECK (signal_type IN (
                        'new_principal',
                        'new_music_teacher',
                        'new_activities_director',
                        'board_minutes_hire',
                        'pto_officer_change',
                        'fundraiser_detected',      -- found a live campaign page
                        'competitor_vendor_detected',
                        'enrollment_change',
                        'school_closing',
                        'district_consolidation'
                    )),
    detected_at     timestamptz NOT NULL DEFAULT now(),
    effective_date  date,           -- when the change actually takes effect
    source_url      text,
    payload         jsonb,
    ingest_run_id   bigint REFERENCES ingest_runs(id),
    notes           text,
    CHECK (school_id IS NOT NULL OR district_id IS NOT NULL)
);

CREATE INDEX ON signals (school_id, detected_at DESC);
CREATE INDEX ON signals (signal_type, detected_at DESC);


-- =============================================================================
-- SECTION 7: SCORING
-- Generate once at import, store the result, never call the model on page view.
-- Store the rationale text alongside the number: an unexplained score does not
-- get trusted or used.
-- =============================================================================

CREATE TABLE scores (
    id                  bigserial PRIMARY KEY,
    school_id           bigint NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
    territory_id        bigint REFERENCES territories(id),
        -- nullable: some score components (drive time) are territory-relative,
        -- others are absolute. A null territory_id means the absolute score.
    score_version       text NOT NULL,      -- 'v1','v2' - bump when weights change
    model               text,               -- which model wrote the rationale
    score               numeric(5,2) NOT NULL,
    components          jsonb NOT NULL,
        -- {"enrollment":8.5,"pto_revenue":6.0,"frl":4.0,"segment":9.0,
        --  "locale":7.0,"drive_time":3.5}
    rationale           text,
    generated_at        timestamptz NOT NULL DEFAULT now(),
    ingest_run_id       bigint REFERENCES ingest_runs(id)
);

CREATE INDEX ON scores (school_id, score_version, generated_at DESC);
CREATE INDEX ON scores (territory_id, score DESC);


-- =============================================================================
-- SECTION 8: ROUTING
-- 70,700 square miles and 116,000 students. In a state like this, "value per
-- day of travel" is the real metric, not value per school.
-- =============================================================================

CREATE TABLE route_clusters (
    id              bigserial PRIMARY KEY,
    territory_id    bigint NOT NULL REFERENCES territories(id) ON DELETE CASCADE,
    name            text NOT NULL,
    centroid_lat    double precision,
    centroid_lon    double precision,
    drive_minutes_from_base integer,
    school_count    integer,
    total_enrollment integer,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE school_clusters (
    school_id       bigint NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
    cluster_id      bigint NOT NULL REFERENCES route_clusters(id) ON DELETE CASCADE,
    drive_minutes_from_base integer,
    PRIMARY KEY (school_id, cluster_id)
);


-- =============================================================================
-- SECTION 9: REP ACTIVITY (tenant-scoped)
-- =============================================================================

-- Weekly batches so nothing gets buried and generation date stays traceable.
CREATE TABLE prospect_batches (
    id              bigserial PRIMARY KEY,
    org_id          bigint NOT NULL REFERENCES orgs(id),
    territory_id    bigint NOT NULL REFERENCES territories(id),
    label           text NOT NULL,      -- 'Week of 2026-09-07'
    criteria        jsonb NOT NULL,     -- the filter that produced it
    generated_at    timestamptz NOT NULL DEFAULT now(),
    generated_by    bigint REFERENCES users(id)
);

CREATE TABLE batch_members (
    batch_id            bigint NOT NULL REFERENCES prospect_batches(id) ON DELETE CASCADE,
    school_id           bigint NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
    rank                integer,
    score_at_generation numeric(5,2),
    PRIMARY KEY (batch_id, school_id)
);

-- 'contacted' and 'acknowledged' are deliberately distinct. Acknowledged means
-- reviewed and consciously skipped (existing relationship, wrong fit, already
-- committed to a vendor). Without it, reps either spam or silently drop records.
CREATE TABLE rep_actions (
    id              bigserial PRIMARY KEY,
    org_id          bigint NOT NULL REFERENCES orgs(id),
    user_id         bigint NOT NULL REFERENCES users(id),
    school_id       bigint NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
    contact_id      bigint REFERENCES contacts(id),
    batch_id        bigint REFERENCES prospect_batches(id),
    action_type     text NOT NULL
                    CHECK (action_type IN (
                        'contacted','acknowledged','meeting_set','quoted',
                        'won','lost','do_not_contact'
                    )),
    channel         text
                    CHECK (channel IN ('email','phone','in_person','mail','other')),
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    outcome_detail  text,
    notes           text
);

CREATE INDEX ON rep_actions (org_id, school_id, occurred_at DESC);
CREATE INDEX ON rep_actions (user_id, occurred_at DESC);

-- Bounces and auto-replies are free data updates. Wire these to fire a
-- re-verification task rather than silently failing.
CREATE TABLE email_events (
    id              bigserial PRIMARY KEY,
    org_id          bigint NOT NULL REFERENCES orgs(id),
    contact_id      bigint REFERENCES contacts(id) ON DELETE SET NULL,
    email           text NOT NULL,
    event_type      text NOT NULL
                    CHECK (event_type IN (
                        'sent','delivered','open','reply','bounce_hard',
                        'bounce_soft','auto_reply','complaint','unsubscribe'
                    )),
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    parsed_successor_name text,   -- from "I am no longer here, contact X"
    raw             jsonb
);

CREATE INDEX ON email_events (contact_id, occurred_at DESC);
CREATE INDEX ON email_events (event_type, occurred_at DESC);


-- =============================================================================
-- SECTION 10: COMPLIANCE
-- CAN-SPAM does not require opt-in, but it does require honoring opt-outs
-- permanently. Suppression is org-scoped for rep preferences and global for
-- legal requests.
-- =============================================================================

CREATE TABLE suppressions (
    id              bigserial PRIMARY KEY,
    org_id          bigint REFERENCES orgs(id),   -- null = global suppression
    email           text,
    school_id       bigint REFERENCES schools(id),
    district_id     bigint REFERENCES districts(id),
    reason          text NOT NULL
                    CHECK (reason IN (
                        'unsubscribe','complaint','do_not_contact_request',
                        'district_policy','state_restriction','bad_data'
                    )),
    added_at        timestamptz NOT NULL DEFAULT now(),
    added_by        bigint REFERENCES users(id),
    notes           text,
    CHECK (email IS NOT NULL OR school_id IS NOT NULL OR district_id IS NOT NULL)
);

CREATE INDEX ON suppressions (email) WHERE email IS NOT NULL;


-- =============================================================================
-- SECTION 11: CONVENIENCE VIEWS
-- =============================================================================

-- Records due for re-verification, tiered. Tier A/B/C is driven by whether the
-- school has recent rep activity, not by a flat rule. Trying to keep 100% of a
-- national universe fresh is what makes these projects collapse.
CREATE VIEW v_verification_queue AS
SELECT
    c.id AS contact_id,
    c.school_id,
    s.name AS school_name,
    s.state_code,
    c.role,
    c.first_name,
    c.last_name,
    c.status,
    c.last_verified_at,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM rep_actions ra
            WHERE ra.school_id = c.school_id
              AND ra.occurred_at > now() - interval '180 days'
        ) THEN 'A'
        WHEN s.enrollment > 300 THEN 'B'
        ELSE 'C'
    END AS tier,
    CASE
        WHEN c.status IN ('bounced','departed') THEN 0
        WHEN c.last_verified_at IS NULL THEN 1
        ELSE EXTRACT(day FROM now() - c.last_verified_at)::int
    END AS staleness_days
FROM contacts c
JOIN schools s ON s.id = c.school_id
WHERE s.status = 'open';

-- Districts where knowing the email pattern would unlock the most addresses.
-- Work this list top-down; each row solved derives emails for every named
-- staff member in that district.
CREATE VIEW v_email_pattern_gaps AS
SELECT
    d.id AS district_id,
    d.name,
    d.state_code,
    d.email_pattern_confidence,
    count(c.id) FILTER (WHERE c.email IS NULL AND c.last_name IS NOT NULL)
        AS names_without_email,
    count(DISTINCT s.id) AS schools
FROM districts d
JOIN schools s ON s.district_id = d.id AND s.status = 'open'
LEFT JOIN contacts c ON c.school_id = s.id
WHERE d.email_pattern_confidence IN ('unknown','low')
GROUP BY d.id, d.name, d.state_code, d.email_pattern_confidence
ORDER BY names_without_email DESC;
