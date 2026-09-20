"""Evidence-bound cold-start Formula QA for a previously uncurated paper.

The runner intentionally refuses an input ``formula-index.json``.  It derives
the presentation index from Scholar-Slides structured artifacts, validates the
identity/source gate, and writes only derived QA outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from formula_projection import (
    build_formula_index_from_paths,
    formula_index_digest,
    validate_formula_index_binding,
    write_formula_index,
)
from paper_tutor_projector import Projection


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run(map_project: Path, scholar_project: Path, output: Path) -> dict[str, Any]:
    map_project = map_project.resolve(); scholar_project = scholar_project.resolve(); output = output.resolve()
    prefilled = map_project / "formula-index.json"
    if prefilled.exists():
        raise ValueError(f"cold-start input must not contain formula-index.json: {prefilled}")
    paper_map = load(map_project / "paper-map.json")
    tutor_state = load(map_project / "tutor-state.json")
    reading_view = load(scholar_project / "reading-view.json")
    digest = load(scholar_project / "digest.json")
    source = paper_map.get("source") or {}
    if source.get("mode") != "integrated" or source.get("verification_level") != "scholar_slides_validated":
        raise ValueError("cold-start source gate requires integrated + scholar_slides_validated")
    before = {name: sha256(root / name) for root, name in ((scholar_project, "digest.json"), (scholar_project, "reading-view.json"), (map_project, "paper-map.json"))}
    index = build_formula_index_from_paths(map_project, scholar_project)
    validate_formula_index_binding(index, paper_map)
    output.mkdir(parents=True, exist_ok=True)
    index_path = write_formula_index(index, output / "formula-index.json")
    projection = Projection(paper_map, tutor_state, reading_view, digest, formula_index=index)
    deep = projection.deep()
    deep_path = output / "paper-tutor-deep-v2.md"; deep_path.write_text(deep, encoding="utf-8")
    html_path = output / "paper-tutor-deep-v2.html"; html_path.write_text(projection.deep_html(), encoding="utf-8")
    coverage = projection.coverage(deep)
    coverage["formula_index_sha256"] = formula_index_digest(index)
    coverage["formula_index"] = str(index_path)
    coverage["deep"] = str(deep_path)
    coverage["deep_html"] = str(html_path)
    coverage["no_prefilled_formula_index"] = True
    coverage["source_gate"] = source
    coverage["source_hashes_before"] = before
    coverage["source_hashes_after"] = {name: sha256(root / name) for root, name in ((scholar_project, "digest.json"), (scholar_project, "reading-view.json"), (map_project, "paper-map.json"))}
    coverage["source_hashes_unchanged"] = coverage["source_hashes_before"] == coverage["source_hashes_after"]
    (output / "formula-cold-start-coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return coverage


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map-project", required=True)
    parser.add_argument("--scholar-project", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(run(Path(args.map_project), Path(args.scholar_project), Path(args.output)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
