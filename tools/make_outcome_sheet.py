"""
Builds a human labelling sheet for the outcome label (allowed / dismissed / ...).

The reviewer reads the operative part (the end of the judgment) and picks what the court decided.  The pipeline's own
guess is NOT shown (so it cannot bias the reviewer); it is written to a separate key file used by score_outcome.py.
The sample is stratified by the pipeline's label so the rare classes get enough documents; the scorer re-weights.

Usage:  python tools/make_outcome_sheet.py [--n 200] [--seed 11]
Outputs: review/outcome_review.html   (give to the reviewer)
         review/outcome_key.json      (keep; the pipeline's labels + population counts)
Both are git-ignored (they contain court text).
"""
import os
import sys
import json
import html
import random
import argparse
from collections import Counter

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BASE_DIR = os.environ.get("MLDC_BASE", os.path.dirname(REPO))

QUOTA = {"allowed": 0.25, "dismissed": 0.25, "partially_allowed": 0.15, "remanded": 0.10, "disposed": 0.10, "unknown": 0.15}
LABELS = [("allowed", "Allowed (अपील/याचिका मंजूर, आदेश रद्द)"), ("dismissed", "Dismissed (फेटाळले)"),
          ("partially_allowed", "Partly allowed"), ("remanded", "Remanded (परत पाठवले)"),
          ("disposed", "Disposed of (निकाली, no win/loss)"), ("unclear", "Unclear / not a final decision")]

PAGE = """<!doctype html>
<html lang="mr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Outcome review</title>
<style>
:root{--bg:#fff;--fg:#1d1d1f;--mut:#6b6b70;--card:#f6f6f8;--line:#d8d8de;--ok:#d9f2e0;--okfg:#14683a}
@media (prefers-color-scheme:dark){:root{--bg:#161618;--fg:#ececf0;--mut:#9a9aa3;--card:#202024;--line:#38383f;--ok:#17402a;--okfg:#9be3b6}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.7 system-ui,"Nirmala UI","Mangal",sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;z-index:5}
header span{color:var(--mut);font-size:13px;margin:0 10px}
button{font:inherit;font-size:14px;padding:6px 12px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg);cursor:pointer}
main{max-width:900px;margin:0 auto;padding:16px}
.how{background:var(--card);border-radius:10px;padding:12px 16px;font-size:14px}
.doc{border:1px solid var(--line);border-radius:12px;margin:18px 0;padding:12px 16px}
.doc h2{font-size:13px;margin:0 0 8px;color:var(--mut);font-weight:600}
.txt{white-space:pre-wrap;word-break:break-word}
.opts{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.opts button.on{background:var(--ok);color:var(--okfg);border-color:var(--okfg);font-weight:600}
details{margin-top:8px;color:var(--mut);font-size:14px}
</style></head><body>
<header><b>Outcome review</b><span id="stat"></span><button onclick="dl()">Download results</button></header>
<main>
<div class="how"><b>What to do.</b> For each judgment read the final order and press what the court <b>finally decided</b> in this
document. If the final order is not visible, open "show more of the end". Choose <i>Unclear</i> if you cannot tell.
A judgment that allows the appeal and sets aside the lower order = <b>Allowed</b>. Press the button again to clear. Press
<b>Download results</b> when done; progress is kept in this browser.</div>
__DOCS__
</main>
<script>
const KEY="outcome_review_v1";let S={};try{S=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){}
function save(){try{localStorage.setItem(KEY,JSON.stringify(S))}catch(e){}stat()}
function stat(){document.getElementById("stat").textContent=Object.keys(S).filter(k=>S[k]).length+" / __N__ labelled"}
document.querySelectorAll(".doc").forEach(c=>{const d=c.dataset.id;
 const paint=()=>c.querySelectorAll(".opts button").forEach(b=>b.classList.toggle("on",S[d]===b.dataset.v));paint();
 c.querySelectorAll(".opts button").forEach(b=>b.onclick=()=>{S[d]=(S[d]===b.dataset.v)?null:b.dataset.v;paint();save()})});
stat();
function dl(){const rows=[["doc_id","human_label"]];for(const d in S)if(S[d])rows.push([d,S[d]]);
 const a=document.createElement("a");a.href=URL.createObjectURL(new Blob(["\\ufeff"+rows.map(r=>r.join(",")).join("\\n")],{type:"text/csv"}));
 a.download="outcome_review_results.csv";a.click()}
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--final", default=os.path.join(BASE_DIR, "corpus", "final", "mldc_v1.jsonl"))
    ap.add_argument("--out-dir", default=os.path.join(REPO, "review"))
    a = ap.parse_args()

    by = {k: [] for k in QUOTA}
    with open(a.final, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            by.setdefault(d["labels"]["outcome_normalized"], []).append(d)
    population = {k: len(v) for k, v in by.items()}
    rnd = random.Random(a.seed)
    pick = []
    for k, share in QUOTA.items():
        pick += [(k, d) for d in rnd.sample(by[k], min(len(by[k]), round(a.n * share)))]
    rnd.shuffle(pick)

    cards, key = [], {}
    for i, (pred, d) in enumerate(pick, 1):
        sec = d["content"]["sections"].get("case_result") or ""
        full = d["content"]["full_text"]
        main_txt = sec if len(sec) > 40 else full[-2500:]
        more = full[-6000:-len(main_txt)] if len(full) > len(main_txt) + 200 else ""
        did = d["doc_id"]
        key[did] = pred
        opts = "".join(f'<button data-v="{v}">{html.escape(t)}</button>' for v, t in LABELS)
        cards.append(f'<section class="doc" data-id="{did}"><h2>{i}/{len(pick)} &middot; {did}</h2>'
                     f'<div class="txt">{html.escape(main_txt[:3500])}</div>'
                     + (f'<details><summary>show more of the end</summary><div class="txt">{html.escape(more)}</div></details>' if more else "")
                     + f'<div class="opts">{opts}</div></section>')
    os.makedirs(a.out_dir, exist_ok=True)
    with open(os.path.join(a.out_dir, "outcome_review.html"), "w", encoding="utf-8") as f:
        f.write(PAGE.replace("__DOCS__", "\n".join(cards)).replace("__N__", str(len(pick))))
    with open(os.path.join(a.out_dir, "outcome_key.json"), "w", encoding="utf-8") as f:
        json.dump({"pipeline_label": key, "population": population}, f, ensure_ascii=False, indent=1)
    print(f"[OK] {len(pick)} documents {dict(Counter(k for k, _ in pick))}\n     population {population}\n     -> {a.out_dir}")


if __name__ == "__main__":
    main()
