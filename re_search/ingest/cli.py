"""`re ingest ...` サブコマンド群。"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from ..config import Config
from ..db import connect
from .manual import ListingDraft, add_listing

ingest_app = typer.Typer(no_args_is_help=True, help="物件データの取り込み")
console = Console()


@ingest_app.command("add")
def add_cmd(
    address: str = typer.Option(..., "--address", "-a", help="住所（例: 東京都目黒区大橋1-2-10）"),
    rent: int | None = typer.Option(None, "--rent", help="家賃（円/月）"),
    mgmt: int | None = typer.Option(None, "--mgmt", help="管理費（円/月）"),
    layout: str | None = typer.Option(None, "--layout", help="間取り（例: 1LDK）"),
    area: float | None = typer.Option(None, "--area", help="専有面積（m²）"),
    year: int | None = typer.Option(None, "--year", help="築年（西暦）"),
    walk: int | None = typer.Option(None, "--walk", help="駅徒歩（分）"),
    station: str | None = typer.Option(None, "--station", help="最寄駅"),
    structure: str | None = typer.Option(None, "--structure", help="構造（RC/SRC/木造 等）"),
    quake: str | None = typer.Option(None, "--quake", help="耐震（旧/新/2000基準 等）"),
    ownership: str | None = typer.Option(None, "--ownership", help="所有権（所有権/借地権 等）"),
    units: int | None = typer.Option(None, "--units", help="総戸数"),
    orientation: str | None = typer.Option(None, "--orientation", help="玄関方位 N/NE/E/SE/S/SW/W/NW"),
    url: str | None = typer.Option(None, "--url", help="出典URL（任意。HTMLは保存しない）"),
    source_name: str | None = typer.Option(None, "--source-name", help="出典名（任意）"),
    note: str | None = typer.Option(None, "--note", help="メモ"),
    name: str | None = typer.Option(None, "--name", help="物件名（building name; 現状は note に併記）"),
) -> None:
    """1件の物件をDBに登録する。住所はジオコードして location に紐付ける。"""
    cfg = Config.load()
    if not cfg.db_path.exists():
        console.print("[red]DB が初期化されていません。[/] 先に [bold]re init[/] を実行してください。")
        raise typer.Exit(code=1)

    note_combined = note
    if name:
        note_combined = f"[{name}] " + (note or "")

    draft = ListingDraft(
        address=address,
        layout=layout,
        area_m2=area,
        rent_jpy=rent,
        mgmt_fee_jpy=mgmt,
        building_year=year,
        walk_min=walk,
        station=station,
        structure=structure,
        earthquake_grade=quake,
        ownership=ownership,
        total_units=units,
        orientation=orientation,
        source_url=url,
        source_name=source_name or name,
        note=note_combined,
    )

    conn = connect(cfg)
    try:
        listing_id = add_listing(conn, draft, config=cfg)
        cur = conn.execute(
            "SELECT l.id, l.address, l.layout, l.rent_jpy, l.building_year, "
            "       loc.lat, loc.lon, loc.ward, loc.town_code "
            "FROM listing l LEFT JOIN location loc ON l.location_id = loc.id "
            "WHERE l.id = ?",
            (listing_id,),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    table = Table(title=f"登録完了 listing_id={listing_id}", show_header=False, box=None)
    table.add_column(style="cyan")
    table.add_column()
    if name:
        table.add_row("物件名", name)
    table.add_row("住所", row["address"])
    if row["layout"]:
        table.add_row("間取り", row["layout"])
    if row["rent_jpy"]:
        table.add_row("家賃", f"¥{row['rent_jpy']:,}")
    if row["building_year"]:
        table.add_row("築年", str(row["building_year"]))
    if row["lat"] is not None:
        table.add_row("緯度経度", f"{row['lat']:.6f}, {row['lon']:.6f}")
    else:
        table.add_row("緯度経度", "[yellow]ジオコード失敗（住所表記の調整で再登録可）[/]")
    if row["ward"]:
        table.add_row("区", f"{row['ward']} ({row['town_code']})")
    console.print(table)


@ingest_app.command("list")
def list_cmd(
    limit: int = typer.Option(20, "--limit", "-n", help="表示件数"),
) -> None:
    """登録済み物件の一覧。"""
    cfg = Config.load()
    if not cfg.db_path.exists():
        console.print("[red]DB が初期化されていません。[/]")
        raise typer.Exit(code=1)

    conn = connect(cfg)
    try:
        cur = conn.execute(
            "SELECT l.id, l.address, l.layout, l.rent_jpy, l.building_year, "
            "       l.walk_min, l.station, loc.ward "
            "FROM listing l LEFT JOIN location loc ON l.location_id = loc.id "
            "WHERE l.status = 'active' "
            "ORDER BY l.id DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        console.print("[yellow]物件はまだ登録されていません。[/]")
        return

    table = Table(title=f"物件一覧 (latest {len(rows)})")
    table.add_column("ID", justify="right")
    table.add_column("住所")
    table.add_column("間取り")
    table.add_column("家賃", justify="right")
    table.add_column("築年", justify="right")
    table.add_column("駅")
    table.add_column("徒歩", justify="right")
    for r in rows:
        table.add_row(
            str(r["id"]),
            r["address"],
            r["layout"] or "-",
            f"¥{r['rent_jpy']:,}" if r["rent_jpy"] else "-",
            str(r["building_year"]) if r["building_year"] else "-",
            r["station"] or "-",
            f"{r['walk_min']}分" if r["walk_min"] else "-",
        )
    console.print(table)
