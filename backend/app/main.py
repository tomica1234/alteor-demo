from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import re
import time
import sqlite3
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .ai import local_ai
from .config import settings
from .connectors import allowed_operation, run_read, run_write
from .db import audit, connect, init_database, row_dict, rows_dict, utc_now
from .documents import parse_document
from .retrieval import retrieve


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    yield


app = FastAPI(title="Alteor Offline AI", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://127.0.0.1:5174", "http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Content-Type", "X-User-Id"],
)

ACCESS_COOKIE = "alteor_access"
AUTH_PUBLIC_PATHS = {"/api/health", "/api/auth/status", "/api/auth/login", "/api/auth/logout"}


def _session_token() -> str:
    expires_at = int(time.time()) + settings.session_ttl_seconds
    payload = str(expires_at)
    signature = hmac.new(settings.session_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def _valid_session(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    expires_at, signature = token.split(".", 1)
    if not expires_at.isdigit() or int(expires_at) <= int(time.time()):
        return False
    expected = hmac.new(settings.session_secret.encode("utf-8"), expires_at.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


@app.middleware("http")
async def access_password_gate(request: Request, call_next):
    if (
        settings.access_password
        and request.url.path.startswith("/api/")
        and request.method != "OPTIONS"
        and request.url.path not in AUTH_PUBLIC_PATHS
        and not _valid_session(request.cookies.get(ACCESS_COOKIE))
    ):
        return JSONResponse(status_code=401, content={"detail": "パスワードを入力してください。"})
    return await call_next(request)


class CaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    client_name: str = Field(min_length=1, max_length=160)
    summary: str = Field(default="", max_length=4000)


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class CaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    client_name: str | None = Field(default=None, min_length=1, max_length=160)
    summary: str | None = Field(default=None, max_length=4000)
    status: Literal["preparing", "reviewing", "pending_approval", "approved", "closed"] | None = None


class MemberUpdate(BaseModel):
    user_id: str
    access_level: Literal["owner", "reviewer", "editor", "viewer"]


class DeadlineCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    kind: Literal["court", "client", "internal", "other"] = "internal"
    owner_id: str
    note: str = Field(default="", max_length=2000)


class DeadlineUpdate(BaseModel):
    status: Literal["open", "completed"]


class DecisionChatCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class MessageCreate(BaseModel):
    question: str = Field(min_length=1, max_length=12000)
    task_type: Literal[
        "general",
        "draft",
        "consistency_check",
        "contract_review",
        "legal_research",
        "litigation",
        "client_support",
        "clause",
        "mail",
        "checklist",
        "timeline",
    ] = "general"


class FeedbackCreate(BaseModel):
    rating: Literal["helpful", "needs_improvement"]
    comment: str = Field(default="", max_length=2000)


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    comment: str = Field(default="", max_length=2000)


class DraftVersionCreate(BaseModel):
    source_message_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=100000)


class FindingResolutionUpdate(BaseModel):
    status: Literal["open", "resolved", "ignored"]
    note: str = Field(default="", max_length=2000)


class ConnectorUpdate(BaseModel):
    mode: Literal["local", "live"]
    provider: Literal["google", "microsoft", "generic_rest", "google_or_microsoft", "google_or_generic"]
    base_url: str | None = Field(default=None, max_length=500)
    token_env: str | None = Field(default=None, max_length=100)
    enabled: bool = True


class ConnectorActionCreate(BaseModel):
    action_type: Literal["read", "write"]
    operation: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)


def get_current_user(
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> dict[str, Any]:
    user_id = x_user_id or "user-admin"
    with connect() as connection:
        user = row_dict(connection.execute("SELECT * FROM users WHERE id = ? AND active = 1", (user_id,)).fetchone())
    if not user:
        raise HTTPException(status_code=401, detail="利用者情報を確認できません。")
    return user


CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]


def require_case_access(
    connection: sqlite3.Connection,
    case_id: str,
    user: dict[str, Any],
    *,
    write: bool = False,
) -> dict[str, Any]:
    case = row_dict(connection.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone())
    if not case:
        raise HTTPException(status_code=404, detail="案件が見つかりません。")
    if user["role"] == "admin":
        return case
    membership = connection.execute(
        "SELECT access_level FROM case_members WHERE case_id = ? AND user_id = ?",
        (case_id, user["id"]),
    ).fetchone()
    if not membership:
        raise HTTPException(status_code=403, detail="この案件を閲覧する権限がありません。")
    if write and membership["access_level"] == "viewer":
        raise HTTPException(status_code=403, detail="この案件を更新する権限がありません。")
    return case


def require_reviewer(user: dict[str, Any]) -> None:
    if user["role"] not in {"admin", "lawyer"}:
        raise HTTPException(status_code=403, detail="承認・差戻しは確認責任者または管理者のみ実行できます。")


@app.get("/api/health")
def health() -> dict[str, Any]:
    database_ok = False
    try:
        with connect() as connection:
            connection.execute("SELECT 1").fetchone()
            database_ok = True
    except Exception:
        pass
    return {
        "ok": database_ok,
        "database": {"reachable": database_ok, "path": str(settings.database_path)},
        "prototype": local_ai.health(),
        "external_connectors_allowed": settings.allow_external_connectors,
        "offline_mode": settings.offline_mode,
        "processing_boundary": "standalone_offline" if settings.offline_mode else "local_or_office_lan",
    }


@app.get("/api/auth/status")
def auth_status(request: Request) -> dict[str, bool]:
    required = bool(settings.access_password)
    return {"required": required, "authenticated": not required or _valid_session(request.cookies.get(ACCESS_COOKIE))}


@app.post("/api/auth/login")
def login(body: LoginRequest) -> JSONResponse:
    if settings.access_password and not hmac.compare_digest(body.password, settings.access_password):
        raise HTTPException(status_code=401, detail="パスワードが正しくありません。")
    response = JSONResponse({"authenticated": True})
    if settings.access_password:
        response.set_cookie(
            ACCESS_COOKIE,
            _session_token(),
            max_age=settings.session_ttl_seconds,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="lax",
            path="/",
        )
    return response


@app.post("/api/auth/logout")
def logout() -> JSONResponse:
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(ACCESS_COOKIE, path="/")
    return response


@app.get("/api/users")
def list_users(_: CurrentUser) -> list[dict[str, Any]]:
    with connect() as connection:
        return rows_dict(connection.execute("SELECT id, display_name, initials, role FROM users WHERE active = 1 ORDER BY role, display_name").fetchall())


@app.get("/api/cases")
def list_cases(user: CurrentUser) -> list[dict[str, Any]]:
    with connect() as connection:
        if user["role"] == "admin":
            rows = connection.execute("SELECT c.*, 'owner' AS access_level FROM cases c ORDER BY updated_at DESC").fetchall()
        else:
            rows = connection.execute(
                """SELECT c.*, cm.access_level FROM cases c
                   JOIN case_members cm ON cm.case_id = c.id
                   WHERE cm.user_id = ? ORDER BY c.updated_at DESC""",
                (user["id"],),
            ).fetchall()
        return [_case_payload(connection, dict(row)) for row in rows]


@app.post("/api/cases", status_code=201)
def create_case(body: CaseCreate, user: CurrentUser) -> dict[str, Any]:
    case_id = f"C-{utc_now()[:4]}-{uuid.uuid4().hex[:6].upper()}"
    now = utc_now()
    with connect() as connection:
        connection.execute(
            """INSERT INTO cases(id, name, client_name, summary, status, owner_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'preparing', ?, ?, ?)""",
            (case_id, body.name, body.client_name, body.summary, user["id"], now, now),
        )
        connection.execute(
            "INSERT INTO case_members(case_id, user_id, access_level) VALUES (?, ?, 'owner')",
            (case_id, user["id"]),
        )
        audit(connection, user_id=user["id"], event_type="case.created", target_type="case", target_id=case_id, case_id=case_id)
        case = row_dict(connection.execute("SELECT c.*, 'owner' AS access_level FROM cases c WHERE id = ?", (case_id,)).fetchone())
        assert case is not None
        return _case_payload(connection, case)


@app.get("/api/cases/{case_id}")
def get_case(case_id: str, user: CurrentUser) -> dict[str, Any]:
    with connect() as connection:
        case = require_case_access(connection, case_id, user)
        return _case_payload(connection, case, include_members=True)


@app.patch("/api/cases/{case_id}")
def update_case(case_id: str, body: CaseUpdate, user: CurrentUser) -> dict[str, Any]:
    changes = body.model_dump(exclude_none=True)
    if changes.get("status") in {"approved", "closed"}:
        require_reviewer(user)
    with connect() as connection:
        require_case_access(connection, case_id, user, write=True)
        if changes:
            assignments = ", ".join(f"{key} = ?" for key in changes)
            connection.execute(
                f"UPDATE cases SET {assignments}, updated_at = ? WHERE id = ?",
                (*changes.values(), utc_now(), case_id),
            )
        audit(connection, user_id=user["id"], event_type="case.updated", target_type="case", target_id=case_id, case_id=case_id, detail={"fields": list(changes)})
        case = row_dict(connection.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone())
        assert case is not None
        return _case_payload(connection, case, include_members=True)


@app.put("/api/cases/{case_id}/members")
def update_member(case_id: str, body: MemberUpdate, user: CurrentUser) -> dict[str, Any]:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="担当者の変更は管理者のみ実行できます。")
    with connect() as connection:
        require_case_access(connection, case_id, user, write=True)
        target = connection.execute("SELECT id FROM users WHERE id = ? AND active = 1", (body.user_id,)).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="利用者が見つかりません。")
        connection.execute(
            """INSERT INTO case_members(case_id, user_id, access_level) VALUES (?, ?, ?)
               ON CONFLICT(case_id, user_id) DO UPDATE SET access_level = excluded.access_level""",
            (case_id, body.user_id, body.access_level),
        )
        audit(connection, user_id=user["id"], event_type="case.member_updated", target_type="user", target_id=body.user_id, case_id=case_id, detail={"access_level": body.access_level})
        case = row_dict(connection.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone())
        assert case is not None
        return _case_payload(connection, case, include_members=True)


