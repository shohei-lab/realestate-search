"""FastAPI アプリ。SQLite を読み取り専用で開いて表示する。

ルート:
- GET /                 物件一覧（カードグリッド + 4軸スコア）
- GET /listing/{id}     物件詳細（メタ + 地図 + POI + 再開発 + 沿革 + 風水 + スコア）
- GET /api/listing/{id}/pois.json  地図ピン用JSON
"""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from ..config import Config

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    """SQLite を読み取り専用URIで開く。WebUIから誤書込しないため。"""
    uri = f"file:{db_path}?mode=ro"
    c = sqlite3.connect(uri, uri=True, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def _walk_minutes(distance_m: float | None) -> int | None:
    if distance_m is None or distance_m <= 0:
        return None
    return int(math.ceil(distance_m / 80.0))


def create_app(config: Config | None = None) -> FastAPI:
    cfg = config or Config.load()
    app = FastAPI(title="re-search WebUI", version="0.0.1")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters["walkmin"] = _walk_minutes
    templates.env.filters["intdistance"] = lambda v: f"{int(v)}m" if v is not None else "-"
    templates.env.filters["yen"] = lambda v: f"¥{v:,}" if v else "-"

    KIND_LABEL = {
        "super": ("🛒", "スーパー", "#22c55e"),
        "gym": ("💪", "ジム", "#a855f7"),
        "busstop": ("🚌", "バス停", "#3b82f6"),
        "station": ("🚉", "駅", "#ef4444"),
    }

    SCORE_LABEL = {
        "livability": "🏠 住みやすさ",
        "locality": "📍 地域力",
        "heritage": "🏯 沿革・地相",
        "fengshui": "🧭 風水",
    }

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        with _connect_ro(cfg.db_path) as c:
            rows = c.execute(
                """
                SELECT l.*, loc.lat, loc.lon, loc.ward
                FROM listing l
                LEFT JOIN location loc ON l.location_id = loc.id
                ORDER BY l.id DESC
                """
            ).fetchall()
            scores: dict[int, dict[str, float]] = {}
            for r in c.execute("SELECT listing_id, kind, value FROM score").fetchall():
                scores.setdefault(r["listing_id"], {})[r["kind"]] = r["value"]
            poi_summary: dict[int, dict[str, Any]] = {}
            for r in c.execute(
                """
                SELECT l.id AS lid, p.kind, COUNT(*) AS n, MIN(p.distance_m) AS nearest
                FROM listing l
                JOIN poi p ON p.location_id = l.location_id
                GROUP BY l.id, p.kind
                """
            ).fetchall():
                d = poi_summary.setdefault(r["lid"], {})
                d[r["kind"]] = {"n": r["n"], "nearest": r["nearest"]}
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "listings": rows,
                "scores": scores,
                "poi_summary": poi_summary,
                "score_label": SCORE_LABEL,
            },
        )

    @app.get("/listing/{listing_id}", response_class=HTMLResponse)
    def detail(request: Request, listing_id: int) -> HTMLResponse:
        with _connect_ro(cfg.db_path) as c:
            listing = c.execute(
                """
                SELECT l.*, loc.lat AS lat, loc.lon AS lon,
                       loc.ward, loc.town_code, loc.terrain_class,
                       s.name AS source_name, s.url AS source_url
                FROM listing l
                LEFT JOIN location loc ON l.location_id = loc.id
                LEFT JOIN source s ON l.source_id = s.id
                WHERE l.id = ?
                """,
                (listing_id,),
            ).fetchone()
            if listing is None:
                raise HTTPException(status_code=404, detail=f"listing_id={listing_id} not found")

            pois = []
            if listing["location_id"] is not None:
                pois = c.execute(
                    "SELECT * FROM poi WHERE location_id = ? ORDER BY kind, distance_m",
                    (listing["location_id"],),
                ).fetchall()

            scores: dict[str, dict[str, Any]] = {}
            for r in c.execute(
                "SELECT * FROM score WHERE listing_id = ?", (listing_id,)
            ):
                scores[r["kind"]] = {
                    "value": r["value"],
                    "breakdown": json.loads(r["breakdown_json"] or "{}"),
                    "scored_at": r["scored_at"],
                }

            heritage = []
            if listing["town_code"]:
                heritage = c.execute(
                    "SELECT * FROM area_history WHERE town_code = ? ORDER BY era",
                    (listing["town_code"],),
                ).fetchall()

            redev = c.execute(
                """
                SELECT r.*, lr.confidence, lr.confirmed_by_user, lr.note AS link_note
                FROM redevelopment_project r
                JOIN listing_redev lr ON r.id = lr.project_id
                WHERE lr.listing_id = ?
                ORDER BY r.expected_completion_year DESC
                """,
                (listing_id,),
            ).fetchall()

            fengshui_evals = c.execute(
                "SELECT * FROM fengshui_eval WHERE listing_id = ? ORDER BY id",
                (listing_id,),
            ).fetchall()

            waterways = c.execute("SELECT * FROM waterway ORDER BY id").fetchall()

        pois_by_kind: dict[str, list] = {}
        for p in pois:
            pois_by_kind.setdefault(p["kind"], []).append(p)

        return templates.TemplateResponse(
            request,
            "listing.html",
            {
                "listing": listing,
                "pois": pois,
                "pois_by_kind": pois_by_kind,
                "scores": scores,
                "heritage": heritage,
                "redev": redev,
                "fengshui_evals": fengshui_evals,
                "waterways": waterways,
                "score_label": SCORE_LABEL,
                "kind_label": KIND_LABEL,
            },
        )

    @app.get("/api/listing/{listing_id}/pois.json")
    def pois_json(listing_id: int) -> JSONResponse:
        with _connect_ro(cfg.db_path) as c:
            listing = c.execute(
                "SELECT l.id AS id, l.location_id, l.address, loc.lat AS lat, loc.lon AS lon "
                "FROM listing l LEFT JOIN location loc ON l.location_id = loc.id "
                "WHERE l.id = ?",
                (listing_id,),
            ).fetchone()
            if listing is None:
                raise HTTPException(status_code=404)
            pois = []
            if listing["location_id"] is not None:
                rows = c.execute(
                    "SELECT id, kind, name, brand, lat, lon, distance_m, osm_type "
                    "FROM poi WHERE location_id = ?",
                    (listing["location_id"],),
                ).fetchall()
                pois = [dict(r) for r in rows]
        return JSONResponse(
            {
                "listing": {
                    "id": listing["id"],
                    "address": listing["address"],
                    "lat": listing["lat"],
                    "lon": listing["lon"],
                },
                "pois": pois,
            }
        )

    return app


# uvicorn が文字列で読み込めるようにモジュールレベルで露出（DBが無い環境でも import は通すため遅延）
def _module_app():
    try:
        return create_app()
    except Exception:
        # DBが無い等の状況でもimport自体は通す
        return FastAPI()

app = _module_app()
