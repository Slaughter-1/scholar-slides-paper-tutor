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

from reading_view import ReadingViewError, _locator_in_text, load_reading_view  # noqa: E402


def _write_pdf(path: Path, pages: int = 4) -> None:
    document = pymupdf.open()
    labels = ["Introduction", "Method", "Results", "Table 1"]
    for index in range(pages):
        page = document.new_page()
        page.insert_text((72, 72), labels[index] if index < len(labels) else f"Page {index + 1}")
    document.save(path)
    document.close()


def _record(content: str, *, claim_type: str = "paper_fact", refs: list[str] | None = None) -> dict:
    return {
        "content": content,
        "claim_type": claim_type,
        "availability": "supported",
        "evidence_refs": refs or ["p. 1, Introduction"],
    }


def _view(pdf_sha: str, source_path: str) -> dict:
    return {
        "schema_version": 1,
        "paper_identity": {
            "title": "Example Paper",
            "source_pdf_sha256": pdf_sha,
        },
        "source_bindings": [{"path": source_path, "sha256": pdf_sha}],
        "language": "zh-CN",
        "paper_type": {"kind": "method", "reason": "A new method is the primary contribution."},
        "overview": {
            "problem": _record("Existing systems fail on the target task."),
            "gap": _record("Prior methods do not address the failure."),
            "approach": _record("The paper adds a verified processing stage."),
            "insight": _record("The paper makes the missing verification step explicit.", claim_type="analysis"),
            "findings": _record("The main experiment improves the reported metric."),
            "boundary": _record("The evidence is limited to the tested setting.", claim_type="analysis"),
        },
        "mechanism_steps": [
            {
                "title": "Encode input",
                "purpose": "Represent the input.",
                "input": "Raw example",
                "output": "Encoded example",
                "necessity": "The next stage consumes the representation.",
                "claim_type": "paper_fact",
                "availability": "supported",
                "evidence_refs": ["p. 2, Method"],
            }
        ],
        "argument_chain": [
            {
                "node": "Prior gap",
                "relation": "motivates",
                "claim_type": "paper_fact",
                "availability": "supported",
                "evidence_refs": ["p. 1, Introduction"],
            }
        ],
        "decisive_evidence": [
            {
                "question": "Does the method improve the task?",
                "comparison": "Method versus baseline on Dataset A",
                "metric": "F1",
                "result": "75 versus 70",
                "can_support": "The method performs better in this setup.",
                "cannot_support": "It does not establish generalization to other datasets.",
                "claim_type": "paper_fact",
                "availability": "supported",
                "evidence_refs": ["p. 4, Table 1"],
            }
        ],
        "terms": [
            {
                "term": "F1",
                "plain": "A balance between precision and recall.",
                "role": "The main evaluation metric in this paper.",
                "confusions": "It is not accuracy.",
                "claim_type": "explanation",
                "availability": "supported",
                "evidence_refs": ["p. 4, Table 1"],
            }
        ],
        "takeaways": [
            {
                "kind": "author_contribution",
                "content": "The authors introduce the processing stage.",
                "claim_type": "paper_fact",
                "availability": "supported",
                "evidence_refs": ["p. 2, Method"],
            }
        ],
    }


