"""
Scores the extraction review: word error rate of plain PyMuPDF text vs our glyph-recovered text.
WER here = marked-wrong words / words shown, counted over the pages the reviewer ticked as checked.

Usage:  python tools/score_extraction.py extraction_review_results.csv [review/extraction_key.json]
"""
import os
import sys
import csv
import json
from collections import Counter

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main(results, keyfile):
    key = json.load(open(keyfile, encoding="utf-8"))
    shown, wrong = Counter(), Counter()
    pages, bad_pages = set(), Counter()
    seen_bad = set()
    with open(results, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            method = key[r["page_id"]][r["version"]]
            if r["kind"] == "checked":
                shown[method] += int(r["words_in_view"] or 0)
                pages.add(r["page_id"])
            else:
                wrong[method] += 1
                if (r["page_id"], method) not in seen_bad:
                    seen_bad.add((r["page_id"], method))
                    bad_pages[method] += 1
    n = len(pages)
    if not n:
        sys.exit("no checked pages")
    print(f"pages checked: {n}\n")
    print(f"{'method':<12}{'words':>8}{'wrong':>8}{'WER':>9}{'pages with any error':>24}")
    for m in ("plain", "recovered"):
        if shown[m]:
            print(f"{m:<12}{shown[m]:>8}{wrong[m]:>8}{100 * wrong[m] / shown[m]:>8.1f}%{bad_pages[m]:>14} of {n}")


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(here), "review", "extraction_key.json"))
