"""
Spot-check the text extraction of ONE pdf: what the old (plain) extraction gave vs. what stage 1b gives.

    python tools/spot_check.py <path-to.pdf> [--page N] [--png out.png]

Prints, for the chosen page (default: the first page that has text):
  BEFORE  plain PyMuPDF text   (control characters shown as <0x13> etc.)
  AFTER   glyph-recovered text (stage 1b)
and the document-level quality numbers. With --png it also saves an image of the page so you can compare the
printed page with the AFTER text by eye — the most convincing test.
"""
import os
import re
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import glyphfix as g  # noqa: E402

CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def show_ctrl(s):
    return CTRL.sub(lambda m: "<0x%02x>" % ord(m.group(0)), s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--page", type=int, default=0, help="1-based page number (default: first page with text)")
    ap.add_argument("--png", help="save an image of the page here")
    ap.add_argument("--chars", type=int, default=700)
    a = ap.parse_args()

    labels = g.load_glyph_map(os.path.join(os.path.dirname(HERE), "glyph_map.json"))
    res = g.extract_pdf(a.pdf, labels)
    doc = g.pymupdf.open(a.pdf)
    idx = a.page - 1 if a.page else next((i for i, p in enumerate(res["pages"]) if len(p.strip()) > 100), 0)
    before = doc[idx].get_text("text")
    print("=" * 70)
    print(f"{os.path.basename(a.pdf)}   page {idx + 1}/{res['n_pages']}   method: {res['method']}")
    print("=" * 70)
    print("BEFORE (plain extraction):\n" + show_ctrl(before[:a.chars]))
    print("-" * 70)
    print("AFTER (stage 1b):\n" + res["pages"][idx][:a.chars])
    print("=" * 70)
    print(f"control characters  before: {len(CTRL.findall(before))}   after: {len(CTRL.findall(res['pages'][idx]))}")
    print(f"document: fonts fixed {res['fonts_fixed']}, unlabeled glyphs {res['unknown_share']:.4%}, "
          f"invalid word starts {res['word_anomalies_per_10k']}/10k, control chars left {res['ctrl_chars_left']}")
    if a.png:
        doc[idx].get_pixmap(dpi=110).save(a.png)
        print(f"page image saved to {a.png} — compare it with the AFTER text")


if __name__ == "__main__":
    main()
