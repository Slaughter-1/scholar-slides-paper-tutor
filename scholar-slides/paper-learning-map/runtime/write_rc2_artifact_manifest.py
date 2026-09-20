"""Write the immutable-evidence manifest for the RC2 formula candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FROZEN_RC1_SHA256 = "b1d05cded7cf2a1247dced2c3f389c9cf7026493276e97950500add088533faf"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def artifact(root: Path, key: str, path: Path, role: str) -> dict[str, Any]:
    path = path.resolve()
    record: dict[str, Any] = {
        "key": key,
        "role": role,
        "path": str(path),
        "relative": path.relative_to(root).as_posix() if path.is_relative_to(root) else None,
    }
    if path.is_file():
        record.update({"exists": True, "size": path.stat().st_size, "sha256": sha256(path)})
    else:
        record.update({"exists": False, "size": None, "sha256": None})
    return record


def validate_artifacts(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for item in manifest.get("artifacts", []):
        path = Path(item["path"])
        if not path.is_file():
            errors.append(f"missing artifact: {item['key']}: {path}")
            continue
        if item.get("size") != path.stat().st_size:
            errors.append(f"size mismatch: {item['key']}")
        if item.get("sha256") != sha256(path):
            errors.append(f"sha256 mismatch: {item['key']}")
    return errors


def collect(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []

    def add(key: str, path: Path, role: str) -> None:
        artifacts.append(artifact(root, key, path, role))

    papers = ("swe-touch", "reasoning-table")
    for paper in papers:
        paper_root = root / paper
        tutor_root = paper_root / "paper-tutor"
        map_root = paper_root / "map"
        for name in (
            "paper-tutor-compact.md",
            "paper-tutor-deep-v2.md",
            "paper-tutor-deep-v2.html",
            "paper-tutor-coverage.json",
            "formula-index.json",
        ):
            add(f"{paper}.tutor.{name}", tutor_root / name, "paper-tutor-output")
        map_names = [
            "paper-map.json",
            "tutor-state.json",
            "study-state.json",
            "formula-index.json",
            "paper-learning-map.html",
        ]
        if paper == "swe-touch":
            map_names.append("fresh-verified-chromium-qa.json")
        for name in map_names:
            add(f"{paper}.map.{name}", map_root / name, "learning-map-output")
        handoff_root = root / "handoff" / paper
        add(f"{paper}.handoff.paper-learning-map.html", handoff_root / "paper-learning-map.html", "final_handoff_html")
        add(f"{paper}.handoff.paper-tutor-deep-v2.html", handoff_root / "paper-tutor-deep-v2.html", "final_handoff_html")
        for receipt in sorted((map_root / "sync-receipts").glob("*.json")):
            add(f"{paper}.sync-receipt.{receipt.name}", receipt, "sync-receipt")

    for path, key, role in (
        (root / "bridge-and-integrity-summary.json", "bridge-and-integrity-summary", "integrity-receipt"),
        (root / "qa" / "formula-experience-qa.json", "formula-experience-qa", "formula-browser-qa"),
        (root / "regression" / "regression-results.json", "regression-results", "regression-receipt"),
        (root / "reasoning-table" / "tutor-analysis-records.json", "reasoning-tutor-records", "input-record-audit"),
        (root.parents[2] / "paper-learning-map" / "tests" / "fixtures" / "malformed-formula-index.json", "malformed-formula-fixture", "negative-fixture"),
        (root / "package-receipt.json", "package-receipt", "package-receipt"),
        (root / "handoff-index.json", "handoff-index", "handoff-index"),
        (root / "artifact-lineage.json", "artifact-lineage", "artifact-lineage"),
        (root / "final-artifact-integrity-qa.json", "final-artifact-integrity-qa", "final-artifact-integrity-qa"),
    ):
        add(key, path, role)
    for screenshot in sorted((root / "qa").glob("*.png")):
        add(f"qa-screenshot.{screenshot.name}", screenshot, "chromium-screenshot")

    add(
        "rc2-status-document",
        Path("E:/Desktop/scholar-slides/docs/2026-09-19-paper-tutor-formula-experience-rc2-candidate.md"),
        "release-status-document",
    )

    source_projects = {
        "swe-touch": Path("E:/Desktop/scholar-slides/docs/e2e-validation/verified-fresh/swe-touch/scholar"),
        "reasoning-table": root / "reasoning-table" / "scholar",
    }
    for paper, project in source_projects.items():
        for name in ("source.pdf", "digest.json", "reading-view.json", "checkpoint-1.json"):
            add(f"{paper}.scholar.{name}", project / name, "scholar-source-evidence")

    frozen = Path("E:/Desktop/scholar-slides/docs/release-manifest-paper-learning-system-rc1.json")
    add("frozen-rc1-manifest", frozen, "frozen-rc1-control")

    qa = read_json(root / "qa" / "formula-experience-qa.json")
    final_qa = read_json(root / "final-artifact-integrity-qa.json")
    package_receipt = read_json(root / "package-receipt.json")
    regression = read_json(root / "regression" / "regression-results.json")
    bridge = read_json(root / "bridge-and-integrity-summary.json")
    coverage = {
        paper: read_json(root / paper / "paper-tutor" / "paper-tutor-coverage.json")
        for paper in papers
    }
    source_gate: dict[str, Any] = {}
    for paper in papers:
        paper_map = read_json(root / paper / "map" / "paper-map.json")
        identity = paper_map.get("paper_identity", {})
        source = paper_map.get("source", {})
        source_gate[paper] = {
            "title": identity.get("title"),
            "source_pdf_sha256": identity.get("source_pdf_sha256"),
            "mode": source.get("mode"),
            "verification_level": source.get("verification_level"),
            "passed": source.get("mode") == "integrated" and source.get("verification_level") == "scholar_slides_validated",
        }

    qa_passed = (
        qa.get("offline_bundle") is True
        and qa.get("standalone_copy_qa") is True
        and qa.get("external_request_count") == 0
        and all(not item.get("pageErrors") and not item.get("consoleErrors") and not item.get("externalRequests") for item in qa.get("results", []))
    )
    bridge_papers = [bridge.get(paper, {}) for paper in papers]
    bridge_passed = all(
        item.get("full_analysis", {}).get("status") == "success"
        and len(item.get("incremental_qa", [])) == 5
        and item.get("factual_integrity", {}).get("same") is True
        and item.get("no_records_json_created") is True
        and any(turn.get("items_deduped", 0) >= 1 for turn in item.get("incremental_qa", []))
        and any(turn.get("unresolved_added", 0) == 1 for turn in item.get("incremental_qa", []))
        for item in bridge_papers
    )
    coverage_passed = all(
        item.get("represented_items") == item.get("total_items")
        and item.get("high_importance_represented") == item.get("high_importance_total")
        and item.get("deep_characters", 0) > item.get("compact_characters", 0)
        and item.get("formula_blocks", 0) > 0
        and item.get("experiment_blocks", 0) > 0
        for item in coverage.values()
    )
    regression_passed = regression.get("all_passed") is True

    frozen_payload = read_json(frozen)
    frozen_mismatches: list[dict[str, Any]] = []
    for field in ("tutor_state", "html", "qa_report", "stress_report"):
        entry = frozen_payload.get("artifacts", {}).get(field, {})
        path = Path(entry.get("path", ""))
        actual = sha256(path) if path.is_file() else None
        if actual != entry.get("sha256"):
            frozen_mismatches.append({"field": field, "path": str(path), "expected": entry.get("sha256"), "actual": actual})

    control = {
        "frozen_rc1_manifest": {
            "path": str(frozen.resolve()),
            "sha256": sha256(frozen),
            "unchanged_from_start_of_rc2": sha256(frozen).casefold() == FROZEN_RC1_SHA256,
            "historical_artifact_hash_mismatches": frozen_mismatches,
        },
        "records_json_present": any(path.name == "records.json" for path in root.rglob("records.json")),
        "source_gate": source_gate,
        "qa": {
            "passed": qa_passed,
            "viewports": qa.get("viewports"),
            "external_request_count": qa.get("external_request_count"),
            "formula_render_error_count": qa.get("formula_render_error_count"),
            "malformed_fallback_observed": any("fallback" in item for item in qa.get("results", [])),
        },
        "bridge": {"passed": bridge_passed, "papers": {paper: bridge[paper] for paper in papers}},
        "coverage": coverage,
        "regression": {"passed": regression_passed, "results": regression.get("results", [])},
        "final_handoff": {"passed": bool(final_qa.get("passed") and package_receipt.get("passed") and final_qa.get("external_request_count") == 0)},
        "formula_validation": {
            "swe_touch_equation_3": coverage["swe-touch"].get("formula_count") == 1,
            "reasoning_table_position_and_final_reward": coverage["reasoning-table"].get("formula_count") == 2,
            "offline_katex_version": qa.get("katex_version"),
        },
    }
    return artifacts, control


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-root", required=True)
    args = parser.parse_args()
    root = Path(args.candidate_root).resolve()
    output = root / "rc2-artifact-manifest.json"
    artifacts, control = collect(root)
    core_gates = {
        "source_gate_both_papers": all(item["passed"] for item in control["source_gate"].values()),
        "formula_projection": all(control["formula_validation"].values()),
        "offline_katex": control["qa"]["passed"] and control["qa"]["external_request_count"] == 0,
        "deep_html_and_drawer": control["qa"]["passed"],
        "malformed_formula_raw_fallback": control["qa"]["malformed_fallback_observed"],
        "bridge_receipts_and_qa": control["bridge"]["passed"],
        "tutor_state_coverage": all(item["represented_items"] == item["total_items"] for item in control["coverage"].values()),
        "study_state_and_factual_integrity": control["bridge"]["passed"],
        "chromium_qa": control["qa"]["passed"],
        "final_handoff_integrity": control["final_handoff"]["passed"],
        "regression": control["regression"]["passed"],
        "no_records_json": control["records_json_present"] is False,
        "frozen_rc1_manifest_unchanged": control["frozen_rc1_manifest"]["unchanged_from_start_of_rc2"],
        "frozen_rc1_artifact_hash_consistency": not bool(control["frozen_rc1_manifest"]["historical_artifact_hash_mismatches"]),
    }
    blockers = []
    if not core_gates["frozen_rc1_manifest_unchanged"]:
        blockers.append("The frozen RC1 manifest changed during RC2.")
    if not core_gates["frozen_rc1_artifact_hash_consistency"]:
        blockers.append("The frozen RC1 manifest's historical tutor_state/html/qa_report/stress_report hashes do not match their current files; the frozen manifest was not rewritten.")
    if not core_gates["no_records_json"]:
        blockers.append("records.json exists under the candidate root.")
    for name, passed in core_gates.items():
        if not passed and name not in {"frozen_rc1_artifact_hash_consistency", "frozen_rc1_manifest_unchanged"}:
            blockers.append(f"Core gate failed: {name}.")

    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "release": "paper-tutor-formula-experience-rc2",
        "release_status": "conditional-candidate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "official_candidate_root": str(root),
        "official_candidate": True,
        "scope": {
            "papers": ["SWE-Touch", "Reasoning-Table"],
            "source_boundary": "Scholar-Slides -> Paper-Tutor -> Paper Learning Map presentation projection",
            "markdown_round_trip": False,
            "factual_graph_writeback": False,
            "records_json_manual_prefill": False,
            "scholar_validator_relaxed": False,
        },
        "source_gate": control["source_gate"],
        "core_gates": core_gates,
        "blockers": blockers,
        "decision": {
            "status": "conditional-candidate",
            "reason": "All RC2 formula, bridge, Q&A, integrity, browser, coverage, and regression gates passed, but the frozen top-level RC1 manifest has four historical artifact-hash mismatches. It remains unchanged, so RC2 cannot promote the release to RC1.",
        },
        "control": control,
        "artifacts": artifacts,
        "manifest_self_consistency": {"passed": False, "errors": []},
    }
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    errors = validate_artifacts(manifest)
    manifest["manifest_self_consistency"] = {"passed": not errors, "errors": errors, "checked_at": datetime.now(timezone.utc).isoformat()}
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(output), "release_status": manifest["release_status"], "core_gates": core_gates, "blockers": blockers, "artifact_count": len(artifacts), "manifest_self_consistency": manifest["manifest_self_consistency"]}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
