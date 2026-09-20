#!/usr/bin/env python3
"""Produce auditable evidence-locator coverage for a reading-view project."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Mapping

from evidence_resolver import build_document_index, resolve_and_verify
from reading_view import _digest_evidence_ids, _resolve_json_pointer, _source_page_texts


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _collect_refs(value: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(value, Mapping):
        raw = value.get("evidence_refs")
        if isinstance(raw, list):
            refs.extend(item.strip() for item in raw if isinstance(item, str) and item.strip())
        for child in value.values():
            refs.extend(_collect_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.extend(_collect_refs(child))
    return refs


def _pointer_resolution(reference: str, project: Path, digest: Mapping[str, Any] | None, bound_digest: bool) -> dict[str, Any] | None:
    if "#" not in reference or not reference.split("#", 1)[0].casefold().endswith("digest.json"):
        return None
    if digest is None or not bound_digest:
        return {"raw": reference, "kind": "digest_pointer", "status": "unresolved", "failure_reason_codes": ["DIGEST_NOT_BOUND"]}
    try:
        _resolve_json_pointer(digest, reference.split("#", 1)[1])
    except KeyError:
        return {"raw": reference, "kind": "digest_pointer", "status": "unresolved", "failure_reason_codes": ["DIGEST_POINTER_NOT_FOUND"]}
    return {"raw": reference, "kind": "digest_pointer", "status": "exact", "evidence_span_verified": True, "failure_reason_codes": []}


def classify_resolution(item: dict[str, Any]) -> str:
    status = item.get("status")
    reasons = set(item.get("failure_reason_codes") or [])
    if status in {"ambiguous", "unresolved"}:
        return "requires_review" if status == "ambiguous" else "producer_bug"
    if status == "partial" and item.get("evidence_span"):
        return "resolver_gap"
    if "UNRECOGNIZED_LOCATOR" in reasons or "EVIDENCE_SPAN_NOT_FOUND" in reasons:
        return "resolver_gap" if item.get("parsed", {}).get("components") else "producer_bug"
    return "resolved"


def build_report(project: Path, *, label: str | None = None) -> dict[str, Any]:
    project = project.resolve()
    reading_path = project / "reading-view.json"
    digest_path = project / "digest.json"
    payload = json.loads(reading_path.read_text(encoding="utf-8"))
    digest = json.loads(digest_path.read_text(encoding="utf-8")) if digest_path.is_file() else None
    source_path: Path | None = None
    for binding in payload.get("source_bindings", []):
        if not isinstance(binding, Mapping):
            continue
        candidate = Path(str(binding.get("path", "")))
        if not candidate.is_absolute():
            candidate = project / candidate
        if candidate.suffix.casefold() == ".pdf" and candidate.is_file():
            source_path = candidate.resolve()
            break
    if source_path is None:
        raise FileNotFoundError(f"no bound PDF found in {reading_path}")
    page_texts = _source_page_texts(source_path)
    if page_texts is None:
        raise RuntimeError(f"cannot extract bound PDF: {source_path}")
    digest_bound = any(
        isinstance(binding, Mapping)
        and (project / str(binding.get("path", ""))).resolve() == digest_path.resolve()
        for binding in payload.get("source_bindings", [])
    ) if digest_path.is_file() else False
    index = build_document_index(page_texts, digest=digest)
    known_ids = _digest_evidence_ids(digest)
    refs = list(dict.fromkeys(_collect_refs(payload)))
    records: list[dict[str, Any]] = []
    for reference in refs:
        pointer = _pointer_resolution(reference, project, digest, digest_bound)
        if pointer is not None:
            records.append(pointer)
            continue
        if reference in known_ids:
            records.append({"raw": reference, "kind": "evidence_id", "status": "exact", "evidence_span_verified": True, "failure_reason_codes": []})
            continue
        started = time.perf_counter()
        resolution = resolve_and_verify(reference, index)
        item = resolution.as_dict()
        item["kind"] = "locator"
        item["evidence_span_verified"] = bool(resolution.evidence_span)
        item["resolution_time_ms"] = round((time.perf_counter() - started) * 1000, 4)
        records.append(item)
    status_counts = Counter(item.get("status", "unresolved") for item in records)
    kind_counts = Counter(item.get("kind", "locator") for item in records)
    category_counts = Counter(classify_resolution(item) if item.get("kind") == "locator" else "resolved" if item.get("status") == "exact" else "producer_bug" for item in records)
    locator_records = [item for item in records if item.get("kind") == "locator"]
    verified = sum(1 for item in records if item.get("evidence_span_verified"))
    locator_verified = sum(1 for item in locator_records if item.get("evidence_span_verified"))
    unresolved = [item for item in records if item.get("status") in {"unresolved", "ambiguous"}]
    return {
        "schema_version": "phase7.2.evidence-resolution-report.v1",
        "label": label or project.name,
        "project": str(project),
        "external_requests": 0,
        "page_coordinate_systems": {
            "pdf_page_index": "zero-based index into the bound PDF",
            "printed_page_label": "label printed by the source when supplied/derived",
            "source_page_reference": "one-based human p. N reference; never silently treated as a PDF index",
        },
        "source": {
            "pdf": str(source_path),
            "pdf_sha256": sha256(source_path),
            "reading_view": str(reading_path),
            "reading_view_sha256": sha256(reading_path),
            "digest": str(digest_path) if digest_path.is_file() else None,
            "digest_sha256": sha256(digest_path) if digest_path.is_file() else None,
            "digest_bound": digest_bound,
            "page_count": len(page_texts),
        },
        "coverage": {
            "total_references": len(records),
            "locator_references": len(locator_records),
            "verified_evidence_spans": verified,
            "verified_locator_spans": locator_verified,
            "evidence_coverage": round(verified / len(records), 6) if records else 1.0,
            "locator_evidence_coverage": round(locator_verified / len(locator_records), 6) if locator_records else 1.0,
            "status_counts": dict(sorted(status_counts.items())),
            "kind_counts": dict(sorted(kind_counts.items())),
            "producer_bug_vs_resolver_gap": dict(sorted(category_counts.items())),
        },
        "failures": {
            "ambiguous_or_unresolved": len(unresolved),
            "reason_counts": dict(sorted(Counter(reason for item in records for reason in item.get("failure_reason_codes", [])).items())),
        },
        "resolutions": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve and verify reading-view evidence locators")
    parser.add_argument("--project", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label")
    args = parser.parse_args()
    report = build_report(Path(args.project), label=args.label)
    target = Path(args.out).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
