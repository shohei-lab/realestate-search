"""heritage スコア計算（沿革の厚み）。

「面白い史実」の件数 × 種別重みで 0〜100 化。
- 旧地名 (old_name): +15 / 件 (max 30)
- 旧用途 (old_use):  +20 / 件 (max 40)
- 旧地形 (old_terrain): +15 / 件 (max 30)

倫理ガード: 差別的旧地名や被差別関連の history は「機械加点に使わない」運用とし、
score 計算からは除外する。具体的にはエントリの `note` に '差別' や 'sensitive'
が含まれる場合は飛ばす。
"""

from __future__ import annotations

import sqlite3
from typing import Any


SENSITIVE_MARKERS = ("差別", "sensitive", "被差別")


def _is_sensitive(row: sqlite3.Row) -> bool:
    note = (row["note"] or "")
    return any(m in note for m in SENSITIVE_MARKERS)


def compute_heritage(
    conn: sqlite3.Connection, listing: sqlite3.Row
) -> tuple[float, dict[str, Any]]:
    breakdown: dict[str, Any] = {"items": []}

    # listing -> location -> town_code
    if listing["location_id"] is None:
        breakdown["comment"] = "ジオコード未完了のため計算不可"
        breakdown["max_total"] = 100
        return 0.0, breakdown

    cur = conn.execute("SELECT town_code FROM location WHERE id = ?", (listing["location_id"],))
    loc = cur.fetchone()
    if loc is None or not loc["town_code"]:
        breakdown["comment"] = "town_code 未設定"
        breakdown["max_total"] = 100
        return 0.0, breakdown

    town_code = loc["town_code"]
    breakdown["town_code"] = town_code

    cur = conn.execute(
        "SELECT * FROM area_history WHERE town_code = ? ORDER BY era",
        (town_code,),
    )
    rows = cur.fetchall()

    name_pts = 0
    use_pts = 0
    terrain_pts = 0
    for r in rows:
        if _is_sensitive(r):
            breakdown["items"].append({"era": r["era"], "skipped": "sensitive"})
            continue
        item: dict[str, Any] = {"era": r["era"]}
        if r["old_name"]:
            name_pts += 15
            item["old_name"] = r["old_name"]
        if r["old_use"]:
            use_pts += 20
            item["old_use"] = r["old_use"]
        if r["old_terrain"]:
            terrain_pts += 15
            item["old_terrain"] = r["old_terrain"]
        breakdown["items"].append(item)

    name_pts = min(name_pts, 30)
    use_pts = min(use_pts, 40)
    terrain_pts = min(terrain_pts, 30)
    total = name_pts + use_pts + terrain_pts
    breakdown["old_name_pts"] = name_pts
    breakdown["old_use_pts"] = use_pts
    breakdown["old_terrain_pts"] = terrain_pts
    breakdown["total"] = total
    breakdown["max_total"] = 100
    breakdown["comment"] = f"史実 {len(rows)} 件 / 加点対象 {len(breakdown['items'])} 件"
    return float(total), breakdown
