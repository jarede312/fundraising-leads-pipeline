import psycopg
from psycopg.rows import dict_row

from ingest.config import PG_DSN


def get_conn():
    conn = psycopg.connect(PG_DSN, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()
