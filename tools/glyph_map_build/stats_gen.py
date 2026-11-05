"""Generic glyph statistics for chosen font families (simple + Type0). usage: stats_gen.py OUT.json FAMILY_SUBSTR [...]"""
import os, sys, json, collections, time, concurrent.futures as cf
sys.stdout.reconfigure(encoding='utf-8'); sys.path.insert(0, "C:/Users/Aryan/OneDrive/Desktop/internship/marathi-legal-document")
import glyphfix as g
from glyphlib import parse_tounicode
pymupdf = g.pymupdf
D = r"C:\Users\Aryan\OneDrive\Documents\internship\pdfs"
FAM = sys.argv[2:]
def fonts_of(doc):
    out = {}
    for pg in doc:
        for x in pg.get_fonts(full=True):
            if x[0] not in out and x[2] in ('TrueType', 'Type0') and any(f in x[3] for f in FAM): out[x[0]] = (x[3], x[2])
    return out
def work(fn):
    try:
        d = pymupdf.open(os.path.join(D, fn)); fs = fonts_of(d)
        if not fs: return {'f': fn, 'n': 0}
        simple, type0 = [], []
        for xr, (bf, sub) in fs.items():
            if sub == 'TrueType':
                h = g.outline_hashes(d, xr)
                if h: simple.append((xr, h, parse_tounicode(d, xr)))
            else:
                h, n = g.type0_hashes(d, xr)
                if h: type0.append((xr, h, n))
        for b, (xr, _, _) in enumerate(simple): g._set_tounicode(d, xr, g._pua_cmap(b))
        for b, (xr, _, n) in enumerate(type0): g._set_tounicode(d, xr, g._pua_cmap_type0(b, n))
        use = collections.Counter(); hi = g.PUA_BASE + 0x100 * len(simple)
        for pg in d:
            for c in pg.get_text("text"):
                o = ord(c)
                if g.PUA_BASE <= o < hi: use[('s', (o - g.PUA_BASE) >> 8, (o - g.PUA_BASE) & 0xFF)] += 1
                elif g.SPUA_BASE <= o < g.SPUA_BASE + 0x10000 * len(type0): use[('t', (o - g.SPUA_BASE) >> 16, (o - g.SPUA_BASE) & 0xFFFF)] += 1
        rows = []
        for (k, b, code), n in use.items():
            if k == 's': xr, h, tu = simple[b]; rows.append((h.get(code), n, tu.get(code), xr, 's', code))
            else: xr, h, _ = type0[b]; rows.append((h.get(code), n, None, xr, 't', code))
        return {'f': fn, 'n': len(simple) + len(type0), 'rows': rows}
    except Exception as e:
        return {'f': fn, 'err': repr(e)[:80]}
if __name__ == '__main__':
    files = sorted(f for f in os.listdir(D) if f.lower().endswith('.pdf')); t0 = time.time()
    H = collections.defaultdict(lambda: {'use': 0, 'docs': 0, 'orig': collections.Counter(), 'rep': None}); docs = []
    with cf.ProcessPoolExecutor(max_workers=4) as ex:
        for i, r in enumerate(ex.map(work, files, chunksize=8), 1):
            if r.get('n'):
                docs.append(r['f'])
                for h, n, o, xr, kind, code in r['rows']:
                    if h is None: continue
                    e = H[h]; e['use'] += n; e['docs'] += 1; e['orig'][o if o is not None else '<MISSING>'] += n
                    if e['rep'] is None: e['rep'] = (r['f'], xr, kind, code)
            if i % 1500 == 0: print(i, f"{time.time()-t0:.0f}s", flush=True)
    out = {h: {'use': e['use'], 'docs': e['docs'], 'orig': e['orig'].most_common(6), 'rep': e['rep']} for h, e in H.items()}
    json.dump({'glyphs': out, 'docs': docs}, open(sys.argv[1], 'w', encoding='utf-8'), ensure_ascii=False)
    print("done", f"{time.time()-t0:.0f}s", "docs", len(docs), "outlines", len(H))
