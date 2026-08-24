"""
Phase 6: a fundraising-potential score per open school, 0-10, stored in `scores` with a
component breakdown and a short auto-generated rationale. Computed once per run, never
at read time - no model call, since the formula is fully deterministic (`scores.model`
stays NULL).

v2 changes (WEBAPP_PLAN.md Checkpoint 0, 2026-08-23), both real problems, not preferences:

1. Contactability, per WEBAPP_BRIEF Phase 5: "a large school with no reachable contact
   is worth less than a mid-size school with a verified PTO president's email." v1 had
   no such signal - 3 of its top 25 schools had zero contacts of any kind.
2. frl_inverted used raw frl_pct even for CEP/Provision-2 schools, where FRL is a
   formula-driven eligibility artifact (every student counted free-eligible regardless
   of actual household income), not a real income measurement - PLAN.md section 1.3
   flagged this risk before Phase 6 was ever built. All 22 open ND schools sitting at
   exactly 100% FRL turned out to be CEP schools (Fort Yates, Selfridge, Cannon Ball,
   Solen, Warwick...), concentrated in reservation and colony communities, and v1's
   score was quietly treating that artifact as real spending-power data. Fixed the same
   way missing FRL already was: `frl_basis IN ('cep','provision_2')` now defaults to the
   statewide median instead of using the reported number.

Weights (locale dropped entirely in v1 - too soft a signal with no real market evidence
behind it):
    enrollment        0.30   raw dollar potential - more kids, more units sold
    contactability     0.20   NEW - can this school actually be reached remotely
    frl_inverted       0.20   household spending power (higher FRL -> lower expected spend)
    pto_capacity       0.15   proof a PTO can already run and fund a program
    segment            0.15   combined K-12 weighted up - one relationship reaches both
                              the catalog-sale (elementary) and spirit-wear (secondary) markets

PTO capacity is only a real number for schools with an actual 990/990-EZ filing (10 of
557 schools - the 990-N e-Postcard carries no financial data at all). Treating "no
filing" as zero capacity would systematically punish small-town schools whose PTO never
incorporated with the IRS, which has nothing to do with real fundraising capacity - so
"no confirmed link" and "linked but e-Postcard only" both get a neutral 5.0, not 0.
Same logic for missing or CEP/Provision-2 FRL: defaults to the statewide median, not 0.

Contactability tiers, best signal available per school:
    10.0   a contact with email_confidence in ('verified','high')
     6.0   a contact with email_confidence 'medium', or a confirmed IRS-linked PTO/
           booster officer name (school_org_links.confirmed) even with no email
     3.0   a contact exists but only low/unknown/invalid email confidence
     0.0   no contact and no confirmed org link at all

Run: python -m ingest.phase6_scoring
"""
import json
import math

from . import db

SCORE_VERSION = "v2"

SEGMENT_SUBSCORE = {
    "combined": 10.0,
    "elementary": 7.0,
    "high": 7.0,
    "middle": 6.0,
    "other": 3.0,
}

WEIGHTS = {
    "enrollment": 0.30,
    "contactability": 0.20,
    "frl_inverted": 0.20,
    "pto_capacity": 0.15,
    "segment": 0.15,
}

CEP_FRL_BASIS = ("cep", "provision_2")


def percentile_ranks(values_by_id):
    """id -> value (value may be None, skipped) => id -> percentile rank in [0,1]."""
    present = sorted((v, k) for k, v in values_by_id.items() if v is not None)
    n = len(present)
    ranks = {}
    for i, (_, k) in enumerate(present):
        ranks[k] = i / (n - 1) if n > 1 else 0.5
    return ranks


def rationale_for(school_name, subs, weighted):
    parts = sorted(weighted.items(), key=lambda kv: -kv[1])
    strongest = parts[0][0]
    weakest = parts[-1][0]
    label = {
        "enrollment": "enrollment", "pto_capacity": "PTO financial capacity",
        "frl_inverted": "household spending power", "segment": "school segment",
        "contactability": "contactability",
    }
    return (
        f"Driven up most by {label[strongest]} (subscore {subs[strongest]:.1f}/10); "
        f"held back most by {label[weakest]} (subscore {subs[weakest]:.1f}/10)."
    )


