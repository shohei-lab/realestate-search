"""国土地理院ジオコーダ (msearch.gsi.go.jp) のクライアント + SQLite キャッシュ。

API 仕様:
    GET https://msearch.gsi.go.jp/address-search/AddressSearch?q=<query>
    Response: [
        {
            "geometry": {"coordinates": [lon, lat], "type": "Point"},
            "type": "Feature",
            "properties": {"addressCode": "...", "title": "..."}
        },
        ...
    ]

利用方針:
- API キーは不要だが、無償サービスなので低頻度（デフォルト 0.5 req/sec）に絞る
- User-Agent を明示する
- 結果は `location` テーブルに raw_address UNIQUE で永続キャッシュする
- 失敗時は (None, None) を返し、呼び出し側で扱えるようにする
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import httpx

from .. import __version__
from ..config import Config
from ..utils.ratelimit import RateLimiter
from .area_codes import ward_from_address
from .normalize import normalize_address

GSI_ENDPOINT = "https://msearch.gsi.go.jp/address-search/AddressSearch"
DEFAULT_USER_AGENT = (
    f"re-search/{__version__} (+https://github.com/shohei-lab/realestate-search; personal use)"
)


@dataclass(frozen=True)
class GeocodeResult:
    raw_address: str           # 入力（正規化前）
    normalized: str            # 正規化済みクエリ
    title: str | None          # API が返した正式表記
    lat: float | None
    lon: float | None
    address_code: str | None   # API が返した addressCode（多くの場合空文字）
    ward: str | None           # 23区のうち推定した区名
    city_code: str | None      # 5桁市区町村コード（13101 等）

    @property
    def is_hit(self) -> bool:
        return self.lat is not None and self.lon is not None


class Geocoder:
    """正規化 → API 呼び出し → SQLite キャッシュ の3段ロケット。"""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        client: httpx.Client | None = None,
        config: Config | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self._conn = conn
        self._owns_client = client is None
        self._config = config or Config.load()
        self._client = client or httpx.Client(
            timeout=10.0,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
        )
        self._rate = rate_limiter or RateLimiter(rps=self._config.scrape_rate_limit_rps or 0.5)

    # ───────── public API ─────────

    def geocode(self, raw_address: str, *, use_cache: bool = True) -> GeocodeResult:
        normalized = normalize_address(raw_address)
        if not normalized:
            return GeocodeResult(raw_address, "", None, None, None, None, None, None)

        if use_cache:
            cached = self._read_cache(normalized)
            if cached is not None:
                return cached

        result = self._call_api(raw_address, normalized)
        self._write_cache(result)
        return result

    def geocode_many(self, addresses: Iterable[str]) -> list[GeocodeResult]:
        return [self.geocode(a) for a in addresses]

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # ───────── internals ─────────

    def _call_api(self, raw_address: str, normalized: str) -> GeocodeResult:
        self._rate.wait()
        try:
            resp = self._client.get(GSI_ENDPOINT, params={"q": normalized})
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError, ValueError):
            data = []

        title: str | None = None
        lat: float | None = None
        lon: float | None = None
        address_code: str | None = None

        if isinstance(data, list) and data:
            first = data[0]
            geom = first.get("geometry", {}) if isinstance(first, dict) else {}
            coords = geom.get("coordinates", [])
            if isinstance(coords, list) and len(coords) >= 2:
                # GeoJSON 順は [lon, lat]
                try:
                    lon = float(coords[0])
                    lat = float(coords[1])
                except (TypeError, ValueError):
                    lon = lat = None
            props = first.get("properties", {}) if isinstance(first, dict) else {}
            title = props.get("title")
            address_code = props.get("addressCode") or None

        ward = ward_from_address(title or normalized)
        from .area_codes import city_code_for_ward
        city_code = city_code_for_ward(ward) if ward else None

        return GeocodeResult(
            raw_address=raw_address,
            normalized=normalized,
            title=title,
            lat=lat,
            lon=lon,
            address_code=address_code,
            ward=ward,
            city_code=city_code,
        )

    def _read_cache(self, normalized: str) -> GeocodeResult | None:
        cur = self._conn.execute(
            "SELECT raw_address, lat, lon, ward, town_code, nearest_station "
            "FROM location WHERE raw_address = ?",
            (normalized,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return GeocodeResult(
            raw_address=row["raw_address"],
            normalized=normalized,
            title=None,
            lat=row["lat"],
            lon=row["lon"],
            address_code=None,
            ward=row["ward"],
            city_code=row["town_code"],
        )

    def _write_cache(self, result: GeocodeResult) -> None:
        if not result.normalized:
            return
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._conn.execute(
            """
            INSERT INTO location (raw_address, lat, lon, pref, ward, town_code, geocoded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(raw_address) DO UPDATE SET
                lat = excluded.lat,
                lon = excluded.lon,
                pref = excluded.pref,
                ward = excluded.ward,
                town_code = excluded.town_code,
                geocoded_at = excluded.geocoded_at
            """,
            (
                result.normalized,
                result.lat,
                result.lon,
                "東京都" if result.ward else None,
                result.ward,
                result.city_code,
                now,
            ),
        )
        self._conn.commit()
