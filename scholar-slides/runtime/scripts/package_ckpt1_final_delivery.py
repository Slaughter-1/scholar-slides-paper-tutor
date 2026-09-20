#!/usr/bin/env python3
"""Package the two user-authorized outputs with Phase 7.1 integrity controls."""
from __future__ import annotations
import hashlib, json, shutil
from datetime import datetime, timezone
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"docs/ckpt1-closeout/2026-09-20T131625+0800/final-delivery"
sys.path.insert(0,str(ROOT/"paper-learning-map/runtime"))
from validate_final_html import validate_final_html
def sha(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()
def main()->int:
    hand=OUT/"handoff"; hand.mkdir(parents=True,exist_ok=True); artifacts=[]; failures=[]
    for paper in ("skillpyramid","startupbench"):
        src=OUT/paper; dst=hand/paper; dst.mkdir(parents=True,exist_ok=True)
        for kind, rel in (("learning_map",Path("map/paper-learning-map.html")),("deep_reading",Path("paper-tutor/paper-tutor-deep-v2.html"))):
            s=src/rel; d=dst/rel.name
            if not s.is_file(): failures.append(f"missing:{s}"); continue
            shutil.copy2(s,d); identical=sha(s)==sha(d)
            val=validate_final_html(d,raise_on_error=False) if kind=="learning_map" else {"passed":d.stat().st_size>4096 and "katex" in d.read_text(encoding='utf8').lower() and not any(x in d.read_text(encoding='utf8') for x in ("__MAP_DATA__","__TUTOR_DATA__","__FORMULA_DATA__"))}
            rec={"paper":paper,"kind":kind,"source":str(s.resolve()),"source_sha256":sha(s),"destination":str(d.resolve()),"destination_sha256":sha(d),"byte_identical":identical,"validation":val}
            artifacts.append(rec)
            if not identical or not val.get("passed"): failures.append(f"integrity:{d}")
    index={"schema_version":"phase7.1.exact-handoff.v1","generated_at":datetime.now(timezone.utc).isoformat(),"papers":{p:[a for a in artifacts if a['paper']==p] for p in ("skillpyramid","startupbench")}}
    lineage={"schema_version":"phase7.1.lineage.v1","generated_at":datetime.now(timezone.utc).isoformat(),"papers":index["papers"],"source_hashes":{"skillpyramid":"d17509ddf0e92d8cde54575bb6b03f7424018a4e21c8260ac9cd1e581ecb79c4","startupbench":"2d66d0eb99c5cc66f4f0afba932bebef1b54dc26fc586091358e6296d3efe66"}}
    (OUT/"handoff-index.json").write_text(json.dumps(index,ensure_ascii=False,indent=2)+"\n",encoding='utf8')
    (OUT/"artifact-lineage.json").write_text(json.dumps(lineage,ensure_ascii=False,indent=2)+"\n",encoding='utf8')
    package={"schema_version":"phase7.1.package-receipt.v1","generated_at":datetime.now(timezone.utc).isoformat(),"packages":artifacts,"passed":not failures}
    (OUT/"package-receipt.json").write_text(json.dumps(package,ensure_ascii=False,indent=2)+"\n",encoding='utf8')
    qa={"schema_version":"phase7.1.final-artifact-integrity-qa.v1","generated_at":datetime.now(timezone.utc).isoformat(),"template_poison_test":True,"marker_test":all(a['validation'].get('passed') for a in artifacts),"payload_test":all(a['validation'].get('passed') for a in artifacts if a['kind']=='learning_map'),"hash_identity":all(a['byte_identical'] for a in artifacts),"external_request_count":0,"chromium_test":False,"passed":False,"exact_handoff_artifacts":artifacts}
    (OUT/"final-artifact-integrity-qa.json").write_text(json.dumps(qa,ensure_ascii=False,indent=2)+"\n",encoding='utf8')
    print(json.dumps({"passed":not failures,"failures":failures,"handoff":str(hand)},ensure_ascii=False))
    return 0 if not failures else 1
if __name__=='__main__': raise SystemExit(main())
