"""緯度経度間の距離計算。

数 km 範囲なら Haversine で十分（誤差 < 0.5%）。
"""

from __future__ import annotations

import math


EARTH_RADIUS_M = 6371000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """2点間の大圏距離をメートルで返す。"""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def walk_minutes(distance_m: float, *, speed_m_per_min: float = 80.0) -> int:
    """日本の不動産表記慣行: 80m/分で徒歩分換算（端数切り上げ）。"""
    if distance_m <= 0:
        return 0
    return int(math.ceil(distance_m / speed_m_per_min))
