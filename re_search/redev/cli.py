"""`re redev ...` サブコマンド。"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from ..config import Config
from ..db import connect
from .manual import (
    RedevDraft,
    add_redev_project,
    link_listing_to_redev,
    list_redev_for_listing,
    VALID_KINDS,
    VALID_STATUS,
)

redev_app = typer.Typer(no_args_is_help=True, help="再開発・建替プロジェクト管理")
console = Console()


@redev_app.command("add")
def add_cmd(
    name: str = typer.Option(..., "--name"),
    kind: str = typer.Option(..., "--kind", help=f"{VALID_KINDS}"),
    status: str = typer.Option(..., "--status", help=f"{VALID_STATUS}"),
    summary: str = typer.Option(None, "--summary"),
    announced: str = typer.Option(None, "--announced", help="YYYY-MM-DD"),
    approved: str = typer.Option(None, "--approved", help="YYYY-MM-DD"),
    completion: int = typer.Option(None, "--completion-year"),
    source_name: str = typer.Option(None, "--source-name"),
    source_url: str = typer.Option(None, "--source-url"),
    scope_kind: str = typer.Option(None, "--scope-kind"),
    scope_data: str = typer.Option(None, "--scope-data"),
    note: str = typer.Option(None, "--note"),
) -> None:
    """再開発プロジェクトを登録。"""
    cfg = Config.load()
    conn = connect(cfg)
    try:
        draft = RedevDraft(
            name=name,
            kind=kind,
            status=status,
            summary=summary,
            announced_at=announced,
            approved_at=approved,
            expected_completion_year=completion,
            source_name=source_name,
            source_url=source_url,
            scope_kind=scope_kind,
            scope_data=scope_data,
            note=note,
        )
        pid = add_redev_project(conn, draft)
        console.print(f"[green]✓[/] redev_project id={pid} を登録: {name}")
    finally:
        conn.close()


@redev_app.command("link")
def link_cmd(
    listing_id: int = typer.Option(..., "--listing-id", "-l"),
    project_id: int = typer.Option(..., "--project-id", "-p"),
    confidence: str = typer.Option("medium", "--confidence"),
    note: str = typer.Option(None, "--note"),
    confirmed: bool = typer.Option(False, "--confirmed", help="ユーザ確認済"),
) -> None:
    """listing と再開発プロジェクトを紐付ける。"""
    cfg = Config.load()
    conn = connect(cfg)
    try:
        link_listing_to_redev(
            conn, listing_id, project_id,
            confidence=confidence, note=note, confirmed_by_user=confirmed,
        )
        console.print(f"[green]✓[/] listing={listing_id} ↔ project={project_id}")
    finally:
        conn.close()


@redev_app.command("list")
def list_cmd(
    listing_id: int = typer.Option(None, "--listing-id", "-l"),
) -> None:
    """再開発プロジェクト一覧（listing 指定時はその物件に紐づくもののみ）。"""
    cfg = Config.load()
    conn = connect(cfg)
    try:
        if listing_id:
            rows = list_redev_for_listing(conn, listing_id)
            title = f"listing_id={listing_id} に紐づく再開発"
        else:
            cur = conn.execute(
                "SELECT * FROM redevelopment_project ORDER BY expected_completion_year DESC"
            )
            rows = cur.fetchall()
            title = "全 再開発プロジェクト"

        if not rows:
            console.print(f"[yellow]{title}: 登録なし[/]")
            return

        t = Table(title=title)
        t.add_column("ID", justify="right")
        t.add_column("名称")
        t.add_column("種別")
        t.add_column("ステータス")
        t.add_column("竣工", justify="right")
        for r in rows:
            t.add_row(
                str(r["id"]),
                r["name"],
                r["kind"],
                r["status"],
                str(r["expected_completion_year"]) if r["expected_completion_year"] else "-",
            )
        console.print(t)
    finally:
        conn.close()
