from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .retrieval import ContextChunk


TASK_LABELS = {
    "draft": ("書類作成", "draft"),
    "consistency_check": ("整合性確認", "consistency_check"),
    "contract_review": ("契約書確認", "review"),
    "legal_research": ("法令・判例調査", "research"),
    "litigation": ("紛争整理", "litigation"),
    "client_support": ("依頼人対応", "client_response"),
    "clause": ("修正文案", "clause"),
    "mail": ("説明文案", "mail"),
    "checklist": ("確認事項", "checklist"),
    "timeline": ("時系列表", "timeline"),
    "general": ("質問・相談", "memo"),
}


@dataclass(frozen=True)
class GenerationResult:
    payload: dict[str, Any] | None
    content: str
    model: str
    used_fallback: bool


class PrototypeMockEngine:
    """Deterministic responses for workflow validation."""

    def health(self) -> dict[str, Any]:
        return {
            "ready": True,
            "mode": "mock",
            "label": "利用可能",
            "description": "案件アシスタント",
        }

    def generate(
        self,
        *,
        question: str,
        task_type: str,
        contexts: list[ContextChunk],
        history: list[dict[str, str]] | None = None,
    ) -> GenerationResult:
        del history
        normalized_task = task_type if task_type in TASK_LABELS else "general"
        if normalized_task == "general":
            return GenerationResult(
                payload=None,
                content=mock_chat_answer(question=question, contexts=contexts),
                model="prototype-mock",
                used_fallback=False,
            )

        citations = [context.citation() for context in contexts[:8]]
        payload = mock_payload(question=question, task_type=normalized_task, contexts=contexts)
        payload["sources"] = citations
        return GenerationResult(
            payload=payload,
            content=str(payload.get("summary") or payload.get("title") or "結果を作成しました。"),
            model="prototype-mock",
            used_fallback=False,
        )


def mock_payload(*, question: str, task_type: str, contexts: list[ContextChunk]) -> dict[str, Any]:
    label, artifact_type = TASK_LABELS[task_type]
    excerpts = [context for context in contexts if context.text.strip()]
    primary = excerpts[0] if excerpts else None
    source_names = list(dict.fromkeys(context.document_name for context in excerpts))
    source_text = "、".join(source_names[:4])
    source_count_text = f"登録した{len(source_names)}件の資料" if source_names else "登録資料"

    if task_type == "draft":
        fact_text = _naturalize_facts(excerpts)
        draft_body = (
            "調査・確認報告書（案）\n\n"
            "1. 依頼の概要\n"
            "本件について、登録されている相談記録、提出書面案および証拠資料を確認し、依頼内容と現時点で確認できる事実を整理した。\n\n"
            "2. 確認できた事実\n"
            f"{fact_text}\n\n"
            "3. 未確認事項\n"
            "資料間で記載が一致しているか、氏名、住所、日付、金額、引用箇所および証拠番号を原本と照合する必要がある。特に、複数の資料で異なる金額や日付が記載されている場合は、その理由を確認する。\n\n"
            "4. 次の対応\n"
            "担当者が事実関係と表現を確認・修正したうえで、確認責任者の承認後に正式な書類へ反映する。"
        )
        return {
            "label": label,
            "title": "書類案",
            "summary": f"{source_count_text}をもとに書類案を作成しました。" if source_names else "書類案の作成に使用できる資料がありません。",
            "artifact_type": artifact_type,
            "blocks": [
                {"title": "書類案本文", "content": draft_body, "tone": "proposal"},
                {"title": "資料から反映した内容", "items": ["相談内容と依頼の概要", "資料から確認できた事実", "日付、金額、当事者に関する記載"], "tone": "neutral"},
                {"title": "担当者確認", "items": ["事実と推測を区別できているか", "引用元と証拠番号が対応しているか", "提出先に適した表現になっているか", "法的評価または調査上の判断が妥当か"], "tone": "risk"},
            ],
            "findings": [],
            "suggested_actions": ["整合性を確認する"],
        }

    if task_type == "consistency_check":
        findings = _consistency_findings(excerpts)
        if not findings:
            findings = [
                {
                    "title": "日付・証拠番号の原本照合が必要",
                    "severity": "medium",
                    "target": "提出用書面・調査報告書",
                    "risk": "書類案と原資料が一致しているか確認できていません。",
                    "recommendation": "該当ページを開き、日付、氏名、証拠番号を照合してください。",
                    "checks": ["日付", "氏名", "金額", "引用箇所", "証拠番号"],
                }
            ]
        return {
            "label": label,
            "title": f"確認事項：{len(findings)}件",
            "summary": f"{source_count_text}を照合し、不一致の可能性がある箇所を抽出しました。" if source_names else "整合性確認に使用できる資料がありません。",
            "artifact_type": artifact_type,
            "blocks": [
                {"title": "確認結果", "items": [item["title"] for item in findings], "tone": "risk"},
                {"title": "照合項目", "items": ["誤字脱字がないか", "氏名・住所が原資料と一致しているか", "日付・期限が時系列と一致しているか", "金額・数量が計算根拠と一致しているか", "引用箇所と証拠番号が対応しているか"], "tone": "neutral"},
                {"title": "対応方法", "content": "各項目の原本を確認し、対応済み、要確認、対象外のいずれかを記録してください。", "tone": "proposal"},
            ],
            "findings": findings,
            "suggested_actions": ["書類案を作成する"],
        }

    if task_type in {"litigation", "timeline"}:
        events = _timeline_items(excerpts)
        return {
            "label": label,
            "title": "時系列表",
            "summary": f"{source_count_text}から日付を含む記載を抽出しました。" if source_names else "時系列表の作成に使用できる資料がありません。",
            "artifact_type": artifact_type,
            "blocks": [
                {"title": "時系列候補", "items": events or ["日付を含む記載が見つからないため、原資料を確認してください。"], "tone": "neutral"},
                {"title": "担当者確認", "items": ["当事者が正しく記載されているか", "日時が原資料と一致しているか", "各項目の参照資料を特定できるか", "次の対応を決められるか"], "tone": "risk"},
            ],
            "findings": [],
            "suggested_actions": ["確認事項を整理する"],
        }

    return {
        "label": label,
        "title": "確認事項",
        "summary": f"「{question[:100]}」に関する確認事項を整理しました。",
        "artifact_type": artifact_type,
        "blocks": [
            {"title": "確認できた内容", "content": _naturalize_excerpt(primary.text) if primary else "案件資料が登録されていないため、確認できる内容がありません。", "tone": "neutral"},
            {"title": "参照資料", "items": source_names[:6] or ["参照できる資料はありません。"], "tone": "neutral"},
            {"title": "担当者確認", "items": ["原文と一致しているか確認する", "不足している資料を特定する", "最終判断と修正内容を確定する"], "tone": "risk"},
        ],
        "findings": [],
        "suggested_actions": ["書類案を作成する", "整合性を確認する"],
    }


