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
    """schema.sql を流し込んでテーブル群を作る（IF NOT EXISTS なので再実行安全）。

    既存DBへの後方互換のため、軽量マイグレーションを最後に走らせる。
    """
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    conn.executescript(sql)
    _apply_migrations(conn)
    conn.commit()


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """既存DBに対して列追加など差分マイグレーションを適用する。"""
    # v2: poi.name / osm_type / osm_id / fetched_at を追加
    cur = conn.execute("PRAGMA table_info(poi)")
    cols = {row[1] for row in cur.fetchall()}
    new_cols = [
        ("name", "TEXT"),
        ("osm_type", "TEXT"),
        ("osm_id", "INTEGER"),
        ("fetched_at", "TEXT"),
    ]
    bumped = False
    for name, typ in new_cols:
        if name not in cols:
            conn.execute(f"ALTER TABLE poi ADD COLUMN {name} {typ}")
            bumped = True
    if bumped:
        conn.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (2)")

    # v3: score.kind の CHECK 制約に 'heritage' を追加
    # SQLite は CHECK の ALTER をサポートしないので、テーブル再作成パターンを使う。
    cur = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='score'"
    )
    row = cur.fetchone()
    if row and "heritage" not in (row[0] or ""):
        conn.executescript(
            """
            PRAGMA foreign_keys=OFF;
            CREATE TABLE score_new (
              listing_id INTEGER NOT NULL REFERENCES listing(id) ON DELETE CASCADE,
              kind TEXT NOT NULL CHECK(kind IN ('livability','locality','heritage','fengshui')),
              value REAL,
              breakdown_json TEXT,
              scored_at TEXT,
              PRIMARY KEY(listing_id, kind)
            );
            INSERT INTO score_new SELECT * FROM score;
            DROP TABLE score;
            ALTER TABLE score_new RENAME TO score;
            PRAGMA foreign_keys=ON;
            """
        )
        conn.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (3)")


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
