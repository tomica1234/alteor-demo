from __future__ import annotations

import math
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from typing import Any


TASK_HINTS = {
    "draft": "書類 ドラフト 下書き 文案 目的 事実 構成 宛先",
    "consistency_check": "整合性 照合 誤字脱字 数字 日付 氏名 引用 証拠",
    "contract_review": "契約 条項 ひな形 差分 リスク 修正 交渉",
    "legal_research": "法律相談 論点 判例 所内Q&A 前提事実 見通し",
    "litigation": "訴訟 紛争 証拠 日付 時系列 当事者 主張 反論",
    "client_support": "顧問先 相談 回答 メール 規程 面談 確認事項",
    "clause": "修正文案 条文 代替案",
    "mail": "説明メール 顧問先 相手方",
    "checklist": "確認事項 チェックリスト",
    "timeline": "時系列 日付 証拠 当事者",
}


@dataclass(frozen=True)
class ContextChunk:
    chunk_id: str
    document_id: str
    document_name: str
    document_kind: str
    page_number: int | None
    section: str
    text: str
    score: float

    def citation(self) -> dict[str, Any]:
        locator = self.section or "本文"
        if self.page_number:
            locator = f"p.{self.page_number} {locator}"
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "document_name": self.document_name,
            "locator": locator,
            "excerpt": self.text[:360],
            "score": round(self.score, 4),
        }


def retrieve(
    connection: sqlite3.Connection,
    *,
    case_id: str,
    query: str,
    task_type: str,
    limit: int = 16,
) -> list[ContextChunk]:
    rows = connection.execute(
        """SELECT c.id AS chunk_id, c.document_id, d.name AS document_name,
                  d.kind AS document_kind, c.page_number, c.section, c.text
           FROM document_chunks c
           JOIN documents d ON d.id = c.document_id
           WHERE c.case_id = ? AND d.deleted_at IS NULL AND d.status = 'ready'""",
        (case_id,),
    ).fetchall()
    if not rows:
        return []

    expanded_query = f"{query} {TASK_HINTS.get(task_type, '')}".strip()
    query_tokens = _tokens(expanded_query)
    target_rows: list[sqlite3.Row] = []
    other_rows: list[sqlite3.Row] = []
    for row in rows:
        if task_type == "contract_review" and row["document_kind"] == "target_contract":
            target_rows.append(row)
        else:
            other_rows.append(row)

    scored = [_score_row(row, query_tokens, query) for row in other_rows]
    scored.sort(key=lambda item: item.score, reverse=True)
    selected = scored[:limit]
    if target_rows:
        selected = [_score_row(row, query_tokens, query, target_bonus=0.4) for row in target_rows[:24]] + selected[:12]

    deduplicated: dict[str, ContextChunk] = {}
    for item in sorted(selected, key=lambda candidate: candidate.score, reverse=True):
        deduplicated.setdefault(item.chunk_id, item)
    return list(deduplicated.values())[: max(limit, len(target_rows[:24]))]


def _score_row(
    row: sqlite3.Row,
    query_tokens: set[str],
    raw_query: str,
    target_bonus: float = 0.0,
) -> ContextChunk:
    haystack = f"{row['section']} {row['text']}"
    tokens = _tokens(haystack)
    overlap = len(query_tokens & tokens)
    normalized = overlap / math.sqrt(max(len(query_tokens), 1) * max(len(tokens), 1))
    exact_bonus = 0.0
    compact_query = re.sub(r"\s+", "", raw_query)
    compact_text = re.sub(r"\s+", "", haystack)
    for size in (8, 6, 4):
        if len(compact_query) >= size and any(
            compact_query[index : index + size] in compact_text
            for index in range(0, len(compact_query) - size + 1, max(size // 2, 1))
        ):
            exact_bonus = size / 20
            break
    return ContextChunk(
        chunk_id=row["chunk_id"],
        document_id=row["document_id"],
        document_name=row["document_name"],
        document_kind=row["document_kind"],
        page_number=row["page_number"],
        section=row["section"],
        text=row["text"],
        score=normalized + exact_bonus + target_bonus,
    )


def _tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    ascii_terms = set(re.findall(r"[a-z0-9][a-z0-9_.-]{1,}", normalized))
    japanese_runs = re.findall(r"[一-龠々〆ヵヶぁ-んァ-ヴー]{2,}", normalized)
    japanese_terms: set[str] = set()
    for run in japanese_runs:
        if len(run) <= 8:
            japanese_terms.add(run)
        for size in (2, 3):
            japanese_terms.update(run[index : index + size] for index in range(len(run) - size + 1))
    return ascii_terms | japanese_terms
