"""
Structure-aware text chunker.
Produces ~800-token chunks with ~150-token overlap. Respects document structure:
- Policy docs split on headings, never mid-clause
- Message exports split per thread (pages already grouped by loader)
- Attaches full metadata to every chunk
"""
from __future__ import annotations

import re
import uuid

from loader import RawPage
from models import Chunk

# Token counting — approximate using word count (1 word ≈ 1.3 tokens)
_CHARS_PER_TOKEN = 4  # rough: average English word is ~5 chars, token ~4


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


TARGET_TOKENS = 800
OVERLAP_TOKENS = 150
TARGET_CHARS = TARGET_TOKENS * _CHARS_PER_TOKEN
OVERLAP_CHARS = OVERLAP_TOKENS * _CHARS_PER_TOKEN

# Heading patterns used to split policy documents
_HEADING_RE = re.compile(
    r'(?m)^(?:'
    r'#{1,4} .+|'                       # Markdown headings
    r'[A-Z][A-Z\s]{4,}$|'              # ALL CAPS headings
    r'\d+\.\s+[A-Z].{10,}$|'          # Numbered sections: "3. Access Control"
    r'(?:Section|Clause|Article)\s+\d' # Explicit section markers
    r')',
    re.MULTILINE
)



def chunk_pages(
    pages: list[RawPage],
    doc_id: str,
    source_type: str,
    doc_title: str,
    authored_at: str | None = None,
) -> list[Chunk]:
    """
    Convert raw pages into overlapping chunks.
    Message-type sources get one chunk per page (threads stay intact).
    Document sources get structural splitting within pages then overlap.
    """
    chunks: list[Chunk] = []

    for page in pages:
        page_authored = page.metadata.get("authored_at") or authored_at
        page_author = page.metadata.get("author")

        if source_type == "message":
            # Each page is already one thread — keep it intact
            chunks.append(Chunk(
                doc_id=doc_id,
                chunk_id=str(uuid.uuid4()),
                source_type=source_type,
                doc_title=doc_title,
                authored_at=page_authored,
                author=page_author,
                page=page.page,
                char_start=page.char_start,
                char_end=page.char_end,
                text=page.text,
                metadata=page.metadata,
            ))
        else:
            page_chunks = _split_text(
                text=page.text,
                page_offset=page.char_start,
                doc_id=doc_id,
                source_type=source_type,
                doc_title=doc_title,
                authored_at=page_authored,
                author=page_author,
                page=page.page,
                metadata=page.metadata,
            )
            chunks.extend(page_chunks)

    return chunks


def _split_text(
    text: str,
    page_offset: int,
    doc_id: str,
    source_type: str,
    doc_title: str,
    authored_at: str | None,
    author: str | None,
    page: int | None,
    metadata: dict,
) -> list[Chunk]:
    if not text.strip():
        return []

    # First try to split on structural boundaries (headings, numbered sections)
    segments = _split_on_headings(text)

    chunks: list[Chunk] = []
    carry = ""  # overlap carry-over from the previous chunk

    for seg in segments:
        seg_text = carry + seg if carry else seg
        carry = ""

        # If segment fits in one chunk, emit it
        if _approx_tokens(seg_text) <= TARGET_TOKENS:
            if seg_text.strip():
                start = text.find(seg[:20]) if seg else 0
                chunks.append(_make_chunk(
                    text=seg_text,
                    abs_start=page_offset + max(0, start),
                    doc_id=doc_id, source_type=source_type,
                    doc_title=doc_title, authored_at=authored_at,
                    author=author, page=page, metadata=metadata,
                ))
            # Carry overlap into next segment
            carry = _tail_chars(seg_text, OVERLAP_CHARS)
        else:
            # Segment too big — slide a window through it
            sub_chunks = _slide_window(seg_text, page_offset, doc_id,
                                       source_type, doc_title, authored_at,
                                       author, page, metadata)
            chunks.extend(sub_chunks)
            if sub_chunks:
                carry = _tail_chars(sub_chunks[-1].text, OVERLAP_CHARS)

    return chunks


def _split_on_headings(text: str) -> list[str]:
    """Split text at heading boundaries, returning non-empty segments."""
    parts = _HEADING_RE.split(text)
    # Reattach heading to the section that follows it
    result: list[str] = []
    headings = _HEADING_RE.findall(text)
    for i, part in enumerate(parts):
        heading = headings[i - 1] if 0 < i <= len(headings) else ""
        combined = (heading + "\n" + part).strip() if heading else part.strip()
        if combined:
            result.append(combined)
    return result if result else [text]


def _slide_window(
    text: str, page_offset: int, doc_id: str, source_type: str,
    doc_title: str, authored_at: str | None, author: str | None,
    page: int | None, metadata: dict,
) -> list[Chunk]:
    """Slide a TARGET_CHARS window with OVERLAP_CHARS step through text."""
    chunks: list[Chunk] = []
    pos = 0
    while pos < len(text):
        end = pos + TARGET_CHARS
        # Snap to sentence boundary if possible
        if end < len(text):
            snap = _find_sentence_end(text, end)
            if snap > pos:
                end = snap
        window = text[pos:end]
        if window.strip():
            chunks.append(_make_chunk(
                text=window,
                abs_start=page_offset + pos,
                doc_id=doc_id, source_type=source_type,
                doc_title=doc_title, authored_at=authored_at,
                author=author, page=page, metadata=metadata,
            ))
        step = TARGET_CHARS - OVERLAP_CHARS
        pos += max(1, step)
    return chunks


def _find_sentence_end(text: str, near: int) -> int:
    """Find the nearest sentence-ending position close to `near`."""
    for offset in range(0, min(200, len(text) - near)):
        c = text[near + offset] if near + offset < len(text) else ""
        if c in ".!?\n":
            return near + offset + 1
        c2 = text[near - offset] if near - offset >= 0 else ""
        if c2 in ".!?\n":
            return near - offset + 1
    return near


def _tail_chars(text: str, n: int) -> str:
    return text[-n:] if len(text) > n else text


def _make_chunk(
    text: str, abs_start: int, doc_id: str, source_type: str,
    doc_title: str, authored_at: str | None, author: str | None,
    page: int | None, metadata: dict,
) -> Chunk:
    return Chunk(
        doc_id=doc_id,
        chunk_id=str(uuid.uuid4()),
        source_type=source_type,
        doc_title=doc_title,
        authored_at=authored_at,
        author=author,
        page=page,
        char_start=abs_start,
        char_end=abs_start + len(text),
        text=text,
        metadata=metadata,
    )
