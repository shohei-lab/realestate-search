"""`re score ...` サブコマンド。"""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from ..config import Config
from ..db import connect
from ..fengshui.eval import compute_fengshui, store_fengshui_eval
from ..heritage.score import compute_heritage
from .livability import compute_livability, store_score

score_app = typer.Typer(no_args_is_help=True, help="スコア計算（livability/heritage/fengshui）")
console = Console()


def _fetch_listing(conn, listing_id: int):
    cur = conn.execute("SELECT * FROM listing WHERE id = ?", (listing_id,))
    row = cur.fetchone()
    if row is None:
        console.print(f"[red]listing_id={listing_id} が見つかりません[/]")
        raise typer.Exit(code=1)
    return row


def _fetch_pois(conn, location_id: int | None):
    if location_id is None:
        return []
    cur = conn.execute(
        "SELECT * FROM poi WHERE location_id = ? ORDER BY kind, distance_m",
        (location_id,),
    )
    return cur.fetchall()


@score_app.command("compute")
def compute_cmd(
    listing_id: int = typer.Option(..., "--listing-id", "-l"),
    kinds: list[str] = typer.Option(
        ["livability", "heritage", "fengshui"],
        "--kind",
        "-k",
        help="計算するスコア種別（複数可）",
    ),
) -> None:
    """指定 listing のスコアを計算して保存。"""
    cfg = Config.load()
    conn = connect(cfg)
    try:
        listing = _fetch_listing(conn, listing_id)
        pois = _fetch_pois(conn, listing["location_id"])

        results: list[tuple[str, float, dict]] = []

        if "livability" in kinds:
            v, b = compute_livability(listing, pois)
            store_score(conn, listing_id, "livability", v, b)
            results.append(("livability", v, b))

        if "heritage" in kinds:
            v, b = compute_heritage(conn, listing)
            store_score(conn, listing_id, "heritage", v, b)
            results.append(("heritage", v, b))

        if "fengshui" in kinds:
            v, b, evals = compute_fengshui(conn, listing, pois)
            store_score(conn, listing_id, "fengshui", v, b)
            store_fengshui_eval(conn, listing_id, evals)
            results.append(("fengshui", v, b))

        t = Table(title=f"スコア結果 (listing_id={listing_id})")
        t.add_column("種別")
        t.add_column("点数", justify="right")
        t.add_column("満点", justify="right")
        t.add_column("コメント")
        for kind, v, b in results:
            comment = b.get("comment") or ""
            t.add_row(kind, f"{v:.0f}", str(b.get("max_total", 100)), comment)
        console.print(t)
    finally:
        conn.close()


@score_app.command("show")
def show_cmd(listing_id: int = typer.Argument(...)) -> None:
    """保存済スコアを表示。"""
    cfg = Config.load()
    conn = connect(cfg)
    try:
        cur = conn.execute(
            "SELECT kind, value, breakdown_json, scored_at FROM score WHERE listing_id = ?",
            (listing_id,),
        )
        rows = cur.fetchall()
        if not rows:
            console.print(f"[yellow]listing_id={listing_id} のスコアはまだ計算されていません。[/]")
            return
        for r in rows:
            t = Table(title=f"{r['kind']} = {r['value']:.0f}")
            t.add_column("項目")
            t.add_column("内訳")
            b = json.loads(r["breakdown_json"] or "{}")
            for k, v in b.items():
                t.add_row(k, json.dumps(v, ensure_ascii=False))
            console.print(t)
    finally:
        conn.close()
