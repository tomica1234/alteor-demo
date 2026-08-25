from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any

import httpx

from .config import settings


READ_OPERATIONS = {
    "calendar": {"availability", "events"},
    "mail": {"threads", "messages"},
    "drive": {"files", "search"},
    "database": {"case", "history"},
}

WRITE_OPERATIONS = {
    "calendar": {"create_tentative_event"},
    "mail": {"save_draft", "send_message"},
    "drive": {"save_artifact"},
    "database": {"update_case_memo"},
}


def allowed_operation(kind: str, operation: str, action_type: str) -> bool:
    table = READ_OPERATIONS if action_type == "read" else WRITE_OPERATIONS
    return operation in table.get(kind, set())


def run_read(connector: dict[str, Any], operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    if connector.get("mode") != "live":
        return local_result(connector["kind"], operation, payload, executed=True)
    return _run_live(connector, operation, payload, method="GET")


def run_write(connector: dict[str, Any], operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    if connector.get("mode") != "live":
        return local_result(connector["kind"], operation, payload, executed=True)
    return _run_live(connector, operation, payload, method="POST")


def local_result(kind: str, operation: str, payload: dict[str, Any], *, executed: bool) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    if kind == "calendar" and operation in {"availability", "events"}:
        return {
            "mode": "local",
            "executed": executed,
            "summary": "担当者2名の空き時間から3件の候補を作成しました。",
            "items": [
                {"start": (now + timedelta(days=1, hours=1)).isoformat(timespec="minutes"), "duration_minutes": 30, "attendees": ["担当者", "担当弁護士"]},
                {"start": (now + timedelta(days=2, hours=3)).isoformat(timespec="minutes"), "duration_minutes": 30, "attendees": ["担当者", "担当弁護士"]},
                {"start": (now + timedelta(days=3, hours=2)).isoformat(timespec="minutes"), "duration_minutes": 60, "attendees": ["担当者", "担当弁護士"]},
            ],
        }
    if kind == "calendar":
        return {
            "mode": "local",
            "executed": executed,
            "summary": "承認済みの仮予定をローカル連携履歴へ登録しました。",
            "event": {"title": payload.get("title", "案件打合せ"), "start": payload.get("start"), "status": "tentative"},
        }
    if kind == "mail" and operation in {"threads", "messages"}:
        return {
            "mode": "local",
            "executed": executed,
            "summary": "案件名に一致する2件のメールスレッドを確認しました。",
            "items": [
                {"subject": "NDA更新案の送付", "from": "legal@example.jp", "date": "2026-07-10", "snippet": "NDA更新案をお送りします。"},
                {"subject": "Re: NDA更新条件", "from": "client@example.jp", "date": "2025-04-18", "snippet": "再委託先への共有について確認しました。"},
            ],
        }
    if kind == "mail":
        return {
            "mode": "local",
            "executed": executed,
            "summary": "承認済みメールをローカル下書きとして保存しました。" if operation == "save_draft" else "承認済みメールの送信操作をローカル履歴へ記録しました。",
            "message": {"subject": payload.get("subject", "案件のご連絡"), "status": "draft" if operation == "save_draft" else "sent"},
        }
    if kind == "drive" and operation in {"files", "search"}:
        return {
            "mode": "local",
            "executed": executed,
            "summary": "案件フォルダから3件の関連資料を確認しました。",
            "items": [
                {"name": "A社_NDA_2026-07-10.docx", "folder": "A社/契約"},
                {"name": "NDA標準ひな形_v3.2.docx", "folder": "所内ひな形"},
                {"name": "A社_過去の確認記録.pdf", "folder": "A社/確認記録"},
            ],
        }
    if kind == "drive":
        return {
            "mode": "local",
            "executed": executed,
            "summary": "承認済みの作成結果を案件フォルダへ保存しました。",
            "file": {"name": payload.get("name", "作成結果.txt"), "status": "saved"},
        }
    if kind == "database" and operation in {"case", "history"}:
        return {
            "mode": "local",
            "executed": executed,
            "summary": "案件管理台帳の相談履歴と担当者情報を確認しました。",
            "case": {"status": "確認中", "owner": "橘 駿太", "last_contact": "2026-07-10"},
        }
    return {
        "mode": "local",
        "executed": executed,
        "summary": "承認済みメモをローカル案件DB履歴へ反映しました。",
        "record": {"status": "updated", "memo": payload.get("memo", "確認済みメモ")},
    }


def _run_live(
    connector: dict[str, Any],
    operation: str,
    payload: dict[str, Any],
    *,
    method: str,
) -> dict[str, Any]:
    if not settings.allow_external_connectors:
        raise RuntimeError("外部連携は無効です。ALTEOR_ALLOW_EXTERNAL_CONNECTORS=true を設定してください。")
    base_url = str(connector.get("base_url") or "").rstrip("/")
    token_env = str(connector.get("token_env") or "")
    if not base_url or not token_env:
        raise RuntimeError("実接続用のURLとトークン環境変数名を設定してください。")
    token = os.getenv(token_env)
    if not token:
        raise RuntimeError(f"環境変数 {token_env} に連携トークンが設定されていません。")

    endpoint = _endpoint(connector, operation)
    request = _prepare_request(connector, operation, payload, method)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    with httpx.Client(timeout=30) as client:
        if request["files"]:
            response = client.request(
                request["method"],
                f"{base_url}{endpoint}",
                headers=headers,
                params=request["params"],
                files=request["files"],
            )
        elif request["method"] == "GET":
            response = client.get(f"{base_url}{endpoint}", headers=headers, params=request["params"])
        else:
            response = client.request(
                request["method"],
                f"{base_url}{endpoint}",
                headers={**headers, "Content-Type": "application/json"},
                params=request["params"],
                json=request["json"],
            )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if response.status_code == 202 or not response.content:
            result = {"accepted": True}
        else:
            result = response.json() if "json" in content_type else {"text": response.text[:4000]}
    return {"mode": "live", "executed": True, "status_code": response.status_code, "result": result}


def _prepare_request(
    connector: dict[str, Any], operation: str, payload: dict[str, Any], default_method: str
) -> dict[str, Any]:
    provider = connector.get("provider")
    kind = connector.get("kind")
    method = default_method
    params: dict[str, Any] = {}
    json_body: dict[str, Any] | None = payload
    files: dict[str, Any] | None = None
    now = datetime.now(timezone.utc)
    range_days = max(1, min(int(payload.get("range_days", 7)), 90))

    if provider == "google":
        if kind == "calendar" and operation == "availability":
            method = "POST"
            json_body = {
                "timeMin": payload.get("time_min") or now.isoformat(),
                "timeMax": payload.get("time_max") or (now + timedelta(days=range_days)).isoformat(),
                "timeZone": payload.get("time_zone", "Asia/Tokyo"),
                "items": [{"id": item} for item in payload.get("calendar_ids", ["primary"])],
            }
        elif kind == "calendar" and operation == "events":
            params = {
                "timeMin": payload.get("time_min") or now.isoformat(),
                "timeMax": payload.get("time_max") or (now + timedelta(days=range_days)).isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
            }
            json_body = None
        elif kind == "calendar" and operation == "create_tentative_event":
            start = _parse_datetime(payload.get("start"))
            end = start + timedelta(minutes=int(payload.get("duration_minutes", 30)))
            json_body = {
                "summary": payload.get("title", "案件打合せ"),
                "description": payload.get("description", "Alteorで承認された仮予定"),
                "start": {"dateTime": start.isoformat(), "timeZone": payload.get("time_zone", "Asia/Tokyo")},
                "end": {"dateTime": end.isoformat(), "timeZone": payload.get("time_zone", "Asia/Tokyo")},
                "transparency": "transparent",
            }
        elif kind == "mail" and operation in {"threads", "messages"}:
            params = {"q": payload.get("query", ""), "maxResults": min(int(payload.get("max_results", 20)), 100)}
            json_body = None
        elif kind == "mail" and operation == "save_draft":
            json_body = {"message": {"raw": _gmail_raw(payload)}}
        elif kind == "mail" and operation == "send_message":
            _require_recipient(payload)
            json_body = {"raw": _gmail_raw(payload)}
        elif kind == "drive" and operation in {"files", "search"}:
            query = str(payload.get("query", "")).replace("'", "\\'")
            params = {"q": f"name contains '{query}' and trashed = false" if query else "trashed = false", "fields": "files(id,name,mimeType,modifiedTime,parents)", "pageSize": min(int(payload.get("max_results", 20)), 100)}
            json_body = None
        elif kind == "drive" and operation == "save_artifact":
            metadata: dict[str, Any] = {"name": payload.get("name", "作成結果.txt")}
            if payload.get("parent_id"):
                metadata["parents"] = [payload["parent_id"]]
            files = {
                "metadata": (None, json.dumps(metadata, ensure_ascii=False), "application/json; charset=UTF-8"),
                "file": (metadata["name"], str(payload.get("content", "")).encode("utf-8"), "text/plain; charset=UTF-8"),
            }
            params = {"uploadType": "multipart", "fields": "id,name,mimeType,webViewLink"}
            json_body = None

    if provider == "microsoft":
        if kind == "calendar" and operation in {"availability", "events"}:
            params = {
                "startDateTime": payload.get("time_min") or now.isoformat(),
                "endDateTime": payload.get("time_max") or (now + timedelta(days=range_days)).isoformat(),
                "$select": "subject,start,end,showAs,organizer",
                "$orderby": "start/dateTime",
            }
            json_body = None
        elif kind == "calendar" and operation == "create_tentative_event":
            start = _parse_datetime(payload.get("start"))
            end = start + timedelta(minutes=int(payload.get("duration_minutes", 30)))
            json_body = {
                "subject": payload.get("title", "案件打合せ"),
                "body": {"contentType": "text", "content": payload.get("description", "Alteorで承認された仮予定")},
                "start": {"dateTime": start.isoformat(), "timeZone": payload.get("time_zone", "Tokyo Standard Time")},
                "end": {"dateTime": end.isoformat(), "timeZone": payload.get("time_zone", "Tokyo Standard Time")},
                "showAs": "tentative",
            }
        elif kind == "mail" and operation in {"threads", "messages"}:
            params = {"$top": min(int(payload.get("max_results", 20)), 100), "$select": "id,subject,from,receivedDateTime,bodyPreview,conversationId"}
            if payload.get("query"):
                params["$search"] = f'"{payload["query"]}"'
            json_body = None
        elif kind == "mail" and operation in {"save_draft", "send_message"}:
            if operation == "send_message":
                _require_recipient(payload)
            message = _graph_message(payload)
            json_body = {"message": message, "saveToSentItems": True} if operation == "send_message" else message

    if provider == "generic_rest":
        if default_method == "GET":
            params = payload
            json_body = None

    return {"method": method, "params": params, "json": json_body, "files": files}


def _endpoint(connector: dict[str, Any], operation: str) -> str:
    provider = connector.get("provider")
    kind = connector.get("kind")
    if provider == "microsoft":
        return {
            ("calendar", "availability"): "/me/calendarView",
            ("calendar", "events"): "/me/events",
            ("calendar", "create_tentative_event"): "/me/events",
            ("mail", "threads"): "/me/messages",
            ("mail", "messages"): "/me/messages",
            ("mail", "save_draft"): "/me/messages",
            ("mail", "send_message"): "/me/sendMail",
        }.get((kind, operation), f"/{operation}")
    if provider == "google":
        return {
            ("calendar", "availability"): "/calendar/v3/freeBusy",
            ("calendar", "events"): "/calendar/v3/calendars/primary/events",
            ("calendar", "create_tentative_event"): "/calendar/v3/calendars/primary/events",
            ("mail", "threads"): "/gmail/v1/users/me/threads",
            ("mail", "messages"): "/gmail/v1/users/me/messages",
            ("mail", "save_draft"): "/gmail/v1/users/me/drafts",
            ("mail", "send_message"): "/gmail/v1/users/me/messages/send",
            ("drive", "files"): "/drive/v3/files",
            ("drive", "search"): "/drive/v3/files",
            ("drive", "save_artifact"): "/upload/drive/v3/files",
        }.get((kind, operation), f"/{operation}")
    return f"/{operation}"


def _gmail_raw(payload: dict[str, Any]) -> str:
    message = EmailMessage()
    message["Subject"] = str(payload.get("subject", "案件のご連絡"))
    if payload.get("to"):
        message["To"] = str(payload["to"])
    if payload.get("cc"):
        message["Cc"] = str(payload["cc"])
    message.set_content(str(payload.get("body", "")))
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")


def _graph_message(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "subject": payload.get("subject", "案件のご連絡"),
        "body": {"contentType": "text", "content": payload.get("body", "")},
    }
    if payload.get("to"):
        result["toRecipients"] = [{"emailAddress": {"address": address.strip()}} for address in str(payload["to"]).split(",") if address.strip()]
    if payload.get("cc"):
        result["ccRecipients"] = [{"emailAddress": {"address": address.strip()}} for address in str(payload["cc"]).split(",") if address.strip()]
    return result


def _require_recipient(payload: dict[str, Any]) -> None:
    if not str(payload.get("to", "")).strip():
        raise RuntimeError("メール送信には承認対象の宛先が必要です。")


def _parse_datetime(value: Any) -> datetime:
    if not value:
        return datetime.now(timezone.utc) + timedelta(days=1)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("予定の開始日時はISO 8601形式で指定してください。") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
