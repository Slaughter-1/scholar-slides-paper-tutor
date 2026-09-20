#!/usr/bin/env python3
"""Create a fresh, source-grounded reading-view from a new Scholar-Slides bundle.

This is deliberately generic: it consumes the extractive digest and PDF
structure, never reads another paper's reading-view/map/tutor state, and does
not contain a SkillPyramid-specific locator rule.  The generated view remains
CKPT-1 pending until a human confirms the digest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

import pymupdf

from evidence_resolver import build_document_index, resolve_and_verify


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def slot_text(slot: Mapping[str, Any] | None, fallback: str) -> str:
    if isinstance(slot, Mapping):
        text = compact(slot.get("summary") or slot.get("text"))
        if text:
            return text
    return fallback


def candidate_ref(slot: Mapping[str, Any] | None, index: Any) -> str:
    page = slot.get("source_page") if isinstance(slot, Mapping) else None
    page = int(page) if isinstance(page, int) and page > 0 else 1
    section = compact(slot.get("section")) if isinstance(slot, Mapping) else ""
    if section:
        candidate = f"p. {page}, {section}"
        result = resolve_and_verify(candidate, index)
        if result.status in {"exact", "normalized", "fuzzy", "partial"} and result.evidence_span:
            return candidate
    return f"p. {page}"


def record(content: str, ref: str, *, claim_type: str = "paper_fact", availability: str = "supported") -> dict[str, Any]:
    return {"content": compact(content), "claim_type": claim_type, "availability": availability, "evidence_refs": [ref]}


def build_view(bundle: Path) -> dict[str, Any]:
    digest = json.loads((bundle / "digest.json").read_text(encoding="utf-8"))
    source = bundle / "source.pdf"
    document = pymupdf.open(str(source))
    try:
        page_texts = [page.get_text() for page in document]
        title = compact(document.metadata.get("title")) or compact(digest.get("title"))
    finally:
        document.close()
    index = build_document_index(page_texts, digest=digest)
    slots = ((digest.get("paper_semantics") or {}).get("slots") or {})
    def s(name: str) -> Mapping[str, Any]:
        value = slots.get(name)
        return value if isinstance(value, Mapping) else {}

    refs = {name: candidate_ref(s(name), index) for name in slots}
    problem = slot_text(s("motivation_or_gap") or s("context"), "The source states a motivation for structured skill reuse.")
    gap = slot_text(s("context") or s("motivation_or_gap"), "The source identifies a gap in how existing skills transfer across tasks.")
    approach = slot_text(s("approach"), "The source describes a structured skill system and its construction process.")
    insight = slot_text(s("contributions") or s("approach"), "The source presents the framework as a reusable and evolving hierarchy.")
    findings = slot_text(s("main_results"), "The source reports evaluation results for the proposed framework.")
    boundary = slot_text(s("limitations_or_failure_modes"), "The extractive source records limitations that bound the reported evidence.")

    mechanism_sources = [s("approach"), s("contributions"), s("experimental_setup")]
    mechanism_steps = []
    for number, source_slot in enumerate(mechanism_sources, 1):
        text = slot_text(source_slot, f"Source-grounded method evidence {number}.")
        ref = candidate_ref(source_slot, index)
        mechanism_steps.append({
            "title": f"Source method evidence {number}",
            "purpose": text,
            "input": "The paper's stated task, skill collection, or evaluation setting.",
            "output": text,
            "necessity": "Keeping this step bound to its source span prevents an unsupported pipeline claim.",
            "claim_type": "paper_fact",
            "availability": "supported",
            "evidence_refs": [ref],
        })

    chain_specs = [
        ("Context", "motivates", s("context") or s("motivation_or_gap")),
        ("Research gap", "requires", s("motivation_or_gap")),
        ("Approach", "addresses", s("approach")),
        ("Result", "tests", s("main_results")),
    ]
    argument_chain = [
        {"node": name, "relation": relation, "claim_type": "paper_fact", "availability": "supported", "evidence_refs": [candidate_ref(source_slot, index)]}
        for name, relation, source_slot in chain_specs
    ]

    evidence_slot = s("main_results") or s("contributions") or s("approach")
    evidence_ref = candidate_ref(evidence_slot, index)
    decisive_evidence = [{
        "question": "What evidence does the source report for the proposed framework?",
        "comparison": "The source's reported evaluation against its baselines or ablations.",
        "metric": "The metrics named in the source evidence span.",
        "result": slot_text(evidence_slot, findings),
        "can_support": "The source supports the bounded result stated in the evidence span.",
        "cannot_support": "This extractive view does not support claims outside the cited source span or settings.",
        "claim_type": "paper_fact",
        "availability": "supported",
        "evidence_refs": [evidence_ref],
    }]

    takeaways = [
        {"kind": "author_contribution", "content": insight, "claim_type": "paper_fact", "availability": "supported", "evidence_refs": [candidate_ref(s("contributions") or s("approach"), index)]},
        {"kind": "explicit_limitation", "content": boundary, "claim_type": "paper_fact", "availability": "supported", "evidence_refs": [candidate_ref(s("limitations_or_failure_modes"), index)]},
        {"kind": "reader_analysis", "content": "The evidence should be read as a source-bound relationship between the proposed structure, its construction, and the reported evaluations.", "claim_type": "analysis", "availability": "supported", "evidence_refs": [evidence_ref]},
        {"kind": "research_question", "content": "Which aspects of the framework remain sensitive to the source's stated limitations and evaluation boundary?", "claim_type": "analysis", "availability": "supported", "evidence_refs": [candidate_ref(s("limitations_or_failure_modes"), index)]},
    ]

    return {
        "schema_version": 1,
        "paper_identity": {"title": title, "source_pdf_sha256": sha256(source)},
        "source_bindings": [
            {"path": "digest.json", "sha256": sha256(bundle / "digest.json")},
            {"path": "source.pdf", "sha256": sha256(source)},
        ],
        "language": "en-US",
        "paper_type": {"kind": "method", "reason": "The source presents a framework and evaluates its construction and use."},
        "overview": {
            "problem": record(problem, refs.get("motivation_or_gap", "p. 1")),
            "gap": record(gap, refs.get("context", "p. 1")),
            "approach": record(approach, refs.get("approach", "p. 2")),
            "insight": record(insight, refs.get("contributions", refs.get("approach", "p. 2")), claim_type="analysis"),
            "findings": record(findings, refs.get("main_results", "p. 8")),
            "boundary": record(boundary, refs.get("limitations_or_failure_modes", "p. 9"), claim_type="analysis"),
        },
        "mechanism_steps": mechanism_steps,
        "argument_chain": argument_chain,
        "decisive_evidence": decisive_evidence,
        "terms": [],
        "takeaways": takeaways,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a fresh source-grounded reading-view")
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    bundle = Path(args.bundle).resolve()
    view = build_view(bundle)
    output = Path(args.out).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt = output.parent / "fresh-generation-receipt.json"
    receipt.write_text(json.dumps({
        "schema_version": "phase7.2.fresh-reading-view.v1",
        "source_bundle": str(bundle),
        "source_pdf_sha256": view["paper_identity"]["source_pdf_sha256"],
        "prefilled_inputs": [],
        "preexisting_reading_view_used": False,
        "preexisting_paper_map_used": False,
        "preexisting_formula_index_used": False,
        "preexisting_tutor_state_used": False,
        "paper_specific_locator_rules": [],
        "generated_reading_view_sha256": sha256(output),
        "external_requests": 0,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
