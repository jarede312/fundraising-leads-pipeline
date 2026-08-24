"""Phase 8 (WEBAPP_BRIEF Phase 3): nightly follow-up generation.

Two sources, in priority order (as of 2026-08-23 - window-anchored generation was
dropped; see below):

1. signal-driven - a new_principal / new_music_teacher / pto_officer_change signal.
   Deduped exactly via source_signal_id (migration 009) rather than a fuzzy text match.
2. cadence - 10 days since the last real connection (spoke / email_replied /
   meeting_set), tightening to 5 days once 2+ non-connect outcomes have stacked up
   since that connection. An attempt never resets the clock, only a connection does.
   A (school, entity) that's never been contacted at all is always immediately due.
   Deduped by skipping if an open/snoozed follow-up already exists for that pair - the
   interval only governs when the *next* one gets created after the current one
   resolves.

Dropped: a "window-anchored" source used to fire when a school's decision window was
open and it had gone quiet 60+ days. Removed because every school currently shares the
same seeded placeholder window (migrations/007_crm_layer.sql) - "the whole industry is
in-window" made the trigger meaningless in practice. decision windows remain in the
schema/UI as reference info a rep can correct per school; they just no longer drive
Today. Revisit once real per-school window data exists.

Suppressed entirely for a (school, buying_entity) whose most recent action_type is
'lost' or 'do_not_contact' - reversible the moment a new action gets logged.

Entities considered per school: every buying_entity ever used in rep_actions for that
school, plus 'school_admin' always as a baseline candidate (the office is always a
valid target even before any entity-specific contact has been logged).

Run (dry run, default - prints what would be created, writes nothing):
    python -m ingest.phase8_follow_ups
Run for real:
    python -m ingest.phase8_follow_ups --commit
"""
import sys
from datetime import date, timedelta

from . import db

CONNECT_OUTCOMES = ("spoke", "email_replied", "meeting_set")
NON_CONNECT_OUTCOMES = ("no_answer", "left_voicemail", "gatekept", "declined")
SUPPRESS_ACTION_TYPES = ("lost", "do_not_contact")

SIGNAL_TYPES = ("new_principal", "new_music_teacher", "pto_officer_change")
SIGNAL_ENTITY_OVERRIDE = {"pto_officer_change": "pto"}
DEFAULT_SIGNAL_ENTITY = "school_admin"

CADENCE_BASE_DAYS = 10
CADENCE_ESCALATED_DAYS = 5
CADENCE_ESCALATE_AFTER = 2


