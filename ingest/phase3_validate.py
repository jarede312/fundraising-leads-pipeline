"""Checkpoint 3 validation demo: pick 20 known contacts spanning confidence tiers, hide
their real email, run derive_email() against their district's stored pattern, and compare
to the actual address. This is the honest way to show "derivation works" when there are
currently zero named-but-emailless contacts to derive against for real (Phase 2 came in at
100% email coverage) - that changes once Phase 5's site crawl finds name-only staff pages.

Run: python -m ingest.phase3_validate
"""
from . import db
from .email_pattern import derive_email


def main():
    conn = db.connect()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT d.name, d.email_pattern, d.email_pattern_confidence, d.email_domain,
                   c.first_name, c.last_name, c.email
            FROM contacts c
            JOIN schools s ON s.id = c.school_id
            JOIN districts d ON d.id = s.district_id
            WHERE c.email IS NOT NULL AND d.email_pattern IS NOT NULL
            ORDER BY (d.email_pattern_confidence = 'high') DESC, random()
            LIMIT 20
            """
        )
        rows = cur.fetchall()
    conn.close()

    correct = 0
    print(f"{'district':<22} {'pattern':<11} {'tier':<7} {'name':<22} {'actual':<38} {'derived':<38} match")
    for dname, pattern, tier, domain, first, last, actual in rows:
        derived = derive_email(first, last, pattern, domain)
        ok = derived is not None and derived.lower() == actual.lower()
        correct += ok
        print(f"{dname[:22]:<22} {pattern:<11} {tier:<7} {f'{first} {last}'[:22]:<22} {actual[:38]:<38} {(derived or ''):<38} {'OK' if ok else 'MISS'}")
    print(f"\n{correct}/{len(rows)} derived addresses match the real one on file.")


if __name__ == "__main__":
    main()
