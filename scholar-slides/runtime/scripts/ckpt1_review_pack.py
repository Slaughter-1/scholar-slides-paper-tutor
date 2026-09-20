#!/usr/bin/env python3
"""Phase 7.3 CKPT-1 source-bound human review and promotion protocol.

A review pack is an immutable proposal over the Phase 7.2 source artifacts.
It carries resolver statuses into claim-level review, but it never records
human approval. A receipt is stale when any bound hash changes. Promotion is
fail-closed and does not mutate evidence status or downstream artifacts.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import sys
from typing import Any, Iterable, Mapping

from evidence_resolver import build_document_index, resolve_and_verify
from reading_view import _resolve_json_pointer, _source_page_texts

SCHEMA_VERSION = "phase7.3.ckpt1-review-pack.v1"
RECEIPT_SCHEMA_VERSION = "phase7.3.ckpt1-human-review-receipt.v1"
PROMOTION_SCHEMA_VERSION = "phase7.3.ckpt1-promotion-receipt.v1"
RESOLUTION_STATUSES = ("exact", "normalized", "fuzzy", "partial", "ambiguous", "unresolved")
DECISIONS = ("approve", "approve_as_partial", "reject", "needs_fix", "not_applicable")
NON_EXACT_STATUSES = ("normalized", "fuzzy", "partial", "ambiguous", "unresolved")


class CKPT1ReviewPackError(ValueError):
    """Raised when a pack, receipt, or source binding is invalid."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def read_json(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CKPT1ReviewPackError(f"cannot read JSON: {target}: {exc}") from exc
    if not isinstance(value, dict):
        raise CKPT1ReviewPackError(f"JSON root must be an object: {target}")
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _norm_ref(value: Any) -> str:
    value = _clean(value).casefold().replace("—", " ").replace("–", " ")
    return re.sub(r"[^a-z0-9\u3400-\u9fff]+", "", value)


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.casefold()).strip("-")
    return value or "paper"


