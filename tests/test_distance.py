"""距離計算の単体テスト。"""

from __future__ import annotations

import math

import pytest

from re_search.utils.distance import haversine_m, walk_minutes


def test_haversine_zero():
    assert haversine_m(35.0, 139.0, 35.0, 139.0) == 0.0


def test_haversine_tokyo_to_osaka_approx():
    # 東京駅 〜 新大阪駅 ≈ 396km（直線）
    d = haversine_m(35.681236, 139.767125, 34.733457, 135.499905)
    assert 390_000 < d < 410_000


def test_haversine_short_distance():
    # 100m 程度の差
    d = haversine_m(35.6517, 139.6889, 35.6517, 139.6900)
    assert 95 < d < 105


def test_walk_minutes_basic():
    assert walk_minutes(80) == 1
    assert walk_minutes(800) == 10
    assert walk_minutes(81) == 2  # 切り上げ


def test_walk_minutes_zero():
    assert walk_minutes(0) == 0
    assert walk_minutes(-5) == 0
