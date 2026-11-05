"""
Builds a human check of text extraction quality: page image next to two extracted texts, in random order (A / B).
One is plain PyMuPDF text (what a normal pipeline gets), the other is our glyph-recovered text.  The reviewer does not
know which is which.  Clicking a word that is wrong (a wrong letter, broken conjunct, wrong order, missing/extra
character) marks it; the scorer then gives a word error rate for each method.

Usage:  python tools/make_extraction_sheet.py [--n 24] [--seed 5] [--words 90]
Outputs: review/extraction_review.html  and  review/extraction_key.json  (git-ignored)
"""
import os
import re
import sys
import json
import html
import base64
import random
import argparse

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BASE_DIR = os.environ.get("MLDC_BASE", os.path.dirname(REPO))

PAGE = """<!doctype html>
<html lang="mr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Extraction review</title>
<style>
:root{--bg:#fff;--fg:#1d1d1f;--mut:#6b6b70;--card:#f6f6f8;--line:#d8d8de;--bad:#ffd9d6;--badfg:#a31b10}
@media (prefers-color-scheme:dark){:root{--bg:#161618;--fg:#ececf0;--mut:#9a9aa3;--card:#202024;--line:#38383f;--bad:#5a1f1b;--badfg:#ffb4ad}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.7 system-ui,"Nirmala UI","Mangal",sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;z-index:5}
header span{color:var(--mut);font-size:13px;margin:0 10px}
button{font:inherit;font-size:14px;padding:6px 12px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg);cursor:pointer}
main{max-width:1200px;margin:0 auto;padding:16px}
.how{background:var(--card);border-radius:10px;padding:12px 16px;font-size:14px}
.pg{border:1px solid var(--line);border-radius:12px;margin:18px 0;padding:12px 16px}
.pg h2{font-size:13px;margin:0 0 8px;color:var(--mut);font-weight:600;display:flex;justify-content:space-between}
.cols{display:grid;grid-template-columns:1.1fr 1fr 1fr;gap:12px}
@media (max-width:900px){.cols{grid-template-columns:1fr}}
.cols img{width:100%;border:1px solid var(--line);border-radius:6px}
.col h3{font-size:13px;margin:0 0 4px;color:var(--mut)}
.txt{white-space:pre-wrap;word-break:break-word;font-size:15px;line-height:1.8}
.w{cursor:pointer;border-radius:3px}.w:hover{background:var(--card);outline:1px solid var(--line)}
.w.bad{background:var(--bad);color:var(--badfg);font-weight:600}
</style></head><body>
<header><b>Extraction review</b><span id="stat"></span><button onclick="dl()">Download results</button></header>
<main>
<div class="how"><b>What to do.</b> Left: the real page. Middle (A) and right (B): two machine-read versions of the <b>first part of
the page</b> (start at the top of the page image). Click every word in A and in B that is <b>wrong</b> compared with the image: a wrong
or missing letter or matra, a broken conjunct, characters in the wrong order, garbage symbols. Do not mark things that are only line-break
or spacing differences. Click again to undo. Tick "checked" when a page is done, then press <b>Download results</b>.</div>
__PAGES__
</main>
<script>
const KEY="extraction_review_v1";let S={};try{S=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){}
function save(){try{localStorage.setItem(KEY,JSON.stringify(S))}catch(e){}stat()}
function st(p){return S[p]||(S[p]={checked:false,marks:{}})}
function stat(){let c=0,m=0;for(const p in S){if(!S[p].checked)continue;c++;m+=Object.keys(S[p].marks).length}
document.getElementById("stat").textContent=c+" pages checked, "+m+" wrong words marked"}
document.querySelectorAll(".pg").forEach(card=>{const p=card.dataset.id,s=st(p);
 const cb=card.querySelector("input");cb.checked=s.checked;cb.onchange=e=>{st(p).checked=e.target.checked;save()};
 card.querySelectorAll(".w").forEach(w=>{const k=w.dataset.v+w.dataset.i;if(s.marks[k])w.classList.add("bad");
  w.onclick=()=>{const m=st(p).marks;if(m[k]){delete m[k];w.classList.remove("bad")}else{m[k]={v:w.dataset.v,t:w.textContent};w.classList.add("bad")}save()}})});
stat();
function dl(){const rows=[["page_id","kind","version","text","words_in_view"]];
 document.querySelectorAll(".pg").forEach(c=>{const p=c.dataset.id,s=st(p);if(!s.checked)return;
  rows.push([p,"checked","A","",c.dataset.wa]);rows.push([p,"checked","B","",c.dataset.wb]);
  for(const k in s.marks)rows.push([p,"wrong",s.marks[k].v,s.marks[k].t,""])});
 const csv="\\ufeff"+rows.map(r=>r.map(x=>'"'+String(x).replace(/"/g,'""')+'"').join(",")).join("\\n");
 const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([csv],{type:"text/csv"}));a.download="extraction_review_results.csv";a.click()}
</script></body></html>"""


