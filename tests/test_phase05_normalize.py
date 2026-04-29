"""Phase 0.5: 住所正規化の純関数テスト。"""

from __future__ import annotations

import pytest

from re_search.geo.normalize import (
    kanji_numbers_to_arabic,
    normalize_address,
    parse_chome_banchi,
)


def test_normalize_zenkaku_to_hankaku():
    assert normalize_address("東京都目黒区大橋１丁目２－１０") == "東京都目黒区大橋1丁目2-10"


def test_normalize_strip_whitespace():
    assert normalize_address("  東京都  渋谷区 代々木 1-2-3  ") == "東京都渋谷区代々木1-2-3"


def test_normalize_default_pref_added():
    assert normalize_address("目黒区大橋1-2-10").startswith("東京都")


def test_normalize_keeps_existing_pref():
    assert normalize_address("神奈川県横浜市中区日本大通1") == "神奈川県横浜市中区日本大通1"


def test_normalize_pref_disabled():
    assert normalize_address("目黒区大橋1-2-10", default_pref=None) == "目黒区大橋1-2-10"


def test_normalize_dash_family_unified():
    # ‐ ‒ – — ― ー － は全て - に統一
    raw = "東京都目黒区大橋1‐2–10"
    assert normalize_address(raw) == "東京都目黒区大橋1-2-10"


def test_kanji_numbers_compound():
    assert kanji_numbers_to_arabic("二十三") == "23"
    assert kanji_numbers_to_arabic("百二十三") == "123"


def test_kanji_numbers_dont_break_placenames():
    # 単漢字数字や単独単位は地名を壊さないよう保持
    assert kanji_numbers_to_arabic("千代田") == "千代田"
    assert kanji_numbers_to_arabic("百人町") == "百人町"
    assert kanji_numbers_to_arabic("十条") == "十条"
    assert kanji_numbers_to_arabic("一橋") == "一橋"


def test_kanji_compound_in_address():
    # "二十三番地" のような複合は変換される
    assert "23番地" in kanji_numbers_to_arabic("世田谷区代田二十三番地")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("東京都目黒区大橋1丁目2-10", ("東京都目黒区大橋", 1, 2, 10)),
        ("東京都渋谷区代々木1-2-3", ("東京都渋谷区代々木", 1, 2, 3)),
        ("東京都新宿区西新宿2丁目8番1号", ("東京都新宿区西新宿", 2, 8, 1)),
        ("東京都港区六本木6", ("東京都港区六本木", 6, None, None)),
    ],
)
def test_parse_chome_banchi(raw, expected):
    norm = normalize_address(raw)
    assert parse_chome_banchi(norm) == expected
