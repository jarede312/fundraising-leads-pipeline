-- Phase 7: a tiered view over contacts needing a human to confirm them, prioritized by
-- how much it matters (the school's Phase 6 score) crossed with how uncertain the
-- contact currently is. Scoped to `contacts` specifically - the 65 unconfirmed
-- school_org_links from Phase 4 are a separate, smaller one-time cleanup task with a
-- different remediation action (confirm a name match, not verify a phone/email), not
-- folded in here.
--
-- Tier 1: a high-value school (score >= 7) with a low/unknown-confidence email - call
--         these first, the payoff for getting it right is highest.
-- Tier 2: everything else that's either uncertain (low/unknown confidence) or has never
--         been verified by any method at all, regardless of score.
-- Tier 3: already-confident contacts, just due for a periodic re-check.
CREATE VIEW v_export_verification_queue AS
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
LEFT JOIN scores sc ON sc.school_id = s.id AND sc.score_version = 'v1'
WHERE c.status = 'active'
ORDER BY tier, sc.score DESC NULLS LAST;