@app.get("/api/cases/{case_id}/deadlines")
def list_deadlines(case_id: str, user: CurrentUser) -> list[dict[str, Any]]:
    with connect() as connection:
        require_case_access(connection, case_id, user)
        rows = connection.execute(
            """SELECT d.*, u.display_name AS owner_name
               FROM deadlines d JOIN users u ON u.id = d.owner_id
               WHERE d.case_id = ? ORDER BY d.due_date, d.created_at""",
            (case_id,),
        ).fetchall()
        return rows_dict(rows)


@app.post("/api/cases/{case_id}/deadlines", status_code=201)
def create_deadline(case_id: str, body: DeadlineCreate, user: CurrentUser) -> dict[str, Any]:
    deadline_id = f"deadline-{uuid.uuid4().hex}"
    now = utc_now()
    with connect() as connection:
        require_case_access(connection, case_id, user, write=True)
        owner = connection.execute(
            """SELECT u.id, u.display_name FROM users u
               JOIN case_members cm ON cm.user_id = u.id
               WHERE cm.case_id = ? AND u.id = ? AND u.active = 1""",
            (case_id, body.owner_id),
        ).fetchone()
        if not owner:
            raise HTTPException(status_code=403, detail="期限の担当者は、この案件の参加者から選択してください。")
        connection.execute(
            """INSERT INTO deadlines(id, case_id, title, due_date, kind, status, owner_id, note, created_by, created_at)
               VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)""",
            (deadline_id, case_id, body.title, body.due_date, body.kind, body.owner_id, body.note, user["id"], now),
        )
        audit(connection, user_id=user["id"], event_type="deadline.created", target_type="deadline", target_id=deadline_id, case_id=case_id, detail={"due_date": body.due_date})
        row = row_dict(connection.execute("SELECT d.*, u.display_name AS owner_name FROM deadlines d JOIN users u ON u.id = d.owner_id WHERE d.id = ?", (deadline_id,)).fetchone())
        assert row is not None
        return row


