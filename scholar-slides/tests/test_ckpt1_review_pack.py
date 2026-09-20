from __future__ import annotations

import sys
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime" / "scripts"))
from ckpt1_review_pack import (  # noqa: E402
    SCHEMA_VERSION,
    canonical_sha256,
    evaluate_promotion,
    new_review_receipt,
    sha256_file,
    validate_review_receipt,
)


class CKPT1ReviewPackTests(unittest.TestCase):
    def make_pack(self, root: Path, *, status: str = "exact", critical: bool = True) -> dict:
        paths = {}
        for name in ("source_pdf", "digest", "reading_view", "resolver_report"):
            path = root / f"{name}.bin"
            path.write_bytes((name + "-source").encode("utf-8"))
            paths[name] = path
        item = {
            "item_id": "paper.claim.problem.01",
            "category": "Problem",
            "claim": "A source-bound claim",
            "critical": critical,
            "resolution": {"status": status, "evidence_span_verified": True},
            "review": {"decision": None, "comment": "", "reviewer": None, "reviewed_at": None},
        }
        pack = {
            "schema_version": SCHEMA_VERSION,
            "kind": "ckpt-1-review-pack",
            "review_pack_id": "paper-ckpt1-review-pack",
            "paper": "Paper",
            "paper_identity": {"title": "Paper", "source_pdf_sha256": sha256_file(paths["source_pdf"])},
            "inputs": {name: {"path": str(path), "sha256": sha256_file(path)} for name, path in paths.items()},
            "review_protocol": {
                "state": "WAITING_FOR_HUMAN_CKPT1",
                "human_confirmation_required": True,
                "evidence_status_immutable": True,
                "stale_when_any_input_hash_changes": True,
            },
            "review_items": [item],
            "coverage": {"review_items_total": 1, "status_counts": {status: 1}, "non_exact_groups": {}},
            "promotion_status": "WAITING_FOR_HUMAN_CKPT1",
            "evidence_status_snapshot": {item["item_id"]: status},
        }
        pack["pack_sha256"] = canonical_sha256(pack)
        return pack

    def human_receipt(self, pack: dict, decision: str = "approve") -> dict:
        receipt = new_review_receipt(pack)
        receipt["review_items"][0]["decision"] = decision
        receipt["human_confirmation"] = {
            "received": True,
            "reviewer": "human@example.test",
            "reviewed_at": "2026-09-20T04:00:00Z",
        }
        receipt["review_status"] = "ready_for_promotion"
        return receipt

    def test_pending_receipt_waits_without_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            pack = self.make_pack(Path(value))
            result = evaluate_promotion(pack, new_review_receipt(pack))
            self.assertEqual(result["promotion_status"], "WAITING_FOR_HUMAN_CKPT1")
            self.assertFalse(result["promoted"])
            self.assertFalse(result["source_evidence_status_mutated"])

    def test_source_change_marks_receipt_stale(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            pack = self.make_pack(root)
            receipt = new_review_receipt(pack)
            (root / "digest.bin").write_bytes(b"changed")
            result = evaluate_promotion(pack, receipt)
            self.assertEqual(result["promotion_status"], "STALE_REVIEW")
            self.assertTrue(any("digest" in reason for reason in result["blocked_reasons"]))

    def test_ambiguous_critical_evidence_blocks_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            pack = self.make_pack(Path(value), status="ambiguous", critical=True)
            result = evaluate_promotion(pack, self.human_receipt(pack))
            self.assertEqual(result["promotion_status"], "PROMOTION_BLOCKED")
            self.assertTrue(any("ambiguous_critical_evidence" in reason for reason in result["blocked_reasons"]))

    def test_valid_partial_human_receipt_does_not_mutate_status(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            pack = self.make_pack(Path(value), status="partial", critical=False)
            receipt = self.human_receipt(pack, "approve_as_partial")
            result = evaluate_promotion(pack, receipt)
            self.assertEqual(result["promotion_status"], "PROMOTED")
            self.assertTrue(result["promoted"])
            self.assertFalse(result["source_evidence_status_mutated"])
            self.assertEqual(pack["evidence_status_snapshot"], {"paper.claim.problem.01": "partial"})
            self.assertFalse(validate_review_receipt(receipt, pack)["stale"])

    def test_receipt_binds_all_four_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            pack = self.make_pack(Path(value))
            receipt = new_review_receipt(pack)
            self.assertEqual(set(receipt["bound_inputs"]), {"source_pdf", "digest", "reading_view", "resolver_report"})
            self.assertEqual(receipt["review_pack_sha256"], pack["pack_sha256"])
            self.assertFalse(receipt["human_confirmation"]["received"])


if __name__ == "__main__":
    unittest.main()

