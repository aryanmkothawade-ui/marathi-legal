"""
Builds a human review sheet for the anonymizer: one self-contained HTML page with ~50 anonymized documents.

The reviewer reads each document and clicks
  * a normal word that is still personal information (a name, place, phone ...)  -> marked red   = MISSED
  * a <placeholder> that hides something that is NOT personal information         -> marked orange = OVER-MASKED
and presses "Download results" at the end.  `tools/score_review.py` turns that file into recall / precision numbers.

Sample: 30 documents where the header parties were found + 20 where they were not (the harder case), fixed seed.
Only the first and last part of long documents is shown (names cluster in the header and the closing lines).

Usage:  python tools/make_review_sheet.py [--n 50] [--seed 7] [--out review/anonymizer_review.html]
The page contains the anonymized text only (no real names).  It may still contain leaks - that is what you are
looking for - so it is git-ignored; do not publish it.
"""
import os
import re
import sys
import json
import html
import random
import argparse

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BASE_DIR = os.environ.get("MLDC_BASE", os.path.dirname(REPO))
HEAD, TAIL = 4500, 1500
PLACEHOLDER = re.compile(r"<[^<>\s][^<>]{0,40}>")

PAGE = """<!doctype html>
<html lang="mr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Anonymizer review</title>
<style>
:root{--bg:#fff;--fg:#1d1d1f;--mut:#6b6b70;--card:#f6f6f8;--line:#d8d8de;--ph:#e3efff;--phfg:#0b4a9a;--miss:#ffd9d6;--missfg:#a31b10;--over:#ffe9c2;--overfg:#8a5200}
@media (prefers-color-scheme:dark){:root{--bg:#161618;--fg:#ececf0;--mut:#9a9aa3;--card:#202024;--line:#38383f;--ph:#1c3556;--phfg:#9cc5ff;--miss:#5a1f1b;--missfg:#ffb4ad;--over:#53390a;--overfg:#ffd48a}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.7 system-ui,"Nirmala UI","Mangal",sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;z-index:5}
header b{font-size:15px}header span{color:var(--mut);font-size:13px;margin-left:10px}
button{font:inherit;font-size:14px;padding:6px 12px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg);cursor:pointer}
main{max-width:900px;margin:0 auto;padding:16px}
.how{background:var(--card);border-radius:10px;padding:12px 16px;font-size:14px}
.doc{border:1px solid var(--line);border-radius:12px;margin:18px 0;padding:12px 16px}
.doc h2{font-size:14px;margin:0 0 8px;color:var(--mut);font-weight:600;display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}
.txt{white-space:pre-wrap;word-break:break-word}
.w{cursor:pointer;border-radius:3px}.w:hover{background:var(--card);outline:1px solid var(--line)}
.p{background:var(--ph);color:var(--phfg)}
.w.miss{background:var(--miss);color:var(--missfg);font-weight:600}
.w.over{background:var(--over);color:var(--overfg);font-weight:600}
.cut{color:var(--mut);font-style:italic;margin:8px 0}
</style></head><body>
<header><b>Anonymizer review</b><span id="stat"></span> <button onclick="dl()">Download results</button></header>
<main>
<div class="how"><b>What to do.</b> Read each document. Click any word that is still <b>personal information</b> (a person's name,
a village/address, phone, id, a company that identifies a person) - it turns <span style="color:var(--missfg)"><b>red</b></span>.
Click a blue <span class="p">&lt;placeholder&gt;</span> that hides something harmless (a common word, a court, a law) - it turns
<span style="color:var(--overfg)"><b>orange</b></span>. Click again to undo. Judges and advocates are meant to be masked.
Tick "reviewed" when you finish a document, and press <b>Download results</b> at the end (progress is also kept in this browser).
Only documents ticked as reviewed are counted.</div>
__DOCS__
</main>
<script>
const KEY="anon_review_v1";let S={};try{S=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){}
function save(){try{localStorage.setItem(KEY,JSON.stringify(S))}catch(e){}stat()}
function st(d){return S[d]||(S[d]={reviewed:false,marks:{}})}
function stat(){let r=0,m=0,o=0;for(const d in S){if(!S[d].reviewed)continue;r++;for(const k in S[d].marks){S[d].marks[k].kind=="miss"?m++:o++}}
document.getElementById("stat").textContent=r+" reviewed, "+m+" missed, "+o+" over-masked"}
document.querySelectorAll(".doc").forEach(card=>{const d=card.dataset.id,s=st(d);
 card.querySelector("input").checked=s.reviewed;
 card.querySelector("input").onchange=e=>{st(d).reviewed=e.target.checked;save()};
 card.querySelectorAll(".w").forEach(w=>{const k=w.dataset.i;if(s.marks[k])w.classList.add(s.marks[k].kind);
  w.onclick=()=>{const isP=w.classList.contains("p"),kind=isP?"over":"miss",m=st(d).marks;
   if(m[k]){delete m[k];w.classList.remove("miss","over")}else{m[k]={kind,text:w.textContent};w.classList.add(kind)}save()}})});
stat();
function dl(){const rows=[["doc_id","kind","text","placeholders_in_view"]];
 document.querySelectorAll(".doc").forEach(c=>{const d=c.dataset.id,s=st(d);if(!s.reviewed)return;
  rows.push([d,"reviewed","",c.dataset.ph]);
  for(const k in s.marks)rows.push([d,s.marks[k].kind,s.marks[k].text,""])});
 const csv="\\ufeff"+rows.map(r=>r.map(x=>'"'+String(x).replace(/"/g,'""')+'"').join(",")).join("\\n");
 const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([csv],{type:"text/csv"}));a.download="anonymizer_review_results.csv";a.click()}
</script></body></html>"""


