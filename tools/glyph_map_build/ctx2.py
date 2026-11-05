import sys, os, json, collections
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, "C:/Users/Aryan/OneDrive/Desktop/internship/marathi-legal-document")
from glyphfix import reorder, outline_hashes, target_fonts, inject_pua, PUA_BASE, pymupdf
from exc2 import EXC2
D = r"C:\Users\Aryan\OneDrive\Documents\internship\pdfs"
order = json.load(open('order2.json')); reps = json.load(open('reps2.json'))
S = json.load(open('stats2.json', encoding='utf-8'))['glyphs']
probe = {int(a): f"⟦{a}⟧" for a in sys.argv[1:]}; lab = {}
for h, g in S.items(): lab[h] = None if g['orig'][0][0] == '<MISSING>' else g['orig'][0][0]
for i, v in EXC2.items(): lab[order[i]] = v
for k, m in probe.items(): lab[order[k]] = m
want = {order[k] for k in probe}; files = list(dict.fromkeys(reps[order[k]][0] for k in probe))
# add more Nirmala docs so each glyph has several contexts
allf = [f for f in json.load(open('stats.json', encoding='utf-8'))['no_target']]
found = collections.defaultdict(list)
for f in files + allf[:150]:
    try:
        d = pymupdf.open(os.path.join(D, f)); xr = list(target_fonts(d)); maps = [outline_hashes(d, x) for x in xr]
        if not xr or not any(h in want for m in maps for h in m.values()): continue
        inject_pua(d, xr); d2 = pymupdf.open(stream=d.tobytes(), filetype='pdf')
        for pg in d2:
            for line in pg.get_text("text").split('\n'):
                toks = []
                for ch in line:
                    o = ord(ch)
                    if PUA_BASE <= o < PUA_BASE + 0x100 * len(xr): toks.append(lab.get(maps[(o - PUA_BASE) >> 8].get((o - PUA_BASE) & 0xFF)))
                    else: toks.append(ch)
                s = reorder(toks)[0]
                RAW = os.environ.get('RAW')
                if RAW and any(m in ''.join(t or '?' for t in toks) for m in probe.values()):
                    seq = [t if t is None or len(t) < 3 else t for t in toks]
                    for k, m in probe.items():
                        for ix, t in enumerate(toks):
                            if t == m and len(found[k]) < 5: found[k].append(' | '.join(str(x) for x in toks[max(0, ix-6):ix+5]))
                    continue
                for k, m in probe.items():
                    if m in s and len(found[k]) < 5: p = s.index(m); found[k].append(s[max(0, p - 18):p + 12])
    except Exception as e: pass
    if all(len(found[k]) >= 5 for k in probe): break
for k in probe:
    print(f"\n#{k}:"); [print("   ", c) for c in found[k]]
