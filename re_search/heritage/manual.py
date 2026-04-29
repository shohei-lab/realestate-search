"""area_history / waterway への手動登録。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


VALID_ERAS = ("edo", "meiji", "taisho", "showa_pre", "showa_post", "heisei", "reiwa")


@dataclass
class HeritageEntry:
    town_code: str
    era: str
    old_name: str | None = None
    old_use: str | None = None
    old_terrain: str | None = None
    source: str | None = None
    citation: str | None = None
    note: str | None = None


def add_heritage_entry(conn: sqlite3.Connection, entry: HeritageEntry) -> int:
    if entry.era not in VALID_ERAS:
        raise ValueError(f"era は {VALID_ERAS} のいずれか")
    cur = conn.execute(
        """
        INSERT INTO area_history (
            town_code, era, old_name, old_use, old_terrain,
            source, citation, note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry.town_code,
            entry.era,
            entry.old_name,
            entry.old_use,
            entry.old_terrain,
            entry.source,
            entry.citation,
            entry.note,
        ),
    )
    conn.commit()
    return int(cur.lastrowid or 0)


@dataclass
class WaterwayEntry:
    name: str | None
    kind: str          # river / old_river / spring / pond
    geom_wkt: str | None = None
    source: str | None = None


def add_waterway(conn: sqlite3.Connection, entry: WaterwayEntry) -> int:
    cur = conn.execute(
        "INSERT INTO waterway (name, kind, geom_wkt, source) VALUES (?, ?, ?, ?)",
        (entry.name, entry.kind, entry.geom_wkt, entry.source),
    )
    conn.commit()
    return int(cur.lastrowid or 0)


def list_heritage_for_town(conn: sqlite3.Connection, town_code: str) -> list[sqlite3.Row]:
    cur = conn.execute(
        "SELECT * FROM area_history WHERE town_code = ? ORDER BY era",
        (town_code,),
    )
    return cur.fetchall()
