import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

SCHEMA = Path(__file__).with_name("schema.sql")


def connect() -> psycopg.Connection:
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True, row_factory=dict_row)


def init_db() -> None:
    with connect() as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
