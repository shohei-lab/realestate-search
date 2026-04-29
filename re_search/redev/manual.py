"""再開発プロジェクトの手動登録と listing への紐付け。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable


VALID_KINDS = (
    "mansion_rebuild",
    "urban_redev1",
    "urban_redev2",
    "lot_adjust",
    "disaster_zone",
    "private_plan",
)
VALID_STATUS = (
    "planned",
    "announced",
    "approved",
    "under_construction",
    "completed",
)


@dataclass
class RedevDraft:
    name: str
    kind: str                       # VALID_KINDS のいずれか
    status: str                     # VALID_STATUS のいずれか
    summary: str | None = None
    announced_at: str | None = None
    approved_at: str | None = None
    expected_completion_year: int | None = None
    scope_kind: str | None = None   # 'address_list'|'town_codes'|'geojson'
    scope_data: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    note: str | None = None


def add_redev_project(conn: sqlite3.Connection, draft: RedevDraft) -> int:
    if draft.kind not in VALID_KINDS:
        raise ValueError(f"kind は {VALID_KINDS} のいずれか")
    if draft.status not in VALID_STATUS:
        raise ValueError(f"status は {VALID_STATUS} のいずれか")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = conn.execute(
        """
        INSERT INTO redevelopment_project (
            name, kind, status, announced_at, approved_at,
            expected_completion_year, scope_kind, scope_data,
            summary, source_url, source_name, fetched_at, note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            draft.name,
            draft.kind,
            draft.status,
            draft.announced_at,
            draft.approved_at,
            draft.expected_completion_year,
            draft.scope_kind,
            draft.scope_data,
            draft.summary,
            draft.source_url,
            draft.source_name,
            now,
            draft.note,
        ),
    )
    conn.commit()
    return int(cur.lastrowid or 0)


def link_listing_to_redev(
    conn: sqlite3.Connection,
    listing_id: int,
    project_id: int,
    *,
    confidence: str = "medium",
    note: str | None = None,
    confirmed_by_user: bool = False,
) -> None:
    if confidence not in ("high", "medium", "low"):
        raise ValueError("confidence は high/medium/low")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO listing_redev (
            listing_id, project_id, link_kind, confidence,
            confirmed_by_user, note, linked_at
        ) VALUES (?, ?, 'manual', ?, ?, ?, ?)
        ON CONFLICT(listing_id, project_id) DO UPDATE SET
            confidence=excluded.confidence,
            confirmed_by_user=excluded.confirmed_by_user,
            note=excluded.note,
            linked_at=excluded.linked_at
        """,
        (
            listing_id,
            project_id,
            confidence,
            1 if confirmed_by_user else 0,
            note,
            now,
        ),
    )
    conn.commit()


def list_redev_for_listing(conn: sqlite3.Connection, listing_id: int) -> list[sqlite3.Row]:
    cur = conn.execute(
        """
        SELECT r.*, lr.confidence, lr.confirmed_by_user, lr.note AS link_note
        FROM redevelopment_project r
        JOIN listing_redev lr ON r.id = lr.project_id
        WHERE lr.listing_id = ?
        ORDER BY r.expected_completion_year DESC
        """,
        (listing_id,),
    )
    return cur.fetchall()