def mock_chat_answer(*, question: str, contexts: list[ContextChunk]) -> str:
    excerpts = [context for context in contexts if context.text.strip()]
    if not excerpts:
        return (
            "書類案の作成と整合性確認を行えます。\n"
            "案件資料を登録し、作成する書類または確認する内容を入力してください。"
        )
    primary = excerpts[0]
    return (
        f"登録資料を確認したところ、「{question[:100]}」に関連する記載が"
        f"{primary.document_name}の{primary.section or '本文'}に見つかりました。\n\n"
        f"{_naturalize_excerpt(primary.text)}"
    )


def _timeline_items(contexts: list[ContextChunk]) -> list[str]:
    events: list[str] = []
    date_pattern = re.compile(r"(?:20\d{2})[年/.-](?:0?[1-9]|1[0-2])[月/.-](?:0?[1-9]|[12]\d|3[01])日?")
    for context in contexts:
        for line in context.text.splitlines():
            match = date_pattern.search(line)
            if match:
                detail = line.replace(match.group(0), "").strip(" ：:　")
                events.append(f"{match.group(0)}について、{detail or '関連する記録があります'}。参照資料は{context.document_name}です。")
    return list(dict.fromkeys(events))[:12]


def _consistency_findings(contexts: list[ContextChunk]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    amounts: dict[str, list[str]] = {}
    dates: dict[str, list[str]] = {}
    amount_pattern = re.compile(r"\d[\d,，]*(?:円|万円|億円)")
    date_pattern = re.compile(r"(?:20\d{2})[年/.-](?:0?[1-9]|1[0-2])[月/.-](?:0?[1-9]|[12]\d|3[01])日?")
    for context in contexts:
        for value in amount_pattern.findall(context.text):
            amounts.setdefault(value, []).append(context.document_name)
        for value in date_pattern.findall(context.text):
            dates.setdefault(value, []).append(context.document_name)
    if len(amounts) > 1:
        values = "、".join(amounts)
        findings.append({"title": "資料間で金額が一致していません", "severity": "high", "target": "金額・明細", "risk": f"登録資料には{values}が記載されています。同一の支払額または取引額を指す場合は、資料間に差異があります。", "recommendation": "各金額の対象取引と計算根拠を確認し、原本と照合してください。", "checks": list(amounts)})
    if len(dates) > 1:
        values = "、".join(dates)
        findings.append({"title": "資料間で日付が一致していません", "severity": "medium", "target": "日付・期限", "risk": f"登録資料には{values}が記載されています。契約日、発生日、支払日、返金期限のいずれに当たるかを確認する必要があります。", "recommendation": "各日付の意味を確認し、時系列と原文を照合してください。", "checks": list(dates)})
    return findings[:8]


def _naturalize_excerpt(text: str) -> str:
    """Turn extracted source lines into readable prose for the prototype response."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines and (lines[0].endswith("記録") or lines[0].endswith("抜粋") or "（確認前）" in lines[0] or "（確認用抜粋）" in lines[0]):
        lines = lines[1:]
    normalized: list[str] = []
    for line in lines:
        if line in {"次の対応", "確認事項", "提出前チェックリスト"}:
            continue
        line = re.sub(r"^([^：:]{1,20})[：:]\s*", r"\1は", line)
        normalized.append(line)
    return " ".join(normalized)[:1200] or "登録資料に記載された内容を確認してください。"


def _naturalize_facts(contexts: list[ContextChunk]) -> str:
    sentences: list[str] = []
    skip_phrases = ("確認する", "照合する", "一致しているか", "対応しているか", "確認したか", "原本確認前")
    for context in contexts:
        for raw_line in context.text.splitlines():
            line = raw_line.strip()
            if not line or line in {"次の対応", "確認事項", "提出前チェックリスト"} or line.startswith("確認事項:"):
                continue
            if line[0].isdigit() and re.match(r"^\d+[.．]", line):
                continue
            if any(phrase in line for phrase in skip_phrases):
                continue
            if line.endswith(("記録", "抜粋", "（確認前）")) and len(line) < 40:
                continue
            if "（確認用抜粋）" in line:
                continue
            line = re.sub(r"^([^：:]{1,20})[：:]\s*", r"\1は", line)
            if not line.endswith(("。", "！", "？")):
                line += "。"
            sentences.append(line)
    unique_sentences = list(dict.fromkeys(sentences))
    return " ".join(unique_sentences)[:1600] or "登録資料がないため、現時点で確認できる事実を記載できません。"


local_ai = PrototypeMockEngine()
