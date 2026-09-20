from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from tutor_state import TutorStateStore, _atomic_json, _validate_study_state


def main() -> int:
    parser = argparse.ArgumentParser(description="Update downstream Paper Learning Map state")
    parser.add_argument("--project", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("mark-learning", "mark-understood", "mark-mastered"):
        p = sub.add_parser(name); p.add_argument("node_id")
    p = sub.add_parser("mark-important"); p.add_argument("node_id"); p.add_argument("value", choices=("true", "false"))
    p = sub.add_parser("mark-confusing"); p.add_argument("node_id"); p.add_argument("value", choices=("true", "false"))
    p = sub.add_parser("add-question"); p.add_argument("node_id"); p.add_argument("question")
    args = parser.parse_args(); project = Path(args.project).resolve()
    study_path = project / "study-state.json"
    store = TutorStateStore(project)
    study = json.loads(study_path.read_text(encoding="utf-8"))
    expected = store.paper_map.get("paper_identity", {}).get("source_pdf_sha256")
    actual = study.get("paper_identity", {}).get("source_pdf_sha256")
    if expected != actual:
        raise SystemExit("study-state paper identity does not match paper-map")
    _validate_study_state(study)
    now = datetime.now(timezone.utc).isoformat(); node_id = args.node_id
    if node_id not in study["nodes"]: raise SystemExit(f"unknown node: {node_id}")
    state = study["nodes"][node_id]; state["last_reviewed_at"] = now
    if args.command.startswith("mark-") and args.command not in {"mark-important", "mark-confusing"}:
        state["status"] = args.command.removeprefix("mark-"); state["mastery"] = {"learning": 1, "understood": 2, "mastered": 3}[state["status"]]
    elif args.command == "mark-important": state["important"] = args.value == "true"
    elif args.command == "mark-confusing": state["confusing"] = args.value == "true"
    else:
        store.add_user_question(node_id=node_id, question=args.question, answer="", important=True, study_path=study_path)
        store.save()
        # add_user_question performs the validated atomic study-state update.
        # Do not write the stale snapshot loaded above: doing so would revert
        # an unseen -> learning transition.
        return 0
    _validate_study_state(study)
    _atomic_json(study_path, study)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
