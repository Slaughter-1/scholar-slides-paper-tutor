#!/usr/bin/env python3
"""Apply the bounded, source-bound CKPT-1 closeout repair manifest.

This is a closeout data operation, not a new review or extraction platform. It
copies the existing Phase 7.3 packs, records old/new values and source quotes,
keeps resolver evidence statuses unchanged, and emits waiting-only receipts.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "runtime" / "scripts"))
from ckpt1_review_pack import (  # noqa: E402
    canonical_sha256,
    evaluate_promotion,
    new_review_receipt,
    read_json,
    render_review_html,
    validate_review_pack,
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def suffix_map(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get("item_id", "")).split(".")[-2] + "." + str(item.get("item_id", "")).split(".")[-1]: item for item in items}


def item_suffix(item_id: str) -> str:
    parts = item_id.split(".")
    return ".".join(parts[-3:]) if len(parts) >= 3 else ".".join(parts[-2:])


def lookup_repair(mapping: Mapping[str, Any], item_id: str) -> tuple[str, Any] | tuple[None, None]:
    parts = item_id.split(".")
    if ".formula." in item_id:
        candidates = [".".join(parts[-2:])]
    else:
        candidates = [".".join(parts[-3:]), ".".join(parts[-2:])] if len(parts) >= 3 else [".".join(parts[-2:])]
    for key in candidates:
        if key in mapping:
            return key, mapping[key]
    return None, None


def _source_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    source = deepcopy(record.get("source") or {})
    return {
        "status": record.get("support_status", "partial"),
        "kind": record.get("support_kind", "source_quote"),
        "source": source,
        "classification": record.get("classification", "closeout_source_check"),
        **({"note": record["note"]} if record.get("note") else {}),
        **({"duplicate_group": record["duplicate_group"]} if record.get("duplicate_group") else {}),
    }


def apply_paper(*, paper: str, old_pack_path: Path, manifest: Mapping[str, Any], out_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    old_pack = read_json(old_pack_path)
    pack = deepcopy(old_pack)
    spec = manifest["papers"][paper]
    item_repairs = spec.get("item_repairs", {})
    formula_repairs = spec.get("formula_repairs", {})
    diffs: list[dict[str, Any]] = []
    repaired_items = 0
    formula_count = 0
    caption_only = 0

    for item in pack.get("review_items", []):
        item_id = str(item.get("item_id", ""))
        suffix = ".".join(item_id.split(".")[-2:]) if ".formula." in item_id else item_suffix(item_id)
        before = deepcopy(item)
        matched_item_suffix, record = lookup_repair(item_repairs, item_id)
        if matched_item_suffix:
            suffix = matched_item_suffix
        if record is not None:
            if record.get("new_claim"):
                item["claim"] = record["new_claim"]
            item["claim_support"] = _source_payload(record)
            item["closeout_repair"] = {
                "action": record.get("action"),
                "human_decision_required": True,
                "old_claim": before.get("claim"),
                "new_claim": item.get("claim"),
                "source_bound": True,
            }
            repaired_items += 1
        elif str(item.get("category")) in {"Figure", "Table"}:
            # A caption identifies an asset but cannot substantiate a numeric or
            # methodological claim. Preserve this finding for human review.
            item["claim_support"] = {
                "status": "partial",
                "kind": "caption_only_asset_identity",
                "source": {"locator": item.get("locator"), "quote": item.get("claim")},
                "classification": "caption_or_header_only",
                "note": "Caption/title is retained as asset identity; substantive support must be checked against the rendered asset or surrounding paragraph.",
            }
            caption_only += 1

        if suffix.startswith("formula."):
            _, formula = lookup_repair(formula_repairs, item_id)
            if formula is not None:
                canonical = str(formula.get("canonical", "")).strip()
                item["claim"] = f"Formula pre-gate candidate (source-bound): {canonical}"
                item["formula_disposition"] = {
                    "status": "duplicate_not_projected" if formula.get("action") == "mark_duplicate_no_projection" else "source_verified_candidate",
                    "action": formula.get("action"),
                    "canonical": canonical,
                    "source": deepcopy(formula.get("source") or {}),
                    "human_decision_required": True,
                    **({"duplicate_of_suffix": formula["duplicate_of_suffix"]} if formula.get("duplicate_of_suffix") else {}),
                    **({"verification_mode": formula["verification_mode"]} if formula.get("verification_mode") else {}),
                }
                item["closeout_repair"] = {
                    "action": formula.get("action"),
                    "human_decision_required": True,
                    "old_claim": before.get("claim"),
                    "new_claim": item.get("claim"),
                    "source_bound": True,
                }
                diffs.append({"item_id": item["item_id"], "kind": "formula", "old": before.get("claim"), "new": item.get("claim"), "disposition": deepcopy(item["formula_disposition"])})
                formula_count += 1
                continue

        if record is not None:
            diffs.append({"item_id": item["item_id"], "kind": "claim", "old": before.get("claim"), "new": item.get("claim"), "repair": deepcopy(item.get("closeout_repair")), "support": deepcopy(item.get("claim_support"))})

    # The evidence resolver snapshot is deliberately unchanged. The closeout
    # layer is an auditable correction to claim/formula material only.
    pack["closeout"] = {
        "schema_version": "phase7.3.ckpt1-closeout.v1",
        "state": "WAITING_FOR_HUMAN_CKPT1",
        "repair_manifest_sha256": sha256_file(ROOT / "docs" / "ckpt1-closeout" / "2026-09-20T131625+0800" / "repair-manifest.json"),
        "raw_inputs_unchanged": True,
        "evidence_status_mutated": False,
        "human_confirmation_required": True,
        "claim_repairs": repaired_items,
        "formula_repairs": formula_count,
        "caption_only_assets_flagged": caption_only,
        "promotion_allowed": False,
    }
    pack["coverage"]["closeout_claim_support_counts"] = {
        "source_bound_repairs": repaired_items,
        "caption_or_header_only_assets": caption_only,
        "formula_candidates_with_disposition": formula_count,
    }
    pack["pack_sha256"] = canonical_sha256({k: v for k, v in pack.items() if k != "pack_sha256"})
    validate_review_pack(pack, current=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ckpt-1-review-pack.json").write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "ckpt-1-review.html").write_text(render_review_html(pack), encoding="utf-8")
    receipt = new_review_receipt(pack)
    (out_dir / "ckpt-1-human-review-receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    promotion = evaluate_promotion(pack, receipt)
    (out_dir / "ckpt-1-promotion-receipt.json").write_text(json.dumps(promotion, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return pack, {"paper": paper, "old_pack_sha256": old_pack.get("pack_sha256"), "new_pack_sha256": pack.get("pack_sha256"), "diffs": diffs, "promotion": promotion}


def main() -> int:
    workdir = ROOT / "docs" / "ckpt1-closeout" / "2026-09-20T131625+0800"
    manifest_path = workdir / "repair-manifest.json"
    manifest = read_json(manifest_path)
    results: list[dict[str, Any]] = []
    for paper in ("skillpyramid", "startupbench"):
        pack, result = apply_paper(
            paper=paper,
            old_pack_path=ROOT / "docs" / "phase7-3-human-review" / paper / "ckpt-1-review-pack.json",
            manifest=manifest,
            out_dir=workdir / paper,
        )
        results.append(result)
    diff = {
        "schema_version": "phase7.3.ckpt1-closeout-repair-diff.v1",
        "state": "WAITING_FOR_HUMAN_CKPT1",
        "raw_inputs_unchanged": True,
        "evidence_status_mutated": False,
        "external_requests": 0,
        "papers": results,
    }
    (workdir / "repair-diff.json").write_text(json.dumps(diff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"workdir": str(workdir), "papers": [{"paper": r["paper"], "pack_sha256": r["new_pack_sha256"], "promotion_status": r["promotion"].get("promotion_status")} for r in results]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
