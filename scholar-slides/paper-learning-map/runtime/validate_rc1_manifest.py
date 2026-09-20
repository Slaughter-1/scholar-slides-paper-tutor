"""Build and validate the release manifest from actual RC1 artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact(path: Path, root: Path) -> dict[str, str]:
    return {"path": str(path), "relative": path.resolve().relative_to(root.resolve()).as_posix(), "sha256": sha256(path)}


def browser_viewport_passes(result: dict[str, Any]) -> bool:
    """Apply the complete Fresh Chromium assertion set to one viewport."""

    base = result.get("base") or {}
    off = result.get("off") or {}
    key = result.get("key") or {}
    all_collapsed = result.get("all_collapsed") or {}
    expanded = result.get("after_group_expand") or {}
    drawer = result.get("drawer") or {}
    search = result.get("search") or {}
    collapse = result.get("collapse") or {}
    dark = result.get("dark") or {}
    subtitle = str(base.get("subtitle") or "")
    return all(
        (
            not result.get("page_errors"),
            not result.get("console_errors"),
            "integrated" in subtitle,
            "scholar_slides_validated" in subtitle,
            int(base.get("factualNodes") or 0) > 0,
            int(base.get("blackFactNodes") or 0) == 0,
            off.get("value") == "off",
            int(off.get("groups") or 0) == 0,
            int(off.get("items") or 0) == 0,
            key.get("value") == "key",
            int(key.get("groups") or 0) > 0,
            all_collapsed.get("value") == "all",
            int(all_collapsed.get("groups") or 0) > 0,
            int(expanded.get("items") or 0) > 0,
            drawer.get("open") is True,
            drawer.get("closed") is True,
            search.get("drawerOpen") is True,
            search.get("selected") is True,
            int(result.get("fit_finite_nonfinite") or 0) == 0,
            int(result.get("relations_active") or 0) > 0,
            collapse.get("before") != collapse.get("after"),
            collapse.get("expanded") == collapse.get("before"),
            dark.get("enabled") is True,
            int(dark.get("blackFactNodes") or 0) == 0,
        )
    )


def qa_turns_pass(qa: dict[str, Any], project: Path, paper_sha256: str) -> bool:
    """Validate the five required turns plus the duplicate receipt."""

    rows = qa.get("qa") or []
    if not isinstance(rows, list) or len(rows) != 6:
        return False
    by_id = {row.get("id"): row for row in rows if isinstance(row, dict)}
    expected_ids = {"Q1", "Q2", "Q3", "Q4", "Q5", "duplicate"}
    if set(by_id) != expected_ids:
        return False
    receipt_root = (project / "sync-receipts").resolve()
    for row in rows:
        if row.get("status") != "success":
            return False
        try:
            receipt_path = Path(str(row["receipt"])).resolve(strict=True)
            receipt_path.relative_to(receipt_root)
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (KeyError, OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return False
        if (
            receipt.get("event") != "incremental_qa_sync"
            or receipt.get("status") != "success"
            or receipt.get("paper_sha256") != paper_sha256
        ):
            return False
    for turn_id in ("Q1", "Q2", "Q3", "Q4"):
        row = by_id[turn_id]
        transition = row.get("study_state_transition") or {}
        if not all(
            (
                bool(row.get("resolved_node")),
                int(row.get("items_added") or 0) == 1,
                int(row.get("unresolved_added") or 0) == 0,
                row.get("study_before") == "unseen",
                row.get("study_after") == "learning",
                transition.get("node_id") == row.get("resolved_node"),
                transition.get("before") == "unseen",
                transition.get("after") == "learning",
            )
        ):
            return False
    q5 = by_id["Q5"]
    if not all(
        (
            q5.get("resolved_node") is None,
            int(q5.get("items_added") or 0) == 0,
            int(q5.get("unresolved_added") or 0) == 1,
            q5.get("study_before") is None,
            q5.get("study_after") is None,
            q5.get("study_state_transition") is None,
        )
    ):
        return False
    duplicate = by_id["duplicate"]
    return all(
        (
            duplicate.get("resolved_node") == by_id["Q1"].get("resolved_node"),
            int(duplicate.get("items_added") or 0) == 0,
            int(duplicate.get("items_deduped") or 0) >= 1,
            duplicate.get("study_before") == duplicate.get("study_after") == "learning",
            duplicate.get("study_state_transition") is None,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--scholar-project", required=True)
    parser.add_argument("--map-project", required=True)
    parser.add_argument("--tutor-output", required=True)
    parser.add_argument("--receipt-dir", required=True)
    parser.add_argument("--stress-report", required=True)
    parser.add_argument("--install-smoke", required=True)
    parser.add_argument("--backup", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.workspace).resolve()
    status = Path(args.status).resolve()
    scholar = Path(args.scholar_project).resolve()
    project = Path(args.map_project).resolve()
    tutor = Path(args.tutor_output).resolve()
    receipts = Path(args.receipt_dir).resolve()
    stress = Path(args.stress_report).resolve()
    install_smoke = Path(args.install_smoke).resolve()
    backup = Path(args.backup).resolve()
    required = {
        "status_document": status,
        "source_pdf": scholar / "source.pdf",
        "digest": scholar / "digest.json",
        "reading_view": scholar / "reading-view.json",
        "checkpoint": scholar / "checkpoint-1.json",
        "paper_map": project / "paper-map.json",
        "tutor_state": project / "tutor-state.json",
        "study_state": project / "study-state.json",
        "html": project / "paper-learning-map.html",
        "fresh_e2e_receipt": receipts / "fresh-verified-e2e-receipt.json",
        "qa_report": receipts / "qa-report.json",
        "regression_results": receipts / "regression-results.json",
        "fresh_browser_report": project / "fresh-verified-chromium-qa.json",
        "stress_report": stress,
        "install_smoke_map": install_smoke / "paper-learning-map.html",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if not backup.is_dir():
        missing.append("paper_tutor_backup")
    if missing:
        raise SystemExit("manifest missing artifacts: " + ", ".join(missing))
    paper_map = json.loads((project / "paper-map.json").read_text(encoding="utf-8"))
    tutor_state = json.loads((project / "tutor-state.json").read_text(encoding="utf-8"))
    study_state = json.loads((project / "study-state.json").read_text(encoding="utf-8"))
    checkpoint = json.loads((scholar / "checkpoint-1.json").read_text(encoding="utf-8"))
    qa = json.loads((receipts / "qa-report.json").read_text(encoding="utf-8"))
    browser = json.loads((project / "fresh-verified-chromium-qa.json").read_text(encoding="utf-8"))
    regression = json.loads((receipts / "regression-results.json").read_text(encoding="utf-8"))
    fresh_receipt = json.loads((receipts / "fresh-verified-e2e-receipt.json").read_text(encoding="utf-8"))
    source_pdf_sha256 = sha256(scholar / "source.pdf")
    reading_view = json.loads((scholar / "reading-view.json").read_text(encoding="utf-8"))
    source_gate = all(
        (
            paper_map.get("source", {}).get("mode") == "integrated",
            paper_map.get("source", {}).get("verification_level") == "scholar_slides_validated",
            paper_map.get("paper_identity", {}).get("source_pdf_sha256") == source_pdf_sha256,
            reading_view.get("paper_identity", {}).get("source_pdf_sha256") == source_pdf_sha256,
            checkpoint.get("source_identity", {}).get("pdf_sha256") == source_pdf_sha256,
        )
    )
    checkpoint_artifact = checkpoint.get("artifact") or {}
    checkpoint_gate = all(
        (
            checkpoint.get("status") == "confirmed",
            bool(checkpoint.get("confirmed_by")),
            Path(str(checkpoint_artifact.get("path") or "")).resolve() == (scholar / "digest.json").resolve(),
            checkpoint_artifact.get("sha256") == sha256(scholar / "digest.json"),
            checkpoint.get("approval_bindings", {}).get("source_pdf_sha256") == source_pdf_sha256,
            checkpoint.get("approval_bindings", {}).get("digest_sha256") == sha256(scholar / "digest.json"),
        )
    )
    browser_results = browser.get("results") or []
    qa_gate = (
        {result.get("viewport") for result in browser_results if isinstance(result, dict)} == {"1440x900", "1920x1080"}
        and all(browser_viewport_passes(result) for result in browser_results)
    )
    full_analysis = qa.get("full_analysis") or {}
    bridge_result = full_analysis.get("bridge_result") or {}
    try:
        full_receipt_path = Path(str(full_analysis["receipt"])).resolve(strict=True)
        full_receipt_path.relative_to((project / "sync-receipts").resolve())
        full_receipt = json.loads(full_receipt_path.read_text(encoding="utf-8"))
    except (KeyError, OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        full_receipt = {}
    tutor_gate = all(
        (
            bridge_result.get("status") == "success",
            int(full_analysis.get("records_in_memory") or 0) > 0,
            bridge_result.get("records_received") == full_analysis.get("records_in_memory"),
            full_receipt.get("event") == "full_analysis_sync",
            full_receipt.get("status") == "success",
            full_receipt.get("paper_sha256") == source_pdf_sha256,
            qa.get("tutor_state", {}).get("schema_version") == "1.1",
            int(qa.get("tutor_state", {}).get("map_items") or 0) > 0,
            qa.get("factual_integrity", {}).get("same") is True,
            qa.get("no_records_json_created") is True,
            not (project / "records.json").exists(),
        )
    )
    q_gate = qa_turns_pass(qa, project, source_pdf_sha256)
    expected_regressions = {
        "scholar_regression", "paper_learning_map_regression", "renderer_qa",
        "tutor_overlay_qa", "stress_qa", "fresh_chromium_qa",
    }
    regression_rows = regression.get("results") or []
    tests_gate = (
        regression.get("all_passed") is True
        and {row.get("name") for row in regression_rows if isinstance(row, dict)} == expected_regressions
        and all(row.get("passed") is True and row.get("returncode") == 0 for row in regression_rows)
    )
    install_receipts: list[dict[str, Any]] = []
    for receipt_path in (install_smoke / "sync-receipts").glob("*.json"):
        try:
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            install_receipts.append(payload)
    install_gate = (
        (install_smoke / "paper-learning-map.html").is_file()
        and any(
            receipt.get("event") == "full_analysis_sync"
            and receipt.get("status") == "success"
            and receipt.get("paper_sha256") == source_pdf_sha256
            and receipt.get("error") is None
            for receipt in install_receipts
        )
    )
    gates = {
        "verified_fresh_integrated": source_gate and checkpoint_gate,
        "full_sync_success": tutor_gate,
        "qas_success": q_gate,
        "integrity_success": qa.get("factual_integrity", {}).get("same") is True,
        "browser_qa_success": qa_gate,
        "tests_success": tests_gate,
        "installed_smoke_success": install_gate,
    }
    # Cross-artifact consistency checks required by the release gate.
    consistency_errors: list[str] = []
    fresh_source = fresh_receipt.get("source", {})
    if fresh_source.get("pdf_sha256") != sha256(scholar / "source.pdf"):
        consistency_errors.append("fresh_receipt.pdf_sha256")
    if fresh_source.get("digest_sha256") != sha256(scholar / "digest.json"):
        consistency_errors.append("fresh_receipt.digest_sha256")
    if fresh_source.get("reading_view_sha256") != sha256(scholar / "reading-view.json"):
        consistency_errors.append("fresh_receipt.reading_view_sha256")
    if fresh_source.get("paper_map_sha256") != sha256(project / "paper-map.json"):
        consistency_errors.append("fresh_receipt.paper_map_sha256")
    if fresh_receipt.get("browser_qa", {}).get("report_sha256") != sha256(project / "fresh-verified-chromium-qa.json"):
        consistency_errors.append("fresh_receipt.browser_report_sha256")
    if fresh_receipt.get("stress", {}).get("report_sha256") != sha256(stress):
        consistency_errors.append("fresh_receipt.stress_report_sha256")
    status_text = status.read_text(encoding="utf-8")
    # Do not let a historical performance sentence survive into the release
    # record.  The old RC notes used both the earlier millisecond pair and a
    # rounded seconds range; neither is valid once the stress receipt has been
    # rerun.  Keep the check phrase-specific so ordinary paper numbers do not
    # trigger a false positive.
    forbidden_stale = (
        "10286", "9932", "5636", "5434", "9.9–10.3", "9.9-10.3",
        "Agent Harness SFT / DPO / RLHF",
    )
    if any(marker in status_text for marker in forbidden_stale):
        consistency_errors.append("status_document_stale_marker")
    try:
        stress_payload = json.loads(stress.read_text(encoding="utf-8"))
        measured_expansions = [
            float(viewport["expand_ms"])
            for viewport in stress_payload.get("viewports", [])
            if isinstance(viewport, dict) and isinstance(viewport.get("expand_ms"), (int, float))
        ]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        measured_expansions = []
        consistency_errors.append("stress_report_invalid")
    if len(measured_expansions) < 2:
        consistency_errors.append("stress_report_missing_latest_timing")
    else:
        # The status document must quote the current receipt values, not only
        # a stale rounded summary.  This makes the no-old-timing requirement
        # part of the executable release gate.
        for measured in measured_expansions[:2]:
            if f"{measured:.2f} ms" not in status_text:
                consistency_errors.append("status_document_timing_mismatch")
                break
    if consistency_errors:
        raise SystemExit("cross-artifact consistency failed: " + ", ".join(consistency_errors))
    release_status = "RC1" if all(gates.values()) else "conditional-candidate"
    artifacts = {name: artifact(path, root) for name, path in required.items()}
    artifacts["paper_tutor_backup"] = {"path": str(backup), "relative": str(backup)}
    manifest: dict[str, Any] = {
        "release": "paper-learning-system-rc1",
        "release_status": release_status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace": str(root),
        "fresh_verified_sample": {
            "title": "SWE-Touch: Benchmarking Coding Agents When Users Touch the Code",
            "source_url": "https://arxiv.org/pdf/2608.02499",
            "pdf_sha256": sha256(scholar / "source.pdf"),
            "page_count": 39,
            "paper_type": "benchmark",
            "checkpoint_status": checkpoint.get("status"),
            "paper_map_source": paper_map.get("source"),
            "factual_node_count": sum(node.get("claim_type") == "paper_fact" for node in paper_map.get("nodes", [])),
            "tutor_node_count": len(tutor_state.get("nodes", {})),
            "tutor_map_item_count": sum(len(node.get("map_items", [])) for node in tutor_state.get("nodes", {}).values()),
            "unresolved_count": len(tutor_state.get("unresolved_items", [])),
        },
        "sync_observability": {
            "mode": "model-driven hook with explicit receipt-based observability",
            "receipt_directory": str(project / "sync-receipts"),
            "receipt_count": len(list((project / "sync-receipts").glob("*.json"))),
            "fresh_e2e_receipt": artifact(receipts / "fresh-verified-e2e-receipt.json", root),
        },
        "gates": gates,
        "artifacts": artifacts,
        "browser_qa": {
            "report": artifact(project / "fresh-verified-chromium-qa.json", root),
            "screenshots": [artifact(project / "screenshots" / name, root) for name in browser.get("screenshots", [])],
        },
        "performance": {
            "stress_report": artifact(stress, root),
            "latest_measured": json.loads(stress.read_text(encoding="utf-8")).get("viewports", []),
        },
        "regression": artifact(receipts / "regression-results.json", root),
        "install_smoke": {"map": artifact(install_smoke / "paper-learning-map.html", root), "backup": str(backup)},
        "limitations": [
            "Paper-Tutor is model-driven; actual hook calls are observable by receipt but future turns are not guaranteed by code.",
            "Question dedupe is deterministic lexical canonicalization, not embedding semantic matching.",
            "Stress full expansion remains approximately multi-second at 100 factual / 200 Tutor items.",
            "No mobile, KaTeX, or CKPT-2 presentation export was added in this gate.",
        ],
    }
    output = Path(args.output).resolve()
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Self-consistency: every recorded file hash must match immediately after
    # writing, and status must agree with the computed gate.
    check = json.loads(output.read_text(encoding="utf-8"))
    errors = []
    for name, entry in check["artifacts"].items():
        if name == "paper_tutor_backup":
            continue
        path = Path(entry["path"])
        if not path.is_file() or sha256(path) != entry["sha256"]:
            errors.append(name)
    if check["release_status"] != ("RC1" if all(check["gates"].values()) else "conditional-candidate"):
        errors.append("release_status")
    if errors:
        raise SystemExit("manifest self-consistency failed: " + ", ".join(errors))
    validation = {"manifest": str(output), "manifest_sha256": sha256(output), "release_status": release_status, "gates": gates, "errors": errors, "cross_artifact_errors": consistency_errors}
    validation_path = output.with_name("release-manifest-self-check.json")
    validation_path.write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
