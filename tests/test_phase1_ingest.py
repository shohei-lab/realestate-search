"""Phase 1 (先取り): `re ingest add` の最小動作確認。"""

from __future__ import annotations

import httpx
import pytest

from re_search.config import Config
from re_search.db import connect, init_schema
from re_search.geo.geocode import Geocoder
from re_search.ingest.manual import ListingDraft, add_listing
from re_search.utils.ratelimit import RateLimiter


@pytest.fixture
def tmp_config(tmp_path, monkeypatch) -> Config:
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    monkeypatch.setattr("re_search.config.user_config_dir", lambda *_a, **_kw: str(config_dir))
    monkeypatch.setattr("re_search.config.user_data_dir", lambda *_a, **_kw: str(data_dir))
    return Config.load()


def make_geocoder_with_mock(conn, cfg, lat=35.661, lon=139.685, title="東京都目黒区大橋一丁目"):
    payload = [
        {
            "geometry": {"coordinates": [lon, lat], "type": "Point"},
            "type": "Feature",
            "properties": {"title": title},
        }
    ]

    def handler(request):
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return Geocoder(conn, client=client, config=cfg, rate_limiter=RateLimiter(rps=0))


def test_add_listing_basic(tmp_config):
    conn = connect(tmp_config)
    try:
        init_schema(conn)
        geo = make_geocoder_with_mock(conn, tmp_config)

        draft = ListingDraft(
            address="東京都目黒区大橋1-2-10",
            layout="1LDK",
            area_m2=45.5,
            rent_jpy=200000,
            mgmt_fee_jpy=10000,
            building_year=1983,
            walk_min=6,
            station="池尻大橋",
            structure="SRC",
            total_units=149,
            source_name="ライオンズプラザ池尻大橋 (test)",
        )
        listing_id = add_listing(conn, draft, config=tmp_config, geocoder=geo)
        geo.close()

        cur = conn.execute(
            "SELECT l.id, l.address, l.rent_jpy, l.total_units, "
            "       loc.lat, loc.lon, loc.ward, loc.town_code "
            "FROM listing l LEFT JOIN location loc ON l.location_id = loc.id "
            "WHERE l.id = ?",
            (listing_id,),
        )
        row = cur.fetchone()
        assert row is not None
        assert row["address"] == "東京都目黒区大橋1-2-10"
        assert row["rent_jpy"] == 200000
        assert row["total_units"] == 149
        assert row["lat"] == pytest.approx(35.661)
        assert row["lon"] == pytest.approx(139.685)
        assert row["ward"] == "目黒区"
        assert row["town_code"] == "13110"

        # snapshot も記録されている
        cur = conn.execute(
            "SELECT COUNT(*) AS n FROM listing_snapshot WHERE listing_id = ?",
            (listing_id,),
        )
        assert cur.fetchone()["n"] == 1
    finally:
        conn.close()