def _bound_path(value: Any, base: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        candidate = candidate.resolve()
    except OSError:
        candidate = candidate.absolute()
    return candidate if candidate.is_file() else None


def _bound_pdf(view: Mapping[str, Any], reading_path: Path) -> Path:
    for binding in view.get("source_bindings", []) or []:
        if not isinstance(binding, Mapping):
            continue
        candidate = _bound_path(binding.get("path"), reading_path.parent)
        if candidate is not None and candidate.suffix.casefold() == ".pdf":
            return candidate
    raise CKPT1ReviewPackError(f"reading-view has no existing bound PDF: {reading_path}")


def _report_lookup(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for value in report.get("resolutions", []) or []:
        if not isinstance(value, Mapping):
            continue
        raw = value.get("raw")
        if isinstance(raw, str) and raw.strip():
            lookup.setdefault(_norm_ref(raw), dict(value))
    return lookup


def _classification(status: str, item: Mapping[str, Any]) -> str:
    if status == "partial":
        return "resolver_gap"
    if status == "ambiguous":
        return "requires_review"
    if status == "unresolved":
        return "producer_bug" if (item.get("parsed") or {}).get("components") else "unresolved_locator"
    return "resolved"


def _pointer_resolution(reference: str, digest: Mapping[str, Any] | None) -> dict[str, Any]:
    if digest is None:
        return {"raw": reference, "kind": "digest_pointer", "status": "unresolved",
                "evidence_span_verified": False, "failure_reason_codes": ["DIGEST_NOT_BOUND"]}
    try:
        _resolve_json_pointer(digest, reference.split("#", 1)[1])
    except (KeyError, IndexError, ValueError):
        return {"raw": reference, "kind": "digest_pointer", "status": "unresolved",
                "evidence_span_verified": False, "failure_reason_codes": ["DIGEST_POINTER_NOT_FOUND"]}
    return {"raw": reference, "kind": "digest_pointer", "status": "exact",
            "evidence_span_verified": True, "failure_reason_codes": []}


class EvidenceContext:
    """Resolve claim references against the four frozen input artifacts."""

    def __init__(self, *, reading_path: str | Path, digest_path: str | Path,
                 resolver_path: str | Path) -> None:
        self.reading_path = Path(reading_path).resolve()
        self.digest_path = Path(digest_path).resolve()
        self.resolver_path = Path(resolver_path).resolve()
        self.reading_view = read_json(self.reading_path)
        self.digest = read_json(self.digest_path) if self.digest_path.is_file() else None
        self.resolver_report = read_json(self.resolver_path)
        self.pdf_path = _bound_pdf(self.reading_view, self.reading_path)
        page_texts = _source_page_texts(self.pdf_path)
        if page_texts is None:
            raise CKPT1ReviewPackError(f"cannot extract bound PDF: {self.pdf_path}")
        self.index = build_document_index(page_texts, digest=self.digest)
        self.lookup = _report_lookup(self.resolver_report)

    @property
    def inputs(self) -> dict[str, Any]:
        source = self.resolver_report.get("source") or {}
        return {
            "source_pdf": {"path": str(self.pdf_path), "sha256": sha256_file(self.pdf_path)},
            "digest": {"path": str(self.digest_path), "sha256": sha256_file(self.digest_path)},
            "reading_view": {"path": str(self.reading_path), "sha256": sha256_file(self.reading_path)},
            "resolver_report": {"path": str(self.resolver_path), "sha256": sha256_file(self.resolver_path)},
            "page_count": source.get("page_count") or len(self.index.page_texts),
            "page_coordinate_systems": {
                "pdf_page_index": "zero-based index into the bound PDF",
                "printed_page_label": "label printed by the source when supplied/derived",
                "source_page_reference": "one-based human p. N reference",
            },
        }

    def resolve(self, reference: str) -> dict[str, Any]:
        reference = _clean(reference)
        if not reference:
            return {"raw": reference, "status": "unresolved", "evidence_span_verified": False,
                    "failure_reason_codes": ["EMPTY_LOCATOR"]}
        if "#" in reference and reference.split("#", 1)[0].casefold().endswith("digest.json"):
            return _pointer_resolution(reference, self.digest)
        known = self.lookup.get(_norm_ref(reference))
        if known is None:
            known = self.lookup.get(_norm_ref(reference.replace("—", ",").replace("–", ",")))
        result = deepcopy(known) if known is not None else resolve_and_verify(reference, self.index).as_dict()
        result.setdefault("status", "unresolved")
        result["evidence_span_verified"] = bool(result.get("evidence_span_verified") or result.get("evidence_span"))
        result["classification"] = _classification(str(result["status"]), result)
        return result

    def claim_resolution(self, references: Iterable[str]) -> tuple[str, list[dict[str, Any]]]:
        refs = [ref for ref in references if isinstance(ref, str) and ref.strip()]
        if not refs:
            return "unresolved", [self.resolve("")]
        resolutions = [self.resolve(ref) for ref in refs]
        statuses = [str(value.get("status", "unresolved")) for value in resolutions]
        if "ambiguous" in statuses:
            status = "ambiguous"
        elif "unresolved" in statuses:
            status = "unresolved"
        elif "partial" in statuses:
            status = "partial"
        elif "fuzzy" in statuses:
            status = "fuzzy"
        elif "normalized" in statuses:
            status = "normalized"
        else:
            status = "exact"
        return status, resolutions


def _evidence_refs(record: Mapping[str, Any]) -> list[str]:
    refs = record.get("evidence_refs")
    return [ref.strip() for ref in refs if isinstance(ref, str) and ref.strip()] if isinstance(refs, list) else []


def _review_item(*, item_id: str, category: str, claim: str, claim_type: str,
                 importance: str, critical: bool, refs: list[str],
                 context: EvidenceContext, locator: str | None = None,
                 note: str = "") -> dict[str, Any]:
    status, resolutions = context.claim_resolution(refs)
    result = {
        "item_id": item_id,
        "category": category,
        "claim": _clean(claim),
        "claim_type": _clean(claim_type) or "paper_fact",
        "importance": importance,
        "critical": bool(critical),
        "evidence_refs": list(refs),
        "locator": locator or (refs[0] if refs else None),
        "resolution": {
            "status": status,
            "evidence_span_verified": all(bool(value.get("evidence_span_verified")) for value in resolutions),
            "resolutions": resolutions,
            "failure_reason_codes": sorted({reason for value in resolutions for reason in value.get("failure_reason_codes", [])}),
            "classifications": sorted({str(value.get("classification", "unresolved")) for value in resolutions}),
        },
        "review": {"decision": None, "comment": "", "reviewer": None, "reviewed_at": None},
        "allowed_decisions": list(DECISIONS),
    }
    if note:
        result["protocol_note"] = note
    return result


def _overview_items(view: Mapping[str, Any], context: EvidenceContext, prefix: str) -> list[dict[str, Any]]:
    overview = view.get("overview") if isinstance(view.get("overview"), Mapping) else {}
    result: list[dict[str, Any]] = []
    definitions = [
        ("problem", "Problem", True, "high"),
        ("gap", "Gap", True, "high"),
        ("approach", "Core Idea", True, "high"),
        ("insight", "Core Idea", True, "high"),
        ("findings", "Main Result", True, "critical"),
        ("boundary", "Limitation", True, "high"),
    ]
    counts: Counter[str] = Counter()
    for key, category, critical, importance in definitions:
        record = overview.get(key)
        if not isinstance(record, Mapping) or not _clean(record.get("content")):
            continue
        slug = category.casefold().replace(" ", "-")
        counts[slug] += 1
        result.append(_review_item(
            item_id=f"{prefix}.claim.{slug}.{counts[slug]:02d}",
            category=category, claim=record.get("content", ""),
            claim_type=record.get("claim_type", "paper_fact"), importance=importance,
            critical=critical, refs=_evidence_refs(record), context=context,
        ))
    return result


def _method_items(view: Mapping[str, Any], context: EvidenceContext, prefix: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, record in enumerate(view.get("mechanism_steps", []) or [], start=1):
        if not isinstance(record, Mapping):
            continue
        claim = _clean(record.get("purpose")) or _clean(record.get("output")) or _clean(record.get("title"))
        result.append(_review_item(
            item_id=f"{prefix}.method.{index:02d}", category="Method", claim=claim,
            claim_type=record.get("claim_type", "paper_fact"), importance="high", critical=True,
            refs=_evidence_refs(record), context=context, note=_clean(record.get("title")),
        ))
    return result


def _takeaway_items(view: Mapping[str, Any], context: EvidenceContext, prefix: str) -> list[dict[str, Any]]:
    """Keep author-contribution takeaways visible even when their locator is partial."""
    result: list[dict[str, Any]] = []
    index = 0
    for record in view.get("takeaways", []) or []:
        if not isinstance(record, Mapping) or not _clean(record.get("content")):
            continue
        if _clean(record.get("kind")).casefold() not in {"author_contribution", "explicit_limitation"}:
            continue
        index += 1
        kind = _clean(record.get("kind")).casefold()
        category = "Core Idea" if kind == "author_contribution" else "Limitation"
        result.append(_review_item(
            item_id=f"{prefix}.takeaway.{index:02d}", category=category,
            claim=record.get("content", ""), claim_type=record.get("claim_type", "paper_fact"),
            importance="high", critical=(category == "Core Idea"), refs=_evidence_refs(record), context=context,
        ))
    return result


def _result_items(view: Mapping[str, Any], context: EvidenceContext, prefix: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, record in enumerate(view.get("decisive_evidence", []) or [], start=1):
        if not isinstance(record, Mapping):
            continue
        claim = _clean(record.get("result")) or _clean(record.get("comparison"))
        result.append(_review_item(
            item_id=f"{prefix}.result.evidence.{index:02d}", category="Main Result", claim=claim,
            claim_type=record.get("claim_type", "paper_fact"), importance="critical", critical=True,
            refs=_evidence_refs(record), context=context,
        ))
    return result


def _asset_items(digest: Mapping[str, Any], view: Mapping[str, Any],
                 context: EvidenceContext, prefix: str) -> list[dict[str, Any]]:
    decisive_refs = {
        _norm_ref(ref)
        for record in (view.get("decisive_evidence", []) or [])
        if isinstance(record, Mapping)
        for ref in _evidence_refs(record)
    }
    result: list[dict[str, Any]] = []
    for index, asset in enumerate(digest.get("figures", []) or [], start=1):
        if not isinstance(asset, Mapping):
            continue
        label = _clean(asset.get("label")) or _clean(asset.get("id")) or f"Asset {index}"
        kind = _clean(asset.get("kind")).casefold()
        category = "Figure" if kind == "figure" or label.casefold().startswith("figure") else "Table"
        ref = _clean(asset.get("source_ref"))
        if not ref:
            ref = f"p. {asset.get('page')}, {label}" if asset.get("page") else label
        ref_alias = ref.replace("—", ",").replace("–", ",")
        critical = _norm_ref(ref) in decisive_refs or _norm_ref(ref_alias) in decisive_refs
        caption = _clean(asset.get("caption")) or label
        result.append(_review_item(
            item_id=f"{prefix}.asset.{index:03d}", category=category,
            claim=f"{label}: {caption}", claim_type="paper_fact",
            importance="critical" if critical else "high", critical=critical, refs=[ref],
            context=context, locator=ref,
        ))
    return result


def _formula_items(digest: Mapping[str, Any], view: Mapping[str, Any],
                   context: EvidenceContext, prefix: str) -> list[dict[str, Any]]:
    """Expose pre-gate formula candidates without emitting a formula index."""
    try:
        formula_runtime = Path(__file__).resolve().parents[2] / "paper-learning-map" / "runtime"
        sys.path.insert(0, str(formula_runtime))
        from formula_projection import _iter_formula_sources  # type: ignore
        candidates = _iter_formula_sources(digest, view)
    except Exception:
        candidates = []
    result: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        if not isinstance(candidate, Mapping):
            continue
        text = _clean(candidate.get("latex_or_text")) or _clean(candidate.get("source_text"))
        ref = _clean(candidate.get("source_ref"))
        item = _review_item(
            item_id=f"{prefix}.formula.{index:03d}", category="Formula",
            claim=f"Formula pre-gate candidate: {text}", claim_type="paper_formula_candidate",
            importance="high", critical=False, refs=[ref] if ref else [], context=context,
            locator=ref or None, note="pre-gate candidate; no formula-index emitted",
        )
        item["resolution"]["status"] = "partial" if ref else "unresolved"
        item["resolution"]["failure_reason_codes"] = sorted(
            set(item["resolution"].get("failure_reason_codes", [])) | {"FORMULA_PRE_GATE_NOT_PROJECTED"}
        )
        item["resolution"]["classifications"] = ["downstream_gate"]
        result.append(item)
    return result


def build_review_pack(*, paper: str, reading_view_path: str | Path,
                      digest_path: str | Path, resolver_report_path: str | Path) -> dict[str, Any]:
    """Build a source-bound claim-level pack with no human decisions."""
    view = read_json(reading_view_path)
    digest = read_json(digest_path)
    context = EvidenceContext(reading_path=reading_view_path, digest_path=digest_path, resolver_path=resolver_report_path)
    identity = view.get("paper_identity") if isinstance(view.get("paper_identity"), Mapping) else {}
    metadata = digest.get("paper_metadata") if isinstance(digest.get("paper_metadata"), Mapping) else {}
    title = _clean(identity.get("title")) or _clean(digest.get("title")) or _clean(metadata.get("title"))
    prefix = _slug(paper)
    items = _overview_items(view, context, prefix)
    items.extend(_takeaway_items(view, context, prefix))
    items.extend(_method_items(view, context, prefix))
    items.extend(_result_items(view, context, prefix))
    items.extend(_asset_items(digest, view, context, prefix))
    items.extend(_formula_items(digest, view, context, prefix))
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if item["item_id"] not in seen:
            seen.add(item["item_id"])
            deduped.append(item)
    status_counts = Counter(str(item["resolution"]["status"]) for item in deduped)
    groups: dict[str, list[str]] = {status: [] for status in NON_EXACT_STATUSES}
    for item in deduped:
        status = item["resolution"]["status"]
        if status in groups:
            groups[status].append(item["item_id"])
    inputs = context.inputs
    pack: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "ckpt-1-review-pack",
        "review_pack_id": f"{prefix}-ckpt1-review-pack",
        "paper": paper,
        "paper_identity": {
            "title": title,
            "authors": metadata.get("authors", []),
            "arxiv": (metadata.get("identifiers") or {}).get("arxiv") if isinstance(metadata.get("identifiers"), Mapping) else None,
            "source_pdf_sha256": inputs["source_pdf"]["sha256"],
            "page_count": inputs["page_count"],
        },
        "inputs": inputs,
        "source_state": {
            "digest_review_status": digest.get("review_status"),
            "digest_extractive_only": digest.get("extractive_only"),
            "digest_flags": digest.get("flags", []),
            "resolver_schema_version": context.resolver_report.get("schema_version"),
            "resolver_coverage": context.resolver_report.get("coverage", {}),
        },
        "review_protocol": {
            "state": "WAITING_FOR_HUMAN_CKPT1",
            "human_confirmation_required": True,
            "decisions_are_empty_until_human_review": True,
            "promotion_requires_all_claims_reviewed": True,
            "ambiguous_or_unresolved_critical_blocks": True,
            "partial_or_fuzzy_requires_explicit_decision": True,
            "evidence_status_immutable": True,
            "stale_when_any_input_hash_changes": True,
        },
        "review_items": deduped,
        "review_status": "pending",
        "coverage": {
            "review_items_total": len(deduped),
            "critical_items_total": sum(1 for item in deduped if item.get("critical")),
            "status_counts": dict(sorted(status_counts.items())),
            "evidence_span_verified": sum(1 for item in deduped if item["resolution"].get("evidence_span_verified")),
            "non_exact_groups": groups,
            "claim_categories": dict(sorted(Counter(item["category"] for item in deduped).items())),
        },
        "promotion_status": "WAITING_FOR_HUMAN_CKPT1",
        "evidence_status_snapshot": {item["item_id"]: item["resolution"]["status"] for item in deduped},
        "generated_at": _utc_now(),
    }
    pack["pack_sha256"] = canonical_sha256(pack)
    return pack


def _pack_without_hash(pack: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(pack))
    value.pop("pack_sha256", None)
    return value


def validate_review_pack(pack: Mapping[str, Any], *, current: bool = True) -> dict[str, Any]:
    if pack.get("schema_version") != SCHEMA_VERSION or pack.get("kind") != "ckpt-1-review-pack":
        raise CKPT1ReviewPackError("unsupported CKPT-1 review pack schema")
    if pack.get("promotion_status") != "WAITING_FOR_HUMAN_CKPT1":
        raise CKPT1ReviewPackError("review pack cannot self-promote")
    if pack.get("pack_sha256") != canonical_sha256(_pack_without_hash(pack)):
        raise CKPT1ReviewPackError("review pack hash mismatch")
    items = pack.get("review_items")
    if not isinstance(items, list) or not items:
        raise CKPT1ReviewPackError("review pack requires claim-level review items")
    ids: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            raise CKPT1ReviewPackError("review item must be an object")
        item_id = item.get("item_id")
        if not isinstance(item_id, str) or not item_id or item_id in ids:
            raise CKPT1ReviewPackError("review item ids must be unique")
        ids.add(item_id)
        status = (item.get("resolution") or {}).get("status")
        if status not in RESOLUTION_STATUSES:
            raise CKPT1ReviewPackError(f"unsupported evidence status: {status}")
        review = item.get("review") or {}
        if review.get("decision") is not None or review.get("reviewer") is not None or review.get("reviewed_at") is not None:
            raise CKPT1ReviewPackError(f"review pack contains a prefilled human decision: {item_id}")
    inputs = pack.get("inputs") or {}
    stale_inputs: list[str] = []
    for name in ("source_pdf", "digest", "reading_view", "resolver_report"):
        entry = inputs.get(name) or {}
        path = Path(str(entry.get("path", "")))
        expected = entry.get("sha256")
        if not path.is_file():
            stale_inputs.append(f"{name}:missing")
        elif expected != sha256_file(path):
            stale_inputs.append(f"{name}:hash_mismatch")
    if current and stale_inputs:
        raise CKPT1ReviewPackError("review pack is stale: " + ", ".join(stale_inputs))
    return {"valid": True, "stale": bool(stale_inputs), "stale_inputs": stale_inputs,
            "review_items_total": len(items), "critical_items_total": sum(1 for item in items if item.get("critical")),
            "pack_sha256": pack.get("pack_sha256")}


def new_review_receipt(pack: Mapping[str, Any]) -> dict[str, Any]:
    """Create a receipt that explicitly has no human confirmation."""
    validate_review_pack(pack, current=False)
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "kind": "ckpt-1-human-review-receipt",
        "review_pack_id": pack["review_pack_id"],
        "paper": pack["paper"],
        "bound_inputs": deepcopy(pack["inputs"]),
        "review_pack_sha256": pack["pack_sha256"],
        "evidence_status_snapshot": deepcopy(pack["evidence_status_snapshot"]),
        "review_items": [
            {"item_id": item["item_id"], "resolution_status": item["resolution"]["status"],
             "decision": None, "comment": ""}
            for item in pack["review_items"]
        ],
        "review_status": "pending",
        "human_confirmation": {"received": False, "reviewer": None, "reviewed_at": None},
        "promotion_status": "WAITING_FOR_HUMAN_CKPT1",
        "evidence_status_immutable": True,
        "generated_at": _utc_now(),
    }


def _input_hashes(pack: Mapping[str, Any]) -> dict[str, str | None]:
    values: dict[str, str | None] = {}
    for name in ("source_pdf", "digest", "reading_view", "resolver_report"):
        entry = (pack.get("inputs") or {}).get(name) or {}
        path = Path(str(entry.get("path", "")))
        values[name] = sha256_file(path) if path.is_file() else None
    return values


def validate_review_receipt(receipt: Mapping[str, Any], pack: Mapping[str, Any], *, current: bool = True) -> dict[str, Any]:
    # A receipt validator must be able to return STALE_REVIEW after a source
    # change; do not raise before the hash comparison can report that state.
    validate_review_pack(pack, current=False)
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION or receipt.get("kind") != "ckpt-1-human-review-receipt":
        raise CKPT1ReviewPackError("unsupported human review receipt schema")
    if receipt.get("review_pack_id") != pack.get("review_pack_id"):
        raise CKPT1ReviewPackError("receipt is bound to a different review pack")
    stale: list[str] = []
    if receipt.get("review_pack_sha256") != pack.get("pack_sha256"):
        stale.append("review_pack_hash_changed")
    bound = receipt.get("bound_inputs") or {}
    actual = _input_hashes(pack)
    for name in ("source_pdf", "digest", "reading_view", "resolver_report"):
        expected = ((pack.get("inputs") or {}).get(name) or {}).get("sha256")
        recorded = (bound.get(name) or {}).get("sha256")
        if recorded != expected:
            stale.append(f"{name}:receipt_binding_mismatch")
        if actual.get(name) != expected:
            stale.append(f"{name}:source_changed")
    if receipt.get("evidence_status_snapshot") != pack.get("evidence_status_snapshot"):
        stale.append("evidence_status_snapshot_changed")
    item_map = {str(item.get("item_id")): item for item in receipt.get("review_items", []) or [] if isinstance(item, Mapping)}
    pack_items = {str(item["item_id"]): item for item in pack.get("review_items", [])}
    missing = [item_id for item_id in pack_items if item_id not in item_map]
    stale.extend(f"{item_id}:resolution_status_changed" for item_id, item in item_map.items()
                 if item_id in pack_items and item.get("resolution_status") != (pack_items[item_id].get("resolution") or {}).get("status"))
    invalid: list[str] = []
    for item_id, item in item_map.items():
        if item_id not in pack_items:
            invalid.append(f"{item_id}:unknown_item")
        if item.get("decision") is not None and item.get("decision") not in DECISIONS:
            invalid.append(item_id)
    confirmation = receipt.get("human_confirmation") or {}
    received = confirmation.get("received") is True
    if received and (not isinstance(confirmation.get("reviewer"), str) or not confirmation["reviewer"].strip()):
        invalid.append("human_confirmation.reviewer")
    if received and not isinstance(confirmation.get("reviewed_at"), str):
        invalid.append("human_confirmation.reviewed_at")
    return {
        "valid": not missing and not invalid,
        "stale": bool(stale),
        "stale_reasons": sorted(set(stale)),
        "missing_items": missing,
        "invalid_decisions": invalid,
        "human_confirmation_received": received,
        "review_items_total": len(pack.get("review_items", [])),
        "review_items_with_decisions": sum(1 for item in item_map.values() if item.get("decision") is not None),
    }


def evaluate_promotion(pack: Mapping[str, Any], receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Return a promotion receipt; source artifacts are never written."""
    check = validate_review_receipt(receipt, pack, current=True)
    result: dict[str, Any] = {
        "schema_version": PROMOTION_SCHEMA_VERSION,
        "kind": "ckpt-1-promotion-receipt",
        "review_pack_id": pack.get("review_pack_id"),
        "paper": pack.get("paper"),
        "bound_inputs": deepcopy(pack.get("inputs")),
        "review_pack_sha256": pack.get("pack_sha256"),
        "review_receipt_sha256": canonical_sha256(receipt),
        "evidence_status_immutable": True,
        "source_evidence_status_mutated": False,
        "before_verification_level": "tutor_only",
        "after_verification_level": "tutor_only",
        "generated_at": _utc_now(),
    }
    if check["stale"]:
        result.update({"promotion_status": "STALE_REVIEW", "promoted": False, "blocked_reasons": check["stale_reasons"]})
        return result
    if not check["valid"]:
        result.update({"promotion_status": "INVALID_REVIEW_RECEIPT", "promoted": False,
                       "blocked_reasons": check["missing_items"] + check["invalid_decisions"]})
        return result
    if not check["human_confirmation_received"]:
        result.update({"promotion_status": "WAITING_FOR_HUMAN_CKPT1", "promoted": False,
                       "blocked_reasons": ["human_confirmation_required"]})
        return result
    reviews = {str(item["item_id"]): item for item in receipt.get("review_items", [])}
    blockers: list[str] = []
    for item in pack.get("review_items", []):
        decision = (reviews.get(str(item["item_id"])) or {}).get("decision")
        status = (item.get("resolution") or {}).get("status")
        if decision is None:
            blockers.append(f"{item['item_id']}:decision_missing")
        elif decision in {"reject", "needs_fix"}:
            blockers.append(f"{item['item_id']}:{decision}")
        elif item.get("critical") and status in {"ambiguous", "unresolved"}:
            blockers.append(f"{item['item_id']}:{status}_critical_evidence")
        elif status in {"partial", "fuzzy"} and decision not in {"approve", "approve_as_partial"}:
            blockers.append(f"{item['item_id']}:{status}_requires_explicit_decision")
    if blockers:
        result.update({"promotion_status": "PROMOTION_BLOCKED", "promoted": False, "blocked_reasons": blockers})
        return result
    result.update({
        "promotion_status": "PROMOTED",
        "promoted": True,
        "blocked_reasons": [],
        "after_verification_level": "scholar_slides_validated",
        "downstream_unlocked": ["Formula", "Paper-Tutor Deep", "Learning Map integrated", "Phase 7.1 exact handoff"],
    })
    return result


def _json_script(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def _resolution_html(resolution: Mapping[str, Any]) -> str:
    rows: list[str] = []
    for value in resolution.get("resolutions", []) or []:
        evidence = value.get("evidence_span") or {}
        spans = evidence.get("spans") if isinstance(evidence, Mapping) else []
        if not isinstance(spans, list):
            spans = []
        span_text = " | ".join(_clean(item.get("text")) for item in spans if isinstance(item, Mapping))
        rows.append(
            "<div class='evidence-row'><code>" + html.escape(_clean(value.get("raw"))) + "</code> "
            + "<span class='status status-" + html.escape(_clean(value.get("status"))) + "'>" + html.escape(_clean(value.get("status"))) + "</span>"
            + " <span>PDF pages " + html.escape(", ".join(str(x) for x in value.get("pdf_page_indices", [])) or "—") + "</span>"
            + ((" <span class='span-text'>span: " + html.escape(span_text) + "</span>") if span_text else "")
            + ((" <span class='reason'>" + html.escape(", ".join(value.get("failure_reason_codes", []))) + "</span>") if value.get("failure_reason_codes") else "")
            + "</div>"
        )
    return "".join(rows) or "<div class='evidence-row'>No verified evidence reference</div>"


def _closeout_html(item: Mapping[str, Any]) -> str:
    """Render optional closeout repair/support metadata without changing the review protocol."""
    support = item.get("claim_support") if isinstance(item.get("claim_support"), Mapping) else None
    disposition = item.get("formula_disposition") if isinstance(item.get("formula_disposition"), Mapping) else None
    repair = item.get("closeout_repair") if isinstance(item.get("closeout_repair"), Mapping) else None
    if not support and not disposition and not repair:
        return ""
    bits: list[str] = ["<div class='closeout-box'><strong>Closeout source check</strong>"]
    if support:
        bits.append("<div><b>claim support:</b> " + html.escape(_clean(support.get("status"))) + " · " + html.escape(_clean(support.get("kind"))) + "</div>")
        source = support.get("source") if isinstance(support.get("source"), Mapping) else {}
        if source.get("locator"):
            bits.append("<div><b>source:</b> " + html.escape(_clean(source.get("locator"))) + "</div>")
        if source.get("quote"):
            bits.append("<blockquote>" + html.escape(_clean(source.get("quote"))) + "</blockquote>")
        if support.get("classification"):
            bits.append("<div><b>classification:</b> " + html.escape(_clean(support.get("classification"))) + "</div>")
        if support.get("note"):
            bits.append("<div class='reason'>" + html.escape(_clean(support.get("note"))) + "</div>")
    if disposition:
        bits.append("<div><b>formula disposition:</b> " + html.escape(_clean(disposition.get("status"))) + " · " + html.escape(_clean(disposition.get("action"))) + "</div>")
        if disposition.get("canonical"):
            bits.append("<div><b>canonical source form:</b> <code>" + html.escape(_clean(disposition.get("canonical"))) + "</code></div>")
        source = disposition.get("source") if isinstance(disposition.get("source"), Mapping) else {}
        if source.get("quote"):
            bits.append("<blockquote>" + html.escape(_clean(source.get("quote"))) + "</blockquote>")
        if disposition.get("duplicate_of_suffix"):
            bits.append("<div class='reason'>duplicate of " + html.escape(_clean(disposition.get("duplicate_of_suffix"))) + "; do not project twice</div>")
    if repair:
        bits.append("<div><b>repair action:</b> " + html.escape(_clean(repair.get("action"))) + " · human decision required</div>")
    bits.append("</div>")
    return "".join(bits)


def render_review_html(pack: Mapping[str, Any]) -> str:
    """Render an offline page with separate non-exact evidence groups."""
    validate_review_pack(pack, current=False)
    title = html.escape(_clean((pack.get("paper_identity") or {}).get("title")) or _clean(pack.get("paper")))
    items = pack.get("review_items", [])
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[str((item.get("resolution") or {}).get("status", "unresolved"))].append(item)
    sections: list[str] = []
    for status in ("partial", "fuzzy", "ambiguous", "unresolved", "normalized", "exact"):
        current = grouped.get(status, [])
        cards: list[str] = []
        for item in current:
            resolution = item.get("resolution") or {}
            options = "".join("<option value='" + html.escape(decision) + "'>" + html.escape(decision) + "</option>" for decision in item.get("allowed_decisions", DECISIONS))
            cards.append(
                "<article class='claim-card' data-status='" + html.escape(status) + "' data-item-id='" + html.escape(_clean(item.get("item_id"))) + "'>"
                + "<div class='claim-head'><span class='category'>" + html.escape(_clean(item.get("category"))) + "</span>"
                + "<span class='status status-" + html.escape(status) + "'>" + html.escape(status) + "</span>"
                + ("<span class='critical'>critical</span>" if item.get("critical") else "")
                + "</div><h3>" + html.escape(_clean(item.get("claim"))) + "</h3>"
                + "<div class='meta'><code>" + html.escape(_clean(item.get("item_id"))) + "</code> · importance: " + html.escape(_clean(item.get("importance"))) + "</div>"
                + "<div class='evidence'>" + _resolution_html(resolution) + "</div>"
                + _closeout_html(item)
                + "<label>Human decision <select data-decision><option value=''>pending</option>" + options + "</select></label>"
                + "<label>Comment <textarea data-comment rows='2' placeholder='Required for partial, fuzzy, ambiguous, unresolved, reject, or needs_fix'></textarea></label></article>"
            )
        if not cards:
            cards.append("<div class='notice'>No claims currently have this evidence status.</div>")
        sections.append("<section><h2>" + html.escape(status) + " evidence (" + str(len(current)) + ")</h2>" + "".join(cards) + "</section>")
    pack_json = _json_script(pack)
    source_hash = html.escape(_clean((pack.get("inputs") or {}).get("source_pdf", {}).get("sha256")))
    footer = (
        "Pack hash: <code>" + html.escape(_clean(pack.get("pack_sha256"))) + "</code><br>"
        "PDF: <code>" + source_hash + "</code><br>"
        "Digest: <code>" + html.escape(_clean((pack.get("inputs") or {}).get("digest", {}).get("sha256"))) + "</code><br>"
        "Reading-view: <code>" + html.escape(_clean((pack.get("inputs") or {}).get("reading_view", {}).get("sha256"))) + "</code><br>"
        "Resolver report: <code>" + html.escape(_clean((pack.get("inputs") or {}).get("resolver_report", {}).get("sha256"))) + "</code>"
    )
    return """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CKPT-1 Human Review · """ + title + """</title>
<style>
:root{color-scheme:light;--ink:#17202a;--muted:#5a6673;--line:#d9e0e7;--bg:#f6f8fb;--card:#fff;--accent:#155eef;--warn:#9a6700;--bad:#b42318;--good:#067647}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
header{background:#10233f;color:#fff;padding:28px 5vw}header h1{margin:0 0 8px;font-size:clamp(22px,3vw,34px)}header p{margin:4px 0;color:#dbe7fb}
main{max-width:1300px;margin:24px auto;padding:0 20px}section{margin:28px 0}h2{font-size:20px;margin:0 0 12px;text-transform:capitalize}h3{margin:8px 0;font-size:17px;line-height:1.35}
.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin:18px 0}.stat,.claim-card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;box-shadow:0 1px 2px #10233f0d}.stat strong{display:block;font-size:24px}
.claim-card{margin:12px 0}.claim-head{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.category{font-weight:700}.status,.critical{display:inline-block;border-radius:999px;padding:2px 8px;font-size:12px;font-weight:700}
.status-exact{background:#dcfae6;color:var(--good)}.status-normalized,.status-fuzzy{background:#e0ecff;color:#175cd3}.status-partial{background:#fff4cc;color:var(--warn)}.status-ambiguous,.status-unresolved{background:#fee4e2;color:var(--bad)}.critical{background:#1d2939;color:#fff}
.meta{color:var(--muted);font-size:12px}.evidence{margin:10px 0;padding:10px;background:#f8fafc;border-radius:8px}.evidence-row{padding:5px 0;border-bottom:1px solid #e7ecf1;font-size:13px}.evidence-row:last-child{border-bottom:0}.span-text{color:#344054}.reason{color:var(--bad)}.closeout-box{margin:10px 0;padding:10px 12px;background:#fffdf2;border:1px solid #f0d98a;border-radius:8px;font-size:13px}.closeout-box blockquote{margin:6px 0;padding-left:10px;border-left:3px solid #d9a441;color:#344054}.closeout-box code{white-space:pre-wrap}
label{display:block;margin-top:8px;font-weight:600}select,textarea{display:block;width:100%;margin-top:4px;padding:8px;border:1px solid #b8c2cc;border-radius:7px;font:inherit;background:#fff}.notice{border-left:4px solid var(--warn);padding:12px 14px;background:#fff8e1}footer{color:var(--muted);font-size:12px;margin:30px 0}
</style></head><body><header><h1>CKPT-1 Human Review</h1><p>""" + title + """</p><p><strong>WAITING_FOR_HUMAN_CKPT1</strong> · evidence status is source-bound and immutable</p></header>
<main><div class="notice">This page is an offline review surface. Selecting a decision does not promote the paper. A human reviewer must export and sign a receipt bound to all four input hashes.</div>
<div class="summary"><div class="stat"><strong>""" + str(len(items)) + """</strong>claim-level items</div><div class="stat"><strong>""" + str(sum(1 for item in items if item.get("critical"))) + """</strong>critical items</div><div class="stat"><strong>""" + str(pack.get("coverage", {}).get("evidence_span_verified", 0)) + """</strong>verified spans</div><div class="stat"><strong>""" + source_hash[:12] + """</strong>PDF hash prefix</div></div>
""" + "".join(sections) + """
<footer>""" + footer + """</footer></main><script id="review-pack" type="application/json">""" + pack_json + """</script><script>
const pack=JSON.parse(document.getElementById('review-pack').textContent);
document.querySelectorAll('[data-decision]').forEach(function(select){select.addEventListener('change',function(){document.title='CKPT-1 Human Review · draft decisions selected';});});
</script></body></html>
"""


def write_outputs(*, pack: Mapping[str, Any], out_dir: str | Path, prefix: str) -> dict[str, str]:
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    pack_path = out / f"{prefix}-ckpt1-review-pack.json"
    html_path = out / f"{prefix}-ckpt1-review.html"
    receipt_path = out / f"{prefix}-ckpt1-review.json"
    promotion_path = out / f"{prefix}-ckpt1-promotion-receipt.json"
    pack_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(render_review_html(pack), encoding="utf-8")
    receipt = new_review_receipt(pack)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    promotion_path.write_text(json.dumps(evaluate_promotion(pack, receipt), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Keep the paper-specific directory names exact for consumers that expect
    # the protocol's canonical ckpt-1 filenames.
    canonical_dir = out / prefix
    canonical_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pack_path, canonical_dir / "ckpt-1-review-pack.json")
    shutil.copyfile(html_path, canonical_dir / "ckpt-1-review.html")
    shutil.copyfile(receipt_path, canonical_dir / "ckpt-1-review.json")
    shutil.copyfile(promotion_path, canonical_dir / "ckpt-1-promotion-receipt.json")
    return {"pack": str(pack_path), "html": str(html_path), "review_receipt": str(receipt_path), "promotion_receipt": str(promotion_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 7.3 CKPT-1 human review pack and promotion gate")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--paper", required=True)
    build.add_argument("--reading-view", required=True)
    build.add_argument("--digest", required=True)
    build.add_argument("--resolver-report", required=True)
    build.add_argument("--out-dir", required=True)
    build.add_argument("--prefix")
    build.set_defaults(func=lambda args: _cli_build(args))
    validate = sub.add_parser("validate")
    validate.add_argument("--pack", required=True)
    validate.add_argument("--receipt")
    validate.add_argument("--allow-stale", action="store_true")
    validate.set_defaults(func=lambda args: _cli_validate(args))
    promote = sub.add_parser("promote")
    promote.add_argument("--pack", required=True)
    promote.add_argument("--receipt")
    promote.add_argument("--out")
    promote.set_defaults(func=lambda args: _cli_promote(args))
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except CKPT1ReviewPackError as exc:
        parser.error(str(exc))
        return 2


def _cli_build(args: argparse.Namespace) -> int:
    pack = build_review_pack(paper=args.paper, reading_view_path=args.reading_view,
                             digest_path=args.digest, resolver_report_path=args.resolver_report)
    paths = write_outputs(pack=pack, out_dir=args.out_dir, prefix=args.prefix or _slug(args.paper))
    print(json.dumps({"pack_sha256": pack["pack_sha256"], "outputs": paths}, ensure_ascii=False, indent=2))
    return 0


def _cli_validate(args: argparse.Namespace) -> int:
    pack = read_json(args.pack)
    result = validate_review_pack(pack, current=not args.allow_stale)
    if args.receipt:
        result["receipt"] = validate_review_receipt(read_json(args.receipt), pack, current=not args.allow_stale)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cli_promote(args: argparse.Namespace) -> int:
    pack = read_json(args.pack)
    receipt = read_json(args.receipt) if args.receipt else new_review_receipt(pack)
    result = evaluate_promotion(pack, receipt)
    if args.out:
        target = Path(args.out).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("promotion_status") == "PROMOTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
