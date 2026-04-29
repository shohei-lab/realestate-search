"""SQLite 接続とスキーマ初期化。"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import Config

SCHEMA_FILE = Path(__file__).parent / "schema.sql"


def connect(config: Config) -> sqlite3.Connection:
    """設定からSQLite接続を作る。必要なディレクトリは事前に作成する。"""
    config.ensure_dirs()
    conn = sqlite3.connect(config.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """schema.sql を流し込んでテーブル群を作る（IF NOT EXISTS なので再実行安全）。"""
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()


def get_schema_version(conn: sqlite3.Connection) -> int | None:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    )
    if cur.fetchone() is None:
        return None
    cur = conn.execute("SELECT MAX(version) AS v FROM schema_version")
    row = cur.fetchone()
    return row["v"] if row else None


@contextmanager
def get_conn(config: Config | None = None) -> Iterator[sqlite3.Connection]:
    cfg = config or Config.load()
    conn = connect(cfg)
    try:
        yield conn
    finally:
        conn.close()
