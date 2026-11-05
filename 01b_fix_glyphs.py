"""
Stage 1b: Glyph-recovery text extraction  (drop-in replacement for 01_extract.py on this corpus)

Most PDFs here use subset fonts with a broken ToUnicode map, so plain extraction gives text like
'अ\\x13ुवाद' / 'आलिर्ण' instead of 'अनुवाद' / 'आणि' (see glyphfix.py for the full explanation).
This stage repairs the text deterministically, without OCR, using glyph_map.json.

Output
  <out-dir>/<doc_id>.txt     one file per PDF; pages are separated by "\\n\\f\\n"
  <log>                      per-document quality metrics (JSON), used by later stages to flag bad docs

Per-document flags in the log
  source_defective   the PDF itself renders as overprinted junk (many glyphs with no valid label) — not recoverable
  needs_review       residual control characters / invalid word starts above threshold

Usage
  python 01b_fix_glyphs.py --pdf-dir <pdfs> --out-dir <raw_text> [--log logs/glyph_fix_log.json]
                           [--workers N] [--limit N] [--force] [--only list.json]
Re-running skips finished documents unless glyph_map.json has changed (or --force).
"""
import os
import sys
import json
import argparse
import concurrent.futures as cf

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.environ.get("MLDC_BASE", os.path.dirname(HERE))
MAP_PATH = os.path.join(HERE, "glyph_map.json")
PAGE_SEP = "\n\f\n"

DEFECTIVE_UNKNOWN_SHARE = 0.005        # >0.5% unlabeled glyphs => PDF is visually corrupt
REVIEW_ANOMALIES_PER_10K = 30          # invalid word starts per 10k words
REVIEW_CTRL_CHARS = 20                 # residual control chars (other, unfixed fonts)

_labels = None


def _init(map_path):
    global _labels
    import glyphfix
    _labels = glyphfix.load_glyph_map(map_path)


def process_one(args):
    fname, pdf_dir, out_dir = args
    import glyphfix
    doc_id = os.path.splitext(fname)[0]
    try:
        r = glyphfix.extract_pdf(os.path.join(pdf_dir, fname), _labels)
    except Exception as e:                                      # corrupt / unreadable PDF
        return {"file": fname, "doc_id": doc_id, "status": "error", "error": repr(e)[:160]}
    text = PAGE_SEP.join(r.pop("pages"))
    with open(os.path.join(out_dir, doc_id + ".txt"), "w", encoding="utf-8") as f:
        f.write(text)
    r.update({
        "file": fname, "doc_id": doc_id, "status": "ok",
        "source_defective": r["unknown_share"] > DEFECTIVE_UNKNOWN_SHARE,
        "needs_review": (r["word_anomalies_per_10k"] > REVIEW_ANOMALIES_PER_10K
                         or r["ctrl_chars_left"] > REVIEW_CTRL_CHARS),
    })
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf-dir", default=os.path.join(BASE_DIR, "pdfs"))
    ap.add_argument("--out-dir", default=os.path.join(BASE_DIR, "corpus", "raw_text"))
    ap.add_argument("--log", default=os.path.join(BASE_DIR, "logs", "glyph_fix_log.json"))
    ap.add_argument("--map", default=MAP_PATH)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", help="JSON file with a list of PDF file names to (re)process")
    a = ap.parse_args()

    import glyphfix
    os.makedirs(a.out_dir, exist_ok=True)
    os.makedirs(os.path.dirname(a.log), exist_ok=True)
    sha = glyphfix.map_sha(a.map)
    stamp = os.path.join(a.out_dir, ".glyph_map_sha")
    same_map = os.path.exists(stamp) and open(stamp).read().strip() == sha

    pdfs = sorted(f for f in os.listdir(a.pdf_dir) if f.lower().endswith(".pdf"))
    if a.only:
        wanted = set(json.load(open(a.only, encoding="utf-8")))
        pdfs = [f for f in pdfs if f in wanted]
    if a.limit:
        pdfs = pdfs[:a.limit]
    log = {}
    if os.path.exists(a.log) and same_map and not a.force:
        try:
            log = {e["file"]: e for e in json.load(open(a.log, encoding="utf-8"))}
        except Exception:
            log = {}
    todo = [f for f in pdfs if a.force or a.only or not same_map or f not in log
            or not os.path.exists(os.path.join(a.out_dir, os.path.splitext(f)[0] + ".txt"))]

    print("=" * 65)
    print("  MLDC -- Stage 1b: Glyph-recovery extraction")
    print("=" * 65)
    print(f"  PDFs: {len(pdfs)}   to process: {len(todo)}   workers: {a.workers}   map: {sha}")

    def save():
        with open(a.log, "w", encoding="utf-8") as f:
            json.dump(list(log.values()), f, ensure_ascii=False, indent=1)

    with open(stamp, "w") as f:                 # written up front so an interrupted run can resume
        f.write(sha)

    done = 0
    with cf.ProcessPoolExecutor(max_workers=a.workers, initializer=_init, initargs=(a.map,),
                                max_tasks_per_child=200) as ex:
        jobs = ex.map(process_one, [(f, a.pdf_dir, a.out_dir) for f in todo], chunksize=4)
        for r in jobs:
            log[r["file"]] = r
            done += 1
            if done % 250 == 0:
                save()
                print(f"  [{done}/{len(todo)}]", flush=True)
    save()

    rows = list(log.values())
    ok = [r for r in rows if r["status"] == "ok"]
    print("=" * 65)
    print(f"  ok: {len(ok)}   errors: {sum(r['status'] == 'error' for r in rows)}")
    print(f"  glyph-fixed: {sum(r['method'] == 'glyphfix' for r in ok)}   native: {sum(r['method'] == 'native' for r in ok)}")
    print(f"  source_defective: {sum(r['source_defective'] for r in ok)}   needs_review: {sum(r['needs_review'] for r in ok)}")
    print(f"[OK] text -> {a.out_dir}\n[OK] log  -> {a.log}")


if __name__ == "__main__":
    main()
