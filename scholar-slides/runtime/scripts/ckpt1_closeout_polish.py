#!/usr/bin/env python3
"""Last bounded CKPT-1 review-pack polish; no extraction or formula changes."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "runtime" / "scripts"))
from ckpt1_review_pack import canonical_sha256, evaluate_promotion, new_review_receipt, read_json, render_review_html, validate_review_pack  # noqa: E402

WORK = ROOT / "docs" / "ckpt1-closeout" / "2026-09-20T131625+0800"

PATCHES = {
    "skillpyramid": {
        "claim.gap.01": {
            "claim": "This motivates a different perspective: a growing, structured skill library in which the experience captured by existing skills generalizes effectively to tasks beyond their original scope.",
            "support": {"status": "exact", "kind": "paragraph_sentence", "classification": "closeout_source_check", "source": {"pdf_page_index": 1, "printed_page_label": "2", "source_page_reference": 2, "locator": "p. 2, Introduction", "quote": "This motivates a different perspective: a growing, structured skill library in which the experience captured by existing skills generalizes effectively to tasks beyond their original scope."}},
        },
        "claim.core-idea.01": {
            "claim": "To this end, we construct a pyramidal, reusable, and continuously evolving skill system, where successful skills serve as reusable building blocks for related tasks rather than isolated modules.",
            "support": {"status": "exact", "kind": "method_paragraph", "classification": "closeout_source_check", "source": {"pdf_page_index": 1, "printed_page_label": "2", "source_page_reference": 2, "locator": "p. 2, Method", "quote": "To this end, we construct a pyramidal, reusable, and continuously evolving skill system, where successful skills serve as reusable building blocks for related tasks rather than isolated modules."}},
        },
        "method.03": {
            "claim": "To examine whether SKILLPYRAMID remains useful beyond benchmark-specific skill libraries, we evaluate web-mined skills on GAIA-Lite, a lightweight 75-task subset sampled from the public validation split of GAIA (Mialon et al., 2024).",
            "support": {"status": "exact", "kind": "result_method_paragraph", "classification": "resolver_gap", "source": {"pdf_page_index": 7, "printed_page_label": "8", "source_page_reference": 8, "locator": "p. 8, Pyramidal Consolidation Improves Web-Mined Skills", "quote": "To examine whether SKILLPYRAMID remains useful beyond benchmark-specific skill libraries, we evaluate web-mined skills on GAIA-Lite, a lightweight 75-task subset sampled from the public validation split of GAIA (Mialon et al., 2024)."}},
        },
    },
    "startupbench": {
        "claim.problem.01": {
            "support": {"status": "normalized", "kind": "abstract_and_introduction", "classification": "closeout_source_check", "source": {"pdf_page_index": 0, "printed_page_label": "1", "source_page_reference": 1, "locator": "p. 1, Abstract/Introduction", "quote": "Existing benchmarks largely rely on researcher-selected tasks, leaving uncertain whether such progress extends to the work that real-world users actually demand from AI systems."}},
        },
        "claim.gap.01": {
            "support": {"status": "normalized", "kind": "introduction_paragraph", "classification": "closeout_source_check", "source": {"pdf_page_index": 0, "printed_page_label": "1", "source_page_reference": 1, "locator": "p. 1, Introduction", "quote": "Many benchmark tasks are still largely defined from researchers' perspectives... evaluation protocols are often substantially coarser than the deliverables themselves. Real-world work products typically involve numerous functional, structural, formatting, and domain-specific requirements that holistic evaluations cannot faithfully assess."}},
        },
        "claim.core-idea.01": {
            "support": {"status": "normalized", "kind": "design_principles", "classification": "closeout_source_check", "source": {"pdf_page_index": 1, "printed_page_label": "2", "source_page_reference": 2, "locator": "p. 2, Introduction", "quote": "AI-native startups offer a natural source of real-world AI workflows: their products have been validated through real-world adoption and commercial demand... We therefore introduce StartupBench, a survey- and interview-driven benchmark that draws on these workflows to capture realistic E2E user requirements across domains."}},
        },
        "claim.core-idea.02": {
            "support": {"status": "normalized", "kind": "task_and_evaluation_protocol", "classification": "closeout_source_check", "source": {"pdf_page_index": 5, "printed_page_label": "6", "source_page_reference": 6, "locator": "p. 6, §3.3", "quote": "Every task is evaluated using fine-grained rubrics... Each rubric item is evaluated independently through a dedicated AgentJudge session... The final task score is then obtained by aggregating the outcomes of all rubric-level evaluations."}},
        },
    },
}


def main() -> int:
    diff = {"schema_version": "phase7.3.ckpt1-review-pack-polish-diff.v1", "state": "READY_FOR_HUMAN_CKPT1", "formula_extraction_rerun": False, "human_decisions_written": False, "papers": []}
    for paper, patches in PATCHES.items():
        path = WORK / paper / "ckpt-1-review-pack.json"
        pack = read_json(path)
        old_hash = pack["pack_sha256"]
        entries = []
        for item in pack["review_items"]:
            item_id = str(item["item_id"])
            suffix = next((key for key in patches if item_id.endswith("." + key)), None)
            record = patches.get(suffix) if suffix else None
            if not record:
                continue
            old_claim = item.get("claim")
            if record.get("claim"):
                item["claim"] = record["claim"]
            item["claim_support"] = deepcopy(record["support"])
            item.setdefault("closeout_repair", {})
            item["closeout_repair"].update({"action": "final_review_pack_polish", "human_decision_required": True, "old_claim": old_claim, "new_claim": item["claim"], "source_bound": True})
            entries.append({"item_id": item["item_id"], "old_claim": old_claim, "new_claim": item["claim"], "support": deepcopy(item["claim_support"])})
        pack["closeout"]["state"] = "READY_FOR_HUMAN_CKPT1"
        pack["closeout"]["final_polish"] = {"formula_extraction_rerun": False, "human_decisions_written": False, "critical_items_scanned": True, "polish_entries": len(entries)}
        pack["pack_sha256"] = canonical_sha256({k: v for k, v in pack.items() if k != "pack_sha256"})
        validate_review_pack(pack, current=True)
        path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (WORK / paper / "ckpt-1-review.html").write_text(render_review_html(pack), encoding="utf-8")
        receipt = new_review_receipt(pack)
        (WORK / paper / "ckpt-1-human-review-receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        promotion = evaluate_promotion(pack, receipt)
        (WORK / paper / "ckpt-1-promotion-receipt.json").write_text(json.dumps(promotion, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        diff["papers"].append({"paper": paper, "old_pack_sha256": old_hash, "new_pack_sha256": pack["pack_sha256"], "entries": entries})
    (WORK / "polish-diff.json").write_text(json.dumps(diff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(diff, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
