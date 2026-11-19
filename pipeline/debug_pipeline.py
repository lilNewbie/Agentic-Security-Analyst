"""Quick diagnostic - run from pipeline/ to find where extraction breaks."""
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(override=True)

import db
from loader import load_document, infer_source_type
from chunker import chunk_pages
from extractor import _build_keyword_index, select_candidate_rubrics, extract_facts

# Pick one policy doc
test_file = Path(__file__).parent.parent / "docs" / "2. Company policies" / "Regodit_information_security_policy_v1.0.docx"
print(f"File exists: {test_file.exists()}")

# Load rubrics
rubric_map = {}
raw = db.load_rubrics()
print(f"Rubrics loaded: {len(raw)}")

from models import RubricDef
for r in raw:
    try:
        rubric_map[r["id"]] = RubricDef(**r)
    except Exception as e:
        print(f"  Rubric parse error {r.get('id')}: {e}")
all_rubrics = list(rubric_map.values())
print(f"Rubrics parsed: {len(all_rubrics)}")

# Load document
source_type = infer_source_type(test_file)
print(f"Source type: {source_type}")
pages, meta = load_document(str(test_file), "test-doc-id", source_type, None)
print(f"Pages loaded: {len(pages)}")
if pages:
    print(f"First page text preview: {repr(pages[0].text[:200])}")

# Chunk
chunks = chunk_pages(pages=pages, doc_id="test-doc-id", source_type=source_type,
                     doc_title=meta.get("title", test_file.stem), authored_at=None)
print(f"Chunks created: {len(chunks)}")
if chunks:
    print(f"First chunk text preview: {repr(chunks[0].text[:200])}")

# Keyword matching
keyword_index = _build_keyword_index(all_rubrics)
print(f"Keyword index size: {len(keyword_index)}")
print(f"Sample keywords: {list(keyword_index.keys())[:10]}")

matched = 0
for chunk in chunks:
    rubrics = select_candidate_rubrics(chunk, all_rubrics, keyword_index)
    if rubrics:
        matched += 1

print(f"Chunks with candidate rubrics: {matched}/{len(chunks)}")

# Probe a single substantive chunk - show raw LLM response
import json, os
from anthropic import Anthropic
client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

from extractor import _EXTRACTION_SYSTEM

# Find a chunk with real content (skip tiny ones)
probe_chunk = next((c for c in chunks if len(c.text) > 300), chunks[0])
probe_rubrics = select_candidate_rubrics(probe_chunk, all_rubrics, keyword_index)
print(f"\nProbe chunk ({len(probe_chunk.text)} chars), matched rubrics: {[r.id for r in probe_rubrics]}")
print(f"Chunk text preview: {probe_chunk.text[:400]!r}")

rubric_specs = []
for r in probe_rubrics:
    slots_desc = [{"name": s.name, "type": s.type.value, "required": s.required,
                   **({"enum": s.enum} if s.enum else {})} for s in r.slots]
    rubric_specs.append({"id": r.id, "claim": r.claim, "slots": slots_desc})

user_msg = f"""CHUNK (source_type={probe_chunk.source_type}, doc={probe_chunk.doc_title}, date={probe_chunk.authored_at}):
---
{probe_chunk.text}
---

RUBRICS TO CHECK:
{json.dumps(rubric_specs, indent=2)}

Extract facts from this chunk that directly satisfy one or more slots. Return JSON array."""

resp = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=2000,
    system=_EXTRACTION_SYSTEM,
    messages=[{"role": "user", "content": user_msg}],
)
print(f"\nRaw LLM response:\n{resp.content[0].text}")

# Now test extract_facts (the actual pipeline function) on the same chunk
print("\n--- Testing extract_facts (full pipeline function) ---")
facts = extract_facts(probe_chunk, probe_rubrics)
print(f"Facts returned by extract_facts: {len(facts)}")
for f in facts:
    print(f"  {f.rubric_id}.{f.slot} = {f.value!r}  span={f.span[:60]!r}")
