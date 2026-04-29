"""`re heritage ...` サブコマンド。"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from ..config import Config
from ..db import connect
from .manual import (
    HeritageEntry,
    WaterwayEntry,
    add_heritage_entry,
    add_waterway,
    list_heritage_for_town,
    VALID_ERAS,
)

heritage_app = typer.Typer(no_args_is_help=True, help="沿革・古地名・古地形")
console = Console()


@heritage_app.command("add")
def add_cmd(
    town_code: str = typer.Option(..., "--town-code"),
    era: str = typer.Option(..., "--era", help=f"{VALID_ERAS}"),
    old_name: str = typer.Option(None, "--old-name"),
    old_use: str = typer.Option(None, "--old-use"),
    old_terrain: str = typer.Option(None, "--old-terrain"),
    source: str = typer.Option(None, "--source"),
    citation: str = typer.Option(None, "--citation"),
    note: str = typer.Option(None, "--note"),
) -> None:
    """area_history へ史実を追加。"""
    cfg = Config.load()
    conn = connect(cfg)
    try:
        entry = HeritageEntry(
            town_code=town_code, era=era,
            old_name=old_name, old_use=old_use, old_terrain=old_terrain,
            source=source, citation=citation, note=note,
        )
        eid = add_heritage_entry(conn, entry)
        console.print(f"[green]✓[/] area_history id={eid} 追加")
    finally:
        conn.close()


@heritage_app.command("waterway")
def waterway_cmd(
    name: str = typer.Option(None, "--name"),
    kind: str = typer.Option(..., "--kind", help="river/old_river/spring/pond"),
    geom: str = typer.Option(None, "--geom-wkt"),
    source: str = typer.Option(None, "--source"),
) -> None:
    """waterway を追加（旧川道など）。"""
    cfg = Config.load()
    conn = connect(cfg)
    try:
        wid = add_waterway(conn, WaterwayEntry(name=name, kind=kind, geom_wkt=geom, source=source))
        console.print(f"[green]✓[/] waterway id={wid} 追加")
    finally:
        conn.close()


@heritage_app.command("list")
def list_cmd(
    town_code: str = typer.Argument(...),
) -> None:
    """指定町丁目の史実一覧。"""
    cfg = Config.load()
    conn = connect(cfg)
    try:
        rows = list_heritage_for_town(conn, town_code)
        if not rows:
            console.print(f"[yellow]town_code={town_code} の史実なし[/]")
            return
        t = Table(title=f"area_history (town_code={town_code})")
        t.add_column("ID", justify="right")
        t.add_column("時代")
        t.add_column("旧地名")
        t.add_column("旧用途")
        t.add_column("旧地形")
        t.add_column("出典")
        for r in rows:
            t.add_row(
                str(r["id"]), r["era"], r["old_name"] or "-",
                r["old_use"] or "-", r["old_terrain"] or "-",
                r["source"] or "-",
            )
        console.print(t)
    finally:
        conn.close()
