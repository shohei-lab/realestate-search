"""手動POI追加（OSM 未登録の店舗をユーザが補完）。

OSM の Overpass で拾えない（or 古い）店舗を住所文字列から登録する。
ジオコードして listing からの距離を自動計算し、`osm_type='manual'` を
マーカとして保存することで、`re ingest osm` の再取得時にも保護される。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from ..geo.geocode import GeocodeResult, Geocoder
from ..utils.distance import haversine_m


@dataclass
class POIDraft:
    kind: str                # super/gym/busstop/station 等
    name: str
    address: str
    brand: str | None = None
    note: str | None = None


def add_manual_poi(
    conn: sqlite3.Connection,
    listing_id: int,
    draft: POIDraft,
    *,
    geocoder: Geocoder,
) -> tuple[int, GeocodeResult, float]:
    """ジオコード→距離計算→ poi テーブル INSERT。

    Returns: (poi_id, geocode結果, listingからの距離m)
    """
    cur = conn.execute(
        "SELECT l.location_id, loc.lat AS llat, loc.lon AS llon "
        "FROM listing l LEFT JOIN location loc ON l.location_id = loc.id "
        "WHERE l.id = ?",
        (listing_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"listing_id={listing_id} が存在しません")
    if row["location_id"] is None or row["llat"] is None or row["llon"] is None:
        raise ValueError(
            f"listing_id={listing_id} に座標がありません（先にジオコード済の物件を指定）"
        )

    geo = geocoder.geocode(draft.address)
    if not geo.is_hit or geo.lat is None or geo.lon is None:
        raise ValueError(f"住所のジオコードに失敗: {draft.address!r}")

    distance = haversine_m(row["llat"], row["llon"], geo.lat, geo.lon)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    cur = conn.execute(
        """
        INSERT INTO poi (
            location_id, kind, name, brand, distance_m, lat, lon,
            osm_type, osm_id, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'manual', NULL, ?)
        """,
        (
            row["location_id"],
            draft.kind,
            draft.name,
            draft.brand,
            distance,
            geo.lat,
            geo.lon,
            now,
        ),
    )
    conn.commit()
    return int(cur.lastrowid or 0), geo, distance
