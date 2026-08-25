from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def headers(user: str = "user-admin") -> dict[str, str]:
    return {"X-User-Id": user}


def test_seeded_workspace_and_health() -> None:
    with TestClient(app) as client:
        health = client.get("/api/health", headers=headers())
        assert health.status_code == 200
        assert health.json()["database"]["reachable"] is True
        assert health.json()["offline_mode"] is True

        users = client.get("/api/users", headers=headers())
        assert users.status_code == 200
        assert {item["role"] for item in users.json()} >= {"admin", "lawyer", "staff"}

        cases = client.get("/api/cases", headers=headers())
        assert cases.status_code == 200
        assert cases.json()[0]["id"] == "C-2026-0710"
        assert cases.json()[0]["document_count"] == 4


def test_document_upload_search_generation_and_citations() -> None:
    with TestClient(app) as client:
        uploaded = client.post(
            "/api/cases/C-2026-0710/documents",
            headers=headers(),
            data={"kind": "evidence"},
            files={
                "file": (
                    "納品記録.txt",
                    "2026年7月1日 A社へ成果物を納品した。\n2026年7月3日 A社担当者が受領を返信した。".encode(),
                    "text/plain",
                )
            },
        )
        assert uploaded.status_code == 201, uploaded.text
        document_id = uploaded.json()["id"]

        document = client.get(f"/api/documents/{document_id}", headers=headers())
        assert document.status_code == 200
        assert "2026年7月1日" in document.json()["content"]

        generated = client.post(
            "/api/cases/C-2026-0710/messages",
            headers=headers(),
            json={"task_type": "litigation", "question": "納品と受領を時系列にしてください"},
        )
        assert generated.status_code == 201, generated.text
        body = generated.json()
        assert body["payload"]["artifact_type"] == "litigation"
        assert body["payload"]["sources"]
        assert any(item["document_id"] == document_id for item in body["payload"]["sources"])
        assert body["status"] == "review_required"


def test_general_chat_is_plain_conversation_without_approval() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/cases/C-2026-0710/messages",
            headers=headers(),
            json={"task_type": "general", "question": "こんにちは。今日は何ができますか？"},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["payload"] is None
        assert body["status"] == "complete"
        assert "approval_id" not in body
        assert body["citations"] == []


def test_draft_and_consistency_check_are_reviewable_artifacts() -> None:
    with TestClient(app) as client:
        draft = client.post(
            "/api/cases/C-2026-0710/messages",
            headers=headers(),
            json={"task_type": "draft", "question": "登録資料をもとに書類の初稿を作成してください"},
        )
        assert draft.status_code == 201, draft.text
        assert draft.json()["payload"]["artifact_type"] == "draft"
        assert draft.json()["status"] == "review_required"
        assert draft.json()["approval_id"]

        check = client.post(
            "/api/cases/C-2026-0710/messages",
            headers=headers(),
            json={"task_type": "consistency_check", "question": "数字と日付の整合性を確認してください"},
        )
        assert check.status_code == 201, check.text
        assert check.json()["payload"]["artifact_type"] == "consistency_check"
        assert check.json()["status"] == "review_required"


def test_draft_versions_and_finding_resolutions_are_persisted() -> None:
    with TestClient(app) as client:
        generated = client.post(
            "/api/cases/C-2026-0710/messages",
            headers=headers(),
            json={"task_type": "draft", "question": "登録資料をもとに報告書の初稿を作成してください"},
        )
        assert generated.status_code == 201, generated.text
        message = generated.json()
        title = message["payload"]["title"]
        content = "担当者が確認・修正するドラフト本文です。"

        saved = client.post(
            "/api/cases/C-2026-0710/drafts",
            headers=headers(),
            json={"source_message_id": message["id"], "title": title, "content": content},
        )
        assert saved.status_code == 201, saved.text
        assert saved.json()["version"] == 1
        assert saved.json()["content"] == content

        versions = client.get(f"/api/cases/C-2026-0710/drafts?source_message_id={message['id']}", headers=headers())
        assert versions.status_code == 200
        assert len(versions.json()) == 1

        check = client.post(
            "/api/cases/C-2026-0710/messages",
            headers=headers(),
            json={"task_type": "consistency_check", "question": "資料間の整合性を確認してください"},
        )
        assert check.status_code == 201, check.text
        check_message = check.json()

        findings = client.get(f"/api/messages/{check_message['id']}/findings", headers=headers())
        assert findings.status_code == 200
        assert len(check_message["payload"]["findings"]) >= 1
        assert findings.json() == []

        updated = client.put(
            f"/api/messages/{check_message['id']}/findings/0",
            headers=headers(),
            json={"status": "resolved", "note": "原文と照合済み"},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["status"] == "resolved"

        resolved = client.get(f"/api/messages/{check_message['id']}/findings", headers=headers())
        assert resolved.json()[0]["status"] == "resolved"


def test_role_based_approval_gate() -> None:
    with TestClient(app) as client:
        generated = client.post(
            "/api/cases/C-2026-0710/messages",
            headers=headers("user-staff"),
            json={"task_type": "contract_review", "question": "NDAをレビューしてください"},
        )
        assert generated.status_code == 201
        approval_id = generated.json()["approval_id"]

        forbidden = client.post(
            f"/api/approvals/{approval_id}/decision",
            headers=headers("user-staff"),
            json={"decision": "approved", "comment": "確認"},
        )
        assert forbidden.status_code == 403

        approved = client.post(
            f"/api/approvals/{approval_id}/decision",
            headers=headers("user-lawyer"),
            json={"decision": "approved", "comment": "条文と根拠を確認"},
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"


def test_connector_reads_and_writes_only_after_approval() -> None:
    with TestClient(app) as client:
        read = client.post(
            "/api/cases/C-2026-0710/connectors/calendar/actions",
            headers=headers("user-staff"),
            json={"action_type": "read", "operation": "availability", "payload": {"range_days": 7}},
        )
        assert read.status_code == 201
        assert read.json()["status"] == "executed"
        assert len(read.json()["result"]["items"]) == 3

        write = client.post(
            "/api/cases/C-2026-0710/connectors/calendar/actions",
            headers=headers("user-staff"),
            json={
                "action_type": "write",
                "operation": "create_tentative_event",
                "payload": {"title": "A社打合せ", "start": "2026-07-20T10:00:00+09:00"},
            },
        )
        assert write.status_code == 201
        assert write.json()["status"] == "pending"

        decided = client.post(
            f"/api/approvals/{write.json()['approval_id']}/decision",
            headers=headers("user-lawyer"),
            json={"decision": "approved", "comment": "日程確認済み"},
        )
        assert decided.status_code == 200, decided.text
        assert decided.json()["status"] == "executed"


def test_case_boundaries_are_enforced() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/api/cases",
            headers=headers(),
            json={"name": "機密案件", "client_name": "B社", "summary": "管理者限定"},
        )
        assert created.status_code == 201
        case_id = created.json()["id"]

        denied = client.get(f"/api/cases/{case_id}", headers=headers("user-staff"))
        assert denied.status_code == 403

        invisible = client.get("/api/cases", headers=headers("user-staff"))
        assert all(item["id"] != case_id for item in invisible.json())
