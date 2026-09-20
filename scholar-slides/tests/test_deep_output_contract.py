from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "paper-learning-map" / "runtime"
sys.path.insert(0, str(RUNTIME))

from paper_tutor_projector import project_files  # noqa: E402


SWE_MAP = ROOT / "docs" / "e2e-validation" / "verified-fresh" / "swe-touch" / "learning-map-rc1-verified"
SWE_SCHOLAR = ROOT / "docs" / "e2e-validation" / "verified-fresh" / "swe-touch" / "scholar"
REASONING_MAP = ROOT / "paper-learning-map" / "fixtures" / "Reasoning-Table" / "output"
REASONING_SCHOLAR = ROOT / "docs" / "validation-candidates" / "Reasoning-Table"
FINAL_DELIVERY = ROOT / "docs" / "ckpt1-closeout" / "2026-09-20T131625+0800" / "final-delivery"
SKILLPYRAMID_MAP = FINAL_DELIVERY / "skillpyramid" / "map"
SKILLPYRAMID_SCHOLAR = FINAL_DELIVERY / "skillpyramid" / "scholar"
STARTUPBENCH_MAP = FINAL_DELIVERY / "startupbench" / "map"
STARTUPBENCH_SCHOLAR = FINAL_DELIVERY / "startupbench" / "scholar"


def _render(map_project: Path, scholar_project: Path, root: Path) -> tuple[str, str, dict]:
    compact_path = root / "paper-tutor-compact.md"
    deep_path = root / "paper-tutor-deep-v2.md"
    coverage_path = root / "paper-tutor-coverage.json"
    report = project_files(map_project, scholar_project, compact_path, deep_path, coverage_path)
    return compact_path.read_text(encoding="utf-8"), deep_path.read_text(encoding="utf-8"), report


