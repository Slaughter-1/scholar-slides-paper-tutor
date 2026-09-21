from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "paper-learning-map" / "fixtures"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_portable_fixture(name: str, destination: Path) -> Path:
    """Copy a fixture and replace private source bindings with a local PDF.

    Public fixtures intentionally do not redistribute the original papers.
    Tests still need a source-bound project, so they create a deterministic
    page-count-only PDF and rebind the copied digest/view to it. This keeps
    production validators strict while making CI independent of a developer's
    absolute Windows paths.
    """

    source = FIXTURES / name
    project = destination / name
    shutil.copytree(source, project, ignore=shutil.ignore_patterns("output"))
    digest_path = project / "digest.json"
    digest = json.loads(digest_path.read_text(encoding="utf-8"))
    page_count = 1
    pdf_path = project / "source.pdf"
    document = fitz.open()
    for _ in range(page_count):
        document.new_page(width=612, height=792)
    document.save(pdf_path)
    document.close()
    pdf_hash = _sha256(pdf_path)

    source_meta = digest.setdefault("source", {})
    for key in ("source_sha256", "pdf_sha256"):
        source_meta[key] = pdf_hash
    source_meta["pdf"] = "source.pdf"
    digest_path.write_text(json.dumps(digest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    digest_hash = _sha256(digest_path)

    view_path = project / "reading-view.json"
    view = json.loads(view_path.read_text(encoding="utf-8"))
    view["paper_identity"]["source_pdf_sha256"] = pdf_hash
    def rebind_evidence(value: object) -> None:
        if isinstance(value, dict):
            if "evidence_refs" in value and isinstance(value["evidence_refs"], list):
                value["evidence_refs"] = ["digest.json#/source"]
            for child in value.values():
                rebind_evidence(child)
        elif isinstance(value, list):
            for child in value:
                rebind_evidence(child)
    rebind_evidence(view)
    bindings = view["source_bindings"]
    bindings[0] = {"path": "source.pdf", "sha256": pdf_hash}
    bindings[1] = {"path": "digest.json", "sha256": digest_hash}
    view_path.write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return project
