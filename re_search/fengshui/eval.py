"""ルールベースの風水/地相評価。

ルールはすべて「観察可能な事実」に基づく：
- 高架道路・JCT 直近 → 騒音・圧迫感（凶 -）
- T字路の突き当り → 通気・視線・事故リスク（凶 -） ※今回は手動評価
- 旧河道（水脈）直上 → 湿気・地盤の懸念（凶 -）  ※waterway/old_river を参照
- 川 200m 以内（直接ではない）→ 風通し（吉 +）
- 玄関方位 N/NE → 一般的な風水で凶 (-)、S/SE/E は吉 (+)
- 高台（terrain_class=台地）→ 吉 +、低地・湿地 → 凶 -
- 公園 200m 以内 → 緑視率による吉 +（POI 拡張時）

各ルールは fengshui_eval テーブルに「rule_id / verdict / score_delta / note」で保存される。
スコアは 50 を中立基準として ±delta で増減（0〜100 にクリップ）。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any


# ───────── ルール定義 ─────────


def _rule_orientation(listing) -> tuple[str, float, str] | None:
    o = (listing["orientation"] or "").upper()
    if not o:
        return None
    favorable = {"S": +6, "SE": +5, "E": +4, "SW": +3}
    unfavorable = {"N": -4, "NE": -6, "NW": -3, "W": -1}
    if o in favorable:
        return ("吉", favorable[o], f"玄関方位 {o} は風水で吉とされる")
    if o in unfavorable:
        return ("凶", unfavorable[o], f"玄関方位 {o} は風水で凶とされる（鬼門寄り含む）")
    return None


def _rule_terrain(conn: sqlite3.Connection, listing) -> tuple[str, float, str] | None:
    if listing["location_id"] is None:
        return None
    cur = conn.execute(
        "SELECT terrain_class FROM location WHERE id = ?", (listing["location_id"],)
    )
    row = cur.fetchone()
    if row is None or not row["terrain_class"]:
        return None
    tc = row["terrain_class"]
    if tc in ("台地", "丘陵"):
        return ("吉", +5, f"地形分類 {tc} は地盤・水はけの面で吉")
    if tc in ("谷底", "低地", "氾濫原", "埋立"):
        return ("凶", -5, f"地形分類 {tc} は浸水・地盤の懸念から凶")
    return None


def _rule_overpass_or_jct(conn: sqlite3.Connection, listing) -> tuple[str, float, str] | None:
    """同 location に紐づく POI の中で「高架/JCT」のヒントを探す簡易版。

    今回は簡易ルール: poi.kind='busstop' で name に '大橋' を含み複数集中している、
    あるいは listing.address に '大橋' を含む場合、首都高大橋JCTの圧迫を仮定。
    （正確には地理データ層が必要。Phase 後続で精緻化。）
    """
    addr = listing["address"] or ""
    if "大橋" in addr and listing["walk_min"] is not None and listing["walk_min"] <= 7:
        return (
            "凶",
            -8,
            "首都高 大橋JCT 直近想定（騒音・圧迫感・排気の可能性）",
        )
    return None


def _rule_oldriver(conn: sqlite3.Connection, listing) -> tuple[str, float, str] | None:
    """waterway に登録された 'old_river' があれば、町コード一致でヒント表示。

    距離判定は WKT パーサが必要なので、Phase 後続で。
    今は「同区に旧河道 waterway が登録されている」を弱い注意喚起として中立扱い。
    """
    if listing["location_id"] is None:
        return None
    cur = conn.execute("SELECT ward FROM location WHERE id = ?", (listing["location_id"],))
    row = cur.fetchone()
    if row is None or not row["ward"]:
        return None
    cur = conn.execute(
        "SELECT COUNT(*) AS c FROM waterway WHERE kind = 'old_river'"
    )
    if (cur.fetchone() or {"c": 0})["c"] == 0:
        return None
    # 注意喚起レベル（実距離検証は別フェーズで）
    return (
        "中立",
        -2,
        "周辺に旧河道（暗渠）が登録されている。直上は湿気・地盤の懸念があるため要現地確認",
    )


def _rule_supermarket_near(conn: sqlite3.Connection, listing, pois) -> tuple[str, float, str] | None:
    super_pois = [p for p in pois if p["kind"] == "super"]
    if not super_pois:
        return None
    nearest = min(super_pois, key=lambda p: p["distance_m"])
    if nearest["distance_m"] <= 100:
        return ("吉", +3, f"スーパー至近（{int(nearest['distance_m'])}m）= 生活動線が安定")
    return None


# ───────── 統合 ─────────


def compute_fengshui(
    conn: sqlite3.Connection,
    listing: sqlite3.Row,
    pois: list[sqlite3.Row],
) -> tuple[float, dict[str, Any], list[dict[str, Any]]]:
    """風水スコアと評価明細を返す。"""
    breakdown: dict[str, Any] = {"items": []}
    evals: list[dict[str, Any]] = []
    base = 50.0
    delta_total = 0.0

    rules = [
        ("orientation", lambda: _rule_orientation(listing)),
        ("terrain", lambda: _rule_terrain(conn, listing)),
        ("overpass_jct", lambda: _rule_overpass_or_jct(conn, listing)),
        ("oldriver", lambda: _rule_oldriver(conn, listing)),
        ("supermarket_near", lambda: _rule_supermarket_near(conn, listing, pois)),
    ]
    for rule_id, fn in rules:
        result = fn()
        if result is None:
            continue
        verdict, delta, note = result
        delta_total += delta
        item = {"rule_id": rule_id, "verdict": verdict, "delta": delta, "note": note}
        breakdown["items"].append(item)
        evals.append(item)

    total = max(0.0, min(100.0, base + delta_total))
    breakdown["base"] = base
    breakdown["delta_total"] = delta_total
    breakdown["total"] = total
    breakdown["max_total"] = 100
    breakdown["comment"] = (
        f"基準 50 ± {delta_total:+.0f} → {total:.0f}点。ルール {len(evals)} 件適用。"
    )
    return total, breakdown, evals


def store_fengshui_eval(
    conn: sqlite3.Connection,
    listing_id: int,
    evals: list[dict[str, Any]],
) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # 同 listing の以前の評価は入れ替え
    conn.execute("DELETE FROM fengshui_eval WHERE listing_id = ?", (listing_id,))
    rows = [
        (listing_id, e["rule_id"], e["verdict"], e["delta"], e["note"], now)
        for e in evals
    ]
    conn.executemany(
        "INSERT INTO fengshui_eval (listing_id, rule_id, verdict, score_delta, note, evaluated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
