"""Quick look at the final corpus:  python check_corpus.py [<base-dir>]

Prints a few documents' metadata and section sizes from <base>/corpus/final/mldc_v1.jsonl and the quality counts.
"""
import os
import sys
import json
from collections import Counter

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("MLDC_BASE", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PATH = os.path.join(BASE, "corpus", "final", "mldc_v1.jsonl")
rows = [json.loads(l) for l in open(PATH, encoding="utf-8")]
print(f"{len(rows)} documents in {PATH}\n")
q = Counter(r["quality"]["segmentation_confidence"] for r in rows)
print("segmentation confidence:", dict(q))
print("outcomes:", dict(Counter(r["labels"]["outcome_normalized"] for r in rows)))
print("case types:", dict(Counter(r["metadata"]["case_type"] for r in rows).most_common(6)))
print("all fully anonymized:", all(r["quality"]["anonymized"] for r in rows))
for r in rows[:3]:
    m, s = r["metadata"], r["content"]["sections"]
    print(f"\n--- {r['doc_id']}  {m.get('court')} | {m.get('case_type')} | {m.get('year')} | outcome: {r['labels']['outcome_normalized']}")
    print("    parties:", r["parties"])
    print("    chars:", {k: len(v) for k, v in s.items()})
    print("    result:", repr(s["case_result"][:160]))
