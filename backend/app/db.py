from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from .config import settings


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(settings.database_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_dict(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    initials TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'lawyer', 'staff', 'viewer')),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    client_name TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'preparing',
    owner_id TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS case_members (
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    access_level TEXT NOT NULL CHECK (access_level IN ('owner', 'reviewer', 'editor', 'viewer')),
    PRIMARY KEY (case_id, user_id)
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    mime_type TEXT NOT NULL DEFAULT 'text/plain',
    size_bytes INTEGER NOT NULL DEFAULT 0,
    sha256 TEXT NOT NULL,
    storage_path TEXT,
    content TEXT NOT NULL DEFAULT '',
    page_count INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'ready',
    error TEXT,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    page_number INTEGER,
    section TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL,
    UNIQUE(document_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    task_type TEXT NOT NULL DEFAULT 'general',
    content TEXT NOT NULL,
    payload_json TEXT,
    citations_json TEXT,
    status TEXT NOT NULL DEFAULT 'complete',
    model TEXT,
    parent_id TEXT REFERENCES messages(id),
    version INTEGER NOT NULL DEFAULT 1,
    feedback TEXT,
    feedback_comment TEXT,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS draft_versions (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    source_message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_message_id, version)
);

CREATE TABLE IF NOT EXISTS finding_resolutions (
    message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    finding_index INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'resolved', 'ignored')),
    note TEXT NOT NULL DEFAULT '',
    updated_by TEXT NOT NULL REFERENCES users(id),
    updated_at TEXT NOT NULL,
    PRIMARY KEY(message_id, finding_index)
);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    artifact_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected', 'executed')),
    requested_by TEXT NOT NULL REFERENCES users(id),
    decided_by TEXT REFERENCES users(id),
    comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    decided_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT REFERENCES cases(id) ON DELETE SET NULL,
    user_id TEXT NOT NULL REFERENCES users(id),
    event_type TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT,
    result TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS connectors (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    provider TEXT NOT NULL,
    purpose TEXT NOT NULL,
    read_scope TEXT NOT NULL,
    write_scope TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'local',
    base_url TEXT,
    token_env TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS connector_actions (
    id TEXT PRIMARY KEY,
    connector_id TEXT NOT NULL REFERENCES connectors(id),
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    operation TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL,
    result_json TEXT,
    requested_by TEXT NOT NULL REFERENCES users(id),
    approved_by TEXT REFERENCES users(id),
    created_at TEXT NOT NULL,
    executed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_documents_case ON documents(case_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_chunks_case ON document_chunks(case_id);
CREATE INDEX IF NOT EXISTS idx_messages_case ON messages(case_id, created_at);
CREATE INDEX IF NOT EXISTS idx_draft_versions_case ON draft_versions(case_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_audit_case ON audit_events(case_id, created_at);
CREATE INDEX IF NOT EXISTS idx_approvals_case ON approvals(case_id, created_at);
"""


DEMO_DOCUMENTS = [
    (
        "doc-nda-target",
        "提出書面案_事実関係整理.txt",
        "target_contract",
        """提出書面案（確認前）

依頼人は2026年7月15日に初回相談を行った。
相手方への支払額は3,000,000円であり、2026年7月20日までに返金される予定だった。

提出書面では、相談記録を甲第1号証、振込明細を甲第2号証として引用する。

確認事項: 当事者氏名、相談日、支払額、返金期限、証拠番号。""",
    ),
    (
        "doc-nda-template",
        "依頼人_初回面談記録.txt",
        "consultation",
        """初回面談記録

面談日時: 2026年7月15日 14時00分
依頼人は、2026年7月14日に相手方へ3,000,000円を振り込んだと説明した。
返金期限は2026年7月31日と認識している。

次の対応
振込原本、相手方との連絡履歴、返金期限を合意した資料を確認する。""",
    ),
    (
        "doc-review-history",
        "銀行取引明細_確認用抜粋.txt",
        "evidence",
        """銀行取引明細（確認用抜粋）

取引日: 2026年7月14日
振込先: 相手方名義口座
振込額: 2,800,000円
摘要: 貸付金

PDF原本との照合前に転記したデータ。提出前に原本と照合すること。""",
    ),
    (
        "doc-nda-checklist",
        "提出前チェックリスト.txt",
        "checklist",
        """提出前チェックリスト

1. 当事者氏名と住所が原資料と一致しているか。
2. 日付と時系列が相談記録・証拠資料と一致しているか。
3. 金額と計算根拠が銀行明細と一致しているか。
4. 引用箇所と証拠番号が対応しているか。
5. 最終判断と表現を担当者が確認したか。""",
    ),
]


def init_database() -> None:
    with connect() as connection:
        connection.executescript(SCHEMA)
        seed_database(connection)


def seed_database(connection: sqlite3.Connection) -> None:
    now = utc_now()
    users = [
        ("user-admin", "橘 駿太", "ST", "admin", now),
        ("user-lawyer", "佐藤 裕子", "YS", "lawyer", now),
        ("user-staff", "山田 花子", "HY", "staff", now),
    ]
    connection.executemany(
        """INSERT INTO users(id, display_name, initials, role, created_at) VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET display_name = excluded.display_name,
           initials = excluded.initials, role = excluded.role""",
        users,
    )
    if not settings.seed_demo_data:
        return
    connection.execute(
        """INSERT INTO cases
        (id, name, client_name, summary, status, owner_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET name = excluded.name, client_name = excluded.client_name,
        summary = excluded.summary, status = excluded.status, updated_at = excluded.updated_at""",
        (
            "C-2026-0710",
            "金銭返還／事実関係整理",
            "山田 太郎",
            "相談記録、提出書面、銀行取引明細の内容を照合し、事実関係を整理する。",
            "reviewing",
            "user-admin",
            now,
            now,
        ),
    )
    connection.executemany(
        "INSERT OR IGNORE INTO case_members(case_id, user_id, access_level) VALUES (?, ?, ?)",
        [
            ("C-2026-0710", "user-admin", "owner"),
            ("C-2026-0710", "user-lawyer", "reviewer"),
            ("C-2026-0710", "user-staff", "editor"),
        ],
    )
    for document_id, name, kind, content in DEMO_DOCUMENTS:
        connection.execute(
            """INSERT INTO documents
            (id, case_id, name, kind, mime_type, size_bytes, sha256, content, page_count,
             status, created_by, created_at)
            VALUES (?, 'C-2026-0710', ?, ?, 'text/plain', ?, ?, ?, 1, 'ready', 'user-admin', ?)
            ON CONFLICT(id) DO UPDATE SET name = excluded.name, kind = excluded.kind,
            size_bytes = excluded.size_bytes, content = excluded.content, status = 'ready'""",
            (document_id, name, kind, len(content.encode("utf-8")), document_id, content, now),
        )
        connection.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
        for index, paragraph in enumerate(part.strip() for part in content.split("\n\n") if part.strip()):
            section = paragraph.splitlines()[0][:120]
            connection.execute(
                """INSERT INTO document_chunks
                (id, document_id, case_id, chunk_index, page_number, section, text)
                VALUES (?, ?, 'C-2026-0710', ?, 1, ?, ?)""",
                (f"{document_id}-chunk-{index}", document_id, index, section, paragraph),
            )
    connectors = [
        (
            "calendar",
            "Calendar",
            "calendar",
            "google_or_microsoft",
            "担当者の空き時間確認と面談候補作成",
            "空き時間・予定名の必要範囲",
            "承認後に仮予定を登録",
        ),
        (
            "mail",
            "Gmail / Outlook",
            "mail",
            "google_or_microsoft",
            "過去メール参照と返信案作成",
            "案件に紐づくスレッドのみ",
            "承認後に下書き保存・送信",
        ),
        (
            "drive",
            "Drive / DMS",
            "drive",
            "google_or_generic",
            "契約書・証拠・所内ひな形の参照",
            "既存権限のあるフォルダのみ",
            "承認後に作成結果を保存",
        ),
        (
            "case-db",
            "案件DB",
            "database",
            "generic_rest",
            "相談履歴と確認状況の参照",
            "案件・担当・職位で制御",
            "確認済みメモだけを反映",
        ),
    ]
    connection.executemany(
        """INSERT OR IGNORE INTO connectors
        (id, name, kind, provider, purpose, read_scope, write_scope, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [(*item, now) for item in connectors],
    )


def audit(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    event_type: str,
    target_type: str,
    target_id: str | None,
    result: str = "success",
    case_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        """INSERT INTO audit_events
        (case_id, user_id, event_type, target_type, target_id, result, detail_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            case_id,
            user_id,
            event_type,
            target_type,
            target_id,
            result,
            json.dumps(detail or {}, ensure_ascii=False),
            utc_now(),
        ),
    )
