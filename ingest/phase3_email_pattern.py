"""
Phase 3: derive each district's email convention from the contacts already loaded
(Phase 2's DPI directory, 986 real addresses across ~80 districts), store it with an
evidence trail and a confidence tier.

Confidence, per the schema comment on districts.email_pattern_confidence:
    high   = 3+ known addresses consistent with the chosen pattern on its primary domain
    medium = 1-2
    low    = reserved for Phase 3a (site-crawl / sibling-platform inference) - not set here,
             see the checkpoint report for why guessing it now would be unreliable
    unknown = no email evidence at all yet

Run: python -m ingest.phase3_email_pattern
"""
import json
import re
from collections import Counter, defaultdict

from . import db
from .email_pattern import normalize


def strip_trailing_digits(local):
    return re.sub(r"\d+$", "", local)


def has_trailing_digits(local):
    return bool(re.search(r"\d+$", local))


def classify(first, last, local):
    """Return the schema's pattern label if `local` (lowercased, digit-suffix stripped)
    matches a known convention built from `first`/`last`, else None."""
    f, l = normalize(first), normalize(last)
    if not f or not l:
        return None
    local = strip_trailing_digits(local.lower())
    candidates = [
        ("first.last", f"{f}.{l}"),
        ("first_last", f"{f}_{l}"),
        ("firstlast", f"{f}{l}"),  # not in the brief's suggested list but a real observed
                                   # pattern (e.g. "violaslater") - text+CHECK is meant to
                                   # evolve, so adding it here rather than bucketing as custom
        ("lastf", f"{l}{f[0]}"),
        ("flast", f"{f[0]}{l}"),
        ("firstl", f"{f}{l[0]}"),
        ("first", f),
    ]
    for pattern, candidate in candidates:
        if local == candidate:
            return pattern
    return None


def main():
    conn = db.connect()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.district_id, c.email, c.first_name, c.last_name
            FROM contacts c
            JOIN schools s ON s.id = c.school_id
            WHERE c.email IS NOT NULL AND c.first_name IS NOT NULL AND c.last_name IS NOT NULL
              AND s.district_id IS NOT NULL
            """
        )
        rows = cur.fetchall()

    by_district = defaultdict(list)
    for district_id, email, first, last in rows:
        local, _, domain = email.partition("@")
        domain = domain.lower()
        pattern = classify(first, last, local)
        by_district[district_id].append(
            {"email": email, "name": f"{first} {last}", "domain": domain, "pattern": pattern}
        )

    tier_counts = Counter()
    pattern_counts = Counter()

    with conn.cursor() as cur:
        for district_id, evidence in by_district.items():
            domain_counts = Counter(e["domain"] for e in evidence)
            primary_domain, primary_domain_n = domain_counts.most_common(1)[0]
            other_domains = {d: n for d, n in domain_counts.items() if d != primary_domain}

            on_primary = [e for e in evidence if e["domain"] == primary_domain]
            pattern_tally = Counter(e["pattern"] for e in on_primary if e["pattern"])

            if pattern_tally:
                best_pattern, best_n = pattern_tally.most_common(1)[0]
                confidence = "high" if best_n >= 3 else "medium"
            else:
                best_pattern, best_n = "custom", 0
                confidence = "medium" if len(on_primary) >= 1 else "unknown"

            # Classification strips a trailing numeric suffix before comparing (so
            # "flast" still recognizes "jsmith42"), but if that suffix is present on
            # almost every matching address, it's not incidental (a rare name-collision
            # tiebreaker) - it's a required, opaque part of the real address that a
            # name alone can't reconstruct. Surfacing this separately from confidence:
            # confidence measures "does this pattern describe the known addresses",
            # not "can I safely derive a new one", and those are different questions.
            matching = [e for e in on_primary if e["pattern"] == best_pattern]
            suffix_n = sum(1 for e in matching if has_trailing_digits(e["email"].split("@")[0].lower()))
            suffix_rate = (suffix_n / len(matching)) if matching else 0.0
            requires_suffix = suffix_rate >= 0.7 and len(matching) >= 3

            tier_counts[confidence] += 1
            pattern_counts[best_pattern] += 1

            evidence_json = json.dumps(
                {
                    "primary_domain": primary_domain,
                    "other_domains_seen": other_domains or None,
                    "matched_pattern_count": best_n,
                    "total_on_primary_domain": len(on_primary),
                    "requires_suffix": requires_suffix,
                    "suffix_rate_among_matches": round(suffix_rate, 2),
                    "addresses": [
                        {"email": e["email"], "name": e["name"], "matches": e["pattern"] == best_pattern}
                        for e in evidence
                    ],
                }
            )

            cur.execute(
                """
                UPDATE districts SET
                    email_domain = %s,
                    email_pattern = %s,
                    email_pattern_confidence = %s,
                    email_pattern_evidence = %s,
                    email_pattern_set_at = now()
                WHERE id = %s
                """,
                (primary_domain, best_pattern, confidence, evidence_json, district_id),
            )
    conn.commit()
    conn.close()

    print("Districts with pattern evidence:", len(by_district))
    print("Confidence tiers:", dict(tier_counts))
    print("Pattern distribution:", dict(pattern_counts))


if __name__ == "__main__":
    main()
