"""
Span validator + type coercer.

The spec's primary defence against fabrication:
  "if span not in chunk.text: reject and log"

Also coerces value to the slot's declared type and validates enum membership.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Any

from models import CandidateFact, RubricDef, SlotDef, SlotType, SOURCE_AUTHORITY, SourceType

# Fuzzy match threshold for enum coercion (0–1)
ENUM_MATCH_THRESHOLD = 0.75
# Fabrication rejection log key
REJECTION_KEY = "span_validation"


class ValidatedFact:
    """A CandidateFact that passed span validation and type coercion."""
    def __init__(
        self,
        candidate: CandidateFact,
        coerced_value: Any,
        slot_def: SlotDef,
        rubric_def: RubricDef,
        confidence: float,
    ):
        self.candidate = candidate
        self.coerced_value = coerced_value
        self.slot_def = slot_def
        self.rubric_def = rubric_def
        self.confidence = confidence


def validate_and_coerce(
    candidates: list[CandidateFact],
    rubric_map: dict[str, RubricDef],
    rejection_log: list[dict],
) -> list[ValidatedFact]:
    """
    Run span validation + type coercion on all candidates.
    Returns only the ones that pass. Rejected entries go into rejection_log.
    """
    results: list[ValidatedFact] = []

    for cf in candidates:
        rubric = rubric_map.get(cf.rubric_id)
        if not rubric:
            rejection_log.append({"reason": "unknown_rubric", "rubric_id": cf.rubric_id, "span": cf.span})
            continue

        slot_def = next((s for s in rubric.slots if s.name == cf.slot), None)
        if not slot_def:
            rejection_log.append({"reason": "unknown_slot", "rubric_id": cf.rubric_id, "slot": cf.slot})
            continue

        # ----------------------------------------------------------------
        # THE GOLDEN RULE: span must be a verbatim substring of chunk text
        # ----------------------------------------------------------------
        if not _span_exists_in_chunk(cf.span, cf.chunk.text):
            rejection_log.append({
                "reason": "span_not_in_chunk",
                "rubric_id": cf.rubric_id,
                "slot": cf.slot,
                "span": cf.span[:100],
                "chunk_id": cf.chunk.chunk_id,
            })
            continue

        # Type coercion
        try:
            coerced = _coerce(cf.value, slot_def, rejection_log, cf)
        except ValueError as exc:
            rejection_log.append({
                "reason": "type_coercion_failed",
                "rubric_id": cf.rubric_id,
                "slot": cf.slot,
                "value": str(cf.value)[:100],
                "error": str(exc),
            })
            continue

        if coerced is None:
            # coercion returned None → soft rejection (e.g. enum no match)
            continue

        confidence = _compute_confidence(cf)
        results.append(ValidatedFact(
            candidate=cf,
            coerced_value=coerced,
            slot_def=slot_def,
            rubric_def=rubric,
            confidence=confidence,
        ))

    return results


# ---------------------------------------------------------------------------
# Span check
# ---------------------------------------------------------------------------

def _span_exists_in_chunk(span: str, chunk_text: str) -> bool:
    """
    Verbatim substring check — the spec's primary fabrication guard.
    Tolerates minor whitespace normalisation (collapsed spaces, stripped edges).
    """
    if not span:
        return False
    span_norm = " ".join(span.split())
    text_norm = " ".join(chunk_text.split())
    return span_norm in text_norm


# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------

def _coerce(value: Any, slot: SlotDef, log: list[dict], cf: CandidateFact) -> Any:
    t = slot.type
    if t == SlotType.bool:
        return _to_bool(value)
    elif t == SlotType.enum:
        return _to_enum(value, slot.enum or [], log, cf)
    elif t == SlotType.text:
        return str(value).strip() if value is not None else None
    elif t == SlotType.list:
        if isinstance(value, list):
            return [str(v) for v in value]
        return [str(value)]
    elif t == SlotType.duration:
        return _to_duration(value)
    elif t == SlotType.date:
        return _to_date(value)
    elif t == SlotType.attachment:
        # Attachment value is a document id — pass through as-is
        return str(value) if value else None
    return value


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "yes", "1", "y"):
            return True
        if v in ("false", "no", "0", "n"):
            return False
    raise ValueError(f"Cannot coerce {value!r} to bool")


def _to_enum(value: Any, legal: list[str], log: list[dict], cf: CandidateFact) -> str | None:
    if not legal:
        return str(value)
    v = str(value).strip()
    # Exact match (case-insensitive)
    for candidate in legal:
        if v.lower() == candidate.lower():
            return candidate
    # Fuzzy match
    best_score = 0.0
    best_match = None
    for candidate in legal:
        score = SequenceMatcher(None, v.lower(), candidate.lower()).ratio()
        if score > best_score:
            best_score = score
            best_match = candidate
    if best_score >= ENUM_MATCH_THRESHOLD:
        return best_match
    log.append({
        "reason": "enum_no_match",
        "rubric_id": cf.rubric_id if cf else None,
        "slot": cf.slot if cf else None,
        "value": v,
        "legal": legal,
        "best_score": round(best_score, 2),
    })
    return None


# ISO-8601-ish duration patterns
_DURATION_PATTERNS = [
    (re.compile(r'(\d+)\s*hour', re.I), lambda m: f"PT{m.group(1)}H"),
    (re.compile(r'(\d+)\s*day', re.I),  lambda m: f"P{m.group(1)}D"),
    (re.compile(r'(\d+)\s*week', re.I), lambda m: f"P{int(m.group(1))*7}D"),
    (re.compile(r'(\d+)\s*month', re.I),lambda m: f"P{m.group(1)}M"),
    (re.compile(r'(\d+)\s*year', re.I), lambda m: f"P{m.group(1)}Y"),
    (re.compile(r'P\d+[YMDHMS]', re.I), lambda m: m.group(0).upper()),
]


def _to_duration(value: Any) -> str | None:
    s = str(value).strip()
    for pat, fmt in _DURATION_PATTERNS:
        m = pat.search(s)
        if m:
            return fmt(m)
    return s if s else None


def _to_date(value: Any) -> str | None:
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d %B %Y", "%B %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s if s else None


# ---------------------------------------------------------------------------
# Confidence computation (§3.6)
# ---------------------------------------------------------------------------

def _compute_confidence(cf: CandidateFact) -> float:
    source_type = cf.chunk.source_type
    try:
        st = SourceType(source_type)
        intent_auth, practice_auth = SOURCE_AUTHORITY[st]
    except (ValueError, KeyError):
        intent_auth, practice_auth = 0.5, 0.5

    # Use the higher of intent/practice authority as base
    base = max(intent_auth, practice_auth)

    # User sources get a +0.10 bump (applied in binder when kind==user)
    return max(0.05, min(0.99, base))
