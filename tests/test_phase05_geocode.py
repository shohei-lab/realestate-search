"""Phase 0.5: ジオコーダのテスト（httpx MockTransport で API モック）。"""

from __future__ import annotations

import json

import httpx
import pytest

from re_search.config import Config
from re_search.db import connect, init_schema
from re_search.geo.geocode import Geocoder
from re_search.utils.ratelimit import RateLimiter


@pytest.fixture
def tmp_config(tmp_path, monkeypatch) -> Config:
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    monkeypatch.setattr("re_search.config.user_config_dir", lambda *_a, **_kw: str(config_dir))
    monkeypatch.setattr("re_search.config.user_data_dir", lambda *_a, **_kw: str(data_dir))
    return Config.load()


@pytest.fixture
def conn(tmp_config):
    c = connect(tmp_config)
    init_schema(c)
    yield c
    c.close()


def make_mock_client(response_payload, *, status: int = 200, fail: bool = False) -> tuple[httpx.Client, list[dict]]:
    """API 応答を差し替えた httpx.Client と、呼び出し履歴のリストを返す。"""
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append({"url": str(request.url), "params": dict(request.url.params)})
        if fail:
            raise httpx.ConnectError("simulated network error", request=request)
        return httpx.Response(status, json=response_payload)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return client, calls


def test_geocode_hit(tmp_config, conn):
    payload = [
        {
            "geometry": {"coordinates": [139.685, 35.661], "type": "Point"},
            "type": "Feature",
            "properties": {"addressCode": "13110", "title": "東京都目黒区大橋一丁目"},
        }
    ]
    client, calls = make_mock_client(payload)
    g = Geocoder(conn, client=client, config=tmp_config, rate_limiter=RateLimiter(rps=0))

    result = g.geocode("目黒区大橋1-2-10")
    g.close()

    assert result.is_hit
    assert result.lat == pytest.approx(35.661)
    assert result.lon == pytest.approx(139.685)
    assert result.normalized == "東京都目黒区大橋1-2-10"
    assert result.ward == "目黒区"
    assert result.city_code == "13110"

    # API への q パラメータが正規化済みであること
    assert calls[0]["params"]["q"] == "東京都目黒区大橋1-2-10"


def test_geocode_cache_hit_no_api_call(tmp_config, conn):
    payload = [
        {
            "geometry": {"coordinates": [139.685, 35.661], "type": "Point"},
            "type": "Feature",
            "properties": {"title": "東京都目黒区大橋一丁目"},
        }
    ]
    client, calls = make_mock_client(payload)
    g = Geocoder(conn, client=client, config=tmp_config, rate_limiter=RateLimiter(rps=0))
    g.geocode("目黒区大橋1-2-10")
    assert len(calls) == 1

    # 同じ住所をもう一度 → API は呼ばれない（キャッシュヒット）
    again = g.geocode("目黒区大橋1-2-10")
    g.close()
    assert again.is_hit
    assert len(calls) == 1


def test_geocode_no_cache_flag(tmp_config, conn):
    payload = [
        {
            "geometry": {"coordinates": [139.685, 35.661], "type": "Point"},
            "type": "Feature",
            "properties": {"title": "東京都目黒区大橋一丁目"},
        }
    ]
    client, calls = make_mock_client(payload)
    g = Geocoder(conn, client=client, config=tmp_config, rate_limiter=RateLimiter(rps=0))
    g.geocode("目黒区大橋1-2-10")
    g.geocode("目黒区大橋1-2-10", use_cache=False)
    g.close()
    assert len(calls) == 2


def test_geocode_empty_response_returns_miss(tmp_config, conn):
    client, _ = make_mock_client([])
    g = Geocoder(conn, client=client, config=tmp_config, rate_limiter=RateLimiter(rps=0))
    r = g.geocode("ありもしない地名XYZ123")
    g.close()
    assert not r.is_hit
    assert r.lat is None
    assert r.lon is None


def test_geocode_network_error_returns_miss(tmp_config, conn):
    client, _ = make_mock_client(None, fail=True)
    g = Geocoder(conn, client=client, config=tmp_config, rate_limiter=RateLimiter(rps=0))
    r = g.geocode("東京都港区六本木1-1-1")
    g.close()
    assert not r.is_hit
