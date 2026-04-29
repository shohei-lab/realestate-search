"""`re geocode` サブコマンド。"""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from ..config import Config
from ..db import connect
from .geocode import Geocoder
from .normalize import normalize_address

geo_app = typer.Typer(no_args_is_help=True, help="住所正規化・ジオコーディング")
console = Console()


@geo_app.command("normalize")
def normalize_cmd(address: str = typer.Argument(..., help="正規化したい住所文字列")) -> None:
    """住所文字列を正規化して表示（API呼び出しなし）。"""
    console.print(normalize_address(address))


@geo_app.command("lookup")
def lookup_cmd(
    address: str = typer.Argument(..., help="ジオコードしたい住所"),
    no_cache: bool = typer.Option(False, "--no-cache", help="キャッシュを無視してAPIを呼ぶ"),
    json_output: bool = typer.Option(False, "--json", help="JSON で出力"),
) -> None:
    """住所をジオコードし、結果を表示する。"""
    cfg = Config.load()
    if not cfg.db_path.exists():
        console.print("[red]DB が初期化されていません。[/] 先に [bold]re init[/] を実行してください。")
        raise typer.Exit(code=1)

    conn = connect(cfg)
    try:
        geocoder = Geocoder(conn, config=cfg)
        try:
            result = geocoder.geocode(address, use_cache=not no_cache)
        finally:
            geocoder.close()
    finally:
        conn.close()

    if json_output:
        console.print_json(
            json.dumps(
                {
                    "raw_address": result.raw_address,
                    "normalized": result.normalized,
                    "title": result.title,
                    "lat": result.lat,
                    "lon": result.lon,
                    "address_code": result.address_code,
                    "ward": result.ward,
                    "city_code": result.city_code,
                    "is_hit": result.is_hit,
                },
                ensure_ascii=False,
            )
        )
        return

    table = Table(title=f"Geocode: {address}", show_header=False, box=None)
    table.add_column(style="cyan")
    table.add_column()
    table.add_row("正規化", result.normalized)
    table.add_row("API title", result.title or "[dim]-[/]")
    if result.is_hit:
        table.add_row("緯度経度", f"{result.lat:.6f}, {result.lon:.6f}")
    else:
        table.add_row("緯度経度", "[red]ヒットなし[/]")
    table.add_row("区", result.ward or "[dim]-[/]")
    table.add_row("市区町村コード", result.city_code or "[dim]-[/]")
    table.add_row("addressCode (API)", result.address_code or "[dim]-[/]")
    console.print(table)
