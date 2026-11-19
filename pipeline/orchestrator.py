"""
Ingestion orchestrator — ties loader → chunker → extractor → validator → binder.

Implements the two-pass order from §5.5:
  Pass 1: gate-bearing rubrics first (Q30, Q6, Q15, Q26, Q51, Q65, Vendor Profile)
  Pass 2: remaining rubrics in importance order

Progress is reported via a callback so the FastAPI endpoint can stream it.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

import db
from binder import bind, run_review_pass
from chunker import chunk_pages
from extractor import extract_all, _build_keyword_index
from loader import load_document, infer_source_type
from models import GraphDelta, RubricDef
from validator import validate_and_coerce

# Gate rubric IDs — must be processed in pass 1
GATE_RUBRIC_IDS = {
    "third_party_exists",
    "sensitive_data_access",
    "physical_access_required",
    "web_app_exists",
    "network_access_required",
    "pen_testing",
    # Vendor-profile scope questions would go here too
}

IMPORTANCE_ORDER = {"high": 0, "medium": 1, "low": 2}


def _load_rubrics() -> dict[str, RubricDef]:
    raw = db.load_rubrics()
    result: dict[str, RubricDef] = {}
    for r in raw:
        try:
            result[r["id"]] = RubricDef(**r)
        except Exception:
            pass
    return result


def ingest_document(
    company_id: str,
    file_path: str | Path,
    source_type: str | None = None,
    authored_at: str | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
) -> dict:
    """
    Full ingestion pipeline for one document.
    Returns a summary dict with counts and the rejection log.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {path}")

    if source_type is None:
        source_type = infer_source_type(path)

    def _progress(pct: float, msg: str):
        if progress_cb:
            progress_cb(pct, msg)

    _progress(0.0, "Registering document")

    # Register document in DB
    doc_id = db.register_document(
        company_id=company_id,
        filename=path.name,
        source_type=source_type,
        doc_class=source_type,
        authored_at=authored_at,
        page_count=0,
        raw_path=str(path),
    )

    _progress(0.05, "Loading pages")

    # Load
    pages, doc_meta = load_document(str(path), doc_id, source_type, authored_at)
    if not authored_at:
        authored_at = doc_meta.get("authored_at")

    _progress(0.15, "Chunking")

    # Chunk
    chunks = chunk_pages(
        pages=pages,
        doc_id=doc_id,
        source_type=source_type,
        doc_title=doc_meta.get("title", path.stem),
        authored_at=authored_at,
    )

    _progress(0.25, f"Chunked into {len(chunks)} chunks")

    # Load rubrics
    rubric_map = _load_rubrics()
    all_rubrics = list(rubric_map.values())

    # Two-pass rubric order per §5.5
    gate_rubrics = [r for r in all_rubrics if r.id in GATE_RUBRIC_IDS and not r.malformed]
    rest_rubrics = sorted(
        [r for r in all_rubrics if r.id not in GATE_RUBRIC_IDS and not r.malformed],
        key=lambda r: IMPORTANCE_ORDER.get(r.importance.value, 99),
    )
    ordered_rubrics = gate_rubrics + rest_rubrics

    rejection_log: list[dict] = []
    total_facts = 0
    bound_facts = 0
    delta = GraphDelta()

    # Pass 1 + 2 — extract against gate rubrics first, then the rest
    for pass_num, rubric_subset in enumerate([gate_rubrics, rest_rubrics], start=1):
        if not rubric_subset:
            continue

        _progress(0.25 + (pass_num - 1) * 0.30, f"Pass {pass_num}: extracting {len(rubric_subset)} rubrics")

        candidates = extract_all(chunks, rubric_subset, rejection_log)
        total_facts += len(candidates)

        validated = validate_and_coerce(candidates, rubric_map, rejection_log)

        for vf in validated:
            entry_id = bind(
                company_id=company_id,
                validated=vf,
                rubric_map=rubric_map,
                delta=delta,
                rejection_log=rejection_log,
            )
            if entry_id:
                bound_facts += 1

        # After pass 1 (gates), run a review pass so dependents reflect the gate results
        if pass_num == 1:
            gate_delta = run_review_pass(company_id, rubric_map)
            delta.deltas.extend(gate_delta.deltas)

    _progress(0.90, "Final review pass")
    final_delta = run_review_pass(company_id, rubric_map)
    delta.deltas.extend(final_delta.deltas)

    # Deduplicate delta entries (keep last state per rubric)
    seen = {}
    for d in delta.deltas:
        seen[d.rubric_id] = d
    delta.deltas = list(seen.values())

    _progress(1.0, "Done")

    rejection_rate = (len(rejection_log) / total_facts) if total_facts > 0 else 0.0

    return {
        "doc_id": doc_id,
        "chunks_processed": len(chunks),
        "candidates_extracted": total_facts,
        "facts_bound": bound_facts,
        "rejections": len(rejection_log),
        "fabrication_rate": round(rejection_rate, 4),
        "rejection_log": rejection_log,
        "graph_delta": [d.model_dump() for d in delta.deltas],
    }


def ingest_corpus(
    company_id: str,
    corpus_dir: str | Path,
    progress_cb: Callable[[str, float, str], None] | None = None,
) -> dict:
    """
    Ingest an entire directory of documents.
    Reports progress per file.
    """
    corpus_path = Path(corpus_dir)
    supported = {".pdf", ".docx", ".xlsx", ".txt", ".md", ".json", ".csv"}
    files = [f for f in corpus_path.rglob("*") if f.suffix.lower() in supported]

    results = []
    for i, file in enumerate(files):
        def _file_progress(pct: float, msg: str, _f=file, _i=i, _total=len(files)):
            overall = (_i + pct) / _total
            if progress_cb:
                progress_cb(_f.name, overall, msg)

        try:
            source_type = infer_source_type(file)
            result = ingest_document(company_id, file, source_type, progress_cb=_file_progress)
            results.append({"file": str(file), "status": "ok", **result})
        except Exception as exc:
            results.append({"file": str(file), "status": "error", "error": str(exc)})

    total_bound = sum(r.get("facts_bound", 0) for r in results)
    total_rejected = sum(r.get("rejections", 0) for r in results)
    total_candidates = sum(r.get("candidates_extracted", 0) for r in results)

    return {
        "files_processed": len(files),
        "total_candidates": total_candidates,
        "total_bound": total_bound,
        "total_rejected": total_rejected,
        "fabrication_rate": round(total_rejected / total_candidates, 4) if total_candidates else 0.0,
        "file_results": results,
    }
