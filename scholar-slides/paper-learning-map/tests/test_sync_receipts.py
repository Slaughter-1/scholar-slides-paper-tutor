from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "paper-learning-map"
RUNTIME = MAP / "runtime"
sys.path.insert(0, str(RUNTIME))

from sync_receipt import append_receipt, build_receipt, validate_receipt  # noqa: E402


class SyncReceiptTests(unittest.TestCase):
    def make_project(self) -> Path:
        temp = Path(tempfile.mkdtemp())
        source = MAP / "fixtures" / "Reasoning-Table"
        subprocess.run([sys.executable, str(RUNTIME / "build_paper_map.py"), "--project", str(source), "--out", str(temp)], check=True)
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        return temp

    def run_sync(self, project: Path, payload: list[dict], origin: str = "full_analysis") -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(RUNTIME / "update_tutor_state.py"), "--project", str(project), "sync", "--stdin", "--origin", origin],
            input=json.dumps(payload, ensure_ascii=False), text=True, encoding="utf-8", capture_output=True,
        )

    def receipts(self, project: Path) -> list[Path]:
        return sorted((project / "sync-receipts").glob("*.json"))

    def test_success_and_unresolved_receipts_are_append_only(self) -> None:
        project = self.make_project()
        success = self.run_sync(project, [{"node_id": "overview.problem", "kind": "tutor_explanation", "title": "Receipt success", "summary": "x", "body": "x"}])
        self.assertEqual(success.returncode, 0, success.stderr)
        unresolved = self.run_sync(project, [{"kind": "user_question", "question": "M 是什么意思？", "answer": "上下文不足", "important": False}], "incremental_qa")
        self.assertEqual(unresolved.returncode, 0, unresolved.stderr)
        paths = self.receipts(project)
        self.assertEqual(len(paths), 2)
        first, second = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
        self.assertEqual((first["event"], first["status"], first["items_added"]), ("full_analysis_sync", "success", 1))
        self.assertEqual((second["event"], second["status"], second["unresolved_added"]), ("incremental_qa_sync", "success", 1))
        for receipt in (first, second):
            validate_receipt(receipt)

    def test_identity_mismatch_writes_failed_receipt_without_state_write(self) -> None:
        project = self.make_project()
        state_path = project / "tutor-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["paper_identity"]["source_pdf_sha256"] = "0" * 64
        state_path.write_text(json.dumps(state), encoding="utf-8")
        before = state_path.read_bytes()
        result = self.run_sync(project, [{"node_id": "overview.problem", "kind": "tutor_explanation", "title": "must fail", "summary": "x", "body": "x"}])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(state_path.read_bytes(), before)
        receipt = json.loads(self.receipts(project)[-1].read_text(encoding="utf-8"))
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["error"]["type"], "ValueError")

    def test_no_map_is_observable_as_skipped(self) -> None:
        project = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, project, ignore_errors=True)
        result = self.run_sync(project, [{"node_id": "x", "kind": "tutor_explanation", "title": "skip", "summary": "x", "body": "x"}])
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(self.receipts(project)[0].read_text(encoding="utf-8"))
        self.assertEqual((receipt["event"], receipt["status"], receipt["reason"]), ("sync_skipped", "skipped", "no_learning_map"))

    def test_receipt_atomic_write_cleans_temp_file(self) -> None:
        project = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, project, ignore_errors=True)
        receipt = build_receipt(event="sync_failed", project=project, paper_sha256=None, status="failed", error={"type": "TestError", "short_error": "simulated"})
        with patch("sync_receipt.os.replace", side_effect=OSError("simulated atomic failure")):
            with self.assertRaises(OSError):
                append_receipt(project, receipt)
        self.assertEqual(list((project / "sync-receipts").glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