def main():
    conn = db.connect()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT s.id, s.name, s.enrollment, s.frl_pct, s.frl_basis, s.segment
        FROM schools s WHERE s.status = 'open'
        """
    )
    schools = cur.fetchall()

    cur.execute(
        """
        SELECT l.school_id, n.total_revenue
        FROM school_org_links l JOIN nonprofit_orgs n ON n.ein = l.ein
        WHERE l.confirmed = true AND n.filing_type IN ('990', '990EZ')
              AND n.total_revenue IS NOT NULL AND n.total_revenue > 0
        """
    )
    pto_revenue = dict(cur.fetchall())  # school_id -> total_revenue (real filings only)

    cur.execute(
        "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY frl_pct) "
        "FROM schools WHERE status='open' AND frl_pct IS NOT NULL "
        "AND frl_basis <> ALL(%s)",
        (list(CEP_FRL_BASIS),),
    )
    frl_median = float(cur.fetchone()[0])

    cur.execute(
        """
        SELECT school_id, max(
            CASE
                WHEN email_confidence IN ('verified','high') THEN 3
                WHEN email_confidence = 'medium' THEN 2
                ELSE 1
            END
        ) AS tier
        FROM contacts GROUP BY school_id
        """
    )
    contact_tier_by_school = dict(cur.fetchall())  # school_id -> 1/2/3, best contact on file

    cur.execute(
        "SELECT DISTINCT school_id FROM school_org_links WHERE confirmed = true"
    )
    schools_with_confirmed_org = {r[0] for r in cur.fetchall()}

    enrollment_by_id = {r[0]: r[2] for r in schools}
    enrollment_ranks = percentile_ranks(enrollment_by_id)

    pto_log_by_id = {sid: math.log(float(rev)) for sid, rev in pto_revenue.items()}
    pto_ranks = percentile_ranks(pto_log_by_id)

    CONTACT_TIER_SUBSCORE = {3: 10.0, 2: 6.0, 1: 3.0}

    rows_to_write = []
    for school_id, name, enrollment, frl_pct, frl_basis, segment in schools:
        if frl_pct is None or frl_basis in CEP_FRL_BASIS:
            frl_pct_f = frl_median
        else:
            frl_pct_f = float(frl_pct)

        tier = contact_tier_by_school.get(school_id)
        email_score = CONTACT_TIER_SUBSCORE.get(tier, 0.0)
        org_score = 6.0 if school_id in schools_with_confirmed_org else 0.0
        contactability = max(email_score, org_score)

        subs = {
            "enrollment": enrollment_ranks.get(school_id, 0.5) * 10,
            "contactability": contactability,
            "pto_capacity": pto_ranks[school_id] * 10 if school_id in pto_ranks else 5.0,
            "frl_inverted": (1 - frl_pct_f / 100) * 10,
            "segment": SEGMENT_SUBSCORE.get(segment, 3.0),
        }
        weighted = {k: subs[k] * WEIGHTS[k] for k in WEIGHTS}
        final_score = round(sum(weighted.values()), 2)
        rationale = rationale_for(name, subs, weighted)
        rows_to_write.append((school_id, final_score, subs, rationale))

    with db.ingest_run(
        conn, "scoring",
        f"Phase 6 fundraising-potential score, {SCORE_VERSION} weights "
        f"(enrollment .30 / contactability .20 / frl_inverted .20 / "
        f"pto_capacity .15 / segment .15)",
        "ND",
    ) as (run_id, counts):
        with conn.cursor() as cur:
            for school_id, score, subs, rationale in rows_to_write:
                counts["in"] += 1
                cur.execute(
                    """
                    INSERT INTO scores (school_id, score_version, model, score, components, rationale, ingest_run_id)
                    VALUES (%s, %s, NULL, %s, %s, %s, %s)
                    """,
                    (school_id, SCORE_VERSION, score,
                     json.dumps({k: round(v, 2) for k, v in subs.items()}),
                     rationale, run_id),
                )
                counts["written"] += cur.rowcount
        conn.commit()

    conn.close()
    print(f"Scored {len(rows_to_write)} schools ({SCORE_VERSION}). "
          f"PTO capacity had real data for {len(pto_revenue)} of them.")


if __name__ == "__main__":
    main()
