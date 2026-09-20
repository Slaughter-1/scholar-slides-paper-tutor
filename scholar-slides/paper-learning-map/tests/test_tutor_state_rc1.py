from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "paper-learning-map"
import sys
sys.path.insert(0, str(MAP / "runtime"))

from tutor_state import TutorStateStore, _atomic_json, _validate_study_state  # noqa: E402


class TutorStateRC1Tests(unittest.TestCase):
    def make_project(self) -> Path:
        temp = Path(tempfile.mkdtemp())
        source = MAP / "fixtures" / "Reasoning-Table"
        subprocess = __import__("subprocess")
        subprocess.run(
            [sys.executable, str(MAP / "runtime" / "build_paper_map.py"), "--project", str(source), "--out", str(temp)],
            check=True,
        )
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        return temp

    def test_first_question_moves_only_unseen_to_learning(self) -> None:
        project = self.make_project()
        study_path = project / "study-state.json"
        store = TutorStateStore(project)
        store.add_user_question(node_id="overview.problem", question="为什么？", answer="因为需要定位证据。", study_path=study_path)
        store.save()
        study = json.loads(study_path.read_text(encoding="utf-8"))
        self.assertEqual(study["nodes"]["overview.problem"]["status"], "learning")

        study["nodes"]["overview.problem"]["status"] = "understood"
        study["nodes"]["overview.problem"]["mastery"] = 2
        study_path.write_text(json.dumps(study, ensure_ascii=False), encoding="utf-8")
        store = TutorStateStore(project)
        store.add_user_question(node_id="overview.problem", question="再解释一次？", answer="补充说明。", study_path=study_path)
        store.save()
        study = json.loads(study_path.read_text(encoding="utf-8"))
        self.assertEqual(study["nodes"]["overview.problem"]["status"], "understood")

        before = study["nodes"]["term.1"]["status"]
        store = TutorStateStore(project)
        store.add_user_question(node_id=None, question="上下文不足", answer="无法绑定。", study_path=study_path)
        store.save()
        after = json.loads(study_path.read_text(encoding="utf-8"))["nodes"]["term.1"]["status"]
        self.assertEqual((before, after), ("unseen", "unseen"))

    def test_near_duplicate_question_keeps_one_item_and_variants(self) -> None:
        project = self.make_project()
        store = TutorStateStore(project)
        store.add_user_question(node_id="term.1", question="Agent Harness 是什么？", answer="运行时编排层。")
        store.add_user_question(node_id="term.1", question="Agent Harness 的作用是什么？", answer="连接模型与工具。")
        store.add_user_question(node_id="term.1", question="为什么需要 Agent Harness？", answer="为了统一运行链路。")
        store.save()
        state = json.loads((project / "tutor-state.json").read_text(encoding="utf-8"))
        questions = [item for item in state["nodes"]["term.1"]["map_items"] if item["kind"] == "user_question"]
        self.assertEqual(len(questions), 2)
        self.assertIn("Agent Harness 的作用是什么？", questions[0].get("question_variants", []))

    def test_stale_and_ambiguous_anchors_are_unresolved(self) -> None:
        project = self.make_project()
        store = TutorStateStore(project)
        stale = store.add_structured_item(node_id="node.deleted", kind="intuition", title="stale", summary="x", body="x")
        ambiguous = store.add_structured_item(title_anchor="evidence", kind="intuition", title="ambiguous", summary="x", body="x")
        store.save()
        self.assertEqual(stale["reason"], "stale_node_id")
        self.assertEqual(ambiguous["reason"], "no_unique_anchor")
        state = json.loads((project / "tutor-state.json").read_text(encoding="utf-8"))
        self.assertEqual({item["reason"] for item in state["unresolved_items"]}, {"stale_node_id", "no_unique_anchor"})

    def test_identity_mismatch_is_rejected_without_write(self) -> None:
        project = self.make_project()
        path = project / "tutor-state.json"
        original = path.read_bytes()
        state = json.loads(original)
        state["paper_identity"]["source_pdf_sha256"] = "0" * 64
        mismatched = json.dumps(state).encode("utf-8")
        path.write_bytes(mismatched)
        with self.assertRaises(ValueError):
            TutorStateStore(project)
        # The constructor rejects before any write and leaves the mismatched
        # file exactly as supplied.
        self.assertEqual(path.read_bytes(), mismatched)
        self.assertNotEqual(original, path.read_bytes())

    def test_map_and_tutor_from_different_papers_are_rejected(self) -> None:
        project = self.make_project()
        map_path = project / "paper-map.json"
        paper_map = json.loads(map_path.read_text(encoding="utf-8"))
        paper_map["paper_identity"]["source_pdf_sha256"] = "f" * 64
        map_path.write_text(json.dumps(paper_map), encoding="utf-8")
        with self.assertRaises(ValueError):
            TutorStateStore(project)

    def test_validation_failure_preserves_existing_state_and_atomic_failure_cleans_tmp(self) -> None:
        project = self.make_project()
        path = project / "tutor-state.json"
        original = path.read_bytes()
        store = TutorStateStore(project)
        store.state["unexpected"] = True
        with self.assertRaises(ValueError):
            store.save()
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(project.glob(".tutor-state.json.*.tmp")), [])

        target = project / "atomic.json"
        with patch("tutor_state.os.replace", side_effect=OSError("simulated failure")):
            with self.assertRaises(OSError):
                _atomic_json(target, {"ok": True})
        self.assertFalse(target.exists())
        self.assertEqual(list(project.glob(".atomic.json.*.tmp")), [])

    def test_schema_1_0_is_loaded_and_upgraded_on_write(self) -> None:
        project = self.make_project()
        path = project / "tutor-state.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        state["schema_version"] = "1.0"
        path.write_text(json.dumps(state), encoding="utf-8")
        store = TutorStateStore(project)
        self.assertEqual(store.state["schema_version"], "1.1")
        store.save()
        upgraded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(upgraded["schema_version"], "1.1")
        schema = json.loads((MAP / "schemas" / "tutor-state.schema.json").read_text(encoding="utf-8"))
        self.assertFalse(list(Draft202012Validator(schema).iter_errors(upgraded)))

    def test_study_state_validator_rejects_bad_status(self) -> None:
        project = self.make_project()
        study = json.loads((project / "study-state.json").read_text(encoding="utf-8"))
        study["nodes"]["paper"]["status"] = "mastery_unknown"
        with self.assertRaises(ValueError):
            _validate_study_state(study)

    def test_install_side_bridge_streams_to_shared_writer(self) -> None:
        project = self.make_project()
        payload = json.dumps([
            {"node_id": "overview.problem", "kind": "tutor_explanation", "title": "bridge smoke", "summary": "structured", "body": "Tutor only", "map_visible": True, "importance": "high"}
        ], ensure_ascii=False)
        env = dict(os.environ)
        env["PAPER_LEARNING_MAP_ROOT"] = str(MAP)
        completed = __import__("subprocess").run(
            [sys.executable, str(MAP / "integrations" / "paper_tutor_sync.py"), "--project", str(project)],
            input=payload,
            text=True,
            encoding="utf-8",
            env=env,
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        state = json.loads((project / "tutor-state.json").read_text(encoding="utf-8"))
        item = state["nodes"]["overview.problem"]["map_items"][0]
        self.assertEqual((item["source_layer"], item["origin"]), ("tutor", "full_analysis"))


if __name__ == "__main__":
    unittest.main()
