"""Glyph statistics for Mangal fonts (simple TrueType) across the whole corpus."""
import os, sys, json, collections, time, re, concurrent.futures as cf
sys.stdout.reconfigure(encoding='utf-8'); sys.path.insert(0, "C:/Users/Aryan/OneDrive/Desktop/internship/marathi-legal-document")
import glyphfix as g
from glyphlib import parse_tounicode
pymupdf = g.pymupdf
D = r"C:\Users\Aryan\OneDrive\Documents\internship\pdfs"
def mangal_fonts(doc):
    out = {}
    for pg in doc:
        for x in pg.get_fonts(full=True):
            if x[0] not in out and x[2] == 'TrueType' and 'Mangal' in x[3]: out[x[0]] = x[3]
    return out
def work(fn):
    try:
        d = pymupdf.open(os.path.join(D, fn)); xr = list(mangal_fonts(d))
        if not xr: return {'f': fn, 'n': 0}
        info = [(g.outline_hashes(d, x), parse_tounicode(d, x)) for x in xr]
        for b, x in enumerate(xr): g._set_tounicode(d, x, g._pua_cmap(b))
        use = collections.Counter()
        for pg in d:
            for c in pg.get_text("text"):
                o = ord(c)
                if g.PUA_BASE <= o < g.PUA_BASE + 0x100 * len(xr): use[((o - g.PUA_BASE) >> 8, (o - g.PUA_BASE) & 0xFF)] += 1
        rows = [(info[b][0].get(c), n, info[b][1].get(c)) for (b, c), n in use.items()]
        return {'f': fn, 'n': len(xr), 'glyphs': rows}
    except Exception as e:
        return {'f': fn, 'err': repr(e)[:80]}
if __name__ == '__main__':
    files = sorted(f for f in os.listdir(D) if f.lower().endswith('.pdf')); t0 = time.time()
    H = collections.defaultdict(lambda: {'use': 0, 'docs': 0, 'orig': collections.Counter()}); docs = []; unh = 0
    with cf.ProcessPoolExecutor(max_workers=4) as ex:
        for i, r in enumerate(ex.map(work, files, chunksize=8), 1):
            if r.get('n'):
                docs.append(r['f'])
                for h, n, o in r['glyphs']:
                    if h is None: unh += n; continue
                    e = H[h]; e['use'] += n; e['docs'] += 1; e['orig'][o if o is not None else '<MISSING>'] += n
            if i % 1000 == 0: print(i, f"{time.time()-t0:.0f}s", flush=True)
    json.dump({'glyphs': {h: {'use': e['use'], 'docs': e['docs'], 'orig': e['orig'].most_common(6)} for h, e in H.items()}, 'docs': docs, 'unhashed': unh}, open('stats3.json', 'w', encoding='utf-8'), ensure_ascii=False)
    print("done", f"{time.time()-t0:.0f}s", "mangal docs", len(docs), "outlines", len(H), "unhashed uses", unh)
