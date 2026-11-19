"""
Binder â€” takes validated facts and writes them to the ledger.

The binder is the ONLY place that writes entries. It enforces:
  - Conflict detection when a new value disagrees with an existing one
  - Gate resolution: when a gate slot is written, dependent nodes are updated
  - Confidence computation per Â§3.6
  - Review pass trigger: node_state is recomputed after each write batch

Â§4.1 rule 3: An LLM may never write directly to the ledger. This module
takes already-validated Python values and writes them â€” no LLM calls here.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

import db
from models import (
    CandidateFact, GraphDelta, NodeDelta, NodeState, RubricDef, SlotDef,
    SlotType, SOURCE_AUTHORITY, SourceType, SourceKind,
)
from validator import ValidatedFact


# ---------------------------------------------------------------------------
# Confidence formula (Â§3.6)
# ---------------------------------------------------------------------------

def compute_slot_confidence(
    entries: list[dict],
    new_entry_source_type: str,
    new_entry_kind: str,
    has_open_conflict: bool,
) -> float:
    """
    base        = max authority across all entries for this slot
    corroborate = min(0.15, 0.05 * (independent_agreeing_sources - 1))
    recency     = -0.10 if newest entry older than 18 months
    userconf    = +0.10 if any entry kind == user
    conflict    = -0.40 if open conflict
    """
    if not entries:
        return 0.05

    base = 0.0
    for e in entries:
        st = e.get("source_type", "policy")
        try:
            intent, practice = SOURCE_AUTHORITY[SourceType(st)]
        except (ValueError, KeyError):
            intent, practice = 0.5, 0.5
        base = max(base, max(intent, practice))

    # New entry also contributes
    try:
        intent, practice = SOURCE_AUTHORITY[SourceType(new_entry_source_type)]
        base = max(base, max(intent, practice))
    except (ValueError, KeyError):
        pass

    independent_sources = len({e.get("source_id") for e in entries if e.get("source_id")})
    corroborate = min(0.15, 0.05 * max(0, independent_sources - 1))

    # Recency check
    recency = 0.0
    newest_ts: datetime | None = None
    for e in entries:
        ts_str = e.get("source_authored_at") or e.get("created_at")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if newest_ts is None or ts > newest_ts:
                    newest_ts = ts
            except ValueError:
                pass
    if newest_ts:
        months_old = (datetime.now(timezone.utc) - newest_ts).days / 30
        if months_old > 18:
            recency = -0.10

    userconf = 0.10 if any(e.get("source_kind") == "user" for e in entries) else 0.0
    if new_entry_kind == "user":
        userconf = 0.10

    conflict = -0.40 if has_open_conflict else 0.0

    return max(0.05, min(0.99, base + corroborate + recency + userconf + conflict))


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

def _values_conflict(existing_value: Any, new_value: Any, slot: SlotDef) -> bool:
    """Return True if the two values are incompatible for this slot type."""
    t = slot.type
    if t == SlotType.bool:
        return bool(existing_value) != bool(new_value)
    elif t == SlotType.enum:
        return str(existing_value).lower() != str(new_value).lower()
    elif t in (SlotType.duration, SlotType.date):
        return str(existing_value) != str(new_value)
    elif t == SlotType.text:
        # Only conflict if semantically incompatible (heuristic: very low similarity)
        sim = SequenceMatcher(None, str(existing_value), str(new_value)).ratio()
        return sim < 0.3
    elif t == SlotType.list:
        # Lists conflict only if the slot is exhaustive and they differ
        if not slot.exhaustive:
            return False
        s1 = set(str(v) for v in (existing_value or []))
        s2 = set(str(v) for v in (new_value or []))
        return bool(s1.symmetric_difference(s2))
    return False


def _classify_conflict_kind(
    existing_entry: dict, new_source_type: str,
    existing_source_type: str, existing_authored_at: str | None, new_authored_at: str | None,
) -> str:
    """Classify the conflict kind per Â§3.4."""
    # User correction always takes precedence
    if new_source_type == "user" or existing_entry.get("source_kind") == "user":
        return "user_vs_document"

    # Policy vs infra/message â†’ policy_vs_practice
    if set([existing_source_type, new_source_type]) & {"policy"} and \
       set([existing_source_type, new_source_type]) & {"infra", "message"}:
        return "policy_vs_practice"

    # Date comparison for stale_vs_current
    if existing_authored_at and new_authored_at:
        try:
            dt_old = datetime.fromisoformat(existing_authored_at[:10])
            dt_new = datetime.fromisoformat(new_authored_at[:10])
            if abs((dt_new - dt_old).days) > 180:
                return "stale_vs_current"
        except ValueError:
            pass

    return "source_disagreement"


def _build_conflict_summary(
    rubric: RubricDef, slot: str, existing_entry: dict, new_value: Any,
    new_source_type: str, new_authored_at: str | None,
) -> tuple[str, str]:
    """Return (summary, resolution_question)."""
    existing_value = existing_entry.get("value")
    ex_doc = existing_entry.get("source_id", "document")
    ex_date = existing_entry.get("source_authored_at", "unknown date")[:10] if existing_entry.get("source_authored_at") else "unknown date"
    new_date = new_authored_at[:10] if new_authored_at else "unknown date"
    new_src = new_source_type

    summary = (
        f"For rubric '{rubric.id}', slot '{slot}': "
        f"source '{ex_doc}' ({ex_date}) states '{existing_value}', "
        f"but a {new_src} source ({new_date}) states '{new_value}'."
    )
    resolution_question = (
        f"There is a discrepancy for {rubric.claim}: "
        f"one source ({ex_date}) says '{existing_value}' while "
        f"a {new_src} source ({new_date}) says '{new_value}'. "
        f"Which is currently accurate?"
    )
    return summary, resolution_question


# ---------------------------------------------------------------------------
# Review pass (Â§6.3) â€” deterministic, LLM-free
# ---------------------------------------------------------------------------

def run_review_pass(company_id: str, rubric_map: dict[str, RubricDef]) -> GraphDelta:
    """
    Recompute node_state for every rubric for the given company.
    Returns GraphDelta with every node that changed state.
    """
    delta = GraphDelta()

    for rubric in rubric_map.values():
        old_ns = db.get_node_state(company_id, rubric.id)
        old_state = NodeState(old_ns["state"]) if old_ns else NodeState.unknown

        new_state, filled, empty_req, confidence, attempted = _compute_node_state(
            company_id, rubric, rubric_map,
        )

        provenance_count = len(db.get_active_entries(company_id, rubric.id))
        db.upsert_node_state(
            company_id=company_id,
            rubric_id=rubric.id,
            state=new_state.value,
            filled_slots=filled,
            empty_required=empty_req,
            confidence=confidence,
            provenance_count=provenance_count,
            attempted_and_unknown=attempted,
        )

        if old_state != new_state:
            delta.add(
                rubric_id=rubric.id,
                old=old_state,
                new=new_state,
                filled=filled,
                confidence=confidence,
            )

    return delta


def _compute_node_state(
    company_id: str, rubric: RubricDef, rubric_map: dict[str, RubricDef],
) -> tuple[NodeState, list[str], list[str], float, bool]:
    """
    Returns (state, filled_slots, empty_required_slots, confidence, attempted_unknown).
    """
    # Malformed nodes stay not_applicable
    if rubric.malformed:
        return NodeState.not_applicable, [], [], 0.0, False

    # Gate resolution
    if rubric.depends_on:
        gate_rubric_id = rubric.depends_on.rubric_id
        gate_slot = rubric.depends_on.slot
        gate_expected = rubric.depends_on.equals

        gate_entry = db.get_active_slot_value(company_id, gate_rubric_id, gate_slot)
        if gate_entry is None:
            return NodeState.pending_gate, [], [], 0.0, False
        gate_value = gate_entry.get("value")
        if gate_value != gate_expected:
            return NodeState.not_applicable, [], [], 0.0, False

    entries = db.get_active_entries(company_id, rubric.id)
    filled_map = {e["slot"]: e for e in entries}
    filled_slots = list(filled_map.keys())

    required_slots = [s.name for s in rubric.slots if s.required]
    empty_required = [s for s in required_slots if s not in filled_map]

    # Check for open conflicts
    open_conflicts = db.get_conflicts_for_node(company_id, rubric.id)
    has_conflict = len(open_conflicts) > 0

    if has_conflict:
        state = NodeState.conflicted
    elif empty_required:
        state = NodeState.vague if filled_slots else NodeState.unknown
    elif any(e.get("source_kind") == "user" for e in entries):
        state = NodeState.user_confirmed
    else:
        state = NodeState.verified

    # attempted_unknown
    old_ns = db.get_node_state(company_id, rubric.id)
    attempted = old_ns.get("attempted_and_unknown", False) if old_ns else False
    if state in (NodeState.unknown, NodeState.vague) and attempted:
        state = NodeState.attempted_unknown

    # Confidence = min over required slots (Â§3.6)
    slot_confidences: list[float] = []
    for slot_name in required_slots:
        slot_entries = [e for e in entries if e["slot"] == slot_name]
        conf = compute_slot_confidence(
            slot_entries, "policy", "document", has_conflict
        )
        slot_confidences.append(conf)
    confidence = min(slot_confidences) if slot_confidences else 0.0

    return state, filled_slots, empty_required, confidence, attempted


# ---------------------------------------------------------------------------
# Main bind function â€” called by the orchestrator per validated fact
# ---------------------------------------------------------------------------

def bind(
    company_id: str,
    validated: ValidatedFact,
    rubric_map: dict[str, RubricDef],
    delta: GraphDelta,
    rejection_log: list[dict],
) -> str | None:
    """
    Write one validated fact to the ledger. Returns the new entry_id or None.

    Actions:
      - empty slot          â†’ write entry
      - agrees with current â†’ write corroborating entry
      - disagrees           â†’ write entry + create conflict
      - gate slot           â†’ write entry + re-evaluate dependents
    """
    cf = validated.candidate
    chunk = cf.chunk
    slot_name = cf.slot
    value = validated.coerced_value

    existing = db.get_active_slot_value(company_id, cf.rubric_id, slot_name)

    source_type = chunk.source_type
    authored_at = chunk.authored_at

    # Compute confidence
    existing_entries = db.get_active_entries(company_id, cf.rubric_id)
    slot_entries = [e for e in existing_entries if e["slot"] == slot_name]
    has_conflict = len(db.get_conflicts_for_node(company_id, cf.rubric_id)) > 0
    confidence = compute_slot_confidence(slot_entries, source_type, "document", has_conflict)

    # Write the entry
    entry_id = db.write_entry(
        company_id=company_id,
        rubric_id=cf.rubric_id,
        slot=slot_name,
        value=value,
        confidence=confidence,
        source_kind="document",
        source_id=chunk.doc_id,
        source_type=source_type,
        span=cf.span,
        locator={"page": chunk.page, "char_start": chunk.char_start, "char_end": chunk.char_end},
        authored_at=authored_at,
    )

    # Conflict detection
    if existing:
        existing_value = existing.get("value")
        if _values_conflict(existing_value, value, validated.slot_def):
            kind = _classify_conflict_kind(
                existing, source_type,
                existing.get("source_type", "policy"),
                existing.get("source_authored_at"),
                authored_at,
            )
            summary, question = _build_conflict_summary(
                validated.rubric_def, slot_name, existing, value, source_type, authored_at
            )
            db.create_conflict(
                company_id=company_id,
                rubric_id=cf.rubric_id,
                slot=slot_name,
                kind=kind,
                entry_a=existing["entry_id"],
                entry_b=entry_id,
                summary=summary,
                resolution_question=question,
            )

    # Gate resolution: if this slot is a gate, re-evaluate dependent nodes
    _resolve_gates_if_needed(company_id, cf.rubric_id, slot_name, value, rubric_map, delta)

    return entry_id


def _resolve_gates_if_needed(
    company_id: str, rubric_id: str, slot_name: str, value: Any,
    rubric_map: dict[str, RubricDef], delta: GraphDelta,
) -> None:
    """
    When a gate slot changes, flip all dependents to pending_gate / not_applicable
    or restore them, depending on the new gate value.
    """
    for rubric in rubric_map.values():
        dep = rubric.depends_on
        if dep and dep.rubric_id == rubric_id and dep.slot == slot_name:
            old_ns = db.get_node_state(company_id, rubric.id)
            old_state = NodeState(old_ns["state"]) if old_ns else NodeState.unknown
            new_state, filled, empty_req, conf, attempted = _compute_node_state(
                company_id, rubric, rubric_map,
            )
            if old_state != new_state:
                db.upsert_node_state(
                    company_id=company_id,
                    rubric_id=rubric.id,
                    state=new_state.value,
                    filled_slots=filled,
                    empty_required=empty_req,
                    confidence=conf,
                    provenance_count=len(db.get_active_entries(company_id, rubric.id)),
                    attempted_and_unknown=attempted,
                )
                delta.add(rubric.id, old_state, new_state, filled, conf)


# ---------------------------------------------------------------------------
# User correction (Â§6.5)
# ---------------------------------------------------------------------------

def apply_correction(
    company_id: str,
    rubric_id: str,
    slot: str,
    new_value: Any,
    span: str,
    speaker: str | None,
    rubric_map: dict[str, RubricDef],
) -> tuple[str, GraphDelta]:
    """
    Apply a user correction:
    1. Write new entry with source_kind=user
    2. Supersede the previous entry
    3. Close open conflicts on this slot
    4. Re-evaluate gate dependents
    5. Run review pass
    Returns (new_entry_id, graph_delta).
    """
    delta = GraphDelta()

    # Supersede existing
    existing = db.get_active_slot_value(company_id, rubric_id, slot)

    # Write new user entry
    entry_id = db.write_entry(
        company_id=company_id,
        rubric_id=rubric_id,
        slot=slot,
        value=new_value,
        confidence=0.95,
        source_kind="user",
        source_id=None,
        source_type="user",
        span=span,
        locator=None,
        authored_at=datetime.utcnow().isoformat(),
        speaker=speaker,
    )

    if existing:
        db.supersede_entry(existing["entry_id"], entry_id, "user_correction")

    # Resolve open conflicts on this slot
    for conflict in db.get_conflicts_for_node(company_id, rubric_id):
        if conflict["slot"] == slot:
            db.resolve_conflict(conflict["conflict_id"], entry_id)

    # Gate re-evaluation
    _resolve_gates_if_needed(company_id, rubric_id, slot, new_value, rubric_map, delta)

    # Full review pass
    full_delta = run_review_pass(company_id, rubric_map)
    delta.deltas.extend(full_delta.deltas)

    return entry_id, delta

