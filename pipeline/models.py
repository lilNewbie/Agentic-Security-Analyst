"""
Shared Pydantic models mirroring the contracts in §3 of the spec.
Used by loader, extractor, validator, binder, and the FastAPI routes.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Config types (loaded from config/rubrics.json + themes.json)
# ---------------------------------------------------------------------------

class SlotType(str, Enum):
    bool = "bool"
    enum = "enum"
    text = "text"
    duration = "duration"
    date = "date"
    list = "list"
    attachment = "attachment"


class AnswerType(str, Enum):
    composite = "composite"
    bool = "bool"
    enum = "enum"
    free_text = "free_text"
    attachment = "attachment"


class Importance(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class SlotDef(BaseModel):
    name: str
    type: SlotType
    required: bool = True
    prompt: str = ""
    aliases: list[str] = Field(default_factory=list)
    enum: list[str] | None = None
    enum_hint: list[str] | None = None
    default: Any = None
    exhaustive: bool = False


class DependsOn(BaseModel):
    rubric_id: str
    slot: str
    equals: Any


class RubricDef(BaseModel):
    id: str
    theme: str
    question_ids: list[int]
    claim: str
    importance: Importance
    answer_type: AnswerType
    depends_on: DependsOn | None = None
    malformed: bool = False
    slots: list[SlotDef] = Field(default_factory=list)
    vagueness_rules: list[str] = Field(default_factory=list)
    sufficiency: str = ""
    render_template: str = ""


class ThemeDef(BaseModel):
    key: str
    display_name: str
    question_range: list[int]
    multiplier: float = 1.0


# ---------------------------------------------------------------------------
# Node state (§3.3) — derived, never stored as source of truth
# ---------------------------------------------------------------------------

class NodeState(str, Enum):
    unknown = "unknown"
    not_applicable = "not_applicable"
    pending_gate = "pending_gate"
    vague = "vague"
    conflicted = "conflicted"
    verified = "verified"
    user_confirmed = "user_confirmed"
    attempted_unknown = "attempted_unknown"


STATE_PRECEDENCE = {
    NodeState.conflicted: 7,
    NodeState.pending_gate: 6,
    NodeState.not_applicable: 5,
    NodeState.vague: 4,
    NodeState.user_confirmed: 3,
    NodeState.verified: 2,
    NodeState.attempted_unknown: 1,
    NodeState.unknown: 0,
}


# ---------------------------------------------------------------------------
# Source authority (§3.5)
# ---------------------------------------------------------------------------

class SourceKind(str, Enum):
    document = "document"
    user = "user"
    inference_gate = "inference_gate"


class SourceType(str, Enum):
    policy = "policy"
    assessment = "assessment"
    contract = "contract"
    infra = "infra"
    message = "message"
    user = "user"


# Authority split: (stated_intent, actual_practice)
SOURCE_AUTHORITY: dict[SourceType, tuple[float, float]] = {
    SourceType.policy:     (1.0,  0.6),
    SourceType.assessment: (0.9,  0.85),
    SourceType.contract:   (0.85, 0.5),
    SourceType.infra:      (0.5,  1.0),
    SourceType.message:    (0.3,  0.8),
    SourceType.user:       (0.95, 0.95),
}


# ---------------------------------------------------------------------------
# Chunk — the unit of text fed to the extractor
# ---------------------------------------------------------------------------

class Chunk(BaseModel):
    doc_id: str
    chunk_id: str
    source_type: SourceType
    doc_title: str
    authored_at: str | None = None
    author: str | None = None
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    text: str
    metadata: dict = {}


# ---------------------------------------------------------------------------
# Candidate fact — output of the extractor, input to the validator/binder
# ---------------------------------------------------------------------------

class CandidateFact(BaseModel):
    rubric_id: str
    slot: str
    value: Any
    span: str               # verbatim substring from chunk.text
    reasoning: str = ""
    chunk: Chunk            # back-reference for the span validator


# ---------------------------------------------------------------------------
# Conflict (§3.4)
# ---------------------------------------------------------------------------

class ConflictKind(str, Enum):
    policy_vs_practice = "policy_vs_practice"
    stale_vs_current = "stale_vs_current"
    source_disagreement = "source_disagreement"
    user_vs_document = "user_vs_document"
    scope_ambiguity = "scope_ambiguity"


class ConflictStatus(str, Enum):
    open = "open"
    resolved = "resolved"
    dismissed = "dismissed"


# ---------------------------------------------------------------------------
# Graph delta — returned by every write operation (§3.7)
# ---------------------------------------------------------------------------

class NodeDelta(BaseModel):
    rubric_id: str
    old_state: NodeState | None
    new_state: NodeState
    slots_filled: list[str] = Field(default_factory=list)
    confidence: float


class GraphDelta(BaseModel):
    deltas: list[NodeDelta] = Field(default_factory=list)

    def add(self, rubric_id: str, old: NodeState | None, new: NodeState,
            filled: list[str], confidence: float) -> None:
        self.deltas.append(NodeDelta(
            rubric_id=rubric_id,
            old_state=old,
            new_state=new,
            slots_filled=filled,
            confidence=confidence,
        ))


# ---------------------------------------------------------------------------
# Ingestion job status
# ---------------------------------------------------------------------------

class IngestionStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class IngestionJob(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str
    doc_id: str
    filename: str
    status: IngestionStatus = IngestionStatus.pending
    progress: float = 0.0
    errors: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