def excerpt(text):
    if len(text) <= HEAD + TAIL + 500:
        return text, None
    return text[:HEAD], text[-TAIL:]


def render(text, prefix):
    out, i = [], 0
    for tok in re.split(r"(\s+)", text):
        if not tok:
            continue
        if tok.isspace():
            out.append(tok)
            continue
        cls = "w p" if PLACEHOLDER.fullmatch(tok.strip(".,;:()[]\"'")) or PLACEHOLDER.search(tok) else "w"
        out.append(f'<span class="{cls}" data-i="{prefix}{i}">{html.escape(tok)}</span>')
        i += 1
    return "".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--final", default=os.path.join(BASE_DIR, "corpus", "final", "mldc_v1.jsonl"))
    ap.add_argument("--log", default=os.path.join(BASE_DIR, "logs", "anonymization_log.json"))
    ap.add_argument("--out", default=os.path.join(REPO, "review", "anonymizer_review.html"))
    a = ap.parse_args()

    with open(a.log, encoding="utf-8") as f:
        log = {r["doc_id"]: r for r in json.load(f)}
    docs = []
    with open(a.final, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            # final docs carry their own id; the anonymization log is keyed by the source file stem
            stem = os.path.splitext(d["source"]["original_filename"])[0]
            r = log.get(stem)
            if r and r.get("anonymized"):
                docs.append((stem, d, r.get("header_parties", 0) > 0))
    rnd = random.Random(a.seed)
    with_h = [x for x in docs if x[2]]
    without_h = [x for x in docs if not x[2]]
    k2 = min(len(without_h), round(a.n * 0.4))
    pick = rnd.sample(with_h, min(len(with_h), a.n - k2)) + rnd.sample(without_h, k2)
    rnd.shuffle(pick)

    cards = []
    for n, (stem, d, has_h) in enumerate(pick, 1):
        head, tail = excerpt(d["content"]["full_text"])
        body = render(head, "h")
        if tail is not None:
            body += '<div class="cut">... (middle of the document not shown) ...</div>' + render(tail, "t")
        n_ph = len(PLACEHOLDER.findall(head + (tail or "")))
        cards.append(f'<section class="doc" data-id="{stem}" data-ph="{n_ph}"><h2><span>{n}/{len(pick)} &middot; {stem}'
                     f'{"" if has_h else " &middot; header party not found"}</span>'
                     f'<label><input type="checkbox"> reviewed</label></h2><div class="txt">{body}</div></section>')
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(PAGE.replace("__DOCS__", "\n".join(cards)))
    print(f"[OK] {len(pick)} documents ({len(pick) - k2} with header party, {k2} without) -> {a.out}")


if __name__ == "__main__":
    main()
