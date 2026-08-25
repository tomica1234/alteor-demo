from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


@dataclass(frozen=True)
class ParsedChunk:
    page_number: int | None
    section: str
    text: str


@dataclass(frozen=True)
class ParsedDocument:
    content: str
    page_count: int
    chunks: list[ParsedChunk]


def parse_document(path: Path, filename: str) -> ParsedDocument:
    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        pages = [_extract_docx(path)]
    elif suffix == ".pdf":
        pages = _extract_pdf(path)
    elif suffix in {".txt", ".md", ".csv"}:
        pages = [_read_text(path)]
    else:
        raise ValueError("対応形式はDOCX、PDF、TXTです。")

    chunks: list[ParsedChunk] = []
    for page_number, text in enumerate(pages, start=1):
        chunks.extend(_chunk_page(text, page_number if suffix == ".pdf" else None))
    content = "\n\n".join(page.strip() for page in pages if page.strip())
    if not content.strip():
        if suffix == ".pdf":
            raise ValueError("PDF内の文字を読み取れませんでした。スキャンPDFには対応していません。")
        raise ValueError("資料に読み取れる文字がありません。")
    return ParsedDocument(content=content, page_count=max(len(pages), 1), chunks=chunks)


def _extract_docx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValueError("DOCXファイルが破損しているか、対応していない形式です。") from exc

    root = ElementTree.fromstring(xml)
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    lines: list[str] = []
    for paragraph in root.iter(f"{namespace}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t")).strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def _extract_pdf(path: Path) -> list[str]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return [(page.extract_text() or "").strip() for page in reader.pages]
    except Exception as exc:
        raise ValueError("PDFファイルを読み取れませんでした。") from exc


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp932", "shift_jis"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("テキストの文字コードを判定できませんでした。")


def _chunk_page(text: str, page_number: int | None, max_chars: int = 1200) -> list[ParsedChunk]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", normalized) if part.strip()]
    if len(paragraphs) <= 1:
        paragraphs = [line.strip() for line in normalized.split("\n") if line.strip()]

    chunks: list[ParsedChunk] = []
    buffer: list[str] = []
    buffer_length = 0
    current_section = ""

    def flush() -> None:
        nonlocal buffer, buffer_length
        if not buffer:
            return
        body = "\n".join(buffer).strip()
        chunks.append(
            ParsedChunk(
                page_number=page_number,
                section=current_section or _section_from_text(body),
                text=body,
            )
        )
        buffer = []
        buffer_length = 0

    for paragraph in paragraphs:
        detected_section = _section_from_text(paragraph)
        if detected_section and re.match(r"^(第\s*[0-9０-９一二三四五六七八九十百]+\s*条|[0-9０-９]+[.．])", detected_section):
            flush()
            current_section = detected_section
        if buffer and buffer_length + len(paragraph) + 1 > max_chars:
            flush()
        if len(paragraph) > max_chars:
            flush()
            for start in range(0, len(paragraph), max_chars):
                piece = paragraph[start : start + max_chars]
                chunks.append(
                    ParsedChunk(page_number=page_number, section=current_section or _section_from_text(piece), text=piece)
                )
            continue
        buffer.append(paragraph)
        buffer_length += len(paragraph) + 1
    flush()
    return chunks or [ParsedChunk(page_number=page_number, section="本文", text=normalized[:max_chars])]


def _section_from_text(text: str) -> str:
    first_line = text.splitlines()[0].strip() if text.strip() else "本文"
    article = re.match(r"^(第\s*[0-9０-９一二三四五六七八九十百]+\s*条(?:（[^）]+）)?)", first_line)
    if article:
        return article.group(1).replace(" ", "")
    return first_line[:100]
