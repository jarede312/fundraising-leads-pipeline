-- Migration 008 — v_export_verification_queue was hardcoded to score_version = 'v1'.
-- Scoring moved to v2 in migration 007's companion work (contactability + CEP fix), so
-- the view was silently prioritizing verification calls off a superseded score. Points
-- at whichever version is actually most recent per school instead of a hardcoded string,
-- so the next score bump doesn't silently strand this view again.

CREATE OR REPLACE VIEW v_export_verification_queue AS
SELECT
    c.id AS contact_id,
    c.school_id,
    s.name AS school_name,
    s.city,
    c.role,
    c.role_detail,
    c.first_name,
    c.last_name,
    c.email,
    c.email_confidence,
    c.phone,
    c.status,
    c.last_verified_at,
    c.last_verified_method,
    sc.score,
    CASE
        WHEN sc.score >= 7 AND c.email_confidence IN ('unknown', 'low')
            THEN 1
        WHEN c.email_confidence IN ('unknown', 'low') OR c.last_verified_at IS NULL
            THEN 2
        ELSE 3
    END AS tier
FROM contacts c
JOIN schools s ON s.id = c.school_id
LEFT JOIN LATERAL (
    SELECT score FROM scores
    WHERE school_id = s.id
    ORDER BY generated_at DESC
    LIMIT 1
) sc ON true
WHERE c.status = 'active'
ORDER BY tier, sc.score DESC NULLS LAST;