@app.patch("/api/deadlines/{deadline_id}")
def update_deadline(deadline_id: str, body: DeadlineUpdate, user: CurrentUser) -> dict[str, Any]:
    with connect() as connection:
        deadline = row_dict(connection.execute("SELECT * FROM deadlines WHERE id = ?", (deadline_id,)).fetchone())
        if not deadline:
            raise HTTPException(status_code=404, detail="期限が見つかりません。")
        require_case_access(connection, deadline["case_id"], user, write=True)
        connection.execute("UPDATE deadlines SET status = ? WHERE id = ?", (body.status, deadline_id))
        event = "deadline.completed" if body.status == "completed" else "deadline.reopened"
        audit(connection, user_id=user["id"], event_type=event, target_type="deadline", target_id=deadline_id, case_id=deadline["case_id"])
        row = row_dict(connection.execute("SELECT d.*, u.display_name AS owner_name FROM deadlines d JOIN users u ON u.id = d.owner_id WHERE d.id = ?", (deadline_id,)).fetchone())
        assert row is not None
        return row


@app.get("/api/cases/{case_id}/decision-chat")
def list_decision_chat(case_id: str, user: CurrentUser) -> list[dict[str, Any]]:
    with connect() as connection:
        require_case_access(connection, case_id, user)
        rows = connection.execute(
            """SELECT c.id, c.case_id, c.body, c.author_id, u.display_name AS author_name,
                      u.role AS author_role, c.created_at
               FROM decision_chat_messages c JOIN users u ON u.id = c.author_id
               WHERE c.case_id = ? ORDER BY c.created_at""",
            (case_id,),
        ).fetchall()
        return rows_dict(rows)


@app.post("/api/cases/{case_id}/decision-chat", status_code=201)
def send_decision_chat(case_id: str, body: DecisionChatCreate, user: CurrentUser) -> dict[str, Any]:
    message_id = f"chat-{uuid.uuid4().hex}"
    now = utc_now()
    with connect() as connection:
        require_case_access(connection, case_id, user, write=True)
        connection.execute("INSERT INTO decision_chat_messages(id, case_id, body, author_id, created_at) VALUES (?, ?, ?, ?, ?)", (message_id, case_id, body.body, user["id"], now))
        audit(connection, user_id=user["id"], event_type="decision_chat.sent", target_type="decision_chat", target_id=message_id, case_id=case_id)
        row = row_dict(connection.execute("""SELECT c.id, c.case_id, c.body, c.author_id, u.display_name AS author_name, u.role AS author_role, c.created_at FROM decision_chat_messages c JOIN users u ON u.id = c.author_id WHERE c.id = ?""", (message_id,)).fetchone())
        assert row is not None
        return row


@app.get("/api/cases/{case_id}/overview")
def case_overview(case_id: str, user: CurrentUser) -> dict[str, Any]:
    with connect() as connection:
        case = require_case_access(connection, case_id, user)
        stats = {
            "documents": connection.execute("SELECT COUNT(*) FROM documents WHERE case_id = ? AND deleted_at IS NULL", (case_id,)).fetchone()[0],
            "messages": connection.execute("SELECT COUNT(*) FROM messages WHERE case_id = ? AND role = 'assistant'", (case_id,)).fetchone()[0],
            "pending_approvals": connection.execute("SELECT COUNT(*) FROM approvals WHERE case_id = ? AND status = 'pending'", (case_id,)).fetchone()[0],
            "audit_events": connection.execute("SELECT COUNT(*) FROM audit_events WHERE case_id = ?", (case_id,)).fetchone()[0],
        }
        latest = rows_dict(connection.execute("SELECT * FROM messages WHERE case_id = ? AND role = 'assistant' ORDER BY created_at DESC LIMIT 3", (case_id,)).fetchall())
        return {"case": _case_payload(connection, case, include_members=True), "stats": stats, "latest_messages": [_message_payload(row) for row in latest]}


@app.get("/api/cases/{case_id}/documents")
def list_documents(case_id: str, user: CurrentUser) -> list[dict[str, Any]]:
    with connect() as connection:
        require_case_access(connection, case_id, user)
        rows = connection.execute(
            """SELECT d.*, u.display_name AS created_by_name,
                      (SELECT COUNT(*) FROM document_chunks c WHERE c.document_id = d.id) AS chunk_count
               FROM documents d JOIN users u ON u.id = d.created_by
               WHERE d.case_id = ? AND d.deleted_at IS NULL ORDER BY d.created_at DESC""",
            (case_id,),
        ).fetchall()
        return [_document_payload(dict(row), include_content=False) for row in rows]


