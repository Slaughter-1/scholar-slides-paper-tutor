from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "paper-learning-map" / "runtime"
SCHEMA = ROOT / "paper-learning-map" / "schemas" / "formula-index.schema.json"
sys.path.insert(0, str(RUNTIME))

from formula_projection import (  # noqa: E402
    build_formula_index,
    validate_formula_index_binding,
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class FormulaProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reasoning_root = ROOT / "paper-learning-map" / "fixtures" / "Reasoning-Table"
        self.reasoning_map = load_json(self.reasoning_root / "output" / "paper-map.json")
        self.reasoning_state = load_json(self.reasoning_root / "output" / "tutor-state.json")
        self.reasoning_view = load_json(self.reasoning_root / "reading-view.json")
        self.reasoning_digest = load_json(self.reasoning_root / "digest.json")

    def test_reasoning_formula_identity_anchor_provenance_and_evidence(self) -> None:
        index = build_formula_index(self.reasoning_map, self.reasoning_state, self.reasoning_view, self.reasoning_digest)
        validate_formula_index_binding(index, self.reasoning_map)
        self.assertEqual([f["id"] for f in index["formulas"]], [
            "formula.method.step_3.position_reward",
            "formula.method.step_3.final_reward",
        ])
        for formula in index["formulas"]:
            self.assertEqual(formula["anchor_node_id"], "method.step_3")
            self.assertEqual(formula["paper_formula"]["formula_kind"], "paper_formula")
            self.assertEqual(formula["paper_formula"]["source_layer"], "paper")
            self.assertTrue(formula["paper_formula"]["evidence_refs"])
            self.assertEqual(formula["tutor_derivation"]["source_layer"], "tutor")
            self.assertEqual(formula["tutor_example"]["source_layer"], "tutor")
            self.assertNotEqual(formula["paper_formula"]["latex"], formula["tutor_example"].get("latex", ""))

    def test_swe_touch_eq3_is_stable_and_source_bound(self) -> None:
        root = ROOT / "docs" / "e2e-validation" / "verified-fresh" / "swe-touch"
        paper_map = load_json(root / "learning-map-rc1-verified" / "paper-map.json")
        tutor_state = load_json(root / "learning-map-rc1-verified" / "tutor-state.json")
        view = load_json(root / "scholar" / "reading-view.json")
        digest = load_json(root / "scholar" / "digest.json")
        index = build_formula_index(paper_map, tutor_state, view, digest)
        validate_formula_index_binding(index, paper_map)
        self.assertEqual(len(index["formulas"]), 1)
        formula = index["formulas"][0]
        self.assertEqual(formula["id"], "formula.method.step_2.counter_edit_validation")
        self.assertEqual(formula["equation_label"], "Eq. (3)")
        self.assertIn("V_F^i", formula["paper_formula"]["latex"])
        self.assertEqual(formula["anchor_node_id"], "method.step_2")

    def test_schema_and_missing_formula_are_safe(self) -> None:
        index = build_formula_index(self.reasoning_map, self.reasoning_state, self.reasoning_view, self.reasoning_digest)
        schema = load_json(SCHEMA)
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(index)), [])
        empty = copy.deepcopy(index)
        empty["formulas"] = []
        validate_formula_index_binding(empty, self.reasoning_map)

    def test_identity_anchor_and_duplicate_fail_closed(self) -> None:
        index = build_formula_index(self.reasoning_map, self.reasoning_state, self.reasoning_view, self.reasoning_digest)
        wrong_identity = copy.deepcopy(index)
        wrong_identity["paper_identity"]["source_pdf_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            validate_formula_index_binding(wrong_identity, self.reasoning_map)

        wrong_anchor = copy.deepcopy(index)
        wrong_anchor["formulas"][0]["anchor_node_id"] = "method.missing"
        with self.assertRaises(ValueError):
            validate_formula_index_binding(wrong_anchor, self.reasoning_map)

        duplicate = copy.deepcopy(index)
        duplicate["formulas"].append(copy.deepcopy(duplicate["formulas"][0]))
        duplicate["formulas"][1]["id"] = "formula.duplicate"
        with self.assertRaises(ValueError):
            validate_formula_index_binding(duplicate, self.reasoning_map)

    def test_paper_tutor_and_tutor_example_layers_cannot_swap(self) -> None:
        index = build_formula_index(self.reasoning_map, self.reasoning_state, self.reasoning_view, self.reasoning_digest)
        swapped = copy.deepcopy(index)
        swapped["formulas"][0]["paper_formula"]["source_layer"] = "tutor"
        with self.assertRaises(ValueError):
            validate_formula_index_binding(swapped, self.reasoning_map)


if __name__ == "__main__":
    unittest.main()
