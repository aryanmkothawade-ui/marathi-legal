"""
Turns the CSV downloaded from the review sheet into numbers.

  recall    = correctly masked / (correctly masked + missed)       -> how much personal info we caught
  precision = correctly masked / all placeholders                   -> how little harmless text we hid
where  correctly masked = placeholders shown - over-masked.
Reviewers mark misses, so these are estimates over the reviewed excerpts only; report the number of documents too.

Usage:  python tools/score_review.py anonymizer_review_results.csv
"""
import sys
import csv
from collections import Counter, defaultdict

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main(path):
    reviewed, ph = set(), 0
    kinds = defaultdict(Counter)
    texts = defaultdict(Counter)
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r["kind"] == "reviewed":
                reviewed.add(r["doc_id"])
                ph += int(r["placeholders_in_view"] or 0)
            else:
                kinds[r["doc_id"]][r["kind"]] += 1
                texts[r["kind"]][r["text"]] += 1
    n = len(reviewed)
    if not n:
        sys.exit("no reviewed documents in the file")
    miss = sum(kinds[d]["miss"] for d in reviewed)
    over = sum(kinds[d]["over"] for d in reviewed)
    good = ph - over
    with_miss = sum(1 for d in reviewed if kinds[d]["miss"])
    print(f"documents reviewed        : {n}")
    print(f"placeholders shown        : {ph}   (over-masked: {over})")
    print(f"missed personal info      : {miss}   in {with_miss} documents ({100 * with_miss / n:.0f}% of documents have >= 1 miss)")
    print(f"estimated recall          : {100 * good / (good + miss):.1f}%")
    print(f"estimated precision       : {100 * good / ph:.1f}%" if ph else "estimated precision: n/a")
    print("\nmost frequent missed words :", texts["miss"].most_common(15))
    print("most frequent over-masked  :", texts["over"].most_common(15))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
