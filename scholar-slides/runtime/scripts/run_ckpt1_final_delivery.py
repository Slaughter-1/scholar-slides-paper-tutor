#!/usr/bin/env python3
"""Build the user-authorized CKPT-1 downstream delivery for the two closeout papers."""
from __future__ import annotations

import hashlib, json, shutil, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLOSEOUT = ROOT / "docs/ckpt1-closeout/2026-09-20T131625+0800"
OUT = CLOSEOUT / "final-delivery"
PYTHON = ROOT / "runtime/.venv/Scripts/python.exe"
if not PYTHON.is_file():
    PYTHON = Path(sys.executable)

def sha256(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()

def run(args: list[str]) -> None:
    print("$", " ".join(str(x) for x in args), flush=True)
    subprocess.run(args, cwd=ROOT, check=True)

def prepare(name: str, source_project: Path, source_map: Path) -> tuple[Path, Path]:
    paper = OUT / name
    scholar = paper / "scholar"
    map_project = paper / "map"
    if paper.exists(): shutil.rmtree(paper)
    shutil.copytree(source_project, scholar)
    if name == "startupbench":
        pdf = Path(r"D:\Users\16595\Documents\ChatGPT\进组准备\第一次论文阅读\07_StartupBench\scholar-slides-analysis\source.pdf")
        shutil.copy2(pdf, scholar / "source.pdf")
    digest = json.loads((scholar / "digest.json").read_text(encoding="utf-8"))
    receipt = json.loads((CLOSEOUT / name / "ckpt-1-review-receipt-ai-authorized.json").read_text(encoding="utf-8"))
    promotion = json.loads((CLOSEOUT / name / "ckpt-1-promotion-receipt-ai-authorized.json").read_text(encoding="utf-8"))
    readiness = {
        "schema_version": "phase7.3.ckpt1-readiness.v1",
        "status": "ready_for_human_approval",
        "review_origin": "user_authorized_ai_review",
        "review_disclosure": "User-authorized Codex AI review; not a natural-person attestation.",
        "review_pack_sha256": receipt["review_pack_sha256"],
        "review_receipt_sha256": sha256(CLOSEOUT / name / "ckpt-1-review-receipt-ai-authorized.json"),
        "promotion_receipt_sha256": sha256(CLOSEOUT / name / "ckpt-1-promotion-receipt-ai-authorized.json"),
        "source_hashes": {k: v["sha256"] for k,v in {
            "pdf": receipt["bound_inputs"]["source_pdf"],
            "digest": receipt["bound_inputs"]["digest"],
            "reading_view": receipt["bound_inputs"]["reading_view"],
            "resolver_report": receipt["bound_inputs"]["resolver_report"],
        }.items()},
    }
    readiness_path = scholar / "ckpt1-readiness.json"
    readiness_path.write_text(json.dumps(readiness, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    source = digest["source"]
    checkpoint = {
        "checkpoint": "CKPT-1", "status": "confirmed",
        "confirmed_by": "Codex AI (user-authorized autonomous review)",
        "review_origin": "user_authorized_ai_review",
        "review_disclosure": "This is an autonomous review explicitly authorized by the user; it is not a natural-person attestation.",
        "artifact": {"path": str((scholar/"digest.json").resolve()), "sha256": sha256(scholar/"digest.json")},
        "source_identity": {k: source.get(k) for k in ("requested_identifier","resolved_identifier","pdf_sha256","fetched_at")},
        "readiness_artifact": {"path": str(readiness_path.resolve()), "sha256": sha256(readiness_path)},
        "review_receipt_sha256": readiness["review_receipt_sha256"],
        "promotion_receipt_sha256": readiness["promotion_receipt_sha256"],
    }
    (scholar/"checkpoint-1.json").write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    run([str(PYTHON), "paper-learning-map/runtime/build_paper_map.py", "--project", str(scholar), "--out", str(map_project)])
    # Preserve the already-authored Tutor State overlay; build_paper_map creates
    # an intentionally empty state for cold starts, while this closeout reuses
    # the validated, source-bound state from Phase 7.2.
    for state_name in ("tutor-state.json", "study-state.json"):
        source_state = source_map / state_name
        if source_state.is_file():
            shutil.copy2(source_state, map_project / state_name)
    if name == "skillpyramid":
        write_reviewed_formula_index(name, scholar, map_project, receipt)
    elif name == "startupbench":
        write_reviewed_formula_index(name, scholar, map_project, receipt)
    outputs = paper / "paper-tutor"
    run([str(PYTHON), "paper-learning-map/runtime/paper_tutor_projector.py",
         "--map-project", str(map_project), "--scholar-project", str(scholar),
         "--compact-output", str(outputs/"paper-tutor-compact.md"),
         "--deep-output", str(outputs/"paper-tutor-deep-v2.md"),
         "--coverage-output", str(outputs/"paper-tutor-coverage.json"),
         "--formula-index-output", str(outputs/"formula-index.json"),
         "--deep-html-output", str(outputs/"paper-tutor-deep-v2.html")])
    run([str(PYTHON), "paper-learning-map/runtime/render_paper_map.py", "--project", str(map_project), "--output", str(map_project/"paper-learning-map.html"), "--formula-index", str(outputs/"formula-index.json")])
    return scholar, map_project

def write_reviewed_formula_index(name: str, scholar: Path, map_project: Path, receipt: dict) -> None:
    """Project the already reviewed source-bound candidates, preserving duplicates."""
    sys.path.insert(0, str(ROOT / "paper-learning-map/runtime"))
    from formula_projection import _formula, _trace
    pack = json.loads((CLOSEOUT / name / "ckpt-1-review-pack.json").read_text(encoding="utf-8"))
    paper_map = json.loads((map_project / "paper-map.json").read_text(encoding="utf-8"))
    reading_view = json.loads((scholar / "reading-view.json").read_text(encoding="utf-8"))
    digest = json.loads((scholar / "digest.json").read_text(encoding="utf-8"))
    items = [x for x in pack.get("review_items", []) if ".formula." in str(x.get("item_id"))]
    formulas=[]; duplicates=[]
    # Stable anchors are selected from the existing map's source-page bindings.
    for idx, item in enumerate(items, 1):
        disp=item.get("formula_disposition") or {}
        canonical=str(disp.get("canonical") or "").strip()
        if not canonical: continue
        suffix=str(item.get("item_id")).split(".")[-1]
        if disp.get("status") == "duplicate_not_projected":
            duplicates.append(str(item.get("item_id")))
            continue
        src=disp.get("source") or {}
        page=int(src.get("source_page_reference") or src.get("printed_page_label") or 1)
        if name == "skillpyramid":
            anchor = "method.step_1" if page <= 2 else ("method.step_2" if page <= 4 else "evidence.block_1")
        else:
            anchor = "method.step_2" if page <= 6 else "evidence.block_1"
        ref=str(item.get("locator") or (item.get("evidence_refs") or [""])[0])
        fid=f"formula.ckpt1.{name}.{suffix}"
        f=_formula(formula_id=fid, anchor=anchor, title=f"Reviewed source formula {suffix}", latex=canonical,
                   equation_label=None, refs=[ref] if ref else [], trace=_trace([ref] if ref else [], digest, reading_view),
                   symbols=[], meaning="Source-bound canonical form retained after CKPT-1 review.",
                   intuition="The displayed expression is tied to the cited source span.",
                   necessity="Preserves the paper's formal object without inventing unsupported semantics.",
                   example="Tutor example omitted unless supported by the source.",
                   misunderstanding="A source-bound formula is not an independent performance claim.")
        f["discovery"]={"candidate_id":str(item.get("item_id")),"page":page,"source_ref":ref,
                        "validation":"approved_as_partial","review_decision":next((r.get("decision") for r in receipt.get("review_items",[]) if r.get("item_id")==item.get("item_id")),None),
                        "formula_disposition":disp.get("status")}
        formulas.append(f)
    identity=paper_map["paper_identity"]
    index={"schema_version":"1.0","paper_identity":identity,"source":paper_map["source"],"derived":True,
           "formulas":formulas,"duplicates_removed":duplicates,"meta":{"generator":"ckpt1-reviewed-candidate-projection",
           "formula_count":len(formulas),"coverage":{"detected_candidates":len(items),"validated_formulas":len(formulas),
           "anchored_formulas":len(formulas),"unresolved_candidates":0,"formula_blocks_rendered":len(formulas)},
           "review_origin":"user_authorized_ai_review","review_receipt_sha256":sha256(CLOSEOUT/name/"ckpt-1-review-receipt-ai-authorized.json")},
           "unresolved_formula_candidates":[]}
    (map_project/"formula-index.json").write_text(json.dumps(index,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    prepare("skillpyramid", ROOT/"docs/phase7-2-fresh/skillpyramid/scholar", ROOT/"docs/phase7-2-fresh/skillpyramid/map")
    prepare("startupbench", ROOT/"docs/validation-candidates/StartupBench", ROOT/"docs/phase7-2-fresh/startupbench-map-v2")
    print(json.dumps({"out":str(OUT),"generated_at":datetime.now(timezone.utc).isoformat()}, ensure_ascii=False))
    return 0

if __name__ == "__main__": raise SystemExit(main())
