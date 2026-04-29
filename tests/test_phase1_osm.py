"""Phase 1: Overpass POI 取得のテスト（HTTP モック）。"""

from __future__ import annotations

import httpx
import pytest

from re_search.config import Config
from re_search.db import connect, init_schema
from re_search.ingest.osm import (
    OverpassClient,
    build_overpass_query,
    classify,
    extract_brand,
    extract_name,
    parse_overpass_response,
    store_pois,
)
from re_search.utils.ratelimit import RateLimiter


@pytest.fixture
def tmp_config(tmp_path, monkeypatch) -> Config:
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    monkeypatch.setattr("re_search.config.user_config_dir", lambda *_a, **_kw: str(config_dir))
    monkeypatch.setattr("re_search.config.user_data_dir", lambda *_a, **_kw: str(data_dir))
    return Config.load()


# ───────── pure parsing ─────────


def test_classify_supermarket():
    assert classify({"shop": "supermarket"}) == "super"


def test_classify_fitness_centre():
    assert classify({"leisure": "fitness_centre"}) == "gym"


def test_classify_sports_centre_with_fitness():
    assert classify({"leisure": "sports_centre", "sport": "fitness"}) == "gym"


def test_classify_sports_centre_without_fitness():
    assert classify({"leisure": "sports_centre", "sport": "tennis"}) is None


def test_classify_busstop():
    assert classify({"highway": "bus_stop"}) == "busstop"


def test_classify_unknown():
    assert classify({"shop": "convenience"}) is None
    assert classify({}) is None


def test_extract_name_priority_ja_then_default():
    assert extract_name({"name:ja": "成城石井", "name": "Seijo Ishii"}) == "成城石井"
    assert extract_name({"name": "Anytime Fitness"}) == "Anytime Fitness"
    assert extract_name({}) is None


def test_extract_brand():
    assert extract_brand({"brand": "Anytime Fitness"}) == "Anytime Fitness"
    assert extract_brand({"brand:ja": "エニタイムフィットネス"}) == "エニタイムフィットネス"


def test_build_overpass_query_contains_categories():
    q = build_overpass_query(35.65, 139.68, {"super": 800, "gym": 1000, "busstop": 300})
    assert 'shop"="supermarket"' in q
    assert 'leisure"="fitness_centre"' in q
    assert 'highway"="bus_stop"' in q
    assert "around:800" in q
    assert "around:1000" in q
    assert "around:300" in q


def test_build_overpass_query_skip_categories():
    q = build_overpass_query(35.65, 139.68, {"super": 500})
    assert "supermarket" in q
    assert "fitness_centre" not in q
    assert "bus_stop" not in q


# ───────── parse response ─────────


def _sample_response(origin_lat=35.6517, origin_lon=139.6889):
    """ライオンズプラザ近辺を想定した OSM レスポンスのモック。"""
    return {
        "elements": [
            {
                "type": "node",
                "id": 1,
                "lat": origin_lat + 0.001,  # ~111m 北
                "lon": origin_lon,
                "tags": {"shop": "supermarket", "name:ja": "成城石井 池尻店"},
            },
            {
                "type": "way",
                "id": 2,
                "center": {"lat": origin_lat - 0.002, "lon": origin_lon + 0.001},
                "tags": {
                    "leisure": "fitness_centre",
                    "name": "Anytime Fitness 池尻大橋",
                    "brand:ja": "エニタイムフィットネス",
                    "brand": "Anytime Fitness",
                },
            },
            {
                "type": "node",
                "id": 3,
                "lat": origin_lat,
                "lon": origin_lon - 0.001,
                "tags": {"highway": "bus_stop", "name": "大橋"},
            },
            {
                "type": "node",
                "id": 4,
                "lat": origin_lat + 0.0005,
                "lon": origin_lon + 0.0005,
                # tags なし → 無視されること
            },
            {
                "type": "node",
                "id": 5,
                "lat": origin_lat,
                "lon": origin_lon,
                "tags": {"shop": "convenience"},  # 分類対象外
            },
        ]
    }


def test_parse_overpass_response():
    pois = parse_overpass_response(_sample_response(), 35.6517, 139.6889)
    kinds = [p.kind for p in pois]
    assert kinds.count("super") == 1
    assert kinds.count("gym") == 1
    assert kinds.count("busstop") == 1
    assert len(pois) == 3

    sup = next(p for p in pois if p.kind == "super")
    assert sup.name == "成城石井 池尻店"
    assert 100 < sup.distance_m < 130

    gym = next(p for p in pois if p.kind == "gym")
    assert gym.brand == "エニタイムフィットネス"
    assert gym.name == "Anytime Fitness 池尻大橋"


# ───────── client + DB ─────────


def test_overpass_client_uses_post_with_data():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(200, json=_sample_response())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    ovp = OverpassClient(client=client, rate_limiter=RateLimiter(rps=0))
    pois = ovp.fetch_pois(35.6517, 139.6889)
    ovp.close()

    assert captured["method"] == "POST"
    # POST body は URL エンコードされた `data=...overpass query...` 形式
    body = captured["body"]
    assert body.startswith("data=")
    assert "supermarket" in body
    assert "fitness_centre" in body
    assert "bus_stop" in body
    assert len(pois) == 3


def test_overpass_client_handles_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    ovp = OverpassClient(client=client, rate_limiter=RateLimiter(rps=0))
    pois = ovp.fetch_pois(35.6517, 139.6889)
    ovp.close()
    assert pois == []


def test_store_pois_replaces(tmp_config):
    conn = connect(tmp_config)
    try:
        init_schema(conn)
        # ジオコード結果として location を1件だけ作る
        conn.execute(
            "INSERT INTO location (raw_address, lat, lon, ward, town_code) VALUES (?, ?, ?, ?, ?)",
            ("東京都目黒区大橋1-2-10", 35.6517, 139.6889, "目黒区", "13110"),
        )
        loc_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        pois = parse_overpass_response(_sample_response(), 35.6517, 139.6889)
        n1 = store_pois(conn, loc_id, pois)
        assert n1 == 3

        # 再保存しても合計が増えない（DELETE して入れ替え）
        n2 = store_pois(conn, loc_id, pois)
        assert n2 == 3
        cur = conn.execute("SELECT COUNT(*) AS n FROM poi WHERE location_id = ?", (loc_id,))
        assert cur.fetchone()["n"] == 3
    finally:
        conn.close()
