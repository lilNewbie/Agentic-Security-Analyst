"""
Document loader.
Takes a file path + source_type and returns a list of raw page/section dicts
ready for the chunker.

Supported formats: pdf, docx, xlsx, txt, md, json (message export), csv
"""
from __future__ import annotations

import csv
import io
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator

# Optional heavy imports — graceful degradation if packages not installed
try:
    import pdfplumber
    _PDF_OK = True
except ImportError:
    _PDF_OK = False

try:
    from docx import Document as DocxDocument
    _DOCX_OK = True
except ImportError:
    _DOCX_OK = False

try:
    import openpyxl
    _XLSX_OK = True
except ImportError:
    _XLSX_OK = False


@dataclass
class RawPage:
    """One logical page or section extracted from a document."""
    doc_id: str
    page: int | None
    char_start: int
    char_end: int
    text: str
    metadata: dict = field(default_factory=dict)


def load_document(
    file_path: str | Path,
    doc_id: str,
    source_type: str,
    authored_at: str | None = None,
) -> tuple[list[RawPage], dict]:
    """
    Load a document and return (pages, doc_meta).
    doc_meta contains: title, page_count, authored_at (detected if not given).
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return _load_pdf(path, doc_id, source_type, authored_at)
    elif suffix == ".docx":
        return _load_docx(path, doc_id, source_type, authored_at)
    elif suffix in (".xlsx", ".xls"):
        return _load_xlsx(path, doc_id, source_type, authored_at)
    elif suffix in (".txt", ".md"):
        return _load_text(path, doc_id, source_type, authored_at)
    elif suffix == ".json":
        return _load_json_messages(path, doc_id, source_type, authored_at)
    elif suffix == ".csv":
        return _load_csv_messages(path, doc_id, source_type, authored_at)
    else:
        # Fallback: treat as plain text
        return _load_text(path, doc_id, source_type, authored_at)


# ---------------------------------------------------------------------------
# PDF loader
# ---------------------------------------------------------------------------

def _load_pdf(path: Path, doc_id: str, source_type: str, authored_at: str | None):
    if not _PDF_OK:
        raise RuntimeError("pdfplumber not installed — run: pip install pdfplumber")

    pages: list[RawPage] = []
    detected_date: str | None = authored_at
    offset = 0

    with pdfplumber.open(str(path)) as pdf:
        meta = pdf.metadata or {}
        if not detected_date:
            detected_date = _extract_date_from_metadata(meta)

        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if not detected_date:
                detected_date = _detect_date_in_text(text)
            pages.append(RawPage(
                doc_id=doc_id,
                page=page_num,
                char_start=offset,
                char_end=offset + len(text),
                text=text,
                metadata={"source_type": source_type, "authored_at": detected_date},
            ))
            offset += len(text)

    return pages, {
        "title": path.stem,
        "page_count": len(pages),
        "authored_at": detected_date,
    }


# ---------------------------------------------------------------------------
# DOCX loader
# ---------------------------------------------------------------------------

def _load_docx(path: Path, doc_id: str, source_type: str, authored_at: str | None):
    if not _DOCX_OK:
        raise RuntimeError("python-docx not installed — run: pip install python-docx")

    doc = DocxDocument(str(path))
    detected_date = authored_at

    # Treat each section header as a page boundary
    sections: list[RawPage] = []
    current_text_parts: list[str] = []
    section_num = 1
    offset = 0

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        if not detected_date:
            detected_date = _detect_date_in_text(text)
        is_heading = para.style.name.startswith("Heading")
        if is_heading and current_text_parts:
            combined = "\n".join(current_text_parts)
            sections.append(RawPage(
                doc_id=doc_id,
                page=section_num,
                char_start=offset,
                char_end=offset + len(combined),
                text=combined,
                metadata={"source_type": source_type, "authored_at": detected_date},
            ))
            offset += len(combined)
            section_num += 1
            current_text_parts = [text]
        else:
            current_text_parts.append(text)

    if current_text_parts:
        combined = "\n".join(current_text_parts)
        sections.append(RawPage(
            doc_id=doc_id,
            page=section_num,
            char_start=offset,
            char_end=offset + len(combined),
            text=combined,
            metadata={"source_type": source_type, "authored_at": detected_date},
        ))

    return sections, {
        "title": path.stem,
        "page_count": section_num,
        "authored_at": detected_date,
    }


# ---------------------------------------------------------------------------
# XLSX loader (non-questionnaire documents, e.g. infra spreadsheets)
# ---------------------------------------------------------------------------

def _load_xlsx(path: Path, doc_id: str, source_type: str, authored_at: str | None):
    if not _XLSX_OK:
        raise RuntimeError("openpyxl not installed — run: pip install openpyxl")

    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    pages: list[RawPage] = []
    offset = 0
    detected_date = authored_at

    for sheet_num, sheet in enumerate(wb.worksheets, start=1):
        rows: list[str] = []
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c) if c is not None else "" for c in row]
            if any(cells):
                rows.append("\t".join(cells))
        text = "\n".join(rows)
        if not detected_date:
            detected_date = _detect_date_in_text(text)
        pages.append(RawPage(
            doc_id=doc_id,
            page=sheet_num,
            char_start=offset,
            char_end=offset + len(text),
            text=text,
            metadata={"source_type": source_type, "sheet": sheet.title, "authored_at": detected_date},
        ))
        offset += len(text)

    wb.close()
    return pages, {
        "title": path.stem,
        "page_count": len(pages),
        "authored_at": detected_date,
    }


# ---------------------------------------------------------------------------
# Plain text / markdown loader
# ---------------------------------------------------------------------------

def _load_text(path: Path, doc_id: str, source_type: str, authored_at: str | None):
    text = path.read_text(encoding="utf-8", errors="replace")
    detected_date = authored_at or _detect_date_in_text(text[:2000])

    # Split on markdown headings to preserve structure
    import re
    sections = re.split(r'(?m)^#{1,3} ', text)
    pages: list[RawPage] = []
    offset = 0

    for i, section in enumerate(sections):
        if not section.strip():
            continue
        pages.append(RawPage(
            doc_id=doc_id,
            page=i + 1,
            char_start=offset,
            char_end=offset + len(section),
            text=section,
            metadata={"source_type": source_type, "authored_at": detected_date},
        ))
        offset += len(section)

    if not pages:
        pages.append(RawPage(
            doc_id=doc_id, page=1,
            char_start=0, char_end=len(text), text=text,
            metadata={"source_type": source_type, "authored_at": detected_date},
        ))

    return pages, {
        "title": path.stem,
        "page_count": len(pages),
        "authored_at": detected_date,
    }


# ---------------------------------------------------------------------------
# JSON message export loader (e.g. Slack export)
# ---------------------------------------------------------------------------

def _load_json_messages(path: Path, doc_id: str, source_type: str, authored_at: str | None):
    raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))

    # Support both single-channel [{ts, user, text}] and multi-channel [{channel, messages:[]}]
    if isinstance(raw, list):
        messages = raw
    elif isinstance(raw, dict) and "messages" in raw:
        messages = raw["messages"]
    else:
        messages = []

    # Group messages into thread-sized pages (~20 messages per page)
    pages: list[RawPage] = []
    batch: list[str] = []
    batch_dates: list[str] = []
    offset = 0
    page_num = 1

    for msg in messages:
        speaker = msg.get("user") or msg.get("username") or "unknown"
        text_part = msg.get("text") or msg.get("content") or ""
        ts = msg.get("ts") or msg.get("timestamp") or msg.get("date") or ""
        date_str = _normalise_ts(ts)
        batch.append(f"[{speaker}] {text_part}")
        if date_str:
            batch_dates.append(date_str)
        if len(batch) >= 20:
            combined = "\n".join(batch)
            page_date = batch_dates[-1] if batch_dates else authored_at
            pages.append(RawPage(
                doc_id=doc_id, page=page_num,
                char_start=offset, char_end=offset + len(combined),
                text=combined,
                metadata={"source_type": source_type, "authored_at": page_date,
                           "speakers": list({l.split("]")[0][1:] for l in batch})},
            ))
            offset += len(combined)
            page_num += 1
            batch = []
            batch_dates = []

    if batch:
        combined = "\n".join(batch)
        page_date = batch_dates[-1] if batch_dates else authored_at
        pages.append(RawPage(
            doc_id=doc_id, page=page_num,
            char_start=offset, char_end=offset + len(combined),
            text=combined,
            metadata={"source_type": source_type, "authored_at": page_date},
        ))

    return pages, {
        "title": path.stem,
        "page_count": len(pages),
        "authored_at": authored_at,
    }


# ---------------------------------------------------------------------------
# CSV message export loader
# ---------------------------------------------------------------------------

def _load_csv_messages(path: Path, doc_id: str, source_type: str, authored_at: str | None):
    text = path.read_text(encoding="utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)

    messages = []
    for row in rows:
        speaker = row.get("user") or row.get("username") or row.get("author") or "unknown"
        content = row.get("text") or row.get("content") or row.get("message") or ""
        ts = row.get("timestamp") or row.get("ts") or row.get("date") or ""
        messages.append({"user": speaker, "text": content, "ts": ts})

    # Reuse the JSON loader logic
    mock_path = path.with_suffix(".json")
    return _load_json_messages.__wrapped__ if hasattr(_load_json_messages, "__wrapped__") \
        else _json_messages_from_list(messages, doc_id, source_type, authored_at, path.stem)


def _json_messages_from_list(messages: list[dict], doc_id: str, source_type: str,
                              authored_at: str | None, title: str):
    pages: list[RawPage] = []
    batch: list[str] = []
    batch_dates: list[str] = []
    offset = 0
    page_num = 1

    for msg in messages:
        speaker = msg.get("user", "unknown")
        text_part = msg.get("text", "")
        ts = msg.get("ts", "")
        date_str = _normalise_ts(ts)
        batch.append(f"[{speaker}] {text_part}")
        if date_str:
            batch_dates.append(date_str)
        if len(batch) >= 20:
            combined = "\n".join(batch)
            page_date = batch_dates[-1] if batch_dates else authored_at
            pages.append(RawPage(
                doc_id=doc_id, page=page_num,
                char_start=offset, char_end=offset + len(combined),
                text=combined,
                metadata={"source_type": source_type, "authored_at": page_date},
            ))
            offset += len(combined)
            page_num += 1
            batch = []
            batch_dates = []

    if batch:
        combined = "\n".join(batch)
        pages.append(RawPage(
            doc_id=doc_id, page=page_num,
            char_start=offset, char_end=offset + len(combined),
            text=combined,
            metadata={"source_type": source_type, "authored_at": authored_at},
        ))

    return pages, {"title": title, "page_count": len(pages), "authored_at": authored_at}


# ---------------------------------------------------------------------------
# Source type inference from folder path
# ---------------------------------------------------------------------------

FOLDER_TO_SOURCE_TYPE = {
    "2": "policy",           # 2. Company policies
    "3": "assessment",       # 3. Security Assessment
    "4": "contract",         # 4. Contracts_agreements
    "5": "infra",            # 5. Infrastructure_internal
}


def infer_source_type(file_path: str | Path) -> str:
    path = Path(file_path)
    for part in path.parts:
        first_char = part.strip()[:1]
        if first_char in FOLDER_TO_SOURCE_TYPE:
            return FOLDER_TO_SOURCE_TYPE[first_char]
    suffix = path.suffix.lower()
    if suffix in (".json", ".csv"):
        return "message"
    return "policy"


# ---------------------------------------------------------------------------
# Date extraction helpers
# ---------------------------------------------------------------------------

import re as _re
from datetime import datetime as _datetime

_DATE_PATTERNS = [
    _re.compile(r'\b(20\d{2}[-/]\d{2}[-/]\d{2})\b'),
    _re.compile(r'\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+20\d{2})\b', _re.I),
    _re.compile(r'\b(?:Last\s+reviewed|Published|Updated|Effective\s+Date)[:\s]+([A-Z][a-z]+\s+20\d{2})', _re.I),
]


def _detect_date_in_text(text: str) -> str | None:
    for pat in _DATE_PATTERNS:
        m = pat.search(text)
        if m:
            raw = m.group(1)
            # Normalise to ISO date if possible
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d %B %Y", "%d %b %Y", "%B %Y"):
                try:
                    return _datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    continue
            return raw
    return None


def _extract_date_from_metadata(meta: dict) -> str | None:
    for key in ("ModDate", "CreationDate", "created"):
        val = meta.get(key)
        if val:
            # PDF dates look like D:20241103142210+00'00'
            m = _re.search(r'D:(\d{8})', str(val))
            if m:
                try:
                    return _datetime.strptime(m.group(1), "%Y%m%d").strftime("%Y-%m-%d")
                except ValueError:
                    pass
    return None


def _normalise_ts(ts: str) -> str | None:
    if not ts:
        return None
    # Unix timestamp
    try:
        return _datetime.utcfromtimestamp(float(ts)).strftime("%Y-%m-%d")
    except (ValueError, OverflowError, OSError):
        pass
    # ISO string
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return _datetime.strptime(ts[:10], fmt[:10]).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None
