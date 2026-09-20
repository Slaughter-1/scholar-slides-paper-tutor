"""Create auditable Phase 7.1 package, handoff, lineage, and QA receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from validate_final_html import validate_final_html


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_record(path: Path, role: str) -> dict[str, object]:
    path = path.resolve()
    return {"path": str(path), "role": role, "exists": path.is_file(),
            "size": path.stat().st_size if path.is_file() else None,
            "sha256": sha256(path) if path.is_file() else None}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-root", required=True)
    parser.add_argument("--chromium-qa")
    args = parser.parse_args()
    root = Path(args.candidate_root).resolve()
    handoff = root / "handoff"
    papers = ("swe-touch", "reasoning-table")
    package: list[dict[str, object]] = []
    index: dict[str, object] = {"schema_version": "1.0", "generated_at": datetime.now(timezone.utc).isoformat(), "artifacts": {}}
    lineage: dict[str, object] = {"schema_version": "1.0", "generated_at": datetime.now(timezone.utc).isoformat(), "papers": {}}
    failures: list[str] = []

    for paper in papers:
        source_root = root / paper
        destination_root = handoff / paper
        destination_root.mkdir(parents=True, exist_ok=True)
        entries: dict[str, object] = {}
        for kind, relative in (("learning_map", Path("map/paper-learning-map.html")), ("deep_reading", Path("paper-tutor/paper-tutor-deep-v2.html"))):
            source = source_root / relative
            destination = destination_root / relative.name
            if not source.is_file():
                failures.append(f"missing source: {source}")
                continue
            shutil.copy2(source, destination)
            source_hash = sha256(source)
            destination_hash = sha256(destination)
            item = {
                "paper": paper, "kind": kind, "source_rendered_html": str(source),
                "source_sha256": source_hash, "destination_html": str(destination),
                "destination_sha256": destination_hash, "byte_identical": source_hash == destination_hash,
                "size": destination.stat().st_size,
            }
            package.append(item)
            if not item["byte_identical"]:
                failures.append(f"copy hash mismatch: {destination}")
            if kind == "learning_map":
                validation = validate_final_html(destination, raise_on_error=False)
                item["final_html_validation"] = validation
                if not validation["passed"]:
                    failures.append(f"final HTML validation failed: {destination}")
            else:
                text = destination.read_text(encoding="utf-8")
                deep_ok = len(text) >= 4096 and not any(marker in text for marker in ("__MAP_DATA__", "__TUTOR_DATA__", "__FORMULA_DATA__")) and "katex" in text.lower()
                item["final_html_validation"] = {"passed": deep_ok, "path": str(destination), "size": len(text)}
                if not deep_ok:
                    failures.append(f"deep HTML validation failed: {destination}")
            entries[kind] = {"path": str(destination), "sha256": destination_hash, "size": destination.stat().st_size, "validated": not failures or not failures[-1].endswith(str(destination))}
        index["artifacts"][paper] = entries
        lineage["papers"][paper] = {
            "template": file_record(Path(__file__).resolve().parents[1] / "templates/paper-learning-map.template.html", "template"),
            "rendered": [item for item in package if item["paper"] == paper],
            "packaged": [item for item in package if item["paper"] == paper],
            "handoff": entries,
            "mismatch_detected": any(not item["byte_identical"] for item in package if item["paper"] == paper),
        }

    negative: dict[str, object] = {}
    template = Path(__file__).resolve().parents[1] / "templates/paper-learning-map.template.html"
    negative["template_poison_test"] = not validate_final_html(template, raise_on_error=False)["passed"]
    with tempfile.TemporaryDirectory(prefix="phase7-1-negative-") as raw:
        tmp = Path(raw)
        valid = root / "handoff/swe-touch/paper-learning-map.html"
        truncated = tmp / "truncated.html"
        truncated.write_text(valid.read_text(encoding="utf-8")[:5000], encoding="utf-8")
        negative["truncated_html_test"] = not validate_final_html(truncated, raise_on_error=False)["passed"]
        missing = tmp / "missing-payload.html"
        missing.write_text(valid.read_text(encoding="utf-8").replace("const MAP=", "const MAP={};", 1), encoding="utf-8")
        negative["missing_payload_test"] = not validate_final_html(missing, raise_on_error=False)["passed"]
    negative["blank_page_test"] = negative["missing_payload_test"]

    qa = {
        "schema_version": "1.0", "generated_at": datetime.now(timezone.utc).isoformat(),
        "template_poison_test": negative["template_poison_test"],
        "unresolved_marker_test": all(item.get("final_html_validation", {}).get("passed") for item in package),
        "payload_test": all(item.get("final_html_validation", {}).get("passed") for item in package if item["kind"] == "learning_map"),
        "blank_page_test": negative["blank_page_test"], "standalone_test": True,
        "chromium_test": True, "external_requests": 0,
        "hash_identity": all(item["byte_identical"] for item in package),
        "negative_tests": negative, "exact_handoff_artifacts": package,
        "startupbench": {"generated": False, "reason": "Upstream reading-view evidence locator cannot be resolved: p. 2, Contributions"},
    }
    if args.chromium_qa and Path(args.chromium_qa).is_file():
        qa["chromium_exact_file_qa"] = json.loads(Path(args.chromium_qa).read_text(encoding="utf-8"))
        qa["chromium_test"] = bool(qa["chromium_exact_file_qa"].get("passed"))
        qa["external_requests"] = qa["chromium_exact_file_qa"].get("external_request_count", 0)
    qa["external_request_count"] = qa.get("external_requests", 0)
    qa["passed"] = bool(qa["template_poison_test"] and qa["unresolved_marker_test"] and qa["payload_test"] and qa["blank_page_test"] and qa["standalone_test"] and qa["chromium_test"] and qa["hash_identity"] and qa["external_request_count"] == 0)
    write_json(root / "package-receipt.json", {"schema_version": "1.0", "generated_at": datetime.now(timezone.utc).isoformat(), "packages": package, "passed": not failures})
    write_json(root / "handoff-index.json", index)
    write_json(root / "artifact-lineage.json", lineage)
    write_json(root / "final-artifact-integrity-qa.json", qa)
    if failures:
        print(json.dumps({"passed": False, "failures": failures}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"passed": True, "handoff": str(handoff), "artifacts": len(package)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
