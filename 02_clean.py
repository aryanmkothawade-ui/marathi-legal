"""
Stage 2: Cleaning & normalisation  (rewritten — runs on the repaired text from 01b_fix_glyphs.py)

For every document in <in-dir> (pages separated by "\n\f\n"):
  1. character-level normalisation (NFC, newline-like chars, zero-width chars, control chars, U+FFFD, digits)
  2. page furniture removal (page numbers, repeated headers/footers, file stamps, end marks)
  3. translation disclaimer / heading removal
  4. paragraph reconstruction from wrapped lines
  5. filters: too short, not Marathi, source-defective (from the stage-1b log), exact and near duplicates

Output: <out-dir>/<doc_id>.txt   (paragraphs separated by a blank line)
        <log>                    per-document stats and the reason for every rejected document

Usage: python 02_clean.py [--in-dir D] [--out-dir D] [--log F] [--glyph-log F] [--keep-defective]
                          [--keep-devanagari-digits] [--workers N]
"""
import os
import sys
import json
import argparse
import concurrent.futures as cf

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import textclean as tc

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.environ.get("MLDC_BASE", os.path.dirname(HERE))
MIN_CHARS = 200
MIN_DEVA_RATIO = 0.5          # Devanagari share of all letters
MAX_UNKNOWN_MARKS = 0.005     # share of characters that were unlabeled glyphs


def process_one(args):
    path, keep_digits = args
    doc_id = os.path.splitext(os.path.basename(path))[0]
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    cleaned, st = tc.clean_document(raw, keep_devanagari_digits=keep_digits)
    st.update({"doc_id": doc_id, "raw_chars": len(raw), "clean_chars": len(cleaned),
               "deva_ratio": round(tc.devanagari_ratio(cleaned), 3)})
    st["unknown_mark_share"] = round(st["unknown_glyph_marks"] / max(len(raw), 1), 5)
    st["_simhash"] = tc.simhash(cleaned)              # computed in the worker; removed again before the log is written
    return doc_id, cleaned, st


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in-dir", default=os.path.join(BASE_DIR, "corpus", "raw_text"))
    ap.add_argument("--out-dir", default=os.path.join(BASE_DIR, "corpus", "cleaned"))
    ap.add_argument("--log", default=os.path.join(BASE_DIR, "logs", "clean_log.json"))
    ap.add_argument("--glyph-log", default=os.path.join(BASE_DIR, "corpus", "glyph_fix_log.json"))
    ap.add_argument("--keep-defective", action="store_true", help="do not reject source-defective PDFs")
    ap.add_argument("--keep-devanagari-digits", action="store_true")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    a = ap.parse_args()

    os.makedirs(a.out_dir, exist_ok=True)
    os.makedirs(os.path.dirname(a.log), exist_ok=True)
    for f in os.listdir(a.out_dir):                       # outputs are rebuilt every run so rejected docs never linger
        if f.endswith(".txt"):
            os.remove(os.path.join(a.out_dir, f))

    glyph = {}
    if os.path.exists(a.glyph_log):
        glyph = {r["doc_id"]: r for r in json.load(open(a.glyph_log, encoding="utf-8")) if r.get("status") == "ok"}

    files = sorted(os.path.join(a.in_dir, f) for f in os.listdir(a.in_dir) if f.endswith(".txt"))
    print("=" * 65 + "\n  MLDC -- Stage 2: Cleaning & Normalization\n" + "=" * 65)
    print(f"  documents: {len(files)}   workers: {a.workers}")

    results = {}
    with cf.ProcessPoolExecutor(max_workers=a.workers) as ex:
        for i, (doc_id, cleaned, st) in enumerate(ex.map(process_one, [(p, a.keep_devanagari_digits) for p in files], chunksize=8), 1):
            results[doc_id] = (cleaned, st)
            if i % 1000 == 0:
                print(f"  [{i}/{len(files)}]", flush=True)

    log, keep = [], []
    for doc_id, (cleaned, st) in results.items():
        g = glyph.get(doc_id, {})
        st["source_defective"] = bool(g.get("source_defective"))
        st["glyph_needs_review"] = bool(g.get("needs_review"))
        if st["clean_chars"] < MIN_CHARS:
            st["status"] = "rejected_short"
        elif st["deva_ratio"] < MIN_DEVA_RATIO:
            st["status"] = "rejected_language"
        elif st["source_defective"] and not a.keep_defective:
            st["status"] = "rejected_defective"
        elif st["unknown_mark_share"] > MAX_UNKNOWN_MARKS and not a.keep_defective:
            st["status"] = "rejected_defective"
        else:
            st["status"] = "ok"
            keep.append(doc_id)
        log.append(st)

    # exact duplicates, then near duplicates; keep the longest non-flagged copy
    seen, byid = {}, {s["doc_id"]: s for s in log}
    for doc_id in keep[:]:
        h = tc.sha256(results[doc_id][0])
        if h in seen:
            byid[doc_id]["status"] = "duplicate"; byid[doc_id]["duplicate_of"] = seen[h]; keep.remove(doc_id)
        else:
            seen[h] = doc_id
    items = [(d, results[d][1]["_simhash"], results[d][1]["clean_chars"] - (10 ** 6 if byid[d]["glyph_needs_review"] else 0)) for d in keep]
    for d, k in tc.near_duplicates(items).items():
        byid[d]["status"] = "near_duplicate"; byid[d]["duplicate_of"] = k; keep.remove(d)

    for doc_id in keep:
        with open(os.path.join(a.out_dir, doc_id + ".txt"), "w", encoding="utf-8") as f:
            f.write(results[doc_id][0])
    for st in log:
        st.pop("_simhash", None)
    with open(a.log, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=1)

    from collections import Counter
    c = Counter(s["status"] for s in log)
    print("=" * 65)
    print("  " + "   ".join(f"{k}: {v}" for k, v in c.most_common()))
    print(f"  removed: page numbers {sum(s['page_numbers'] for s in log)}, repeated headers {sum(s['repeated_headers'] for s in log)}, "
          f"boilerplate blocks {sum(s['boilerplate_removed'] for s in log)}")
    print(f"[OK] cleaned -> {a.out_dir}\n[OK] log     -> {a.log}")


if __name__ == "__main__":
    main()
