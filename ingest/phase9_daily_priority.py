"""Phase 9 (WEBAPP_BRIEF Phase 4): nightly daily-priority regeneration.

Reads every currently-open follow_ups row (each already carries its own reason and
buying_entity, per Phase 3), ranks them, and writes today's `daily_priority` snapshot.

Ranking: reason_type priority first - manual (a rep's own scheduled follow-up always
outranks an automatic nudge) > signal > cadence (window-anchored generation was dropped
2026-08-23, see ingest/phase8_follow_ups.py's docstring) - score second within a tier.
Legible over clever: the brief is explicit that a row without an understandable "why" is
noise, and "it's a manual follow-up, those come first" is a why a rep can actually
reason about.

A school with open follow-ups against more than one buying_entity gets a row per
entity, not one row per school - each is a genuinely separate call to make. Flagged
in WEBAPP_PLAN.md as a real choice (the brief's own open question 1), not an obvious
default.

**Recomputed, not accumulated** (brief's explicit rule): today's rows for
`generated_for_date` are deleted and rewritten every run, never appended to. An open
follow-up nobody worked yesterday simply reappears today, re-ranked - nothing is ever
labeled "late" and there is no growing count anywhere in this table.

Run (dry run, default):
    python -m ingest.phase9_daily_priority
Run for real:
    python -m ingest.phase9_daily_priority --commit
"""
import sys
from datetime import date

from . import db

REASON_TYPE_PRIORITY = {"manual": 0, "window": 1, "signal": 2, "cadence": 3}


def generate(conn, today: date):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT f.id, f.school_id, s.name, f.buying_entity, f.reason_type, f.reason_text,
                   sc.score, f.due_date
            FROM follow_ups f
            JOIN schools s ON s.id = f.school_id AND s.status = 'open'
            LEFT JOIN LATERAL (
                SELECT score FROM scores WHERE school_id = f.school_id
                ORDER BY generated_at DESC LIMIT 1
            ) sc ON true
            WHERE f.status = 'open' AND f.due_date <= %(today)s
            """,
            {"today": today},
        )
        rows = cur.fetchall()

    rows.sort(key=lambda r: (
        REASON_TYPE_PRIORITY.get(r[4], 9),
        -(r[6] if r[6] is not None else -1),
    ))
    return rows  # (follow_up_id, school_id, school_name, buying_entity, reason_type, reason_text, score, due_date)


def commit_daily_priority(conn, rows, today: date, counts: dict | None = None) -> int:
    """Deletes + rewrites today's snapshot. Shared by the CLI (main()) and the webapp's
    self-healing regen - same recomputed-not-accumulated write, two callers."""
    written = 0
    with conn.cursor() as cur:
        cur.execute("DELETE FROM daily_priority WHERE generated_for_date = %s", (today,))
        for rank, (fu_id, sid, name, entity, rtype, reason, score, due_date) in enumerate(rows, start=1):
            if counts is not None:
                counts["in"] += 1
            cur.execute(
                """
                INSERT INTO daily_priority
                    (school_id, buying_entity, rank, score, reason_text, generated_for_date, due_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (sid, entity, rank, score if score is not None else 0, reason, today, due_date),
            )
            written += cur.rowcount
            if counts is not None:
                counts["written"] += cur.rowcount
    return written


def print_report(rows, commit: bool):
    print(f"{'DRY RUN - nothing written. ' if not commit else ''}"
          f"{len(rows)} item(s) for today's priority list "
          f"(top 15 shown, {max(0, len(rows) - 15)} would roll to 'Show more').")
    for i, (fu_id, sid, name, entity, rtype, reason, score, due_date) in enumerate(rows[:30], start=1):
        score_str = f"{score:.2f}" if score is not None else " -- "
        marker = " " if i <= 15 else "*"
        print(f"  {marker}{i:>2}. [{rtype:<7}] {score_str}  {name:<40.40}  {entity:<16}  due {due_date}  {reason}")
    if len(rows) > 30:
        print(f"  ... and {len(rows) - 30} more")


def main():
    commit = "--commit" in sys.argv
    conn = db.connect()
    today = date.today()

    rows = generate(conn, today)
    print_report(rows, commit)

    if not commit:
        return

    with db.ingest_run(
        conn, "manual", "Phase 9 daily priority regeneration", "ND",
    ) as (run_id, counts):
        commit_daily_priority(conn, rows, today, counts)
        conn.commit()
    conn.close()
    print(f"\nCommitted {len(rows)} daily_priority rows for {today}.")


if __name__ == "__main__":
    main()
