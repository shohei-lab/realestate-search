"""OpenStreetMap Overpass API による周辺POI取得。

対応カテゴリ:
- super (スーパーマーケット): shop=supermarket
- gym  (ジム/フィットネス): leisure=fitness_centre + leisure=sports_centre[sport~fitness]
- busstop (バス停): highway=bus_stop

利用方針:
- User-Agent 明示（Overpass の利用規約）
- レート制御（公開エンドポイントへの礼儀）
- 結果は poi テーブルに永続キャッシュ（location_id ごと）
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import httpx

from .. import __version__
from ..config import Config
from ..utils.distance import haversine_m
from ..utils.ratelimit import RateLimiter

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"

DEFAULT_USER_AGENT = (
    f"re-search/{__version__} (+https://github.com/shohei-lab/realestate-search; personal use)"
)

# kind ごとのデフォルト探索半径（メートル）
DEFAULT_RADII: dict[str, int] = {
    "super": 800,      # 徒歩10分相当
    "gym": 1000,       # 徒歩12-13分相当
    "busstop": 300,
}


@dataclass(frozen=True)
class POIFetched:
    kind: str               # super/gym/busstop
    name: str | None
    brand: str | None
    lat: float
    lon: float
    distance_m: float
    osm_type: str           # node/way/relation
    osm_id: int


# ───────── Overpass query ─────────


def build_overpass_query(lat: float, lon: float, radii: dict[str, int]) -> str:
    """対象 kind のクエリを連結して1リクエストにまとめる。"""
    parts: list[str] = []
    if "super" in radii:
        parts.append(f'  nwr["shop"="supermarket"](around:{radii["super"]},{lat},{lon});')
    if "gym" in radii:
        parts.append(f'  nwr["leisure"="fitness_centre"](around:{radii["gym"]},{lat},{lon});')
        parts.append(
            f'  nwr["leisure"="sports_centre"]["sport"~"fitness"](around:{radii["gym"]},{lat},{lon});'
        )
    if "busstop" in radii:
        parts.append(f'  nwr["highway"="bus_stop"](around:{radii["busstop"]},{lat},{lon});')

    body = "\n".join(parts) if parts else ""
    return f"[out:json][timeout:25];\n(\n{body}\n);\nout center tags;"


def classify(tags: dict) -> str | None:
    if not tags:
        return None
    if tags.get("shop") == "supermarket":
        return "super"
    if tags.get("leisure") == "fitness_centre":
        return "gym"
    if tags.get("leisure") == "sports_centre" and "fitness" in (tags.get("sport") or ""):
        return "gym"
    if tags.get("highway") == "bus_stop":
        return "busstop"
    return None


def extract_name(tags: dict) -> str | None:
    if not tags:
        return None
    return (
        tags.get("name:ja")
        or tags.get("name")
        or tags.get("name:en")
        or tags.get("ref")
    )


def extract_brand(tags: dict) -> str | None:
    if not tags:
        return None
    return (
        tags.get("brand:ja")
        or tags.get("brand")
        or tags.get("brand:en")
    )


def parse_overpass_response(
    response_json: dict, origin_lat: float, origin_lon: float
) -> list[POIFetched]:
    """Overpass のレスポンスを POIFetched のリストに整形。"""
    results: list[POIFetched] = []
    for el in response_json.get("elements", []):
        tags = el.get("tags") or {}
        kind = classify(tags)
        if kind is None:
            continue

        # node なら lat/lon、way/relation なら center.lat/center.lon
        if "lat" in el and "lon" in el:
            lat = el["lat"]
            lon = el["lon"]
        else:
            center = el.get("center") or {}
            lat = center.get("lat")
            lon = center.get("lon")

        if lat is None or lon is None:
            continue

        distance = haversine_m(origin_lat, origin_lon, lat, lon)
        results.append(
            POIFetched(
                kind=kind,
                name=extract_name(tags),
                brand=extract_brand(tags),
                lat=float(lat),
                lon=float(lon),
                distance_m=distance,
                osm_type=el.get("type", "node"),
                osm_id=int(el.get("id", 0)),
            )
        )

    results.sort(key=lambda p: (p.kind, p.distance_m))
    return results


# ───────── Client ─────────


class OverpassClient:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
        rate_limiter: RateLimiter | None = None,
        config: Config | None = None,
    ) -> None:
        self._owns_client = client is None
        cfg = config or Config.load()
        self._rate = rate_limiter or RateLimiter(rps=cfg.scrape_rate_limit_rps or 0.5)
        self._client = client or httpx.Client(
            timeout=30.0,
            headers={
                "User-Agent": user_agent,
                "Accept": "application/json",
            },
        )

    def fetch_pois(
        self,
        lat: float,
        lon: float,
        *,
        radii: dict[str, int] | None = None,
    ) -> list[POIFetched]:
        radii = radii or dict(DEFAULT_RADII)
        query = build_overpass_query(lat, lon, radii)
        self._rate.wait()
        try:
            resp = self._client.post(
                OVERPASS_ENDPOINT,
                data={"data": query},
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return []
        return parse_overpass_response(data, lat, lon)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


# ───────── DB write ─────────


def store_pois(
    conn: sqlite3.Connection,
    location_id: int,
    pois: Iterable[POIFetched],
) -> int:
    """指定 location の OSM 由来 poi を入れ替え保存。手動POIは温存。返り値は登録件数。"""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # osm_type が 'node'/'way'/'relation' のものだけ削除し、'manual' は保護する。
    conn.execute(
        "DELETE FROM poi WHERE location_id = ? AND osm_type IN ('node','way','relation')",
        (location_id,),
    )
    rows = [
        (
            location_id,
            p.kind,
            p.name,
            p.brand,
            p.distance_m,
            p.lat,
            p.lon,
            p.osm_type,
            p.osm_id,
            now,
        )
        for p in pois
    ]
    conn.executemany(
        """
        INSERT INTO poi (
            location_id, kind, name, brand, distance_m, lat, lon,
            osm_type, osm_id, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return len(rows)
