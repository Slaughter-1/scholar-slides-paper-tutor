from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime" / "scripts"))

from user_documents import render_reading_analysis, write_paper_analysis  # noqa: E402


def _write_pdf(path: Path) -> None:
    document = pymupdf.open()
    for label in ("Introduction", "Method", "Results", "Table 1"):
        page = document.new_page()
        page.insert_text((72, 72), label)
    document.save(path)
    document.close()


def _record(content: str, claim_type: str = "paper_fact") -> dict:
    return {
        "content": content,
        "claim_type": claim_type,
        "availability": "supported",
        "evidence_refs": ["p. 1, Introduction"],
    }


def _reading_view(pdf_sha: str) -> dict:
    return {
        "schema_version": 1,
        "paper_identity": {"title": "Readable Paper", "source_pdf_sha256": pdf_sha},
        "source_bindings": [{"path": "source.pdf", "sha256": pdf_sha}],
        "language": "zh-CN",
        "paper_type": {"kind": "method", "reason": "Method paper."},
        "overview": {
            "problem": _record("旧方法无法稳定解决问题。"),
            "gap": _record("现有方法缺少可靠的验证。"),
            "approach": _record("本文增加验证步骤。"),
            "insight": _record("本文把缺口转成可检验的验证步骤。", "analysis"),
            "findings": _record("实验中指标从 70 提升到 75。"),
            "boundary": _record("只支持当前测试条件。", "analysis"),
        },
        "mechanism_steps": [{
            "title": "验证输入",
            "purpose": "检查输入。",
            "input": "原始输入",
            "output": "已检查输入",
            "necessity": "后续模块依赖这个结果。",
            "claim_type": "paper_fact",
            "availability": "supported",
            "evidence_refs": ["p. 2, Method"],
        }],
        "argument_chain": [{
            "node": "研究缺口",
            "relation": "导致",
            "claim_type": "paper_fact",
            "availability": "supported",
            "evidence_refs": ["p. 1, Introduction"],
        }],
        "decisive_evidence": [{
            "question": "方法是否有效？",
            "comparison": "方法与 baseline",
            "metric": "F1",
            "result": "75 vs 70",
            "can_support": "当前数据集上效果更好。",
            "cannot_support": "不能证明跨域泛化。",
            "claim_type": "paper_fact",
            "availability": "supported",
            "evidence_refs": ["p. 4, Table 1"],
        }],
        "terms": [{
            "term": "baseline",
            "plain": "用来比较的新方法之外的参照系统。",
            "role": "作为效果比较的参照。",
            "confusions": "不等于论文提出的方法。",
            "claim_type": "explanation",
            "availability": "supported",
            "evidence_refs": ["p. 4, Table 1"],
        }],
        "takeaways": [{
            "kind": "author_contribution",
            "content": "增加验证步骤。",
            "claim_type": "paper_fact",
            "availability": "supported",
            "evidence_refs": ["p. 2, Method"],
        }],
    }


class ReadingDocumentTests(unittest.TestCase):
    def test_new_view_render_has_mainline_steps_terms_and_argument_chain(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            source = project / "source.pdf"
            _write_pdf(source)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            output = render_reading_analysis(_reading_view(digest), ckpt1_status="pending_human_confirmation")
            self.assertIn("CKPT-1 待人工确认", output)
            self.assertIn("## 1. 30 秒看懂", output)
            self.assertIn("## 3. 它具体怎么做", output)
            self.assertIn("## 5. 作者如何组织论证", output)
            self.assertIn("baseline", output)
            self.assertIn("75 vs 70", output)
            self.assertNotIn("保留论文原文术语，结合对应方法或实验语境理解", output)

    def test_term_claim_status_is_visible_in_render(self) -> None:
        source = Path(tempfile.gettempdir()) / "reading-view-term-status.pdf"
        _write_pdf(source)
        try:
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            view = _reading_view(digest)
            view["terms"][0]["claim_type"] = "analysis"
            view["terms"][0]["availability"] = "unverifiable"
            output = render_reading_analysis(view)
            self.assertIn("读者分析", output)
            self.assertIn("当前证据无法核实", output)
        finally:
            source.unlink(missing_ok=True)

    def test_english_view_uses_english_headings(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            source = project / "source.pdf"
            _write_pdf(source)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            view = _reading_view(digest)
            view["language"] = "en-US"
            output = render_reading_analysis(view)
            self.assertIn("# Readable Paper", output)
            self.assertIn("## 1. 30-Second Overview", output)
            self.assertNotIn("## 1. 30 秒看懂", output)

    def test_overview_problem_is_not_repeated_verbatim(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            source = project / "source.pdf"
            _write_pdf(source)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            view = _reading_view(digest)
            output = render_reading_analysis(view)
            self.assertEqual(output.count("旧方法无法稳定解决问题。"), 1)

    def test_old_project_falls_back_without_reading_view(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "digest.json").write_text(json.dumps({
                "paper_metadata": {"title": "Legacy Paper", "authors": []},
                "paper_semantics": {"slots": {
                    "approach": {
                        "text": "SFT baseline",
                        "summary": "SFT baseline",
                        "source_page": 1,
                        "section": "Method",
                        "locator": "Method paragraph 1",
                    }
                }},
                "flags": [],
            }), encoding="utf-8")
            output_path = write_paper_analysis(project)
            output = output_path.read_text(encoding="utf-8")
            self.assertIn("# Legacy Paper", output)
            self.assertIn("## 1. 一句话讲清这篇论文", output)
            self.assertNotIn("保留论文原文术语，结合对应方法或实验语境理解", output)

    def test_invalid_view_does_not_overwrite_previous_output(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            source = project / "source.pdf"
            _write_pdf(source)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            (project / "digest.json").write_text(json.dumps({
                "paper_metadata": {"title": "Readable Paper", "pdf_sha256": digest},
                "source": {"source_sha256": digest},
                "paper_semantics": {"slots": {}},
                "flags": [],
            }), encoding="utf-8")
            view = _reading_view(digest)
            view["source_bindings"].append({
                "path": "digest.json",
                "sha256": hashlib.sha256((project / "digest.json").read_bytes()).hexdigest(),
            })
            (project / "reading-view.json").write_text(json.dumps(view), encoding="utf-8")
            output = write_paper_analysis(project)
            original = output.read_text(encoding="utf-8")
            source.write_bytes(b"changed pdf")
            with self.assertRaises(ValueError):
                write_paper_analysis(project)
            self.assertEqual(output.read_text(encoding="utf-8"), original)

    def test_project_language_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            source = project / "source.pdf"
            _write_pdf(source)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            (project / "digest.json").write_text(json.dumps({
                "paper_metadata": {"title": "Readable Paper", "pdf_sha256": digest},
                "source": {"source_sha256": digest},
                "paper_semantics": {"slots": {}},
                "flags": [],
            }), encoding="utf-8")
            view = _reading_view(digest)
            view["source_bindings"].append({
                "path": "digest.json",
                "sha256": hashlib.sha256((project / "digest.json").read_bytes()).hexdigest(),
            })
            (project / "reading-view.json").write_text(json.dumps(view), encoding="utf-8")
            (project / "project-options.json").write_text(json.dumps({"options": {"language": "en-US"}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                write_paper_analysis(project)


if __name__ == "__main__":
    unittest.main()
