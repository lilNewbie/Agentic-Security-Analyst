"""
FastAPI application â€” the Stage 2 API server.
Implements the REST contract from spec Â§3.7.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv(override=True)

import db
from binder import apply_correction
from models import IngestionJob, IngestionStatus
from orchestrator import ingest_document, ingest_corpus

app = FastAPI(title="AI Security Analyst API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory job store (replace with DB for production)
# ---------------------------------------------------------------------------

_jobs: dict[str, IngestionJob] = {}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------

class CreateCompanyRequest(BaseModel):
    name: str
    metadata: dict | None = None


@app.post("/api/company")
def create_company(req: CreateCompanyRequest):
    company_id = db.create_company(req.name, req.metadata)
    return {"company_id": company_id}


@app.get("/api/company/{company_id}")
def get_company(company_id: str):
    company = db.get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


# ---------------------------------------------------------------------------
# Documents + ingestion
# ---------------------------------------------------------------------------

@app.post("/api/company/{company_id}/documents")
async def upload_document(
    company_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    source_type: str | None = None,
    authored_at: str | None = None,
):
    company = db.get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Save upload to temp file
    suffix = Path(file.filename or "upload.bin").suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    shutil.copyfileobj(file.file, tmp)
    tmp.close()
    tmp_path = tmp.name

    job_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    job = IngestionJob(
        job_id=job_id,
        company_id=company_id,
        doc_id=doc_id,
        filename=file.filename or "upload",
        status=IngestionStatus.pending,
    )
    _jobs[job_id] = job

    background_tasks.add_task(
        _run_ingestion, job_id, company_id, tmp_path, source_type, authored_at
    )

    return {"ingestion_job_id": job_id}


def _run_ingestion(job_id: str, company_id: str, file_path: str,
                   source_type: str | None, authored_at: str | None):
    job = _jobs[job_id]
    job.status = IngestionStatus.running

    def progress(pct: float, _msg: str):
        job.progress = pct

    try:
        result = ingest_document(
            company_id=company_id,
            file_path=file_path,
            source_type=source_type,
            authored_at=authored_at,
            progress_cb=progress,
        )
        job.status = IngestionStatus.done
        job.progress = 1.0
        # Store result on job for retrieval
        job.__dict__["result"] = result
    except Exception as exc:
        job.status = IngestionStatus.failed
        job.errors.append(str(exc))
    finally:
        try:
            Path(file_path).unlink()
        except OSError:
            pass


class CorpusRequest(BaseModel):
    corpus_path: str


@app.post("/api/company/{company_id}/documents/corpus")
async def ingest_corpus_endpoint(
    company_id: str,
    req: CorpusRequest,
    background_tasks: BackgroundTasks,
):
    company = db.get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    if not Path(req.corpus_path).is_dir():
        raise HTTPException(status_code=400, detail="corpus_path is not a directory")

    job_id = str(uuid.uuid4())
    job = IngestionJob(
        job_id=job_id,
        company_id=company_id,
        doc_id="corpus",
        filename=req.corpus_path,
        status=IngestionStatus.pending,
    )
    _jobs[job_id] = job

    def _run():
        job.status = IngestionStatus.running
        try:
            result = ingest_corpus(company_id=company_id, corpus_dir=req.corpus_path)
            job.status = IngestionStatus.done
            job.progress = 1.0
            job.__dict__["result"] = result
        except Exception as exc:
            job.status = IngestionStatus.failed
            job.errors.append(str(exc))

    background_tasks.add_task(_run)
    return {"ingestion_job_id": job_id}


@app.get("/api/company/{company_id}/ingestion/{job_id}")
def get_ingestion_status(company_id: str, job_id: str):
    job = _jobs.get(job_id)
    if not job or job.company_id != company_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job_id,
        "status": job.status.value,
        "progress": job.progress,
        "errors": job.errors,
        "result": job.__dict__.get("result"),
    }


# ---------------------------------------------------------------------------
# Graph + nodes
# ---------------------------------------------------------------------------

@app.get("/api/company/{company_id}/graph")
def get_graph(company_id: str):
    _assert_company(company_id)
    rubrics = db.load_rubrics()
    themes = db.load_themes()
    node_states = db.get_all_node_states(company_id)
    conflicts = db.get_open_conflicts(company_id)

    ns_map = {ns["rubric_id"]: ns for ns in node_states}

    nodes = []
    for r in rubrics:
        ns = ns_map.get(r["id"], {})
        nodes.append({
            "rubric_id": r["id"],
            "theme": r["theme"],
            "claim": r["claim"],
            "importance": r["importance"],
            "state": ns.get("state", "unknown"),
            "confidence": ns.get("confidence", 0.0),
            "filled_slots": ns.get("filled_slots", []),
            "empty_required_slots": ns.get("empty_required_slots", []),
            "question_ids": r["question_ids"],
            "malformed": r.get("malformed", False),
        })

    return {
        "themes": themes,
        "nodes": nodes,
        "conflicts": conflicts,
    }


@app.get("/api/company/{company_id}/node/{rubric_id}")
def get_node(company_id: str, rubric_id: str):
    _assert_company(company_id)
    rubrics = {r["id"]: r for r in db.load_rubrics()}
    rubric = rubrics.get(rubric_id)
    if not rubric:
        raise HTTPException(status_code=404, detail="Rubric not found")

    ns = db.get_node_state(company_id, rubric_id)
    entries = db.get_active_entries(company_id, rubric_id)
    conflicts = db.get_conflicts_for_node(company_id, rubric_id)

    return {
        "rubric": rubric,
        "node_state": ns,
        "entries": entries,
        "conflicts": conflicts,
    }


@app.get("/api/company/{company_id}/queue")
def get_queue(company_id: str):
    _assert_company(company_id)
    return db.get_work_queue(company_id)


@app.get("/api/company/{company_id}/stats")
def get_stats(company_id: str):
    _assert_company(company_id)
    return db.get_stats(company_id)


# ---------------------------------------------------------------------------
# Questionnaire render (Â§7.2 / Â§7.8)
# ---------------------------------------------------------------------------

@app.get("/api/company/{company_id}/questionnaire")
def get_questionnaire(company_id: str):
    _assert_company(company_id)
    rubrics = db.load_rubrics()
    rubric_map = {r["id"]: r for r in rubrics}
    node_states = {ns["rubric_id"]: ns for ns in db.get_all_node_states(company_id)}

    # Build a map from question_id â†’ list of rubric ids
    q_to_rubrics: dict[int, list[str]] = {}
    for r in rubrics:
        for qid in r.get("question_ids", []):
            q_to_rubrics.setdefault(qid, []).append(r["id"])

    questions = []
    for qid in range(1, 67):
        rubric_ids = q_to_rubrics.get(qid, [])
        if not rubric_ids:
            questions.append({"question_id": qid, "status": "unknown", "response": None})
            continue

        # Merge across rubrics that answer this question
        statuses = []
        entries_for_q: list[dict] = []
        confidence_vals: list[float] = []

        for rid in rubric_ids:
            ns = node_states.get(rid, {})
            statuses.append(ns.get("state", "unknown"))
            entries_for_q.extend(db.get_active_entries(company_id, rid))
            confidence_vals.append(ns.get("confidence", 0.0))

        # Overall status (most pessimistic)
        STATUS_RANK = {
            "conflicted": 7, "pending_gate": 6, "not_applicable": 5,
            "vague": 4, "user_confirmed": 3, "verified": 2,
            "attempted_unknown": 1, "unknown": 0,
        }
        overall_state = max(statuses, key=lambda s: STATUS_RANK.get(s, 0))

        # Build response string from filled slots
        response = _render_response(qid, rubric_ids, rubric_map, company_id, overall_state)

        evidence = [
            {
                "doc": e.get("source_id"),
                "date": (e.get("source_authored_at") or "")[:10],
                "page": json.loads(e.get("source_locator") or "{}").get("page"),
                "span": e.get("source_span"),
            }
            for e in entries_for_q
            if e.get("source_kind") == "document" and e.get("source_span")
        ]

        questions.append({
            "question_id": qid,
            "status": _map_state_to_render_status(overall_state),
            "response": response,
            "confidence": min(confidence_vals) if confidence_vals else 0.0,
            "evidence": evidence,
        })

    return {"questions": questions}


def _map_state_to_render_status(state: str) -> str:
    mapping = {
        "verified": "verified_from_documents",
        "user_confirmed": "confirmed_by_user",
        "not_applicable": "not_applicable",
        "conflicted": "partial",
        "vague": "partial",
        "unknown": "unknown",
        "attempted_unknown": "unknown",
        "pending_gate": "unknown",
    }
    return mapping.get(state, "unknown")


def _render_response(qid: int, rubric_ids: list[str], rubric_map: dict,
                     company_id: str, state: str) -> str | None:
    if state in ("unknown", "pending_gate", "not_applicable"):
        if state == "not_applicable":
            return "Not applicable"
        return None

    parts: list[str] = []
    for rid in rubric_ids:
        entries = db.get_active_entries(company_id, rid)
        if not entries:
            continue
        rubric = rubric_map.get(rid, {})
        template = rubric.get("render_template", "")
        slot_vals = {e["slot"]: e.get("value") for e in entries}
        if template:
            try:
                # Simple template substitution
                rendered = template
                for k, v in slot_vals.items():
                    rendered = rendered.replace(f"{{{k}}}", str(v) if v is not None else "")
                parts.append(rendered)
            except Exception:
                parts.append(str(slot_vals))
        else:
            parts.append(str(slot_vals))

    return " ".join(parts) if parts else None


# ---------------------------------------------------------------------------
# Corrections + conflict resolution
# ---------------------------------------------------------------------------

class CorrectionRequest(BaseModel):
    rubric_id: str
    slot: str
    value: Any
    span: str = ""
    speaker: str | None = None


@app.post("/api/company/{company_id}/correction")
def post_correction(company_id: str, req: CorrectionRequest):
    _assert_company(company_id)
    rubric_map = _load_rubric_map()
    span = req.span or f"User correction: {req.value}"
    entry_id, delta = apply_correction(
        company_id=company_id,
        rubric_id=req.rubric_id,
        slot=req.slot,
        new_value=req.value,
        span=span,
        speaker=req.speaker,
        rubric_map=rubric_map,
    )
    return {"entry_id": entry_id, "graph_delta": [d.model_dump() for d in delta.deltas]}


class ConflictResolutionRequest(BaseModel):
    winning_entry_id: str
    note: str = ""


@app.post("/api/conflict/{conflict_id}/resolve")
def resolve_conflict(conflict_id: str, req: ConflictResolutionRequest):
    db.resolve_conflict(conflict_id, req.winning_entry_id, req.note)
    return {"status": "resolved"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_company(company_id: str):
    if not db.get_company(company_id):
        raise HTTPException(status_code=404, detail="Company not found")


def _load_rubric_map():
    from models import RubricDef
    return {r["id"]: RubricDef(**r) for r in db.load_rubrics()}


