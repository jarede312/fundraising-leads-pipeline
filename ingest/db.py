from contextlib import contextmanager

import psycopg

from .config import PG_DSN


def connect():
    return psycopg.connect(PG_DSN)


@contextmanager
def ingest_run(conn, source: str, source_detail: str, scope: str):
    """Open an ingest_runs row, yield its id, close it on exit (ok/failed)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ingest_runs (source, source_detail, scope, status)
            VALUES (%s, %s, %s, 'running')
            RETURNING id
            """,
            (source, source_detail, scope),
        )
        run_id = cur.fetchone()[0]
    conn.commit()

    counts = {"in": 0, "written": 0, "cost_usd": 0.0}
    try:
        yield run_id, counts
        status = "ok"
    except Exception:
        status = "failed"
        raise
    finally:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ingest_runs
                SET finished_at = now(), status = %s, records_in = %s, records_written = %s,
                    cost_usd = %s
                WHERE id = %s
                """,
                (status, counts["in"], counts["written"], counts["cost_usd"] or None, run_id),
            )
        conn.commit()
