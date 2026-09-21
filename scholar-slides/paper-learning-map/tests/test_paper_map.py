from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fixture_support import make_portable_fixture

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "paper-learning-map"


class PaperMapTests(unittest.TestCase):
    def test_reasoning_table_projection_and_render(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = make_portable_fixture("Reasoning-Table", Path(raw))
            out = Path(raw) / "output"
            subprocess.run([sys.executable, str(MAP / "runtime" / "build_paper_map.py"), "--project", str(project), "--out", str(out)], check=True)
            subprocess.run([sys.executable, str(MAP / "runtime" / "render_paper_map.py"), "--project", str(out)], check=True)
            data = json.loads((out / "paper-map.json").read_text(encoding="utf-8"))
            self.assertEqual(data["source"]["mode"], "integrated")
            titles = {node["title"] for node in data["nodes"]}
            self.assertIn("Method", titles)
            self.assertTrue((out / "paper-learning-map.html").is_file())
            self.assertIn("Reasoning-Table", (out / "paper-learning-map.html").read_text(encoding="utf-8"))

    def test_startupbench_benchmark_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = make_portable_fixture("StartupBench", Path(raw))
            out = Path(raw) / "output"
            subprocess.run([sys.executable, str(MAP / "runtime" / "build_paper_map.py"), "--project", str(project), "--out", str(out)], check=True)
            data = json.loads((out / "paper-map.json").read_text(encoding="utf-8"))
            self.assertEqual(data["paper_type"], "benchmark")
            self.assertTrue(any(node["node_type"] == "experiment" for node in data["nodes"]))

    def test_unconfirmed_upstream_fails_closed_to_tutor_only(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = make_portable_fixture("Reasoning-Table", Path(raw))
            out = Path(raw) / "output"
            subprocess.run([sys.executable, str(MAP / "runtime" / "build_paper_map.py"), "--project", str(project), "--out", str(out)], check=True)
            data = json.loads((out / "paper-map.json").read_text(encoding="utf-8"))
            self.assertEqual(data["source"]["mode"], "integrated")
            self.assertEqual(data["source"]["verification_level"], "tutor_only")

    def test_downstream_state_does_not_change_reading_view(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = make_portable_fixture("StartupBench", Path(raw))
            source = (project / "reading-view.json").read_bytes()
            out = Path(raw) / "output"
            subprocess.run([sys.executable, str(MAP / "runtime" / "build_paper_map.py"), "--project", str(project), "--out", str(out)], check=True)
            subprocess.run([sys.executable, str(MAP / "runtime" / "update_learning_state.py"), "--project", str(out), "mark-understood", "overview.problem"], check=True)
            self.assertEqual(source, (project / "reading-view.json").read_bytes())

    def test_renderer_v2_contracts(self) -> None:
        source = (MAP / "runtime" / "render_paper_map.py").read_text(encoding="utf-8")
        for token in ("presentation_only", "function measure", "function fit", "drawer", "showRelations", "paper_fact:'fact'"):
            self.assertIn(token, source)
        self.assertNotIn("slice(0,22)", source)
        self.assertNotIn("slice(0,25)", source)
        self.assertNotIn("width=164", source)
        self.assertNotIn("height=58", source)

        template = (MAP / "templates" / "paper-learning-map.template.html").read_text(encoding="utf-8")
        for marker in ("__INLINE_CSS__", "__INLINE_KATEX_CSS__", "__INLINE_KATEX_JS__", "__INLINE_JS__", "__MAP_DATA__", "__TUTOR_DATA__", "__STUDY_DATA__", "__FORMULA_DATA__"):
            self.assertEqual(template.count(marker), 1)
        javascript = (MAP / "assets" / "paper-learning-map.js").read_text(encoding="utf-8")
        for token in ("function measure", "function fit", "drawer", "showRelations", "paper_fact:'fact'"):
            self.assertIn(token, javascript)
        self.assertLess(len(source), 8000)

    def test_tutor_state_full_and_incremental_sync(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = make_portable_fixture("Reasoning-Table", Path(raw))
            out = Path(raw) / "output"
            subprocess.run([sys.executable, str(MAP / "runtime" / "build_paper_map.py"), "--project", str(project), "--out", str(out)], check=True)
            records = [
                {"node_id": "overview.problem", "kind": "tutor_explanation", "title": "为什么需要表格定位", "summary": "答案之外还要检查证据位置。", "body": "Tutor Explanation：定位中间证据可以减少局部错误传到最终答案。", "map_visible": True, "importance": "high"},
                {"node_id": "term.3", "kind": "intuition", "title": "GRPO 的直觉", "summary": "比较同题候选答案。", "body": "Tutor Explanation：GRPO 使用组内相对优势更新策略。", "map_visible": True, "importance": "high"},
                {"node_id": "takeaway.5", "kind": "reader_analysis", "title": "不要过度归因", "summary": "组合有效不等于单一组件必要。", "body": "Tutor Analysis：需要联合查看四分支、奖励消融和扰动实验。", "map_visible": True, "importance": "high"},
            ]
            records_path = out / "records.json"
            records_path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
            subprocess.run([sys.executable, str(MAP / "runtime" / "update_tutor_state.py"), "--project", str(out), "sync", "--records", str(records_path)], check=True)
            for question, answer in (
                ("Position reward 为什么有作用？", "它把回答和推理引用的位置联系起来。"),
                ("GRPO 奖励如何共同工作？", "答案、格式和位置奖励共同参与相对优势计算。"),
                ("能否把全部提升归因给 GRPO？", "不能，四分支和消融只支持受测设置下的组合结论。"),
            ):
                subprocess.run([sys.executable, str(MAP / "runtime" / "update_tutor_state.py"), "--project", str(out), "ask", "--node-id", "term.4", "--question", question, "--answer", answer], check=True)
            subprocess.run([sys.executable, str(MAP / "runtime" / "update_tutor_state.py"), "--project", str(out), "ask", "--question", "M 是什么意思？", "--answer", "当前上下文不足，无法安全绑定。", "--important", "false"], check=True)
            subprocess.run([sys.executable, str(MAP / "runtime" / "update_tutor_state.py"), "--project", str(out), "item", "--title-anchor", "evidence", "--kind", "tutor_explanation", "--title", "Evidence anchor ambiguity", "--summary", "不能猜测", "--body", "多个 evidence 节点都可能匹配。"], check=True)
            state = json.loads((out / "tutor-state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["schema_version"], "1.1")
            self.assertEqual(len(state["nodes"]["term.4"]["questions"]), 3)
            self.assertEqual(len(state["nodes"]["term.4"]["map_items"]), 3)
            self.assertEqual(state["nodes"]["takeaway.5"]["map_items"][0]["source_layer"], "tutor")
            self.assertEqual({item["reason"] for item in state["unresolved_items"]}, {"no_anchor", "no_unique_anchor"})
            self.assertNotIn("map_items", json.loads((out / "paper-map.json").read_text(encoding="utf-8"))["nodes"][0])


if __name__ == "__main__":
    unittest.main()
