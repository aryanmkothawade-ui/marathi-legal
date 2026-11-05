"""
Stage 3: Document segmentation  (rewritten — the logic lives in segmenter.py)

For every cleaned document it
  * recognises the document family (Bombay High Court judgment / Supreme Court reported translation / other),
  * splits it into header, headnote (SC only), facts, petitioner arguments, respondent arguments, the court's
    reasoning (key `judges_summary`) and the operative part (`case_result`),
  * extracts court, bench, case type, case number, case year, decision year and date,
  * decides the outcome (allowed / dismissed / partially_allowed / remanded / disposed / unknown) from the
    operative part and stores the evidence sentence it was based on.

Output: <out-dir>/<doc_id>.json   and   <log> with per-document quality fields.
Usage:  python 03_segment.py [--in-dir D] [--out-dir D] [--log F] [--workers N]
"""
import os
import sys
import json
import argparse
import concurrent.futures as cf
from collections import Counter

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import segmenter

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.environ.get("MLDC_BASE", os.path.dirname(HERE))


def work(args):
    in_dir, out_dir, fname = args
    doc_id = os.path.splitext(fname)[0]
    with open(os.path.join(in_dir, fname), encoding="utf-8") as f:
        text = f.read()
    result = segmenter.segment_document(doc_id, text)
    with open(os.path.join(out_dir, doc_id + ".json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    m, q, lab = result["metadata"], result["quality"], result["labels"]
    return {"doc_id": doc_id, "family": m["family"], "case_type": m["case_type"], "case_number": m["case_number"], "year": m["year"],
            "outcome": lab["outcome_normalized"], "certainty": result["outcome_evidence"]["certainty"],
            "segmentation_confidence": q["segmentation_confidence"], "has_result_section": q["has_result_section"],
            "body_sections_filled": q["body_sections_filled"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in-dir", default=os.path.join(BASE_DIR, "corpus", "cleaned"))
    ap.add_argument("--out-dir", default=os.path.join(BASE_DIR, "corpus", "segmented"))
    ap.add_argument("--log", default=os.path.join(BASE_DIR, "logs", "segment_log.json"))
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    os.makedirs(os.path.dirname(a.log), exist_ok=True)
    for f in os.listdir(a.out_dir):                      # rebuilt every run: documents rejected by stage 2 must not linger
        if f.endswith(".json"):
            os.remove(os.path.join(a.out_dir, f))
    files = sorted(f for f in os.listdir(a.in_dir) if f.endswith(".txt"))
    print("=" * 65 + "\n  MLDC -- Stage 3: Segmentation\n" + "=" * 65)
    print(f"  documents: {len(files)}   workers: {a.workers}")
    with cf.ProcessPoolExecutor(max_workers=a.workers) as ex:
        log = list(ex.map(work, [(a.in_dir, a.out_dir, f) for f in files], chunksize=20))
    with open(a.log, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=1)
    n = len(log)
    pct = lambda k: f"{100 * sum(1 for r in log if k(r)) / n:.0f}%"
    print("=" * 65)
    print("  confidence:", dict(Counter(r["segmentation_confidence"] for r in log)))
    print("  outcomes  :", dict(Counter(r["outcome"] for r in log).most_common()))
    print(f"  no case type {pct(lambda r: r['case_type'] is None)}   no case number {pct(lambda r: r['case_number'] is None)}   "
          f"no result section {pct(lambda r: not r['has_result_section'])}   outcome unknown {pct(lambda r: r['outcome'] == 'unknown')}")
    print(f"[OK] segmented -> {a.out_dir}\n[OK] log       -> {a.log}")


if __name__ == "__main__":
    main()