@app.post("/api/cases/{case_id}/documents", status_code=201)
async def upload_document(
    case_id: str,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    kind: Annotated[str, Form()] = "reference",
) -> dict[str, Any]:
    allowed_kinds = {"target_contract", "internal_template", "past_review", "checklist", "consultation", "evidence", "email", "regulation", "reference"}
    if kind not in allowed_kinds:
        raise HTTPException(status_code=422, detail="資料区分が正しくありません。")
    filename = Path(file.filename or "document").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".docx", ".pdf", ".txt"}:
        raise HTTPException(status_code=415, detail="対応形式はDOCX、PDF、TXTです。")
    raw = await file.read(25 * 1024 * 1024 + 1)
    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="1ファイルの上限は25MBです。")
    if not raw:
        raise HTTPException(status_code=422, detail="空のファイルは登録できません。")

    document_id = f"doc-{uuid.uuid4().hex}"
    saved_path = settings.uploads_dir / f"{document_id}{suffix}"
    saved_path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    now = utc_now()
    try:
        parsed = parse_document(saved_path, filename)
    except ValueError as exc:
        with connect() as connection:
            require_case_access(connection, case_id, user, write=True)
            connection.execute(
                """INSERT INTO documents
                (id, case_id, name, kind, mime_type, size_bytes, sha256, storage_path, status, error, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'failed', ?, ?, ?)""",
                (document_id, case_id, filename, kind, file.content_type or "application/octet-stream", len(raw), digest, str(saved_path), str(exc), user["id"], now),
            )
            audit(connection, user_id=user["id"], event_type="document.parse_failed", target_type="document", target_id=document_id, result="failed", case_id=case_id, detail={"error": str(exc)})
        raise HTTPException(status_code=422, detail={"message": str(exc), "document_id": document_id}) from exc

    with connect() as connection:
        require_case_access(connection, case_id, user, write=True)
        duplicate = connection.execute(
            "SELECT id FROM documents WHERE case_id = ? AND sha256 = ? AND deleted_at IS NULL AND status = 'ready'",
            (case_id, digest),
        ).fetchone()
        if duplicate:
            saved_path.unlink(missing_ok=True)
            raise HTTPException(status_code=409, detail="同じ内容の資料がすでに登録されています。")
        connection.execute(
            """INSERT INTO documents
            (id, case_id, name, kind, mime_type, size_bytes, sha256, storage_path, content, page_count,
             status, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?, ?)""",
            (document_id, case_id, filename, kind, file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream", len(raw), digest, str(saved_path), parsed.content, parsed.page_count, user["id"], now),
        )
        for index, chunk in enumerate(parsed.chunks):
            connection.execute(
                """INSERT INTO document_chunks(id, document_id, case_id, chunk_index, page_number, section, text)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (f"{document_id}-chunk-{index}", document_id, case_id, index, chunk.page_number, chunk.section, chunk.text),
            )
        connection.execute("UPDATE cases SET updated_at = ? WHERE id = ?", (now, case_id))
        audit(connection, user_id=user["id"], event_type="document.uploaded", target_type="document", target_id=document_id, case_id=case_id, detail={"name": filename, "kind": kind, "chunks": len(parsed.chunks)})
        row = row_dict(connection.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone())
        assert row is not None
        return _document_payload(row, include_content=False)


@app.get("/api/documents/{document_id}")
def get_document(document_id: str, user: CurrentUser) -> dict[str, Any]:
    with connect() as connection:
        row = row_dict(connection.execute("SELECT * FROM documents WHERE id = ? AND deleted_at IS NULL", (document_id,)).fetchone())
        if not row:
            raise HTTPException(status_code=404, detail="資料が見つかりません。")
        require_case_access(connection, row["case_id"], user)
        audit(connection, user_id=user["id"], event_type="document.viewed", target_type="document", target_id=document_id, case_id=row["case_id"])
        chunks = rows_dict(connection.execute("SELECT id, chunk_index, page_number, section, text FROM document_chunks WHERE document_id = ? ORDER BY chunk_index", (document_id,)).fetchall())
        payload = _document_payload(row, include_content=True)
        payload["chunks"] = chunks
        return payload


@app.delete("/api/documents/{document_id}")
def delete_document(document_id: str, user: CurrentUser) -> dict[str, Any]:
    with connect() as connection:
        row = row_dict(connection.execute("SELECT * FROM documents WHERE id = ? AND deleted_at IS NULL", (document_id,)).fetchone())
        if not row:
            raise HTTPException(status_code=404, detail="資料が見つかりません。")
        require_case_access(connection, row["case_id"], user, write=True)
        connection.execute("UPDATE documents SET deleted_at = ? WHERE id = ?", (utc_now(), document_id))
        audit(connection, user_id=user["id"], event_type="document.deleted", target_type="document", target_id=document_id, case_id=row["case_id"], detail={"name": row["name"]})
    storage_path = row.get("storage_path")
    if storage_path:
        try:
            path = Path(storage_path).resolve()
            if settings.uploads_dir in path.parents:
                path.unlink(missing_ok=True)
        except OSError:
            pass
    return {"ok": True, "recoverable": False}


@app.get("/api/cases/{case_id}/messages")
def list_messages(case_id: str, user: CurrentUser) -> list[dict[str, Any]]:
    with connect() as connection:
        require_case_access(connection, case_id, user)
        rows = rows_dict(connection.execute("SELECT m.*, u.display_name AS created_by_name, u.initials FROM messages m JOIN users u ON u.id = m.created_by WHERE m.case_id = ? ORDER BY m.created_at", (case_id,)).fetchall())
        return [_message_payload(row) for row in rows]


@app.post("/api/cases/{case_id}/messages", status_code=201)
def create_message(case_id: str, body: MessageCreate, user: CurrentUser) -> dict[str, Any]:
    return _generate_message(case_id=case_id, body=body, user=user, parent_id=None, version=1)


@app.post("/api/messages/{message_id}/regenerate", status_code=201)
def regenerate_message(message_id: str, user: CurrentUser) -> dict[str, Any]:
    with connect() as connection:
        assistant = row_dict(connection.execute("SELECT * FROM messages WHERE id = ? AND role = 'assistant'", (message_id,)).fetchone())
        if not assistant:
            raise HTTPException(status_code=404, detail="再作成する回答が見つかりません。")
        require_case_access(connection, assistant["case_id"], user, write=True)
        parent_id = assistant.get("parent_id")
        question_row = row_dict(connection.execute("SELECT * FROM messages WHERE id = ? AND role = 'user'", (parent_id,)).fetchone()) if parent_id else None
        question = question_row["content"] if question_row else "同じ条件で回答を作成してください。"
        version = connection.execute("SELECT COALESCE(MAX(version), 1) + 1 FROM messages WHERE parent_id = ? AND role = 'assistant'", (parent_id,)).fetchone()[0]
    return _generate_message(case_id=assistant["case_id"], body=MessageCreate(question=question, task_type=assistant["task_type"]), user=user, parent_id=parent_id, version=version, insert_user=False)


@app.post("/api/messages/{message_id}/feedback")
def add_feedback(message_id: str, body: FeedbackCreate, user: CurrentUser) -> dict[str, Any]:
    with connect() as connection:
        message = row_dict(connection.execute("SELECT * FROM messages WHERE id = ? AND role = 'assistant'", (message_id,)).fetchone())
        if not message:
            raise HTTPException(status_code=404, detail="回答が見つかりません。")
        require_case_access(connection, message["case_id"], user)
        connection.execute("UPDATE messages SET feedback = ?, feedback_comment = ? WHERE id = ?", (body.rating, body.comment, message_id))
        audit(connection, user_id=user["id"], event_type="message.feedback", target_type="message", target_id=message_id, case_id=message["case_id"], detail={"rating": body.rating})
        return {"ok": True}


@app.get("/api/cases/{case_id}/drafts")
def list_draft_versions(case_id: str, user: CurrentUser, source_message_id: str | None = None) -> list[dict[str, Any]]:
    with connect() as connection:
        require_case_access(connection, case_id, user)
        if source_message_id:
            rows = connection.execute(
                """SELECT d.*, u.display_name AS created_by_name
                   FROM draft_versions d JOIN users u ON u.id = d.created_by
                   WHERE d.case_id = ? AND d.source_message_id = ?
                   ORDER BY d.version DESC""",
                (case_id, source_message_id),
            ).fetchall()
        else:
            rows = connection.execute(
                """SELECT d.*, u.display_name AS created_by_name
                   FROM draft_versions d JOIN users u ON u.id = d.created_by
                   WHERE d.case_id = ? ORDER BY d.updated_at DESC""",
                (case_id,),
            ).fetchall()
        return rows_dict(rows)


@app.post("/api/cases/{case_id}/drafts", status_code=201)
def save_draft_version(case_id: str, body: DraftVersionCreate, user: CurrentUser) -> dict[str, Any]:
    draft_id = f"draft-{uuid.uuid4().hex}"
    now = utc_now()
    with connect() as connection:
        require_case_access(connection, case_id, user, write=True)
        source = row_dict(connection.execute("SELECT * FROM messages WHERE id = ? AND case_id = ? AND role = 'assistant'", (body.source_message_id, case_id)).fetchone())
        if not source:
            raise HTTPException(status_code=404, detail="元の作成結果が見つかりません。")
        version = connection.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM draft_versions WHERE source_message_id = ?",
            (body.source_message_id,),
        ).fetchone()[0]
        connection.execute(
            """INSERT INTO draft_versions
               (id, case_id, source_message_id, version, title, content, status, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?)""",
            (draft_id, case_id, body.source_message_id, version, body.title, body.content, user["id"], now, now),
        )
        audit(connection, user_id=user["id"], event_type="draft.saved", target_type="draft", target_id=draft_id, case_id=case_id, detail={"source_message_id": body.source_message_id, "version": version})
        row = row_dict(connection.execute("SELECT d.*, u.display_name AS created_by_name FROM draft_versions d JOIN users u ON u.id = d.created_by WHERE d.id = ?", (draft_id,)).fetchone())
        assert row is not None
        return row


@app.get("/api/messages/{message_id}/findings")
def list_finding_resolutions(message_id: str, user: CurrentUser) -> list[dict[str, Any]]:
    with connect() as connection:
        message = row_dict(connection.execute("SELECT * FROM messages WHERE id = ? AND role = 'assistant'", (message_id,)).fetchone())
        if not message:
            raise HTTPException(status_code=404, detail="作成結果が見つかりません。")
        require_case_access(connection, message["case_id"], user)
        rows = connection.execute(
            """SELECT finding_index, status, note, updated_by, updated_at
               FROM finding_resolutions WHERE message_id = ? ORDER BY finding_index""",
            (message_id,),
        ).fetchall()
        return rows_dict(rows)


@app.put("/api/messages/{message_id}/findings/{finding_index}")
def update_finding_resolution(message_id: str, finding_index: int, body: FindingResolutionUpdate, user: CurrentUser) -> dict[str, Any]:
    if finding_index < 0:
        raise HTTPException(status_code=400, detail="確認事項の番号が正しくありません。")
    now = utc_now()
    with connect() as connection:
        message = row_dict(connection.execute("SELECT * FROM messages WHERE id = ? AND role = 'assistant'", (message_id,)).fetchone())
        if not message:
            raise HTTPException(status_code=404, detail="作成結果が見つかりません。")
        require_case_access(connection, message["case_id"], user, write=True)
        payload = _json_load(message.get("payload_json"), {}) or {}
        findings = payload.get("findings", [])
        if finding_index >= len(findings):
            raise HTTPException(status_code=404, detail="確認事項が見つかりません。")
        connection.execute(
            """INSERT INTO finding_resolutions(message_id, finding_index, status, note, updated_by, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(message_id, finding_index) DO UPDATE SET status = excluded.status, note = excluded.note, updated_by = excluded.updated_by, updated_at = excluded.updated_at""",
            (message_id, finding_index, body.status, body.note, user["id"], now),
        )
        audit(connection, user_id=user["id"], event_type="finding.updated", target_type="finding", target_id=f"{message_id}:{finding_index}", case_id=message["case_id"], detail={"status": body.status})
        return {"message_id": message_id, "finding_index": finding_index, "status": body.status, "note": body.note, "updated_at": now}


@app.get("/api/cases/{case_id}/approvals")
def list_approvals(case_id: str, user: CurrentUser) -> list[dict[str, Any]]:
    with connect() as connection:
        require_case_access(connection, case_id, user)
        rows = connection.execute(
            """SELECT a.*, requester.display_name AS requested_by_name,
                      decider.display_name AS decided_by_name,
                      m.payload_json AS message_payload, m.content AS message_content
               FROM approvals a
               JOIN users requester ON requester.id = a.requested_by
               LEFT JOIN users decider ON decider.id = a.decided_by
               LEFT JOIN messages m ON m.id = a.artifact_id
               WHERE a.case_id = ? ORDER BY a.created_at DESC""",
            (case_id,),
        ).fetchall()
        return [_approval_payload(dict(row)) for row in rows]


@app.post("/api/approvals/{approval_id}/decision")
def decide_approval(approval_id: str, body: ApprovalDecision, user: CurrentUser) -> dict[str, Any]:
    require_reviewer(user)
    with connect() as connection:
        approval = row_dict(connection.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone())
        if not approval:
            raise HTTPException(status_code=404, detail="承認依頼が見つかりません。")
        require_case_access(connection, approval["case_id"], user, write=True)
        if approval["status"] != "pending":
            raise HTTPException(status_code=409, detail="この承認依頼はすでに処理されています。")
        now = utc_now()
        final_status = body.decision
        execution_result: dict[str, Any] | None = None
        if body.decision == "approved" and approval["artifact_type"] == "connector_action":
            action = row_dict(connection.execute("SELECT * FROM connector_actions WHERE id = ?", (approval["artifact_id"],)).fetchone())
            if not action:
                raise HTTPException(status_code=404, detail="連携操作が見つかりません。")
            connector = row_dict(connection.execute("SELECT * FROM connectors WHERE id = ?", (action["connector_id"],)).fetchone())
            assert connector is not None
            try:
                execution_result = run_write(connector, action["operation"], json.loads(action["payload_json"]))
                final_status = "executed"
                connection.execute("UPDATE connector_actions SET status = 'executed', approved_by = ?, result_json = ?, executed_at = ? WHERE id = ?", (user["id"], json.dumps(execution_result, ensure_ascii=False), now, action["id"]))
            except Exception as exc:
                connection.execute("UPDATE connector_actions SET status = 'failed', approved_by = ?, result_json = ?, executed_at = ? WHERE id = ?", (user["id"], json.dumps({"error": str(exc)}, ensure_ascii=False), now, action["id"]))
                audit(connection, user_id=user["id"], event_type="connector.write_failed", target_type="connector_action", target_id=action["id"], result="failed", case_id=approval["case_id"], detail={"error": str(exc)})
                raise HTTPException(status_code=502, detail=str(exc)) from exc
        elif approval["artifact_type"] == "connector_action":
            connection.execute("UPDATE connector_actions SET status = 'rejected', approved_by = ?, executed_at = ? WHERE id = ?", (user["id"], now, approval["artifact_id"]))
        connection.execute("UPDATE approvals SET status = ?, decided_by = ?, comment = ?, decided_at = ? WHERE id = ?", (final_status, user["id"], body.comment, now, approval_id))
        audit(connection, user_id=user["id"], event_type=f"approval.{body.decision}", target_type=approval["artifact_type"], target_id=approval["artifact_id"], case_id=approval["case_id"], detail={"comment": body.comment, "executed": final_status == "executed"})
        return {"ok": True, "status": final_status, "execution_result": execution_result}


@app.get("/api/cases/{case_id}/audit-events")
def list_audit_events(case_id: str, user: CurrentUser, limit: int = 200) -> list[dict[str, Any]]:
    with connect() as connection:
        require_case_access(connection, case_id, user)
        rows = rows_dict(connection.execute("""SELECT a.*, u.display_name AS user_name FROM audit_events a JOIN users u ON u.id = a.user_id WHERE a.case_id = ? ORDER BY a.created_at DESC LIMIT ?""", (case_id, min(max(limit, 1), 500))).fetchall())
        for row in rows:
            row["detail"] = _json_load(row.pop("detail_json", None), {})
        return rows


@app.get("/api/connectors")
def list_connectors(user: CurrentUser) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = rows_dict(connection.execute("SELECT * FROM connectors ORDER BY id").fetchall())
        for row in rows:
            row["enabled"] = bool(row["enabled"])
            row["configured"] = row["mode"] == "local" or bool(row.get("base_url") and row.get("token_env"))
            row["external_allowed"] = settings.allow_external_connectors
        return rows


@app.patch("/api/connectors/{connector_id}")
def update_connector(connector_id: str, body: ConnectorUpdate, user: CurrentUser) -> dict[str, Any]:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="連携設定は管理者のみ変更できます。")
    if body.mode == "live" and (not body.base_url or not body.token_env):
        raise HTTPException(status_code=422, detail="実接続にはURLとトークン環境変数名が必要です。")
    with connect() as connection:
        connector = connection.execute("SELECT id FROM connectors WHERE id = ?", (connector_id,)).fetchone()
        if not connector:
            raise HTTPException(status_code=404, detail="連携先が見つかりません。")
        connection.execute("UPDATE connectors SET mode = ?, provider = ?, base_url = ?, token_env = ?, enabled = ?, updated_at = ? WHERE id = ?", (body.mode, body.provider, body.base_url, body.token_env, int(body.enabled), utc_now(), connector_id))
        audit(connection, user_id=user["id"], event_type="connector.configured", target_type="connector", target_id=connector_id, detail={"mode": body.mode, "provider": body.provider, "token_env": body.token_env})
        row = row_dict(connection.execute("SELECT * FROM connectors WHERE id = ?", (connector_id,)).fetchone())
        assert row is not None
        row["enabled"] = bool(row["enabled"])
        return row


@app.post("/api/cases/{case_id}/connectors/{connector_id}/actions", status_code=201)
def create_connector_action(case_id: str, connector_id: str, body: ConnectorActionCreate, user: CurrentUser) -> dict[str, Any]:
    with connect() as connection:
        require_case_access(connection, case_id, user, write=body.action_type == "write")
        connector = row_dict(connection.execute("SELECT * FROM connectors WHERE id = ? AND enabled = 1", (connector_id,)).fetchone())
        if not connector:
            raise HTTPException(status_code=404, detail="有効な連携先が見つかりません。")
        if not allowed_operation(connector["kind"], body.operation, body.action_type):
            raise HTTPException(status_code=422, detail="この連携先では許可されていない操作です。")
        action_id = f"action-{uuid.uuid4().hex}"
        now = utc_now()
        if body.action_type == "read":
            try:
                result = run_read(connector, body.operation, body.payload)
            except Exception as exc:
                audit(connection, user_id=user["id"], event_type="connector.read_failed", target_type="connector", target_id=connector_id, result="failed", case_id=case_id, detail={"operation": body.operation, "error": str(exc)})
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            connection.execute("""INSERT INTO connector_actions(id, connector_id, case_id, action_type, operation, payload_json, status, result_json, requested_by, created_at, executed_at) VALUES (?, ?, ?, 'read', ?, ?, 'executed', ?, ?, ?, ?)""", (action_id, connector_id, case_id, body.operation, json.dumps(body.payload, ensure_ascii=False), json.dumps(result, ensure_ascii=False), user["id"], now, now))
            audit(connection, user_id=user["id"], event_type="connector.read", target_type="connector", target_id=connector_id, case_id=case_id, detail={"operation": body.operation})
            return {"id": action_id, "status": "executed", "result": result, "requires_approval": False}

        connection.execute("""INSERT INTO connector_actions(id, connector_id, case_id, action_type, operation, payload_json, status, requested_by, created_at) VALUES (?, ?, ?, 'write', ?, ?, 'pending', ?, ?)""", (action_id, connector_id, case_id, body.operation, json.dumps(body.payload, ensure_ascii=False), user["id"], now))
        approval_id = f"approval-{uuid.uuid4().hex}"
        connection.execute("""INSERT INTO approvals(id, case_id, artifact_id, artifact_type, status, requested_by, created_at) VALUES (?, ?, ?, 'connector_action', 'pending', ?, ?)""", (approval_id, case_id, action_id, user["id"], now))
        audit(connection, user_id=user["id"], event_type="connector.write_requested", target_type="connector_action", target_id=action_id, case_id=case_id, detail={"connector": connector_id, "operation": body.operation})
        return {"id": action_id, "status": "pending", "approval_id": approval_id, "requires_approval": True, "preview": body.payload}


def _generate_message(
    *,
    case_id: str,
    body: MessageCreate,
    user: dict[str, Any],
    parent_id: str | None,
    version: int,
    insert_user: bool = True,
) -> dict[str, Any]:
    now = utc_now()
    with connect() as connection:
        require_case_access(connection, case_id, user, write=True)
        history_rows = connection.execute(
            """SELECT role, content FROM messages
               WHERE case_id = ? AND task_type = ? AND role IN ('user', 'assistant')
               ORDER BY created_at DESC LIMIT 12""",
            (case_id, body.task_type),
        ).fetchall()
        history = [
            {"role": row["role"], "content": row["content"]}
            for row in reversed(history_rows)
            if row["content"]
        ]
        if insert_user:
            parent_id = f"msg-{uuid.uuid4().hex}"
            connection.execute("""INSERT INTO messages(id, case_id, role, task_type, content, created_by, created_at) VALUES (?, ?, 'user', ?, ?, ?, ?)""", (parent_id, case_id, body.task_type, body.question, user["id"], now))
        contexts = retrieve(connection, case_id=case_id, query=body.question, task_type=body.task_type)
        if body.task_type == "general" and not _chat_requests_case_context(body.question, contexts):
            contexts = []
        audit(connection, user_id=user["id"], event_type="search.completed", target_type="case", target_id=case_id, case_id=case_id, detail={"task_type": body.task_type, "chunks": len(contexts), "documents": list(dict.fromkeys(item.document_id for item in contexts))})

    result = local_ai.generate(
        question=body.question,
        task_type=body.task_type,
        contexts=contexts,
        history=history,
    )
    assistant_id = f"msg-{uuid.uuid4().hex}"
    payload_json = json.dumps(result.payload, ensure_ascii=False) if result.payload is not None else None
    citations = result.payload.get("sources", []) if result.payload is not None else [context.citation() for context in contexts[:12]]
    content = result.content
    is_chat = body.task_type == "general"
    message_status = "complete" if is_chat else "review_required"
    with connect() as connection:
        require_case_access(connection, case_id, user, write=True)
        connection.execute("""INSERT INTO messages(id, case_id, role, task_type, content, payload_json, citations_json, status, model, parent_id, version, created_by, created_at) VALUES (?, ?, 'assistant', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (assistant_id, case_id, body.task_type, content, payload_json, json.dumps(citations, ensure_ascii=False), message_status, result.model, parent_id, version, user["id"], utc_now()))
        approval_id: str | None = None
        if not is_chat:
            approval_id = f"approval-{uuid.uuid4().hex}"
            artifact_type = result.payload.get("artifact_type", "memo") if result.payload is not None else "memo"
            connection.execute("""INSERT INTO approvals(id, case_id, artifact_id, artifact_type, status, requested_by, created_at) VALUES (?, ?, ?, ?, 'pending', ?, ?)""", (approval_id, case_id, assistant_id, artifact_type, user["id"], utc_now()))
            connection.execute("UPDATE cases SET status = 'pending_approval', updated_at = ? WHERE id = ?", (utc_now(), case_id))
        audit(connection, user_id=user["id"], event_type="generation.completed", target_type="message", target_id=assistant_id, case_id=case_id, detail={"task_type": body.task_type, "model": result.model, "fallback": result.used_fallback, "citations": len(citations), "version": version})
        row = row_dict(connection.execute("SELECT m.*, u.display_name AS created_by_name, u.initials FROM messages m JOIN users u ON u.id = m.created_by WHERE m.id = ?", (assistant_id,)).fetchone())
        assert row is not None
        response = _message_payload(row)
        if approval_id:
            response["approval_id"] = approval_id
        return response


def _chat_requests_case_context(question: str, contexts: list[Any]) -> bool:
    """Avoid letting weak keyword matches steer ordinary conversation toward case files."""
    if re.search(r"資料|文書|案件|契約|条項|条文|証拠|記録|NDA|ひな形|規程|メール", question, re.IGNORECASE):
        return True
    return bool(contexts and max(item.score for item in contexts) >= 0.08)


def _case_payload(connection: sqlite3.Connection, case: dict[str, Any], include_members: bool = False) -> dict[str, Any]:
    payload = dict(case)
    payload["document_count"] = connection.execute("SELECT COUNT(*) FROM documents WHERE case_id = ? AND deleted_at IS NULL", (case["id"],)).fetchone()[0]
    payload["pending_approval_count"] = connection.execute("SELECT COUNT(*) FROM approvals WHERE case_id = ? AND status = 'pending'", (case["id"],)).fetchone()[0]
    deadline = connection.execute("SELECT due_date, title FROM deadlines WHERE case_id = ? AND status = 'open' ORDER BY due_date LIMIT 1", (case["id"],)).fetchone()
    payload["deadline_count"] = connection.execute("SELECT COUNT(*) FROM deadlines WHERE case_id = ? AND status = 'open'", (case["id"],)).fetchone()[0]
    payload["next_deadline_at"] = deadline["due_date"] if deadline else None
    payload["next_deadline_title"] = deadline["title"] if deadline else None
    if include_members:
        payload["members"] = rows_dict(connection.execute("""SELECT u.id, u.display_name, u.initials, u.role, cm.access_level FROM case_members cm JOIN users u ON u.id = cm.user_id WHERE cm.case_id = ? ORDER BY cm.access_level""", (case["id"],)).fetchall())
    return payload


def _document_payload(document: dict[str, Any], *, include_content: bool) -> dict[str, Any]:
    payload = dict(document)
    if not include_content:
        payload.pop("content", None)
        payload.pop("storage_path", None)
    payload.pop("sha256", None)
    payload["size_label"] = _size_label(int(payload.get("size_bytes", 0)))
    return payload


def _message_payload(message: dict[str, Any]) -> dict[str, Any]:
    payload = dict(message)
    payload["payload"] = _normalize_payload_copy(_json_load(payload.pop("payload_json", None), None))
    payload["citations"] = _json_load(payload.pop("citations_json", None), [])
    return payload


def _approval_payload(approval: dict[str, Any]) -> dict[str, Any]:
    payload = dict(approval)
    payload["artifact_payload"] = _normalize_payload_copy(_json_load(payload.pop("message_payload", None), None))
    if payload.get("message_content"):
        payload["message_content"] = _normalize_payload_copy(payload["message_content"])
    return payload


def _normalize_payload_copy(value: Any) -> Any:
    """Keep previously saved mock responses consistent with the current interface copy."""
    if isinstance(value, list):
        return [_normalize_payload_copy(item) for item in value]
    if not isinstance(value, dict):
        if not isinstance(value, str):
            return value
        replacements = (
            ("担当者が修正する書類ドラフト", "書類案"),
            ("成果物の短い分類", "作成結果"),
            ("結論が分かるタイトル", "確認結果"),
            ("第8条（第三者への開示）を含む2点の修正を推奨します", "第8条（第三者への開示）ほか修正事項：2件"),
            ("ローカルLLMに接続できなかったため、資料検索と規則ベースの下書きを表示しています。", "登録資料をもとに書類案を作成しました。"),
            ("業務種別: 書類ドラフト | 成果物種別: draft", "書類作成"),
            ("業務種別: 案件アシスタント\n成果物種別: memo", "質問・相談"),
            ("業務種別と成果物種別を整理し、修正が必要なポイントを明確化。法的条文に基づき、確認が必要な事実を提示。", "確認対象を整理し、修正が必要な箇所と確認事項を示します。"),
            ("業務種別と成果物種別を整理し、修正が必要な箇所を明示。関連する条文や条件を確認し、根拠に基づいた調整を提案。", "確認対象を整理し、修正が必要な箇所と対応案を示します。"),
            ("本資料は、業務種別におけるNDAの適用範囲、有効期間、第三者への開示条件について整理しています。各条項の根拠と注意点が明記されています。", "NDAの適用範囲、有効期間、第三者への開示条件を整理しています。"),
            ("本資料は、NDAの条項や有効期間、第三者への開示に関する要点を整理し、弁護士が確認すべき内容を示しています。", "NDAの条項、有効期間、第三者への開示条件に関する確認事項を整理しています。"),
            ("本資料は、再委託先への秘密情報開示に関する条項の確認と、弁護士による適切な条文の調整を目的とした構造化資料です。各条項の適用可能性やリスク点を整理しています。", "再委託先への秘密情報開示に関する条項、適用条件、注意点を整理しています。"),
            ("書類ドラフト", "書類案"),
            ("ドラフト本文", "書類案本文"),
            ("ドラフト", "書類案"),
            ("資料から転記した項目", "資料から反映した内容"),
            ("人が確認する項目", "担当者確認"),
            ("人の作業", "対応方法"),
            ("整合性チェック", "整合性確認"),
            ("契約レビュー", "契約書確認"),
            ("レビュー結果", "確認結果"),
            ("レビュー", "確認"),
            ("弁護士", "確認責任者"),
            ("リスク点", "注意点"),
            ("AI成果物", "作成結果"),
            ("成果物", "作成結果"),
        )
        normalized = value
        for source, target in replacements:
            normalized = normalized.replace(source, target)
        normalized = re.sub(r"確認候補を(\d+)件表示しました", r"確認事項：\1件", normalized)
        normalized = normalized.replace("を参照したデモ用初稿です。", "をもとに作成しました。")
        normalized = normalized.replace("を参照した初稿です。", "をもとに作成しました。")
        if "をもとに作成しました。" in normalized and (".txt" in normalized or ".pdf" in normalized):
            normalized = re.sub(r"[^。\n]+をもとに作成しました。", "登録資料をもとに作成しました。", normalized)
        return normalized

    normalized = {key: _normalize_payload_copy(item) for key, item in value.items()}
    artifact_type = normalized.get("artifact_type")
    labels = {
        "draft": "書類作成",
        "consistency_check": "整合性確認",
        "review": "契約書確認",
        "research": "法令・判例調査",
        "litigation": "紛争整理",
        "client_response": "依頼人対応",
        "clause": "修正文案",
        "mail": "説明文案",
        "checklist": "確認事項",
        "timeline": "時系列表",
        "memo": "質問・相談",
    }
    if artifact_type in labels:
        normalized["label"] = labels[artifact_type]
    if artifact_type == "draft" and isinstance(normalized.get("blocks"), list):
        for block in normalized["blocks"]:
            if not isinstance(block, dict) or block.get("title") != "書類案本文":
                continue
            content = block.get("content")
            if isinstance(content, str) and ("登録された相談記録" in content or "担当者が内容を修正" in content):
                block["content"] = _rewrite_legacy_draft_body(content)
    return normalized


def _rewrite_legacy_draft_body(content: str) -> str:
    facts_match = re.search(r"2\. 確認できた事実\s*(.*?)\s*3\. 未確認事項", content, re.DOTALL)
    facts = _naturalize_excerpt(facts_match.group(1)) if facts_match else "登録資料に記載された事実を確認してください。"
    return (
        "調査・確認報告書（案）\n\n"
        "1. 依頼の概要\n"
        "本件について、登録されている相談記録、提出書面案および証拠資料を確認し、依頼内容と現時点で確認できる事実を整理した。\n\n"
        "2. 確認できた事実\n"
        f"{facts}\n\n"
        "3. 未確認事項\n"
        "氏名、住所、日付、金額、引用箇所および証拠番号について、書類案と原本の記載が一致しているかを確認する必要がある。\n\n"
        "4. 次の対応\n"
        "担当者が事実関係と表現を確認・修正したうえで、確認責任者の承認後に正式な書類へ反映する。"
    )


def _json_load(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _size_label(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.getenv("PORT", "8080")), reload=False)
