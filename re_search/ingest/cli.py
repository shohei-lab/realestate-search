"""`re ingest ...` サブコマンド群。"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..config import Config
from ..db import connect
from ..geo.geocode import Geocoder
from .manual import ListingDraft, add_listing
from .osm import DEFAULT_RADII, OverpassClient, store_pois
from .poi import POIDraft, add_manual_poi

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


@ingest_app.command("poi-add")
def poi_add_cmd(
    listing_id: int = typer.Option(..., "--listing-id", "-l"),
    kind: str = typer.Option(..., "--kind", help="super/gym/busstop/station/..."),
    name: str = typer.Option(..., "--name"),
    address: str = typer.Option(..., "--address", help="POI の住所（ジオコードして距離算出）"),
    brand: str = typer.Option(None, "--brand"),
    note: str = typer.Option(None, "--note"),
) -> None:
    """OSM 未登録のPOIを手動追加（osm_type='manual' で保存され OSM 再取得で消えない）。"""
    cfg = Config.load()
    if not cfg.db_path.exists():
        console.print("[red]DB が初期化されていません。[/]")
        raise typer.Exit(code=1)

    conn = connect(cfg)
    geocoder = Geocoder(conn=conn, config=cfg)
    try:
        draft = POIDraft(kind=kind, name=name, address=address, brand=brand, note=note)
        try:
            poi_id, geo, distance = add_manual_poi(conn, listing_id, draft, geocoder=geocoder)
        except ValueError as e:
            console.print(f"[red]✗ {e}[/]")
            raise typer.Exit(code=1)
        from ..utils.distance import walk_minutes
        console.print(
            f"[green]✓[/] POI id={poi_id} を追加: {name} "
            f"({geo.lat:.5f}, {geo.lon:.5f}) → 物件まで {int(distance)}m / 徒歩{walk_minutes(distance)}分"
        )
    finally:
        geocoder.close()
        conn.close()


@ingest_app.command("osm")
def osm_cmd(
    listing_id: int = typer.Option(..., "--listing-id", "-l", help="対象 listing_id"),
    super_radius: int = typer.Option(DEFAULT_RADII["super"], "--super-radius", help="スーパー探索半径(m)"),
    gym_radius: int = typer.Option(DEFAULT_RADII["gym"], "--gym-radius", help="ジム探索半径(m)"),
    bus_radius: int = typer.Option(DEFAULT_RADII["busstop"], "--bus-radius", help="バス停探索半径(m)"),
    skip_super: bool = typer.Option(False, "--skip-super"),
    skip_gym: bool = typer.Option(False, "--skip-gym"),
    skip_bus: bool = typer.Option(False, "--skip-bus"),
) -> None:
    """指定物件の周辺POI（スーパー・ジム・バス停）を Overpass から取得して保存。"""
    cfg = Config.load()
    if not cfg.db_path.exists():
        console.print("[red]DB が初期化されていません。[/] 先に [bold]re init[/] を実行してください。")
        raise typer.Exit(code=1)

    conn = connect(cfg)
    try:
        cur = conn.execute(
            "SELECT l.id, l.address, l.location_id, loc.lat, loc.lon "
            "FROM listing l LEFT JOIN location loc ON l.location_id = loc.id "
            "WHERE l.id = ?",
            (listing_id,),
        )
        row = cur.fetchone()
        if row is None:
            console.print(f"[red]listing_id={listing_id} が見つかりません[/]")
            raise typer.Exit(code=1)
        if row["lat"] is None or row["lon"] is None or row["location_id"] is None:
            console.print(
                f"[red]listing_id={listing_id} に座標がありません。[/]"
                " ジオコードに失敗している可能性があります。"
            )
            raise typer.Exit(code=1)

        radii: dict[str, int] = {}
        if not skip_super:
            radii["super"] = super_radius
        if not skip_gym:
            radii["gym"] = gym_radius
        if not skip_bus:
            radii["busstop"] = bus_radius

        console.print(
            f"[cyan]Overpass 問い合わせ中:[/] {row['address']} "
            f"(lat={row['lat']:.5f}, lon={row['lon']:.5f}) "
            f"radii={radii}"
        )

        ovp = OverpassClient(config=cfg)
        try:
            pois = ovp.fetch_pois(row["lat"], row["lon"], radii=radii)
        finally:
            ovp.close()

        n = store_pois(conn, row["location_id"], pois)
        console.print(f"[green]✓[/] {n} 件のPOIを保存しました。")

        # 概要テーブル: kind ごとに最寄り3件を表示
        for kind, label in [("super", "🛒 スーパー"), ("gym", "💪 ジム"), ("busstop", "🚌 バス停")]:
            same = [p for p in pois if p.kind == kind]
            if not same:
                console.print(f"\n[dim]{label}: 該当なし[/]")
                continue
            t = Table(title=f"{label}（最寄り {min(3, len(same))} 件 / 全{len(same)}件）")
            t.add_column("名前")
            t.add_column("ブランド")
            t.add_column("距離", justify="right")
            t.add_column("徒歩", justify="right")
            from ..utils.distance import walk_minutes
            for p in same[:3]:
                t.add_row(
                    p.name or "[dim]?[/]",
                    p.brand or "-",
                    f"{int(p.distance_m)}m",
                    f"{walk_minutes(p.distance_m)}分",
                )
            console.print(t)
    finally:
        conn.close()


@ingest_app.command("show")
def show_cmd(
    listing_id: int = typer.Argument(..., help="表示する listing_id"),
) -> None:
    """物件の全フィールド + 周辺POI をまとめて表示。"""
    cfg = Config.load()
    if not cfg.db_path.exists():
        console.print("[red]DB が初期化されていません。[/]")
        raise typer.Exit(code=1)

    conn = connect(cfg)
    try:
        cur = conn.execute(
            """
            SELECT l.*, loc.lat, loc.lon, loc.ward, loc.town_code, loc.id AS loc_id,
                   s.name AS source_name, s.url AS source_url
            FROM listing l
            LEFT JOIN location loc ON l.location_id = loc.id
            LEFT JOIN source s ON l.source_id = s.id
            WHERE l.id = ?
            """,
            (listing_id,),
        )
        row = cur.fetchone()
        if row is None:
            console.print(f"[red]listing_id={listing_id} が見つかりません[/]")
            raise typer.Exit(code=1)

        meta = Table.grid(padding=(0, 2))
        meta.add_column(style="cyan", no_wrap=True)
        meta.add_column()
        meta.add_row("ID", str(row["id"]))
        meta.add_row("物件名 / 出典", row["source_name"] or "-")
        meta.add_row("住所", row["address"])
        if row["lat"] is not None:
            meta.add_row("緯度経度", f"{row['lat']:.6f}, {row['lon']:.6f}")
        if row["ward"]:
            meta.add_row("区 (コード)", f"{row['ward']} ({row['town_code']})")
        if row["layout"]:
            meta.add_row("間取り / 面積", f"{row['layout']} / {row['area_m2']}㎡" if row["area_m2"] else row["layout"])
        if row["rent_jpy"]:
            meta.add_row(
                "家賃 / 管理費",
                f"¥{row['rent_jpy']:,}" + (f" + ¥{row['mgmt_fee_jpy']:,}" if row["mgmt_fee_jpy"] else ""),
            )
        if row["station"]:
            meta.add_row("駅 / 徒歩", f"{row['station']} {row['walk_min'] or '?'}分")
        if row["building_year"]:
            meta.add_row("築年 / 構造", f"{row['building_year']} / {row['structure'] or '-'}")
        if row["earthquake_grade"]:
            meta.add_row("耐震", row["earthquake_grade"])
        if row["total_units"]:
            meta.add_row("総戸数", str(row["total_units"]))
        if row["orientation"]:
            meta.add_row("玄関方位", row["orientation"])
        if row["source_url"]:
            meta.add_row("出典URL", row["source_url"])
        console.print(Panel(meta, title=f"listing_id={row['id']}", title_align="left"))

        # POI 表示
        if row["loc_id"]:
            cur = conn.execute(
                "SELECT kind, name, brand, distance_m FROM poi "
                "WHERE location_id = ? ORDER BY kind, distance_m",
                (row["loc_id"],),
            )
            pois = cur.fetchall()
            if not pois:
                console.print(
                    "[dim]POI 未取得。[/] [bold]re ingest osm --listing-id "
                    f"{row['id']}[/] で取得できます。"
                )
            else:
                from ..utils.distance import walk_minutes
                from collections import defaultdict
                grouped: dict[str, list] = defaultdict(list)
                for p in pois:
                    grouped[p["kind"]].append(p)

                kind_label = {"super": "🛒 スーパー", "gym": "💪 ジム", "busstop": "🚌 バス停"}
                for kind, label in kind_label.items():
                    same = grouped.get(kind, [])
                    if not same:
                        console.print(f"\n[dim]{label}: 該当なし[/]")
                        continue
                    t = Table(title=f"{label} (全 {len(same)} 件)")
                    t.add_column("名前")
                    t.add_column("ブランド")
                    t.add_column("距離", justify="right")
                    t.add_column("徒歩", justify="right")
                    for p in same[:8]:
                        t.add_row(
                            p["name"] or "[dim]?[/]",
                            p["brand"] or "-",
                            f"{int(p['distance_m'])}m",
                            f"{walk_minutes(p['distance_m'])}分",
                        )
                    console.print(t)
    finally:
        conn.close()
