"""CLI エントリポイント (`re ...`)。

Phase 0 段階では `re init` と `re version` のみ実装。
以降のフェーズで sub-typer をぶら下げていく。
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import Config
from .db import connect, get_schema_version, init_schema

app = typer.Typer(
    no_args_is_help=True,
    help="不動産探索CLI - 東京23区の賃貸物件を沿革・風水・建替計画も含めて探す",
    add_completion=False,
)
console = Console()


@app.command()
def init(
    force: bool = typer.Option(
        False, "--force", help="既存DBを削除して作り直す（注意：登録物件・お気に入りも消える）"
    ),
) -> None:
    """SQLite DB と設定ファイルを初期化する。"""
    cfg = Config.load()
    cfg.ensure_dirs()

    db_existed = cfg.db_path.exists()
    if db_existed and force:
        cfg.db_path.unlink()
        console.print(f"[yellow]既存DBを削除しました:[/] {cfg.db_path}")
        db_existed = False

    conn = connect(cfg)
    try:
        init_schema(conn)
        version = get_schema_version(conn)
    finally:
        conn.close()

    wrote_config = cfg.write_default_config_if_missing()

    table = Table(title="re-search 初期化", show_header=False, box=None)
    table.add_column(style="cyan", no_wrap=True)
    table.add_column()
    table.add_row("DB", f"{cfg.db_path} (schema v{version})")
    table.add_row("Config", f"{cfg.config_file}{' [green](新規作成)[/]' if wrote_config else ''}")
    table.add_row("Data dir", str(cfg.data_dir))
    table.add_row("Cache dir", str(cfg.cache_dir))
    if db_existed:
        table.add_row("Status", "[yellow]既存DBにスキーマ適用[/]")
    else:
        table.add_row("Status", "[green]新規DB作成[/]")
    console.print(table)

    console.print(
        "\n次のステップ:\n"
        "  1. [bold]re ingest add <url>[/] で物件を登録（Phase 1 で実装予定）\n"
        "  2. [bold]re search ...[/] で条件検索（Phase 1 で実装予定）\n"
    )


@app.command()
def version() -> None:
    """バージョン表示。"""
    console.print(f"re-search {__version__}")


@app.command()
def info() -> None:
    """現在の設定とDB状態を表示。"""
    cfg = Config.load()
    table = Table(show_header=False, box=None)
    table.add_column(style="cyan")
    table.add_column()
    table.add_row("Version", __version__)
    table.add_row("DB path", str(cfg.db_path))
    table.add_row("DB exists", "yes" if cfg.db_path.exists() else "[yellow]no (run `re init`)[/]")
    table.add_row("Config file", str(cfg.config_file))
    table.add_row("Reinfolib API key", "set" if cfg.reinfolib_api_key else "[yellow]unset[/]")
    table.add_row("Scrape accept risks", str(cfg.scrape_accept_risks))
    console.print(table)


# Phase 1 以降で sub-typer をここに追加していく:
#   from .ingest.cli import ingest_app
#   app.add_typer(ingest_app, name="ingest")
#   from .search.cli import search_app
#   app.add_typer(search_app, name="search")
#   ... etc
from .geo.cli import geo_app
from .ingest.cli import ingest_app
from .redev.cli import redev_app
from .heritage.cli import heritage_app
from .fengshui.cli import fengshui_app
from .score.cli import score_app

app.add_typer(geo_app, name="geo")
app.add_typer(ingest_app, name="ingest")
app.add_typer(redev_app, name="redev")
app.add_typer(heritage_app, name="heritage")
app.add_typer(fengshui_app, name="fengshui")
app.add_typer(score_app, name="score")

if __name__ == "__main__":
    app()
