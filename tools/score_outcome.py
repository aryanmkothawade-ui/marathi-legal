"""
Scores the pipeline's outcome labels against the human labels from the outcome review sheet.

  per-class precision : of the documents the pipeline called X, how many did the human also call X
                        (valid directly, the sample was drawn per pipeline label)
  overall accuracy    : re-weighted by how many documents of each pipeline label exist in the corpus
  recall per class    : estimated the same way (re-weighted), so the rare classes are not over-counted
A human `unclear` counts as the class `unknown` (decision not visible in the text).

Usage:  python tools/score_outcome.py outcome_review_results.csv [review/outcome_key.json]
"""
import os
import sys
import csv
import json
from collections import Counter, defaultdict

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CLASSES = ["allowed", "dismissed", "partially_allowed", "remanded", "disposed", "unknown"]


def main(results, keyfile):
    key = json.load(open(keyfile, encoding="utf-8"))
    pred_of, pop = key["pipeline_label"], key["population"]
    human = {}
    with open(results, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            human[r["doc_id"]] = r["human_label"]
    rows = [(pred_of[d], h) for d, h in human.items() if d in pred_of]
    unclear = sum(1 for _, h in rows if h == "unclear")
    rows = [(p, "unknown" if h == "unclear" else h) for p, h in rows]      # "unclear" = the decision is not visible = unknown
    if not rows:
        sys.exit("no usable labels")
    n_by = Counter(p for p, _ in rows)
    right = Counter(p for p, h in rows if p == h)
    print(f"labelled documents: {len(human)}   of which unclear: {unclear}\n")
    print(f"{'pipeline label':<20}{'n':>5}{'precision':>12}{'population':>12}")
    total_pop = acc = 0.0
    for c in CLASSES:
        if not n_by[c]:
            continue
        prec = right[c] / n_by[c]
        w = pop.get(c, 0)
        total_pop += w
        acc += prec * w
        print(f"{c:<20}{n_by[c]:>5}{100 * prec:>11.0f}%{w:>12}")
    print(f"\nestimated overall accuracy (population-weighted): {100 * acc / total_pop:.1f}%")
    # re-weighted confusion: each sampled row stands for pop[p] / n_by[p] documents
    est = defaultdict(float)
    for p, h in rows:
        est[(p, h)] += pop.get(p, 0) / n_by[p]
    print("\nestimated recall per human label (what share of the true class the pipeline found):")
    for c in CLASSES:
        tot = sum(v for (p, h), v in est.items() if h == c)
        if tot:
            print(f"  {c:<20}{100 * est[(c, c)] / tot:>5.0f}%   (estimated {tot:.0f} such documents in the corpus)")
    print("\nmost common confusions (pipeline -> human):")
    wrong = Counter({(p, h): v for (p, h), v in est.items() if p != h})
    for (p, h), v in wrong.most_common(8):
        print(f"  {p} -> {h}: ~{v:.0f} documents")


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(here), "review", "outcome_key.json"))
