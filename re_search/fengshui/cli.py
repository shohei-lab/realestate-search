"""`re fengshui ...` サブコマンド。"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from ..config import Config
from ..db import connect

fengshui_app = typer.Typer(no_args_is_help=True, help="風水・地相評価")
console = Console()


@fengshui_app.command("show")
def show_cmd(
    listing_id: int = typer.Argument(...),
) -> None:
    """保存済の風水評価を表示。"""
    cfg = Config.load()
    conn = connect(cfg)
    try:
        cur = conn.execute(
            "SELECT * FROM fengshui_eval WHERE listing_id = ? ORDER BY id",
            (listing_id,),
        )
        rows = cur.fetchall()
        if not rows:
            console.print(
                f"[yellow]listing_id={listing_id} の評価はまだ計算されていません。[/]"
                " [bold]re score compute -l N -k fengshui[/] を実行してください。"
            )
            return
        t = Table(title=f"風水評価 (listing_id={listing_id})")
        t.add_column("rule_id")
        t.add_column("判定")
        t.add_column("Δ", justify="right")
        t.add_column("コメント")
        for r in rows:
            t.add_row(
                r["rule_id"],
                r["verdict"],
                f"{r['score_delta']:+.0f}",
                r["note"] or "",
            )
        console.print(t)
    finally:
        conn.close()
