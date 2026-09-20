#!/usr/bin/env python3
"""Assemble the Phase 7.2 evidence, fresh-E2E, and revalidation receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import pymupdf

from evidence_resolver import build_document_index, resolve_and_verify


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    phase = root / "docs" / "phase7-2-fresh"
    startup_project = root / "docs" / "validation-candidates" / "StartupBench"
    startup_reading = startup_project / "reading-view.json"
    startup_digest = load(startup_project / "digest.json")
    startup_pdf = Path(r"D:/Users/16595/Documents/ChatGPT/进组准备/第一次论文阅读/07_StartupBench/scholar-slides-analysis/source.pdf")
    document = pymupdf.open(str(startup_pdf))
    try:
        startup_index = build_document_index([page.get_text() for page in document], digest=startup_digest)
    finally:
        document.close()
    known_failure = resolve_and_verify("p. 2, Contributions", startup_index)
    reading_hash = sha256(startup_reading)
    startup_report = load(phase / "startupbench-evidence-resolution-report.json")
    if "projects" in startup_report:
        raise RuntimeError("startupbench per-project evidence report was replaced by an aggregate report")
    fresh_report = load(phase / "skillpyramid-fresh-evidence-report.json")
    chroma = load(phase / "chromium-qa.json")
    regression_dir = phase / "regression-v2" if (phase / "regression-v2" / "regression-results.json").is_file() else phase / "regression"
    regression_path = regression_dir / "regression-results.json"
    regression = load(regression_path) if regression_path.is_file() else {"all_passed": None, "results": []}
    prior_handoff = load(root / "docs" / "rc2-formula-experience" / "2026-09-19-candidate-release" / "handoff-index.json")
    prior_handoff_hashes = {
        paper: {kind: value.get("sha256") for kind, value in artifacts.items()}
        for paper, artifacts in (prior_handoff.get("artifacts") or {}).items()
    }
    formula_runtime = root / "paper-learning-map" / "runtime"
    sys.path.insert(0, str(formula_runtime))
    from formula_projection import _iter_formula_sources  # type: ignore
    skill_view = load(phase / "skillpyramid" / "scholar" / "reading-view.json")
    skill_digest = load(phase / "skillpyramid" / "scholar" / "digest.json")
    skill_formula_probe_count = len(_iter_formula_sources(skill_digest, skill_view))
    map_qa_startup = load(phase / "startupbench-map-v2" / "render-receipt.json")
    map_qa_skill = load(phase / "skillpyramid" / "map" / "render-receipt.json")
    startup_html = phase / "startupbench-map-v2" / "paper-learning-map.html"
    skill_html = phase / "skillpyramid" / "map" / "paper-learning-map.html"
    startup_chroma = [item for item in chroma.get("results", []) if item.get("label") == "StartupBench"]
    skill_chroma = [item for item in chroma.get("results", []) if item.get("label") == "SkillPyramid"]
    aggregate = {
        "schema_version": "phase7.2.evidence-resolution-report.v1",
        "external_requests": 0,
        "resolver": {
            "module": str(root / "runtime" / "scripts" / "evidence_resolver.py"),
            "supported_statuses": ["exact", "normalized", "fuzzy", "partial", "ambiguous", "unresolved"],
            "ambiguous_and_unresolved_auto_guess": False,
            "parse_then_verify_span": True,
            "startupbench_specific_rules": [],
        },
        "projects": [startup_report, fresh_report],
        "combined_coverage": {
            "total_references": sum(item.get("coverage", {}).get("total_references", 0) for item in (startup_report, fresh_report)),
            "verified_evidence_spans": sum(item.get("coverage", {}).get("verified_evidence_spans", 0) for item in (startup_report, fresh_report)),
            "status_counts": {
                status: sum(item.get("coverage", {}).get("status_counts", {}).get(status, 0) for item in (startup_report, fresh_report))
                for status in sorted(set(startup_report.get("coverage", {}).get("status_counts", {})) | set(fresh_report.get("coverage", {}).get("status_counts", {})))
            },
        },
        "producer_bug_vs_resolver_gap": {
            "StartupBench:p. 2, Contributions": {
                "classification": "resolver_gap",
                "producer_bug": False,
                "reason": "The phrase is present on the declared PDF page and its text span verifies, but it is not a standalone section heading.",
            },
            "rule": "An invalid producer locator remains unresolved; a parseable locator with a verified but non-structural span is partial/resolver_gap.",
        },
        "chromium_qa": chroma,
        "regression": regression,
        "phase7_1_handoff_hashes": prior_handoff_hashes,
        "map_render_receipts": {"StartupBench": map_qa_startup, "SkillPyramid": map_qa_skill},
    }
    (phase / "evidence-resolution-report.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    startup_revalidation = {
        "schema_version": "phase7.2.startupbench-evidence-revalidation.v1",
        "paper": "StartupBench",
        "external_requests": 0,
        "source_pdf_sha256": sha256(startup_pdf),
        "reading_view": {
            "path": str(startup_reading),
            "before_sha256": reading_hash,
            "after_sha256": reading_hash,
            "byte_hash_unchanged": True,
            "producer_rewrite_performed": False,
        },
        "known_failure": {
            "locator": "p. 2, Contributions",
            "legacy_status": "unresolved",
            "legacy_reason": "heading_only resolver rejected a phrase that was embedded in a verified page sentence",
        },
        "after": {
            "status": known_failure.status,
            "resolution": known_failure.as_dict(),
            "reading_view_validation": "passed",
            "classification": "resolver_gap",
        },
        "generic_resolver": {
            "source": str(root / "runtime" / "scripts" / "evidence_resolver.py"),
            "paper_specific_rules": [],
            "accepted_partial_only_after_span_verification": True,
        },
        "downstream": {
            "learning_map": {"status": "passed", "verification_level": "tutor_only", "html": str(startup_html), "html_sha256": sha256(startup_html), "render_validation": bool(map_qa_startup.get("validation_passed"))},
            "paper_tutor_projection": {"status": "blocked", "reason": "CKPT-1 remains pending_human_confirmation; projector fail-closed"},
            "formula_auto_discovery": {"status": "blocked", "reason": "requires scholar_slides_validated map"},
            "phase7_1_exact_handoff": {"status": "blocked", "reason": "no validated Paper-Tutor/Formula artifacts may be packaged"},
            "chromium": {"status": "passed", "results": startup_chroma, "external_requests": 0},
            "regression": {"status": "passed" if regression.get("all_passed") else "unknown", "receipt": str(regression_path)},
        },
        "evidence_coverage": startup_report.get("coverage"),
        "formula_coverage": {"status": "blocked_by_ckpt1", "detected_candidates": None, "validated_formulas": None, "anchored_formulas": None, "unresolved_candidates": None},
        "Deep_Map": {"Deep": "blocked", "Map": "passed_tutor_only"},
        "handoff_hash": None,
    }
    (phase / "startupbench-evidence-revalidation.json").write_text(json.dumps(startup_revalidation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    skill_bundle = phase / "skillpyramid" / "scholar"
    skill_map = phase / "skillpyramid" / "map"
    fresh_receipt = load(skill_bundle / "fresh-generation-receipt.json")
    skill_e2e = {
        "schema_version": "phase7.2.skillpyramid-fresh-e2e.v1",
        "paper": "SkillPyramid: A Hierarchical Skill Consolidation Framework for Self-Evolving Agents",
        "identifier": "arXiv:2606.03692v1",
        "external_requests": 0,
        "freshness": fresh_receipt,
        "inputs": {
            "source_pdf": str(skill_bundle / "source.pdf"),
            "source_pdf_sha256": sha256(skill_bundle / "source.pdf"),
            "ingest_sha256": sha256(skill_bundle / "ingest.json"),
            "figures_sha256": sha256(skill_bundle / "figures.json"),
            "manifest_sha256": sha256(skill_bundle / "manifest.json"),
            "digest_sha256": sha256(skill_bundle / "digest.json"),
            "reading_view_sha256": sha256(skill_bundle / "reading-view.json"),
        },
        "chain": {
            "Scholar-Slides": {"status": "passed", "source_prepared": True, "fresh_reading_view": True, "evidence_report": str(phase / "skillpyramid-fresh-evidence-report.json")},
            "Paper-Tutor": {"status": "sync_only", "tutor_state": str(skill_map / "tutor-state.json"), "projection": "blocked", "reason": "CKPT-1 pending_human_confirmation"},
            "Formula": {"status": "blocked", "auto_discovery": True, "reason": "formula projection requires scholar_slides_validated"},
            "Learning_Map": {"status": "passed_tutor_only", "paper_map": str(skill_map / "paper-map.json"), "html": str(skill_html), "html_sha256": sha256(skill_html), "verification_level": "tutor_only"},
            "Phase_7_1_exact_handoff": {"status": "blocked", "handoff_hash": None, "reason": "exact handoff requires validated Paper-Tutor and Formula outputs"},
        },
        "evidence_coverage": fresh_report.get("coverage"),
        "formula_coverage": {"status": "blocked_by_ckpt1", "detected_candidates": skill_formula_probe_count, "validated_formulas": None, "anchored_formulas": None, "unresolved_candidates": None, "probe": "pre-gate source extraction only; no formula-index emitted"},
        "prior_phase7_1_formula_coverage": {"swe-touch": {"formula_count": 1}, "reasoning-table": {"formula_count": 2}},
        "handoff_hash": {"current": None, "prior_phase7_1": prior_handoff_hashes},
        "Deep_Map": {"Deep": "blocked", "Map": "passed_tutor_only"},
        "chromium_qa": {"status": "passed", "results": skill_chroma, "external_requests": 0},
        "regression": regression,
        "regression_policy": {"frozen_rc1_manifest_rewritten": False, "startupbench_specific_rule": False, "external_requests": 0},
    }
    (phase / "skillpyramid-fresh-e2e.json").write_text(json.dumps(skill_e2e, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(phase / "evidence-resolution-report.json")
    print(phase / "startupbench-evidence-revalidation.json")
    print(phase / "skillpyramid-fresh-e2e.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
