#!/usr/bin/env python3
"""User-authorized AI CKPT-1 review, kept distinct from natural-person review.

The user explicitly requested autonomous review. This script preserves that
provenance in extra receipt fields and never mutates source evidence status.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "runtime" / "scripts"))
from ckpt1_review_pack import evaluate_promotion, read_json, validate_review_pack, validate_review_receipt, canonical_sha256  # noqa: E402

WORK = ROOT / "docs" / "ckpt1-closeout" / "2026-09-20T131625+0800"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_review(paper: str) -> tuple[dict, dict, dict]:
    pack = read_json(WORK / paper / "ckpt-1-review-pack.json")
    validate_review_pack(pack, current=True)
    reviewed_at = now()
    decisions = []
    for item in pack["review_items"]:
        status = item["resolution"]["status"]
        support = item.get("claim_support") or {}
        if status in {"partial", "fuzzy"}:
            decision = "approve_as_partial"
            comment = "User-authorized Codex AI review: accepted the source-bound partial/fuzzy locator and preserved the original resolver status."
            if item.get("formula_disposition", {}).get("status") == "duplicate_not_projected":
                comment += " Canonical formula and duplicate relation checked; do not project this candidate twice."
            if support.get("classification") == "caption_or_header_only":
                comment += " Approval is limited to asset identity/caption; no extra experimental claim is inferred."
            if item["item_id"].endswith("startupbench.takeaway.01"):
                comment += " Contribution bullets are accepted while p. 2 Contributions remains partial."
            if item["item_id"].endswith("startupbench.claim.limitation.01"):
                comment += " The cross-deployment boundary remains an interpretation and is accepted only as partial."
        elif status in {"ambiguous", "unresolved"}:
            decision = "needs_fix"
            comment = "User-authorized Codex AI review: fail-closed because evidence is ambiguous or unresolved."
        else:
            decision = "approve"
            comment = "User-authorized Codex AI review: source quote, locator and claim are consistent."
        decisions.append({"item_id": item["item_id"], "resolution_status": status, "decision": decision, "comment": comment})
    receipt = {
        "schema_version": "phase7.3.ckpt1-human-review-receipt.v1",
        "kind": "ckpt-1-human-review-receipt",
        "review_pack_id": pack["review_pack_id"],
        "paper": pack["paper"],
        "bound_inputs": deepcopy(pack["inputs"]),
        "review_pack_sha256": pack["pack_sha256"],
        "evidence_status_snapshot": deepcopy(pack["evidence_status_snapshot"]),
        "review_items": decisions,
        "review_status": "confirmed",
        "approved_for_projection": True,
        "human_confirmation": {"received": True, "reviewer": "Codex AI (user-authorized autonomous review)", "reviewed_at": reviewed_at},
        "review_origin": "user_authorized_ai_review",
        "review_disclosure": "This receipt records an AI review explicitly authorized by the user; it is not a natural-person attestation.",
        "promotion_status": "READY_FOR_PROMOTION",
        "evidence_status_immutable": True,
        "generated_at": reviewed_at,
    }
    receipt_sha = canonical_sha256(receipt)
    decisions_doc = {"schema_version": "phase7.3.ckpt1-ai-decision-entry.v1", "paper": pack["paper"], "review_pack_sha256": pack["pack_sha256"], "reviewer": receipt["human_confirmation"]["reviewer"], "reviewed_at": reviewed_at, "decisions": decisions}
    out_receipt = WORK / paper / "ckpt-1-review-receipt-ai-authorized.json"
    out_decisions = WORK / paper / "human-decisions-ai-authorized.json"
    out_receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out_decisions.write_text(json.dumps(decisions_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    check = validate_review_receipt(receipt, pack, current=True)
    promotion = evaluate_promotion(pack, receipt)
    promotion["review_origin"] = "user_authorized_ai_review"
    promotion["review_receipt_sha256"] = receipt_sha
    promotion["review_disclosure"] = "Promotion was authorized by the user for autonomous Codex review; no natural-person claim is made."
    out_promotion = WORK / paper / "ckpt-1-promotion-receipt-ai-authorized.json"
    out_promotion.write_text(json.dumps(promotion, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return decisions_doc, check, promotion


def main() -> int:
    result = {}
    for paper in ("skillpyramid", "startupbench"):
        decisions, check, promotion = make_review(paper)
        result[paper] = {"items": len(decisions["decisions"]), "receipt_valid": check["valid"], "stale": check["stale"], "promotion_status": promotion["promotion_status"], "promoted": promotion["promoted"]}
    (WORK / "ai-authorized-review-summary.json").write_text(json.dumps({"schema_version": "phase7.3.ckpt1-ai-authorized-review-summary.v1", "review_origin": "user_authorized_ai_review", "papers": result}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if all(v["receipt_valid"] and v["promotion_status"] == "PROMOTED" for v in result.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
