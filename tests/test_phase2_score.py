"""score / heritage / fengshui の単体テスト。"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from re_search.config import Config
from re_search.db import connect, init_schema
from re_search.fengshui.eval import compute_fengshui, store_fengshui_eval
from re_search.heritage.manual import HeritageEntry, WaterwayEntry, add_heritage_entry, add_waterway
from re_search.heritage.score import compute_heritage
from re_search.redev.manual import (
    RedevDraft,
    add_redev_project,
    link_listing_to_redev,
    list_redev_for_listing,
)
from re_search.score.livability import compute_livability, store_score


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


def _insert_listing(conn, **overrides) -> int:
    """テスト用の listing + location を1件作る。"""
    conn.execute(
        "INSERT INTO location (raw_address, lat, lon, ward, town_code, terrain_class) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            overrides.get("address", "東京都目黒区大橋1-2-10"),
            35.6517, 139.6889, "目黒区", "13110",
            overrides.get("terrain_class", "台地"),
        ),
    )
    loc_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    fields = {
        "address": "東京都目黒区大橋1-2-10",
        "layout": "1LDK",
        "rent_jpy": 200000,
        "building_year": 1983,
        "walk_min": 6,
        "station": "池尻大橋",
        "structure": "SRC",
        "earthquake_grade": "新耐震(要確認)",
        "orientation": "S",
        "location_id": loc_id,
    }
    fields.update(overrides)
    fields["location_id"] = loc_id  # ensure
    cols = ", ".join(fields.keys())
    placeholders = ", ".join("?" * len(fields))
    conn.execute(f"INSERT INTO listing ({cols}) VALUES ({placeholders})", tuple(fields.values()))
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _insert_poi(conn, location_id, kind, name, distance_m, *, osm_type="node"):
    conn.execute(
        "INSERT INTO poi (location_id, kind, name, distance_m, lat, lon, osm_type, osm_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (location_id, kind, name, distance_m, 35.6517, 139.6889, osm_type, 1),
    )


# ───────── livability ─────────


def test_livability_perfect_environment(conn):
    listing_id = _insert_listing(conn)
    listing = conn.execute("SELECT * FROM listing WHERE id = ?", (listing_id,)).fetchone()
    loc_id = listing["location_id"]
    # 至近のスーパー、ジム、バス停を入れる
    _insert_poi(conn, loc_id, "super", "ライフ", 47)
    _insert_poi(conn, loc_id, "super", "成城石井", 282)
    _insert_poi(conn, loc_id, "super", "みらべる", 97)
    _insert_poi(conn, loc_id, "gym", "コナミ", 708)
    _insert_poi(conn, loc_id, "busstop", "大橋", 12)
    pois = conn.execute(
        "SELECT * FROM poi WHERE location_id = ? ORDER BY kind, distance_m", (loc_id,)
    ).fetchall()
    value, breakdown = compute_livability(listing, pois)
    # 駅徒歩6分=20点 + 47mスーパー=20+3=23点 + ジム9分=7+2=9点 + バス12m=10点 + SRC新耐震=20点 = 82点
    assert breakdown["station"]["points"] == int(30 * 0.66)  # 20
    assert breakdown["super"]["points"] >= 20
    assert breakdown["gym"]["points"] >= 7
    assert breakdown["bus"]["points"] == 10
    assert breakdown["structure"]["points"] == 20
    assert 60 <= value <= 100


def test_livability_no_pois(conn):
    listing_id = _insert_listing(conn, walk_min=20)
    listing = conn.execute("SELECT * FROM listing WHERE id = ?", (listing_id,)).fetchone()
    value, breakdown = compute_livability(listing, [])
    assert breakdown["station"]["points"] == 0
    assert breakdown["super"]["points"] == 0
    # 構造 SRC + 新耐震 だけは加点される (20点)
    assert value == 20


def test_store_score_upsert(conn):
    listing_id = _insert_listing(conn)
    store_score(conn, listing_id, "livability", 80, {"foo": "bar"})
    store_score(conn, listing_id, "livability", 85, {"foo": "baz"})
    row = conn.execute(
        "SELECT * FROM score WHERE listing_id = ? AND kind = 'livability'", (listing_id,)
    ).fetchone()
    assert row["value"] == 85


# ───────── heritage ─────────


def test_heritage_with_entries(conn):
    add_heritage_entry(
        conn,
        HeritageEntry(
            town_code="13110", era="edo",
            old_name="大橋", old_terrain="谷地", old_use="街道沿いの集落",
            citation="目黒区史",
        ),
    )
    add_heritage_entry(
        conn,
        HeritageEntry(
            town_code="13110", era="meiji",
            old_terrain="氾濫原",
        ),
    )
    listing_id = _insert_listing(conn)
    listing = conn.execute("SELECT * FROM listing WHERE id = ?", (listing_id,)).fetchone()
    value, breakdown = compute_heritage(conn, listing)
    assert value > 0
    assert breakdown["max_total"] == 100
    assert len(breakdown["items"]) == 2


def test_heritage_skips_sensitive(conn):
    add_heritage_entry(
        conn,
        HeritageEntry(
            town_code="13110", era="edo",
            old_name="X", note="差別的旧地名のため機械加点除外",
        ),
    )
    listing_id = _insert_listing(conn)
    listing = conn.execute("SELECT * FROM listing WHERE id = ?", (listing_id,)).fetchone()
    value, breakdown = compute_heritage(conn, listing)
    assert value == 0
    assert breakdown["items"][0].get("skipped") == "sensitive"


# ───────── fengshui ─────────


def test_fengshui_orientation_south_is_favorable(conn):
    listing_id = _insert_listing(conn, orientation="S")
    listing = conn.execute("SELECT * FROM listing WHERE id = ?", (listing_id,)).fetchone()
    value, breakdown, evals = compute_fengshui(conn, listing, [])
    rule_ids = [e["rule_id"] for e in evals]
    assert "orientation" in rule_ids
    south = next(e for e in evals if e["rule_id"] == "orientation")
    assert south["verdict"] == "吉"
    assert south["delta"] > 0


def test_fengshui_oashi_jct_penalty(conn):
    """大橋住所 + 駅徒歩7分以内 → JCT直近として減点。"""
    listing_id = _insert_listing(conn)  # address に大橋, walk_min=6
    listing = conn.execute("SELECT * FROM listing WHERE id = ?", (listing_id,)).fetchone()
    value, breakdown, evals = compute_fengshui(conn, listing, [])
    assert any(e["rule_id"] == "overpass_jct" and e["delta"] < 0 for e in evals)


def test_fengshui_oldriver_warning(conn):
    add_waterway(conn, WaterwayEntry(name="蛇崩川旧河道", kind="old_river"))
    listing_id = _insert_listing(conn)
    listing = conn.execute("SELECT * FROM listing WHERE id = ?", (listing_id,)).fetchone()
    value, breakdown, evals = compute_fengshui(conn, listing, [])
    assert any(e["rule_id"] == "oldriver" for e in evals)


def test_fengshui_store_replaces_old_evaluations(conn):
    listing_id = _insert_listing(conn)
    store_fengshui_eval(conn, listing_id, [{"rule_id": "x", "verdict": "吉", "delta": 5, "note": "n"}])
    store_fengshui_eval(conn, listing_id, [{"rule_id": "y", "verdict": "凶", "delta": -3, "note": "n2"}])
    rows = conn.execute(
        "SELECT rule_id FROM fengshui_eval WHERE listing_id = ?", (listing_id,)
    ).fetchall()
    rule_ids = [r["rule_id"] for r in rows]
    assert rule_ids == ["y"]  # 古いのは消えている


# ───────── redev ─────────


def test_redev_add_and_link(conn):
    listing_id = _insert_listing(conn)
    pid = add_redev_project(
        conn,
        RedevDraft(
            name="大橋一丁目市街地再開発",
            kind="urban_redev1",
            status="completed",
            expected_completion_year=2009,
            summary="クロスエアタワー竣工",
        ),
    )
    link_listing_to_redev(conn, listing_id, pid, confidence="high", confirmed_by_user=True)
    rows = list_redev_for_listing(conn, listing_id)
    assert len(rows) == 1
    assert rows[0]["confidence"] == "high"
    assert rows[0]["confirmed_by_user"] == 1


def test_redev_invalid_kind_rejected(conn):
    with pytest.raises(ValueError):
        add_redev_project(
            conn, RedevDraft(name="x", kind="invalid_kind", status="planned"),
        )
