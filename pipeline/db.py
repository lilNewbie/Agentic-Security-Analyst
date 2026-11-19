"""
Supabase data access layer.
All reads and writes to the ledger go through here â€” no other module touches
the DB directly.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv(override=True)

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_KEY"]
        _client = create_client(url, key)
    return _client


# ---------------------------------------------------------------------------
# Config loaders (read once at startup)
# ---------------------------------------------------------------------------

_CONFIG_DIR = Path(__file__).parent.parent / "config"


def load_rubrics() -> list[dict]:
    path = _CONFIG_DIR / "rubrics.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_themes() -> list[dict]:
    path = _CONFIG_DIR / "themes.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Company operations
# ---------------------------------------------------------------------------

def create_company(name: str, metadata: dict | None = None) -> str:
    """Create a company record and seed the node_state table from rubrics."""
    db = get_client()
    res = db.table("companies").insert({
        "name": name,
        "metadata": metadata or {}
    }).execute()
    company_id = res.data[0]["company_id"]
    _seed_node_state(company_id)
    return company_id


def _seed_node_state(company_id: str) -> None:
    """Create one node_state row per rubric in unknown/not_applicable state."""
    rubrics = load_rubrics()
    rows = []
    for r in rubrics:
        state = "not_applicable" if r.get("malformed") else "unknown"
        rows.append({
            "company_id": company_id,
            "rubric_id": r["id"],
            "state": state,
            "filled_slots": [],
            "empty_required_slots": [s["name"] for s in r.get("slots", []) if s.get("required", True)],
            "confidence": 0.0,
            "provenance_count": 0,
            "attempted_and_unknown": False,
        })
    # Insert in batches of 100
    for i in range(0, len(rows), 100):
        get_client().table("node_state").insert(rows[i:i+100]).execute()


def get_company(company_id: str) -> dict | None:
    res = get_client().table("companies").select("*").eq("company_id", company_id).execute()
    return res.data[0] if res.data else None


# ---------------------------------------------------------------------------
# Document registration
# ---------------------------------------------------------------------------

def register_document(company_id: str, filename: str, source_type: str,
                       doc_class: str, authored_at: str | None,
                       page_count: int, raw_path: str) -> str:
    doc_id = str(uuid.uuid4())
    get_client().table("documents").insert({
        "id": doc_id,
        "company_id": company_id,
        "filename": filename,
        "source_type": source_type,
        "doc_class": doc_class,
        "authored_at": authored_at,
        "uploaded_at": datetime.utcnow().isoformat(),
        "page_count": page_count,
        "raw_path": raw_path,
    }).execute()
    return doc_id


# ---------------------------------------------------------------------------
# Chunk storage
# ---------------------------------------------------------------------------

def store_chunks(chunks: list[dict]) -> None:
    """Store chunk metadata (not the full text â€” that stays in memory)."""
    if not chunks:
        return
    for i in range(0, len(chunks), 100):
        get_client().table("chunks").insert(chunks[i:i+100]).execute()


# ---------------------------------------------------------------------------
# Ledger entry writes (append-only â€” the trigger enforces this in Postgres)
# ---------------------------------------------------------------------------

def write_entry(
    company_id: str,
    rubric_id: str,
    slot: str,
    value: Any,
    confidence: float,
    source_kind: str,
    source_id: str | None,
    source_type: str,
    span: str,
    locator: dict | None,
    authored_at: str | None,
    speaker: str | None = None,
    superseded_by: str | None = None,
    supersede_reason: str | None = None,
) -> str:
    entry_id = str(uuid.uuid4())
    get_client().table("entries").insert({
        "entry_id": entry_id,
        "company_id": company_id,
        "rubric_id": rubric_id,
        "slot": slot,
        "value": value,
        "confidence": confidence,
        "source_kind": source_kind,
        "source_id": source_id,
        "source_type": source_type,
        "source_span": span,
        "source_locator": locator or {},
        "source_authored_at": authored_at,
        "source_speaker": speaker,
        "created_at": datetime.utcnow().isoformat(),
        "superseded_by": superseded_by,
        "supersede_reason": supersede_reason,
    }).execute()
    return entry_id


def supersede_entry(entry_id: str, new_entry_id: str, reason: str) -> None:
    """
    Mark an entry as superseded. Because the table is append-only the trigger
    blocks UPDATE, so we use a workaround: insert the new entry with
    superseded_by=None, then patch via an RPC or admin-bypass path.

    For the hackathon we relax this: the trigger blocks DELETE but UPDATE is
    actually needed here. The migration should drop the update trigger and
    instead enforce append-only via row-level security on the INSERT path only.
    Until then we use the service-role key which bypasses RLS.
    """
    get_client().table("entries").update({
        "superseded_by": new_entry_id,
        "supersede_reason": reason,
    }).eq("entry_id", entry_id).execute()


# ---------------------------------------------------------------------------
# Active slot values: newest non-superseded entry per slot
# ---------------------------------------------------------------------------

def get_active_entries(company_id: str, rubric_id: str) -> list[dict]:
    res = (get_client()
           .table("entries")
           .select("*")
           .eq("company_id", company_id)
           .eq("rubric_id", rubric_id)
           .is_("superseded_by", "null")
           .order("created_at", desc=True)
           .execute())
    return res.data or []


def get_active_slot_value(company_id: str, rubric_id: str, slot: str) -> dict | None:
    res = (get_client()
           .table("entries")
           .select("*")
           .eq("company_id", company_id)
           .eq("rubric_id", rubric_id)
           .eq("slot", slot)
           .is_("superseded_by", "null")
           .order("created_at", desc=True)
           .limit(1)
           .execute())
    return res.data[0] if res.data else None


# ---------------------------------------------------------------------------
# Node state cache
# ---------------------------------------------------------------------------

def get_node_state(company_id: str, rubric_id: str) -> dict | None:
    res = (get_client()
           .table("node_state")
           .select("*")
           .eq("company_id", company_id)
           .eq("rubric_id", rubric_id)
           .execute())
    return res.data[0] if res.data else None


def upsert_node_state(company_id: str, rubric_id: str, state: str,
                      filled_slots: list[str], empty_required: list[str],
                      confidence: float, provenance_count: int,
                      attempted_and_unknown: bool) -> None:
    get_client().table("node_state").upsert({
        "company_id": company_id,
        "rubric_id": rubric_id,
        "state": state,
        "filled_slots": filled_slots,
        "empty_required_slots": empty_required,
        "confidence": confidence,
        "provenance_count": provenance_count,
        "last_touched": datetime.utcnow().isoformat(),
        "attempted_and_unknown": attempted_and_unknown,
    }).execute()


def get_all_node_states(company_id: str) -> list[dict]:
    res = (get_client()
           .table("node_state")
           .select("*")
           .eq("company_id", company_id)
           .execute())
    return res.data or []


# ---------------------------------------------------------------------------
# Conflict operations
# ---------------------------------------------------------------------------

def create_conflict(company_id: str, rubric_id: str, slot: str,
                    kind: str, entry_a: str, entry_b: str,
                    summary: str, resolution_question: str) -> str:
    conflict_id = str(uuid.uuid4())
    get_client().table("conflicts").insert({
        "conflict_id": conflict_id,
        "company_id": company_id,
        "rubric_id": rubric_id,
        "slot": slot,
        "kind": kind,
        "entry_a": entry_a,
        "entry_b": entry_b,
        "summary": summary,
        "resolution_question": resolution_question,
        "status": "open",
    }).execute()
    return conflict_id


def get_open_conflicts(company_id: str) -> list[dict]:
    res = (get_client()
           .table("conflicts")
           .select("*")
           .eq("company_id", company_id)
           .eq("status", "open")
           .execute())
    return res.data or []


def get_conflicts_for_node(company_id: str, rubric_id: str) -> list[dict]:
    res = (get_client()
           .table("conflicts")
           .select("*")
           .eq("company_id", company_id)
           .eq("rubric_id", rubric_id)
           .eq("status", "open")
           .execute())
    return res.data or []


def resolve_conflict(conflict_id: str, winning_entry_id: str, note: str = "") -> None:
    get_client().table("conflicts").update({
        "status": "resolved",
        "resolved_by_entry": winning_entry_id,
    }).eq("conflict_id", conflict_id).execute()


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_stats(company_id: str) -> dict:
    states = get_all_node_states(company_id)
    counts: dict[str, int] = {}
    for ns in states:
        s = ns["state"]
        counts[s] = counts.get(s, 0) + 1
    return {
        "total": len(states),
        "verified": counts.get("verified", 0),
        "user_confirmed": counts.get("user_confirmed", 0),
        "vague": counts.get("vague", 0),
        "conflicted": counts.get("conflicted", 0),
        "unknown": counts.get("unknown", 0),
        "not_applicable": counts.get("not_applicable", 0),
        "pending_gate": counts.get("pending_gate", 0),
        "attempted_unknown": counts.get("attempted_unknown", 0),
    }


# ---------------------------------------------------------------------------
# Queue (Â§4.3)
# ---------------------------------------------------------------------------

IMPORTANCE_WEIGHT = {"high": 10, "medium": 5, "low": 2}


def get_work_queue(company_id: str) -> list[dict]:
    """Return rubrics ordered by priority score (highest first)."""
    rubrics = {r["id"]: r for r in load_rubrics()}
    themes = {t["key"]: t for t in load_themes()}
    states = get_all_node_states(company_id)
    open_conflicts = {c["rubric_id"] for c in get_open_conflicts(company_id)}

    queue = []
    for ns in states:
        rubric_id = ns["rubric_id"]
        state = ns["state"]
        if state in ("not_applicable", "pending_gate", "verified", "user_confirmed"):
            continue
        rubric = rubrics.get(rubric_id)
        if not rubric:
            continue
        theme = rubric.get("theme", "")
        theme_multiplier = themes.get(theme, {}).get("multiplier", 1.0)
        total_required = len([s for s in rubric.get("slots", []) if s.get("required", True)])
        empty_required = len(ns.get("empty_required_slots", []))
        fill_ratio = (empty_required / total_required) if total_required > 0 else 0
        iw = IMPORTANCE_WEIGHT.get(rubric.get("importance", "low"), 2)
        conflict_bonus = 100 if rubric_id in open_conflicts else 0
        attempted_penalty = -50 if ns.get("attempted_and_unknown") else 0
        priority = iw * fill_ratio * theme_multiplier + conflict_bonus + attempted_penalty
        queue.append({
            "rubric_id": rubric_id,
            "state": state,
            "priority": priority,
            "empty_required_slots": ns.get("empty_required_slots", []),
            "claim": rubric.get("claim", ""),
            "theme": theme,
        })

    queue.sort(key=lambda x: x["priority"], reverse=True)
    return queue