def generate(conn, today: date):
    """Core generation logic, taking an existing connection/transaction - factored out
    of main() so it can be exercised against a rolled-back transaction for testing,
    independent of CLI/commit/print concerns."""
    to_create = []  # (school_id, buying_entity, reason_type, reason_text, source_signal_id)

    with conn.cursor() as cur:
        cur.execute("SELECT id FROM schools WHERE status = 'open'")
        open_school_ids = [r[0] for r in cur.fetchall()]

        cur.execute(
            """
            SELECT school_id, array_agg(DISTINCT buying_entity) FILTER (WHERE buying_entity IS NOT NULL)
            FROM rep_actions GROUP BY school_id
            """
        )
        entities_by_school = {r[0]: set(r[1] or []) for r in cur.fetchall()}

        def suppressed(school_id, entity):
            cur.execute(
                """
                SELECT action_type FROM rep_actions
                WHERE school_id = %s AND buying_entity = %s
                ORDER BY occurred_at DESC LIMIT 1
                """,
                (school_id, entity),
            )
            row = cur.fetchone()
            return row is not None and row[0] in SUPPRESS_ACTION_TYPES

        # ---- 1. signal-driven ----
        cur.execute(
            f"""
            SELECT sig.id, sig.school_id, sig.district_id, sig.signal_type, sig.detected_at
            FROM signals sig
            WHERE sig.signal_type = ANY(%s)
              AND NOT EXISTS (SELECT 1 FROM follow_ups f WHERE f.source_signal_id = sig.id)
            """,
            (list(SIGNAL_TYPES),),
        )
        for sig_id, sch_id, dist_id, sig_type, detected_at in cur.fetchall():
            entity = SIGNAL_ENTITY_OVERRIDE.get(sig_type, DEFAULT_SIGNAL_ENTITY)
            if sch_id is not None:
                target_school_ids = [sch_id]
            else:
                cur.execute(
                    "SELECT id FROM schools WHERE district_id = %s AND status = 'open'",
                    (dist_id,),
                )
                target_school_ids = [r[0] for r in cur.fetchall()]

            for sid in target_school_ids:
                if suppressed(sid, entity):
                    continue
                label = sig_type.replace("_", " ")
                reason = f"{label.capitalize()} detected {detected_at.date()}"
                to_create.append((sid, entity, "signal", reason, sig_id))

        # ---- 2. cadence ----
        # No longer window-gated (windows dropped as a trigger - see module docstring):
        # every open school is a candidate, all the time. A pair never contacted at all
        # is always immediately due; one that's been attempted but never connected
        # anchors on its first attempt, not a window-open date that no longer exists.
        for school_id in open_school_ids:
            entities = entities_by_school.get(school_id, set()) | {"school_admin"}
            for entity in entities:
                if suppressed(school_id, entity):
                    continue

                # Don't stack a cadence nudge on top of an already-open follow-up for
                # this entity - one open item per relationship, not one per reason,
                # matching Phase 4's bounded-list philosophy.
                cur.execute(
                    """
                    SELECT 1 FROM follow_ups
                    WHERE school_id = %s AND buying_entity = %s
                      AND status IN ('open', 'snoozed')
                    """,
                    (school_id, entity),
                )
                if cur.fetchone():
                    continue

                cur.execute(
                    """
                    SELECT max(occurred_at) FROM rep_actions
                    WHERE school_id = %s AND buying_entity = %s AND outcome = ANY(%s)
                    """,
                    (school_id, entity, list(CONNECT_OUTCOMES)),
                )
                last_connection = cur.fetchone()[0]

                if last_connection is None:
                    cur.execute(
                        """
                        SELECT min(occurred_at) FROM rep_actions
                        WHERE school_id = %s AND buying_entity = %s
                        """,
                        (school_id, entity),
                    )
                    first_attempt = cur.fetchone()[0]
                    if first_attempt is None:
                        to_create.append((school_id, entity, "cadence", "Never contacted", None))
                        continue
                    anchor = first_attempt.date()
                else:
                    anchor = last_connection.date()
                days_since = (today - anchor).days

                cur.execute(
                    """
                    SELECT count(*) FROM rep_actions
                    WHERE school_id = %s AND buying_entity = %s AND outcome = ANY(%s)
                      AND occurred_at::date > %s
                    """,
                    (school_id, entity, list(NON_CONNECT_OUTCOMES), anchor),
                )
                non_connect_count = cur.fetchone()[0]
                interval = (
                    CADENCE_ESCALATED_DAYS if non_connect_count >= CADENCE_ESCALATE_AFTER
                    else CADENCE_BASE_DAYS
                )
                if days_since < interval:
                    continue

                reason = (
                    f"{days_since} days since last connection ({non_connect_count} unanswered attempts since)"
                    if last_connection else
                    f"{days_since} days since first attempt, no connection yet"
                )
                to_create.append((school_id, entity, "cadence", reason, None))

    return to_create


def commit_follow_ups(conn, to_create, today: date, counts: dict | None = None) -> int:
    """Writes the rows generate() proposed. Shared by the CLI (main(), wrapped in its
    own ingest_run) and the webapp's self-healing regen on first Today-page load of the
    day - same insert, two callers."""
    written = 0
    with conn.cursor() as cur:
        for school_id, entity, reason_type, reason_text, source_signal_id in to_create:
            if counts is not None:
                counts["in"] += 1
            cur.execute(
                """
                INSERT INTO follow_ups (school_id, buying_entity, due_date, reason_type,
                                         reason_text, source_signal_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (school_id, entity, today, reason_type, reason_text, source_signal_id),
            )
            written += cur.rowcount
            if counts is not None:
                counts["written"] += cur.rowcount
    return written


def print_report(to_create, commit: bool):
    print(f"{'DRY RUN - nothing written. ' if not commit else ''}"
          f"{len(to_create)} follow-up(s) would be created.")
    by_reason = {}
    for s, e, rt, reason, _ in to_create:
        by_reason.setdefault(rt, []).append((s, e, reason))
    for rt in ("signal", "cadence"):
        rows = by_reason.get(rt, [])
        print(f"\n-- {rt} ({len(rows)}) --")
        for s, e, reason in rows[:25]:
            print(f"  school {s:>4}  {e:<16}  {reason}")
        if len(rows) > 25:
            print(f"  ... and {len(rows) - 25} more")


def main():
    commit = "--commit" in sys.argv
    conn = db.connect()
    today = date.today()

    to_create = generate(conn, today)
    print_report(to_create, commit)

    if not commit:
        return

    with db.ingest_run(
        conn, "manual", "Phase 8 follow-up generation (window/signal/cadence)", "ND",
    ) as (run_id, counts):
        commit_follow_ups(conn, to_create, today, counts)
        conn.commit()
    conn.close()
    print(f"\nCommitted {len(to_create)} follow_ups rows.")


if __name__ == "__main__":
    main()
