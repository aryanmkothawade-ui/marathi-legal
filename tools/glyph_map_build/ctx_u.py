import sys, os, json, collections
sys.stdout.reconfigure(encoding='utf-8'); sys.path.insert(0, "C:/Users/Aryan/OneDrive/Desktop/internship/marathi-legal-document")
import glyphfix as g; pymupdf = g.pymupdf
from exc_u import EXCU
P = "C:/Users/Aryan/OneDrive/Documents/internship/pdfs/"
hs = json.load(open('unk_hs.json')); docs = json.load(open('unk_docs.json'))
labels = g.load_glyph_map("C:/Users/Aryan/OneDrive/Desktop/internship/marathi-legal-document/glyph_map.json")
for i, v in EXCU.items(): labels[hs[i]] = v
probe = {int(a): f"⟦{a}⟧" for a in sys.argv[1:]}
for k, m in probe.items(): labels[hs[k]] = m
found = collections.defaultdict(list)
for f in dict.fromkeys(fn for k in probe for fn in docs[hs[k]]):
    d = pymupdf.open(P + f); simple = []
    for xr, (bf, sub) in g.target_fonts(d).items():
        if sub == 'TrueType':
            h = g.outline_hashes(d, xr)
            if h: simple.append((xr, h))
    if not simple: continue
    for b, (xr, _) in enumerate(simple): g._set_tounicode(d, xr, g._pua_cmap(b))
    for pg in d:
        for line in pg.get_text("text").split('\n'):
            toks = []
            for ch in line:
                o = ord(ch)
                toks.append(labels.get(simple[(o - g.PUA_BASE) >> 8][1].get((o - g.PUA_BASE) & 0xFF)) if g.PUA_BASE <= o < g.PUA_BASE + 0x100 * len(simple) else ch)
            s = g.reorder(toks)[0]
            for k, m in probe.items():
                if m in s and len(found[k]) < 5: p = s.index(m); found[k].append(s[max(0, p - 18):p + 12])
for k in probe:
    print(f"\n#{k}:"); [print("   ", c) for c in found[k]]
