from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
import sys

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "runtime" / "scripts"))
from reading_view import load_reading_view  # noqa: E402
from source_projection import build_paper_map  # noqa: E402
from formula_projection import build_formula_index  # noqa: E402


SCHEMA_ROOT = ROOT / "paper-learning-map" / "schemas"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _confirmed_ckpt1(project: Path, digest_path: Path, digest: dict) -> bool:
    """Return true only for a hash-bound, explicitly confirmed CKPT-1.

    ``digest.json`` intentionally remains an extractive pending artifact even
    after confirmation.  The checkpoint record is therefore the only safe
    downstream signal that the source/evidence bundle crossed CKPT-1.  Missing,
    malformed, stale, or unconfirmed records fail closed to ``tutor_only``.
    """

    checkpoint_path = project / "checkpoint-1.json"
    if not checkpoint_path.is_file():
        return False
    try:
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(checkpoint, dict) or checkpoint.get("checkpoint") != "CKPT-1":
        return False
    if checkpoint.get("status") not in {"confirmed", "approved"}:
        return False
    if not isinstance(checkpoint.get("confirmed_by"), str) or not checkpoint["confirmed_by"].strip():
        return False
    artifact = checkpoint.get("artifact")
    if not isinstance(artifact, dict) or not isinstance(artifact.get("path"), str) or not isinstance(artifact.get("sha256"), str):
        return False
    try:
        artifact_path = Path(artifact["path"]).resolve(strict=True)
    except (OSError, ValueError):
        return False
    if artifact_path != digest_path.resolve() or _sha256(digest_path).casefold() != artifact["sha256"].casefold():
        return False
    source = digest.get("source") if isinstance(digest, dict) else None
    identity = checkpoint.get("source_identity")
    if not isinstance(source, dict) or not isinstance(identity, dict):
        return False
    for field in ("requested_identifier", "resolved_identifier", "pdf_sha256", "fetched_at"):
        if source.get(field) != identity.get(field):
            return False
    readiness = checkpoint.get("readiness_artifact")
    if not isinstance(readiness, dict) or not isinstance(readiness.get("path"), str) or not isinstance(readiness.get("sha256"), str):
        return False
    try:
        readiness_path = Path(readiness["path"]).resolve(strict=True)
        readiness_payload = json.loads(readiness_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return (
        readiness_payload.get("status") == "ready_for_human_approval"
        and _sha256(readiness_path).casefold() == readiness["sha256"].casefold()
    )


def _validated_write(path: Path, value: dict, schema_name: str) -> None:
    schema = json.loads((SCHEMA_ROOT / schema_name).read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda error: list(error.path))
    if errors:
        location = ".".join(str(part) for part in errors[0].path) or "$"
        raise ValueError(f"generated {schema_name} is invalid at {location}: {errors[0].message}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a source-grounded Paper Learning Map")
    parser.add_argument("--project", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    project = Path(args.project).resolve(); out = Path(args.out).resolve(); out.mkdir(parents=True, exist_ok=True)
    digest_path = project / "digest.json"
    digest = json.loads(digest_path.read_text(encoding="utf-8")) if digest_path.is_file() else None
    try:
        view = load_reading_view(project, digest=digest)
    except Exception as exc:
        raise SystemExit(f"cannot build Paper Learning Map: upstream reading view is not valid: {exc}") from exc
    verification_level = "scholar_slides_validated" if _confirmed_ckpt1(project, digest_path, digest or {}) else "tutor_only"
    paper_map = build_paper_map(view, project.name, verification_level=verification_level)
    identity = paper_map["paper_identity"]
    tutor_state = {"schema_version": "1.0", "paper_identity": {"source_pdf_sha256": identity["source_pdf_sha256"]}, "nodes": {}}
    study_state = {"schema_version": "1.0", "paper_identity": {"source_pdf_sha256": identity["source_pdf_sha256"]}, "nodes": {node["id"]: {"status": "unseen", "mastery": 0, "important": False, "confusing": False, "last_reviewed_at": ""} for node in paper_map["nodes"]}}
    _validated_write(out / "paper-map.json", paper_map, "paper-map.schema.json")
    _validated_write(out / "tutor-state.json", tutor_state, "tutor-state.schema.json")
    _validated_write(out / "study-state.json", study_state, "study-state.schema.json")
    if verification_level == "scholar_slides_validated":
        formula_index = build_formula_index(paper_map, tutor_state, view, digest or {})
        _validated_write(out / "formula-index.json", formula_index, "formula-index.schema.json")
    print(out / "paper-map.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
