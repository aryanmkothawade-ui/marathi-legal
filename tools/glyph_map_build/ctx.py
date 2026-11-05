import sys, os, json, collections
sys.stdout.reconfigure(encoding='utf-8')
from decode import *; from exc import EXC
D = r"C:\Users\Aryan\OneDrive\Documents\internship\pdfs"
order = json.load(open('order.json'))
probe = {int(a): f"⟦{a}⟧" for a in sys.argv[1:]}
exc = dict(EXC); exc.update(probe)
lab = build_labels(exc=exc)
S = json.load(open('stats.json', encoding='utf-8')); nodoc = set(S['no_target'])
reps = json.load(open('reps.json'))
files = list(dict.fromkeys(reps[order[k]][0] for k in probe))
S2 = json.load(open("stats.json", encoding="utf-8"))["glyphs"]
found = collections.defaultdict(list)
for f in files:
    try: r = decode_doc(os.path.join(D, f), lab)
    except Exception: continue
    if not r: continue
    pages, unk, maps = r
    for pg in pages:
        for toks in pg:
            s = reorder([t for t in toks])
            for k, m in probe.items():
                if m in s and len(found[k]) < 4:
                    p = s.index(m); found[k].append(s[max(0, p - 22):p + 14])
    if all(len(found[k]) >= 4 for k in probe): break
for k in probe:
    print(f"\n#{k}:")
    for c in found[k]: print("   ", c)
