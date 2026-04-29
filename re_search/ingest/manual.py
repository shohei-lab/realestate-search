"""手動/CSV による物件取り込みのコアロジック。

スクレイピングではなく、ユーザーが「自分が見た物件をクリップする」型の入力経路。
最小メタデータのみ保存し、HTML本文・画像等は保存しない。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from .. import __version__
from ..config import Config
from ..geo.geocode import Geocoder


@dataclass
class ListingDraft:
    address: str
    layout: str | None = None
    area_m2: float | None = None
    rent_jpy: int | None = None
    mgmt_fee_jpy: int | None = None
    building_year: int | None = None
    walk_min: int | None = None
    station: str | None = None
    structure: str | None = None
    earthquake_grade: str | None = None
    ownership: str | None = None
    total_units: int | None = None
    orientation: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    note: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_source(conn: sqlite3.Connection, draft: ListingDraft) -> int:
    kind = "manual" if not draft.source_url else "manual"
    name = draft.source_name or "manual"
    cur = conn.execute(
        "INSERT INTO source (name, kind, url, fetched_at) VALUES (?, ?, ?, ?)",
        (name, kind, draft.source_url, _now()),
    )
    return cur.lastrowid


def add_listing(
    conn: sqlite3.Connection,
    draft: ListingDraft,
    *,
    config: Config | None = None,
    geocoder: Geocoder | None = None,
) -> int:
    """物件を listing テーブルへ登録し、住所をジオコードして location に紐付ける。

    Returns:
        新規 listing_id。
    """
    cfg = config or Config.load()

    own_geocoder = geocoder is None
    geo = geocoder or Geocoder(conn, config=cfg)

    try:
        result = geo.geocode(draft.address)
    finally:
        if own_geocoder:
            geo.close()

    cur = conn.execute(
        "SELECT id FROM location WHERE raw_address = ?", (result.normalized,)
    )
    row = cur.fetchone()
    location_id = row["id"] if row else None

    source_id = _ensure_source(conn, draft)

    now = _now()
    cur = conn.execute(
        """
        INSERT INTO listing (
            address, layout, area_m2, rent_jpy, mgmt_fee_jpy,
            building_year, walk_min, station, structure, earthquake_grade,
            ownership, total_units, orientation,
            source_id, location_id, first_seen_at, last_seen_at, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """,
        (
            draft.address,
            draft.layout,
            draft.area_m2,
            draft.rent_jpy,
            draft.mgmt_fee_jpy,
            draft.building_year,
            draft.walk_min,
            draft.station,
            draft.structure,
            draft.earthquake_grade,
            draft.ownership,
            draft.total_units,
            draft.orientation,
            source_id,
            location_id,
            now,
            now,
        ),
    )
    listing_id = cur.lastrowid

    if draft.rent_jpy is not None or draft.mgmt_fee_jpy is not None:
        conn.execute(
            """
            INSERT INTO listing_snapshot (listing_id, snapshotted_at, rent_jpy, mgmt_fee_jpy, raw_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (listing_id, now, draft.rent_jpy, draft.mgmt_fee_jpy, None),
        )

    conn.commit()
    return listing_id
