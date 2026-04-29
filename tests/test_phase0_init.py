"""Phase 0: `re init` と DB スキーマの基本動作を検証。"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from re_search.cli import app
from re_search.config import Config
from re_search.db import connect, get_schema_version, init_schema


@pytest.fixture
def tmp_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    cache_dir = data_dir / "cache"

    monkeypatch.setattr("re_search.config.user_config_dir", lambda *_a, **_kw: str(config_dir))
    monkeypatch.setattr("re_search.config.user_data_dir", lambda *_a, **_kw: str(data_dir))

    cfg = Config.load()
    assert cfg.config_dir == config_dir
    assert cfg.data_dir == data_dir
    assert cfg.cache_dir == cache_dir
    return cfg


def test_init_creates_db_and_config(tmp_config: Config) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    assert tmp_config.db_path.exists()
    assert tmp_config.config_file.exists()


def test_schema_has_expected_tables(tmp_config: Config) -> None:
    conn = connect(tmp_config)
    try:
        init_schema(conn)
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row["name"] for row in cur.fetchall()}
    finally:
        conn.close()

    expected = {
        "source",
        "location",
        "listing",
        "listing_snapshot",
        "area_stats",
        "area_history",
        "waterway",
        "poi",
        "redevelopment_project",
        "listing_redev",
        "score",
        "fengshui_eval",
        "favorite",
        "compare_set",
        "schema_version",
    }
    missing = expected - tables
    assert not missing, f"missing tables: {missing}"


def test_schema_version_recorded(tmp_config: Config) -> None:
    conn = connect(tmp_config)
    try:
        init_schema(conn)
        v = get_schema_version(conn)
    finally:
        conn.close()
    assert v == 1


def test_init_idempotent(tmp_config: Config) -> None:
    """`re init` は冪等で、二回呼んでも壊れない。"""
    runner = CliRunner()
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output


def test_foreign_key_pragma_enabled(tmp_config: Config) -> None:
    conn = connect(tmp_config)
    try:
        init_schema(conn)
        cur = conn.execute("PRAGMA foreign_keys")
        assert cur.fetchone()[0] == 1
    finally:
        conn.close()


def test_redev_kind_check_constraint(tmp_config: Config) -> None:
    conn = connect(tmp_config)
    try:
        init_schema(conn)
        with pytest.raises(Exception):
            conn.execute(
                "INSERT INTO redevelopment_project (name, kind, status) VALUES (?, ?, ?)",
                ("テスト", "invalid_kind", "approved"),
            )
            conn.commit()
    finally:
        conn.close()


def test_version_command() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "re-search" in result.output
