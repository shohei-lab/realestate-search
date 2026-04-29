"""livability（住みやすさ）スコア。

0〜100 のスコア。以下の重み付き加算で算出（説明可能）。

- 駅徒歩 (30点満点): 5分以内=30, 10分以内=20, 15分以内=10, それ以上=0
- スーパー (25点満点): 最寄り徒歩分 5分以内=20 + 1km圏内の件数*1 (max +5)
- ジム (15点満点): 最寄り徒歩分 10分以内=10 + 1km圏内の件数*2 (max +5)
- バス停 (10点満点): 最寄り徒歩分 3分以内=10, 5分以内=7, 10分以内=4
- 構造/築年 (20点満点): SRC/RC=10 + 新耐震=10
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from ..utils.distance import walk_minutes


def _score_walk(walk_min: int | None, *, top: int = 30, scale=(5, 10, 15)) -> int:
    if walk_min is None:
        return 0
    s5, s10, s15 = scale
    if walk_min <= s5:
        return top
    if walk_min <= s10:
        return int(top * 0.66)
    if walk_min <= s15:
        return int(top * 0.33)
    return 0


def _walk_min_of_nearest(pois: list[sqlite3.Row], kind: str) -> int | None:
    same = [p for p in pois if p["kind"] == kind]
    if not same:
        return None
    nearest = min(same, key=lambda r: r["distance_m"])
    return walk_minutes(nearest["distance_m"])


def _count_kind(pois: list[sqlite3.Row], kind: str) -> int:
    return sum(1 for p in pois if p["kind"] == kind)


def compute_livability(
    listing: sqlite3.Row, pois: list[sqlite3.Row]
) -> tuple[float, dict[str, Any]]:
    """listing 1行と poi 行群から livability スコアを算出。"""
    breakdown: dict[str, Any] = {}

    # 1. 駅徒歩
    station_pts = _score_walk(listing["walk_min"], top=30, scale=(5, 10, 15))
    breakdown["station"] = {
        "points": station_pts,
        "max": 30,
        "walk_min": listing["walk_min"],
        "station": listing["station"],
    }

    # 2. スーパー
    super_walk = _walk_min_of_nearest(pois, "super")
    super_count = _count_kind(pois, "super")
    super_pts = 0
    if super_walk is not None:
        if super_walk <= 5:
            super_pts += 20
        elif super_walk <= 10:
            super_pts += 12
        elif super_walk <= 15:
            super_pts += 6
    super_pts += min(super_count, 5)
    super_pts = min(super_pts, 25)
    breakdown["super"] = {
        "points": super_pts,
        "max": 25,
        "nearest_walk_min": super_walk,
        "count": super_count,
    }

    # 3. ジム
    gym_walk = _walk_min_of_nearest(pois, "gym")
    gym_count = _count_kind(pois, "gym")
    gym_pts = 0
    if gym_walk is not None:
        if gym_walk <= 5:
            gym_pts += 10
        elif gym_walk <= 10:
            gym_pts += 7
        elif gym_walk <= 15:
            gym_pts += 4
    gym_pts += min(gym_count * 2, 5)
    gym_pts = min(gym_pts, 15)
    breakdown["gym"] = {
        "points": gym_pts,
        "max": 15,
        "nearest_walk_min": gym_walk,
        "count": gym_count,
    }

    # 4. バス停
    bus_walk = _walk_min_of_nearest(pois, "busstop")
    bus_pts = 0
    if bus_walk is not None:
        if bus_walk <= 3:
            bus_pts = 10
        elif bus_walk <= 5:
            bus_pts = 7
        elif bus_walk <= 10:
            bus_pts = 4
    breakdown["bus"] = {"points": bus_pts, "max": 10, "nearest_walk_min": bus_walk}

    # 5. 構造/築年
    structure = (listing["structure"] or "").upper()
    eq = listing["earthquake_grade"] or ""
    structure_pts = 0
    if structure in ("RC", "SRC"):
        structure_pts += 10
    elif structure:
        structure_pts += 5
    if "新耐震" in eq or "2000" in eq:
        structure_pts += 10
    structure_pts = min(structure_pts, 20)
    breakdown["structure"] = {
        "points": structure_pts,
        "max": 20,
        "structure": listing["structure"],
        "earthquake": listing["earthquake_grade"],
    }

    total = station_pts + super_pts + gym_pts + bus_pts + structure_pts
    breakdown["total"] = total
    breakdown["max_total"] = 100
    return float(total), breakdown


def store_score(
    conn: sqlite3.Connection,
    listing_id: int,
    kind: str,
    value: float,
    breakdown: dict[str, Any],
) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO score (listing_id, kind, value, breakdown_json, scored_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(listing_id, kind) DO UPDATE SET
          value=excluded.value,
          breakdown_json=excluded.breakdown_json,
          scored_at=excluded.scored_at
        """,
        (listing_id, kind, value, json.dumps(breakdown, ensure_ascii=False), now),
    )
    conn.commit()