class ReadingViewTests(unittest.TestCase):
    def test_numbered_locator_requires_heading_or_caption_line(self) -> None:
        self.assertFalse(_locator_in_text("Table 999", "This paragraph mentions Table 999 as an example."))
        self.assertFalse(_locator_in_text("Section 999", "We compare Section 999 as an example."))
        self.assertTrue(_locator_in_text("Table 999", "Table 999: Results by model."))
        self.assertTrue(_locator_in_text("Section 999", "Section 999\n"))
        self.assertFalse(_locator_in_text("Method", "The method improves the result."))
        self.assertTrue(_locator_in_text("Method", "3 Method\n"))

    def test_valid_view_is_loaded_and_bound_to_digest(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            source = project / "source.pdf"
            _write_pdf(source)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            (project / "reading-view.json").write_text(
                json.dumps(_view(digest, "source.pdf"), ensure_ascii=False), encoding="utf-8"
            )
            loaded = load_reading_view(project, digest={"source": {"source_sha256": digest}})
            self.assertEqual(loaded["paper_identity"]["title"], "Example Paper")

    def test_source_binding_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            source = project / "source.pdf"
            _write_pdf(source)
            actual = hashlib.sha256(source.read_bytes()).hexdigest()
            payload = _view("0" * 64, "source.pdf")
            payload["source_bindings"][0]["sha256"] = actual
            (project / "reading-view.json").write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ReadingViewError):
                load_reading_view(project)

    def test_digest_file_must_be_bound_when_digest_is_supplied(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            source = project / "source.pdf"
            _write_pdf(source)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            (project / "digest.json").write_text(json.dumps({"source": {"source_sha256": digest}}), encoding="utf-8")
            (project / "reading-view.json").write_text(
                json.dumps(_view(digest, "source.pdf"), ensure_ascii=False), encoding="utf-8"
            )
            with self.assertRaises(ReadingViewError):
                load_reading_view(project, digest={"source": {"source_sha256": digest}})

    def test_placeholder_term_explanation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            source = project / "source.pdf"
            _write_pdf(source)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            payload = _view(digest, "source.pdf")
            payload["terms"][0]["plain"] = "保留论文原文术语，结合对应方法或实验语境理解。"
            (project / "reading-view.json").write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ReadingViewError):
                load_reading_view(project)

    def test_digest_identity_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            source = project / "source.pdf"
            _write_pdf(source)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            (project / "reading-view.json").write_text(
                json.dumps(_view(digest, "source.pdf")), encoding="utf-8"
            )
            with self.assertRaises(ReadingViewError):
                load_reading_view(project, digest={"source": {"source_sha256": "1" * 64}})

    def test_nonexistent_digest_locator_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            source = project / "source.pdf"
            _write_pdf(source)
            digest_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            digest = {
                "source": {"source_sha256": digest_hash},
                "paper_metadata": {"title": "Example Paper"},
                "paper_semantics": {"slots": {"problem": {"source_page": 1, "section": "Introduction"}}},
            }
            digest_path = project / "digest.json"
            digest_path.write_text(json.dumps(digest), encoding="utf-8")
            payload = _view(digest_hash, "source.pdf")
            payload["source_bindings"].append({
                "path": "digest.json",
                "sha256": hashlib.sha256(digest_path.read_bytes()).hexdigest(),
            })
            payload["overview"]["problem"]["evidence_refs"] = ["digest.json#/paper_semantics/slots/missing"]
            (project / "reading-view.json").write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ReadingViewError):
                load_reading_view(project, digest=digest)

    def test_unknown_evidence_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            source = project / "source.pdf"
            _write_pdf(source)
            digest_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            digest = {"source": {"source_sha256": digest_hash}, "paper_metadata": {"title": "Example Paper"}}
            digest_path = project / "digest.json"
            digest_path.write_text(json.dumps(digest), encoding="utf-8")
            payload = _view(digest_hash, "source.pdf")
            payload["source_bindings"].append({
                "path": "digest.json",
                "sha256": hashlib.sha256(digest_path.read_bytes()).hexdigest(),
            })
            payload["overview"]["problem"]["evidence_refs"] = ["EVIDENCE-ID-DOES-NOT-EXIST"]
            (project / "reading-view.json").write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ReadingViewError):
                load_reading_view(project, digest=digest)

    def test_digest_pointer_must_name_bound_project_digest(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            source = project / "source.pdf"
            _write_pdf(source)
            digest_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            digest = {"source": {"source_sha256": digest_hash}, "paper_metadata": {"title": "Example Paper"}}
            digest_path = project / "digest.json"
            digest_path.write_text(json.dumps(digest), encoding="utf-8")
            payload = _view(digest_hash, "source.pdf")
            payload["source_bindings"].append({
                "path": "digest.json",
                "sha256": hashlib.sha256(digest_path.read_bytes()).hexdigest(),
            })
            payload["overview"]["problem"]["evidence_refs"] = ["other-digest.json#/source"]
            (project / "reading-view.json").write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ReadingViewError):
                load_reading_view(project, digest=digest)

    def test_nonexistent_numbered_locator_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            source = project / "source.pdf"
            _write_pdf(source)
            digest_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            payload = _view(digest_hash, "source.pdf")
            payload["overview"]["problem"]["evidence_refs"] = ["p. 1, Table 999"]
            (project / "reading-view.json").write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ReadingViewError):
                load_reading_view(project)

    def test_unreadable_bound_pdf_is_rejected_for_page_refs(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            source = project / "source.pdf"
            source.write_bytes(b"not a pdf")
            digest_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            payload = _view(digest_hash, "source.pdf")
            (project / "reading-view.json").write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ReadingViewError):
                load_reading_view(project)

    def test_supported_argument_node_requires_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            source = project / "source.pdf"
            _write_pdf(source)
            digest_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            payload = _view(digest_hash, "source.pdf")
            payload["argument_chain"][0]["evidence_refs"] = []
            (project / "reading-view.json").write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ReadingViewError):
                load_reading_view(project)


if __name__ == "__main__":
    unittest.main()
