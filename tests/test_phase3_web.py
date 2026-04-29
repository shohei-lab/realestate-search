"""WebUI 動作テスト（fastapi.testclient）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from re_search.config import Config
from re_search.db import connect, init_schema
from re_search.web.app import create_app


@pytest.fixture
def configured(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    monkeypatch.setattr("re_search.config.user_config_dir", lambda *_a, **_kw: str(config_dir))
    monkeypatch.setattr("re_search.config.user_data_dir", lambda *_a, **_kw: str(data_dir))
    cfg = Config.load()
    cfg.ensure_dirs()
    c = connect(cfg)
    init_schema(c)

    # listing 1件入れる
    c.execute(
        "INSERT INTO source (name, kind) VALUES (?, ?)", ("テスト物件", "manual")
    )
    src_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    c.execute(
        "INSERT INTO location (raw_address, lat, lon, ward, town_code, terrain_class) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("東京都目黒区大橋1-2-10", 35.6517, 139.6889, "目黒区", "13110", "氾濫原"),
    )
    loc_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    c.execute(
        "INSERT INTO listing (address, layout, rent_jpy, building_year, walk_min, station, "
        "structure, source_id, location_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("東京都目黒区大橋1-2-10", "1LDK", 200000, 1983, 6, "池尻大橋", "SRC", src_id, loc_id),
    )
    listing_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    c.execute(
        "INSERT INTO poi (location_id, kind, name, brand, distance_m, lat, lon, osm_type, osm_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (loc_id, "super", "ライフ目黒大橋店", None, 47, 35.6520, 139.6889, "node", 1),
    )
    c.execute(
        "INSERT INTO poi (location_id, kind, name, brand, distance_m, lat, lon, osm_type) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (loc_id, "gym", "エニタイムフィットネス 中目黒池尻大橋店", "エニタイム", 166, 35.6506, 139.6901, "manual"),
    )
    c.execute(
        "INSERT INTO score (listing_id, kind, value, breakdown_json) "
        "VALUES (?, ?, ?, ?)",
        (listing_id, "livability", 88, '{"comment":"良好"}'),
    )
    c.commit()
    c.close()
    return cfg, listing_id


def test_index_page(configured):
    cfg, _ = configured
    app = create_app(cfg)
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "物件一覧" in r.text
    assert "ライオンズ" in r.text or "目黒区" in r.text or "大橋" in r.text


def test_listing_detail(configured):
    cfg, listing_id = configured
    app = create_app(cfg)
    client = TestClient(app)
    r = client.get(f"/listing/{listing_id}")
    assert r.status_code == 200
    # メタ
    assert "目黒区" in r.text
    # 地図 div
    assert 'id="map"' in r.text
    # POI 表示
    assert "ライフ目黒大橋店" in r.text
    assert "エニタイム" in r.text
    # スコア
    assert "88" in r.text


def test_listing_404(configured):
    cfg, _ = configured
    app = create_app(cfg)
    client = TestClient(app)
    r = client.get("/listing/9999")
    assert r.status_code == 404


def test_pois_json_api(configured):
    cfg, listing_id = configured
    app = create_app(cfg)
    client = TestClient(app)
    r = client.get(f"/api/listing/{listing_id}/pois.json")
    assert r.status_code == 200
    data = r.json()
    assert data["listing"]["id"] == listing_id
    assert len(data["pois"]) == 2
    kinds = sorted({p["kind"] for p in data["pois"]})
    assert kinds == ["gym", "super"]


def test_db_is_readonly(configured):
    """WebUI 経由で DB が書き換えられないことを確認（ハンドラ内で write を試みる代替として、URI が ?mode=ro になっていることをアサート）。"""
    from re_search.web.app import _connect_ro
    cfg, listing_id = configured
    c = _connect_ro(cfg.db_path)
    try:
        with pytest.raises(Exception):
            c.execute("UPDATE listing SET rent_jpy = 999 WHERE id = ?", (listing_id,))
    finally:
        c.close()
