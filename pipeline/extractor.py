"""
LLM-based fact extractor.

For each (chunk, candidate_rubric) pair asks Claude to emit zero or more
CandidateFact objects. Temperature is not used â€” determinism matters.

The Golden Rule is enforced at this layer by requiring the LLM to copy the
span verbatim from the chunk. The span validator does the hard check.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from anthropic import Anthropic, APIStatusError
from dotenv import load_dotenv

from models import CandidateFact, Chunk, RubricDef

load_dotenv(override=True)

_client: Anthropic | None = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic()
    return _client


# ---------------------------------------------------------------------------
# Rubric selection â€” which rubrics are plausibly answerable from a chunk?
# ---------------------------------------------------------------------------

def _build_keyword_index(rubrics: list[RubricDef]) -> dict[str, list[RubricDef]]:
    """Map lowercase keyword â†’ list of rubrics that use it as an alias."""
    index: dict[str, list[RubricDef]] = {}
    for rubric in rubrics:
        for slot in rubric.slots:
            for alias in slot.aliases:
                kw = alias.lower()
                index.setdefault(kw, []).append(rubric)
    return index


def select_candidate_rubrics(
    chunk: Chunk,
    rubrics: list[RubricDef],
    keyword_index: dict[str, list[RubricDef]],
    max_rubrics: int = 10,
) -> list[RubricDef]:
    """
    Return up to max_rubrics rubrics that could plausibly be answered by this chunk.
    Uses keyword matching on aliases + rubric claims.
    """
    text_lower = chunk.text.lower()
    scores: dict[str, float] = {}

    # Keyword hit on aliases
    for kw, matched_rubrics in keyword_index.items():
        if kw in text_lower:
            for r in matched_rubrics:
                scores[r.id] = scores.get(r.id, 0) + 1.0

    # Word overlap with rubric claim
    words = set(text_lower.split())
    for rubric in rubrics:
        claim_words = set(rubric.claim.lower().split())
        overlap = len(words & claim_words)
        if overlap > 2:
            scores[rubric.id] = scores.get(rubric.id, 0) + overlap * 0.5

    id_map = {r.id: r for r in rubrics}
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [id_map[rid] for rid, _ in ranked[:max_rubrics] if rid in id_map]


# ---------------------------------------------------------------------------
# Extraction prompt
# ---------------------------------------------------------------------------

_EXTRACTION_SYSTEM = """You are a security compliance analyst extracting factual claims from document chunks.

For each (chunk, rubric) pair you receive, extract zero or more facts that the chunk DIRECTLY STATES.

Rules:
1. The "span" field MUST be copied CHARACTER-FOR-CHARACTER from the chunk text. Never paraphrase.
2. If the chunk only mentions the topic without stating a fact, emit an empty array.
3. Never infer or extrapolate. "They have SOC 2" does NOT imply "they do annual pen tests".
4. For bool values: emit true/false only if the chunk explicitly states it.
5. For enum values: map to the nearest legal enum value. If none fits, omit this fact.
6. For duration values: use ISO-8601-ish strings (P30D, P24H, P1Y).
7. Temperature is 0 â€” emit nothing you are not certain of.

Output format: JSON array of objects, each with:
  {"rubric_id": "...", "slot": "...", "value": <typed>, "span": "verbatim text", "reasoning": "one sentence"}

Emit [] if no facts are extractable. No other text, no markdown fences."""


def extract_facts(
    chunk: Chunk,
    rubrics: list[RubricDef],
    keyword_index: dict[str, list[RubricDef]] | None = None,
) -> list[CandidateFact]:
    """
    Extract facts from a single chunk against a list of rubrics.
    Returns CandidateFact objects â€” not yet validated.
    """
    if not rubrics:
        return []

    rubric_specs = []
    for r in rubrics:
        slots_desc = []
        for s in r.slots:
            sd = {"name": s.name, "type": s.type.value, "required": s.required}
            if s.enum:
                sd["enum"] = s.enum
            if s.aliases:
                sd["aliases"] = s.aliases[:5]
            slots_desc.append(sd)
        rubric_specs.append({
            "id": r.id,
            "claim": r.claim,
            "slots": slots_desc,
        })

    user_message = f"""CHUNK (source_type={chunk.source_type}, doc={chunk.doc_title}, date={chunk.authored_at}):
---
{chunk.text}
---

RUBRICS TO CHECK:
{json.dumps(rubric_specs, indent=2)}

Extract facts from this chunk that directly satisfy one or more slots. Return JSON array."""

    try:
        response = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            system=_EXTRACTION_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        candidates_raw = json.loads(raw)
    except APIStatusError:
        raise
    except Exception:
        return []

    if not isinstance(candidates_raw, list):
        return []

    results: list[CandidateFact] = []
    for item in candidates_raw:
        try:
            cf = CandidateFact(
                rubric_id=item["rubric_id"],
                slot=item["slot"],
                value=item["value"],
                span=item["span"],
                reasoning=item.get("reasoning", ""),
                chunk=chunk,
            )
            results.append(cf)
        except Exception:
            continue

    return results


# ---------------------------------------------------------------------------
# Batch extraction across all chunks for a document
# ---------------------------------------------------------------------------

def extract_all(
    chunks: list[Chunk],
    rubrics: list[RubricDef],
    rejection_log: list[dict] | None = None,
) -> list[CandidateFact]:
    """
    Run extraction on all chunks. Returns all candidate facts.
    rejection_log is populated by the validator later â€” passed through here
    for unified reporting.
    """
    if not rubrics:
        return []

    keyword_index = _build_keyword_index(rubrics)
    all_facts: list[CandidateFact] = []

    for chunk in chunks:
        candidate_rubrics = select_candidate_rubrics(chunk, rubrics, keyword_index)
        if not candidate_rubrics:
            continue
        facts = extract_facts(chunk, candidate_rubrics, keyword_index)
        all_facts.extend(facts)

    return all_facts

