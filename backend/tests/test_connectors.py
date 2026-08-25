from __future__ import annotations

import base64

from app.connectors import _prepare_request


def connector(kind: str, provider: str) -> dict[str, str]:
    return {"kind": kind, "provider": provider}


def test_google_calendar_freebusy_uses_post_body() -> None:
    request = _prepare_request(
        connector("calendar", "google"),
        "availability",
        {"range_days": 5, "calendar_ids": ["primary", "lawyer@example.jp"]},
        "GET",
    )
    assert request["method"] == "POST"
    assert request["json"]["timeZone"] == "Asia/Tokyo"
    assert request["json"]["items"] == [{"id": "primary"}, {"id": "lawyer@example.jp"}]


def test_google_gmail_draft_contains_rfc_message() -> None:
    request = _prepare_request(
        connector("mail", "google"),
        "save_draft",
        {"subject": "NDA確認", "to": "client@example.jp", "body": "確認結果です。"},
        "POST",
    )
    raw = request["json"]["message"]["raw"]
    decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")
    assert "Subject:" in decoded
    assert "client@example.jp" in decoded


def test_microsoft_mail_payload_is_graph_shape() -> None:
    request = _prepare_request(
        connector("mail", "microsoft"),
        "send_message",
        {"subject": "確認結果", "to": "client@example.jp", "body": "本文"},
        "POST",
    )
    assert request["json"]["message"]["body"]["contentType"] == "text"
    assert request["json"]["message"]["toRecipients"][0]["emailAddress"]["address"] == "client@example.jp"


def test_google_drive_upload_is_multipart() -> None:
    request = _prepare_request(
        connector("drive", "google"),
        "save_artifact",
        {"name": "review.txt", "content": "review result"},
        "POST",
    )
    assert request["params"]["uploadType"] == "multipart"
    assert request["files"]["file"][0] == "review.txt"

