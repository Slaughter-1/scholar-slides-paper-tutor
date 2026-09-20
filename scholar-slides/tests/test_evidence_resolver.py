from __future__ import annotations

import sys
import unittest

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime" / "scripts"))

from evidence_resolver import (  # noqa: E402
    build_document_index,
    parse_locator,
    resolve_and_verify,
)


class EvidenceResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pages = [
            "1 Introduction\n\nWe motivate the problem.\n\nprinted i",
            "2 Method\nFigure 1: Pipeline overview\nTable 1: Main results\nEquation (5) x = y + 1\nTo summarize, our contributions are as follows:\nprinted 2",
            "Appendix A: Additional details\nFigure 2: Ablation\nprinted A",
        ]
        self.index = build_document_index(self.pages, printed_page_labels=["i", "2", "A"])

    def test_parse_page_range_and_mixed_locator(self) -> None:
        parsed = parse_locator("pp. 2-3, Section 2, Eq. (5)")
        self.assertEqual([item.kind for item in parsed.components], ["source_page_reference", "section", "equation"])
        self.assertEqual(parsed.components[0].value, "2-3")
        self.assertEqual(parsed.components[2].value, "5")
        self.assertEqual(parse_locator("p. 2, section Contributions").components[1].value, "Contributions")

    def test_page_coordinate_systems_are_explicit(self) -> None:
        self.assertEqual(parse_locator("pdf page index 1").components[0].kind, "pdf_page_index")
        self.assertEqual(parse_locator("printed page 2").components[0].kind, "printed_page_label")
        self.assertEqual(parse_locator("source page 2").components[0].kind, "source_page_reference")
        self.assertEqual(resolve_and_verify("pdf page index 1", self.index).pdf_page_indices, [1])
        self.assertEqual(resolve_and_verify("printed page 2", self.index).pdf_page_indices, [1])
        self.assertEqual(resolve_and_verify("pdf page index 1-2", self.index).pdf_page_indices, [1, 2])

    def test_structural_locators_require_evidence_span(self) -> None:
        for locator in ("p. 2, Figure 1", "p. 2, Table 1", "p. 2, Eq. (5)", "p. 3, Appendix A"):
            result = resolve_and_verify(locator, self.index)
            self.assertIn(result.status, {"exact", "normalized"}, locator)
            self.assertTrue(result.evidence_span, locator)

    def test_free_text_section_is_partial_after_span_validation(self) -> None:
        result = resolve_and_verify("p. 2, Contributions", self.index)
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.failure_reason_codes, ["SECTION_NOT_FOUND"])
        self.assertTrue(result.evidence_span)

    def test_fuzzy_section_is_reported_without_silent_exact_upgrade(self) -> None:
        result = resolve_and_verify("p. 1, Introducton", self.index)
        self.assertEqual(result.status, "fuzzy")
        self.assertTrue(result.evidence_span)

    def test_alias_page_form_is_normalized(self) -> None:
        result = resolve_and_verify("Page 1, Introduction", self.index)
        self.assertEqual(result.status, "normalized")

    def test_ambiguous_printed_label_is_not_guessed(self) -> None:
        index = build_document_index(self.pages, printed_page_labels=["2", "2", "A"])
        result = resolve_and_verify("printed page 2", index)
        self.assertEqual(result.status, "ambiguous")

    def test_mixed_page_structure_mismatch_is_rejected(self) -> None:
        result = resolve_and_verify("p. 1, Table 1", self.index)
        self.assertEqual(result.status, "unresolved")
        self.assertIn("TABLE_NOT_FOUND", result.failure_reason_codes)

    def test_unknown_locator_is_unresolved(self) -> None:
        result = resolve_and_verify("p. 1, Figure 99", self.index)
        self.assertEqual(result.status, "unresolved")
        self.assertFalse(result.evidence_span)


if __name__ == "__main__":
    unittest.main()
