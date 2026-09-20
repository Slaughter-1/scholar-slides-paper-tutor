#!/usr/bin/env python3
"""Integrity checks for the bounded CKPT-1 closeout deliverable."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "runtime" / "scripts"))
from ckpt1_review_pack import (  # noqa: E402
    canonical_sha256,
    read_json,
    sha256_file,
    validate_review_pack,
    validate_review_receipt,
)


def main() -> int:
    workdir = ROOT / "docs" / "ckpt1-closeout" / "2026-09-20T131625+0800"
    manifest = read_json(workdir / "repair-manifest.json")
    manifest_hash = sha256_file(workdir / "repair-manifest.json")
    checks: list[dict[str, object]] = []
    for paper in ("skillpyramid", "startupbench"):
        current = read_json(workdir / paper / "ckpt-1-review-pack.json")
        old = read_json(ROOT / "docs" / "phase7-3-human-review" / paper / "ckpt-1-review-pack.json")
        receipt = read_json(workdir / paper / "ckpt-1-human-review-receipt.json")
        promotion = read_json(workdir / paper / "ckpt-1-promotion-receipt.json")
        pack_check = validate_review_pack(current, current=True)
        receipt_check = validate_review_receipt(receipt, current, current=True)
        status_unchanged = current.get("evidence_status_snapshot") == old.get("evidence_status_snapshot")
        ids_unchanged = {x["item_id"] for x in current["review_items"]} == {x["item_id"] for x in old["review_items"]}
        no_decisions = all((x.get("review") or {}).get("decision") is None for x in current["review_items"])
        promotion_waiting = promotion.get("promotion_status") == "WAITING_FOR_HUMAN_CKPT1" and promotion.get("promoted") is False
        manifest_bound = current.get("closeout", {}).get("repair_manifest_sha256") == manifest_hash
        checks.append({
            "paper": paper,
            "pack_valid": pack_check.get("valid") is True,
            "receipt_valid": receipt_check.get("valid") is True,
            "receipt_current": receipt_check.get("stale") is False,
            "status_unchanged": status_unchanged,
            "stable_item_ids_unchanged": ids_unchanged,
            "human_decisions_empty": no_decisions,
            "promotion_waiting": promotion_waiting,
            "manifest_hash_bound": manifest_bound,
            "pack_sha256": current.get("pack_sha256"),
            "old_pack_sha256": old.get("pack_sha256"),
        })
    qa = read_json(workdir / "ckpt1-closeout-chromium-qa.json")
    output = {
        "schema_version": "phase7.3.ckpt1-closeout-integrity-qa.v1",
        "manifest_sha256": manifest_hash,
        "external_requests": qa.get("external_requests", 0),
        "chromium_qa_passed": qa.get("passed") is True,
        "papers": checks,
        "passed": qa.get("passed") is True and qa.get("external_requests", 0) == 0 and all(all(bool(v) for k, v in c.items() if k not in {"paper", "pack_sha256", "old_pack_sha256"}) for c in checks),
    }
    (workdir / "closeout-integrity-qa.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