def words_html(text, version, n_words):
    toks = text.split()[:n_words]
    return " ".join(f'<span class="w" data-v="{version}" data-i="{i}">{html.escape(t)}</span>' for i, t in enumerate(toks)), len(toks)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=24)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--words", type=int, default=90)
    ap.add_argument("--out-dir", default=os.path.join(REPO, "review"))
    a = ap.parse_args()
    pdf_dir = os.path.join(BASE_DIR, "pdfs")
    raw_dir = os.path.join(BASE_DIR, "corpus", "raw_text")
    glog = json.load(open(os.path.join(BASE_DIR, "corpus", "glyph_fix_log.json"), encoding="utf-8"))
    ok = [g for g in glog if g.get("status") == "ok" and not g.get("source_defective") and g.get("n_pages", 0) >= 3 and g.get("fonts_fixed", 0) > 0]
    rnd = random.Random(a.seed)
    rnd.shuffle(ok)

    cards, key = [], {}
    for g in ok:
        if len(cards) >= a.n:
            break
        did = g["doc_id"]
        try:
            pages = open(os.path.join(raw_dir, did + ".txt"), encoding="utf-8").read().split("\n\f\n")
            doc = pymupdf.open(os.path.join(pdf_dir, did + ".pdf"))
        except Exception:
            continue
        if len(pages) != len(doc):
            continue
        cand = [i for i in range(1, len(doc)) if len(pages[i].split()) >= a.words + 30]
        if not cand:
            continue
        i = rnd.choice(cand)
        plain, recovered = doc[i].get_text(), pages[i]
        pix = doc[i].get_pixmap(dpi=100)
        img = base64.b64encode(pix.tobytes("jpg")).decode()
        pid = f"{did}_p{i + 1}"
        a_is = rnd.choice(["plain", "recovered"])
        texts = {"A": plain if a_is == "plain" else recovered, "B": recovered if a_is == "plain" else plain}
        ha, na = words_html(texts["A"], "A", a.words)
        hb, nb = words_html(texts["B"], "B", a.words)
        key[pid] = {"A": a_is, "B": "recovered" if a_is == "plain" else "plain"}
        cards.append(f'<section class="pg" data-id="{pid}" data-wa="{na}" data-wb="{nb}"><h2><span>{len(cards) + 1}/{a.n} &middot; {pid}</span>'
                     f'<label><input type="checkbox"> checked</label></h2><div class="cols">'
                     f'<div class="col"><h3>page</h3><img alt="page" src="data:image/jpeg;base64,{img}"></div>'
                     f'<div class="col"><h3>A</h3><div class="txt">{ha}</div></div>'
                     f'<div class="col"><h3>B</h3><div class="txt">{hb}</div></div></div></section>')
    os.makedirs(a.out_dir, exist_ok=True)
    with open(os.path.join(a.out_dir, "extraction_review.html"), "w", encoding="utf-8") as f:
        f.write(PAGE.replace("__PAGES__", "\n".join(cards)).replace("__N__", str(len(cards))))
    with open(os.path.join(a.out_dir, "extraction_key.json"), "w", encoding="utf-8") as f:
        json.dump(key, f, indent=1)
    print(f"[OK] {len(cards)} pages -> {a.out_dir}")


if __name__ == "__main__":
    main()