class DeepOutputContractTests(unittest.TestCase):
    @unittest.skipUnless(SWE_MAP.is_dir() and SWE_SCHOLAR.is_dir(), "requires generated SWE-Touch validation artifacts")
    def test_swe_touch_compact_deep_and_benchmark_contract(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            compact, deep, report = _render(SWE_MAP, SWE_SCHOLAR, Path(raw))
        self.assertNotEqual(compact, deep)
        self.assertGreater(len(deep), len(compact) * 2)
        self.assertNotIn("### Formula:", compact)
        self.assertNotIn("### Experiment:", compact)
        for heading in (
            "## Benchmark Card（Overview Index）",
            "## Task → Input / Output Map",
            "## Problem & Motivation",
            "## Research Gap",
            "## Capability Under Test",
            "## Counter-Edit Deep Dive",
            "## Experimental Setup",
            "## Experiments",
            "## Main Results",
            "## Scaling",
            "## Failure Analysis",
            "## Validity",
            "## Limitations",
            "## Research Perspective",
            "## Full Argument Chain",
            "## Verification Questions",
            "## Claim → Evidence Appendix",
        ):
            self.assertIn(heading, deep)
        for token in ("Critical Region Mining", "Counter-Edit Generation", "Three Validation Conditions", "Injection Mechanism", "VF(R−)=0"):
            self.assertIn(token, deep)
        self.assertEqual(report["high_importance_represented"], report["high_importance_total"])
        self.assertEqual(report["represented_items"], report["total_items"])
        self.assertGreaterEqual(report["formula_blocks"], 1)
        self.assertGreaterEqual(report["experiment_blocks"], 4)
        self.assertIn("| Claim | Source | Page | Section | Figure/Table | Evidence ID |", deep)

    @unittest.skipUnless(REASONING_SCHOLAR.is_dir(), "requires generated Reasoning-Table validation artifacts")
    def test_reasoning_table_method_contract_and_tutor_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            compact, deep, report = _render(REASONING_MAP, REASONING_SCHOLAR, Path(raw))
        for heading in (
            "## Problem & Setting",
            "## Research Gap",
            "## Core Insight",
            "## Overall Pipeline",
            "## Components",
            "## Training Objective",
            "## Formula Blocks",
            "## Experiments",
            "## Ablation",
            "## Robustness",
            "## Limitations & Boundary",
            "## Research Perspective",
            "## Full Argument Chain",
            "## Verification Questions",
            "## Claim → Evidence Appendix",
        ):
            self.assertIn(heading, deep)
        for token in ("Reason-SFT", "RL-zero", "GRPO", "Position Reward", "No-Reason SFT", "Reason-SFT+RL", "Original Formula", "Mathematical Meaning", "Misunderstanding"):
            self.assertIn(token, deep)
        self.assertGreaterEqual(report["formula_blocks"], 2)
        self.assertGreaterEqual(report["experiment_blocks"], 5)
        self.assertEqual(report["high_importance_represented"], report["high_importance_total"])
        self.assertEqual(report["represented_items"], report["total_items"])
        self.assertGreater(len(deep), len(compact) * 2)

    @unittest.skipUnless(SWE_MAP.is_dir() and SWE_SCHOLAR.is_dir(), "requires generated SWE-Touch validation artifacts")
    def test_no_empty_or_duplicate_major_headings(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _, deep, _ = _render(SWE_MAP, SWE_SCHOLAR, Path(raw))
        headings = re.findall(r"^(## .+)$", deep, flags=re.MULTILINE)
        self.assertTrue(headings)
        self.assertEqual(len(headings), len(set(headings)))
        self.assertIsNone(re.search(r"^## [^\n]+\n(?:[ \t]*\n)*(?=## [^#]|\Z)", deep, flags=re.MULTILINE))

    @unittest.skipUnless(REASONING_SCHOLAR.is_dir(), "requires generated Reasoning-Table validation artifacts")
    def test_unverified_source_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            map_project = root / "map"
            scholar_project = root / "scholar"
            shutil.copytree(REASONING_MAP, map_project)
            shutil.copytree(REASONING_SCHOLAR, scholar_project)
            paper_map_path = map_project / "paper-map.json"
            paper_map = json.loads(paper_map_path.read_text(encoding="utf-8"))
            paper_map["source"]["verification_level"] = "tutor_only"
            paper_map_path.write_text(json.dumps(paper_map, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValueError):
                _render(map_project, scholar_project, root / "out")

    @unittest.skipUnless(SKILLPYRAMID_MAP.is_dir() and SKILLPYRAMID_SCHOLAR.is_dir(), "requires generated CKPT-1 closeout artifacts")
    def test_skillpyramid_deep_is_source_bound_and_projects_reviewed_formulas(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _, deep, report = _render(SKILLPYRAMID_MAP, SKILLPYRAMID_SCHOLAR, Path(raw))
        self.assertEqual(report["formula_blocks"], 13)
        self.assertEqual(len(re.findall(r"^### Formula:", deep, flags=re.MULTILINE)), 13)
        self.assertEqual(deep.count("#### Role in This Paper"), 13)
        for leaked in ("Co-Edit", "Counter-Edit", "K=1/3/5", "GRPO", "非 SQL 任务"):
            self.assertNotIn(leaked, deep)
        self.assertIn("## Transfer / Generalization", deep)
        self.assertIn("Source method evidence 3", deep)
        self.assertIn("Mode: Integrated", deep)
        self.assertIn("Evidence source：approved evidence, quantitative, figure/table, and CKPT-1 artifacts", deep)
        self.assertIn("Depth: deep", deep)

    @unittest.skipUnless(STARTUPBENCH_MAP.is_dir() and STARTUPBENCH_SCHOLAR.is_dir(), "requires generated CKPT-1 closeout artifacts")
    def test_startupbench_deep_uses_available_evidence_and_projects_formulas(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _, deep, report = _render(STARTUPBENCH_MAP, STARTUPBENCH_SCHOLAR, Path(raw))
        self.assertEqual(report["formula_blocks"], 4)
        self.assertEqual(len(re.findall(r"^### Formula:", deep, flags=re.MULTILINE)), 4)
        self.assertEqual(deep.count("#### Role in This Paper"), 4)
        self.assertNotIn("evidence.block_3", deep)
        self.assertNotIn("evidence.block_4", deep)
        setup = deep.split("## Experimental Setup", 1)[1].split("## Experiments", 1)[0]
        self.assertNotIn("Not verifiable from available evidence.", setup)
        self.assertIn("模型能否可靠完成完整工作？", deep)
        self.assertIn("Agent 框架是否改变总体结论？", deep)
        self.assertIn("Mode: Integrated", deep)
        self.assertIn("Depth: deep", deep)


if __name__ == "__main__":
    unittest.main()
