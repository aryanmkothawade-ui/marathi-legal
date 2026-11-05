import os, sys, json, collections, time, concurrent.futures as cf
sys.stdout.reconfigure(encoding='utf-8')
from glyphlib import *
D = r"C:\Users\Aryan\OneDrive\Documents\internship\pdfs"
def work(fn):
    p = os.path.join(D, fn)
    try:
        d = pymupdf.open(p)
        xr = list(target_fonts(d))
        res = {'f': fn, 'pages': len(d), 'fonts': [], 'other_fonts': sorted({x[3].split('+')[-1] for pg in d for x in pg.get_fonts(full=True) if TARGET not in x[3]})}
        if not xr: return res
        info = {}
        for x in xr:
            info[x] = (outline_hashes(d, x), parse_tounicode(d, x))
        order = inject_pua(d)
        d2 = pymupdf.open(stream=d.tobytes(), filetype='pdf')
        use = collections.Counter()
        for pg in d2:
            for c in pg.get_text("text"):
                o = ord(c)
                if 0xE000 <= o < 0xF000: use[((o - 0xE000) >> 8, (o - 0xE000) & 0xFF)] += 1
        rows = []
        for (blk, code), n in use.items():
            h = info[order[blk]][0].get(code)
            rows.append((h, n, info[order[blk]][1].get(code)))
        res['glyphs'] = rows
        return res
    except Exception as e:
        return {'f': fn, 'err': repr(e)[:100]}
if __name__ == '__main__':
    files = sorted(f for f in os.listdir(D) if f.lower().endswith('.pdf'))
    t0 = time.time(); H = collections.defaultdict(lambda: {'use': 0, 'docs': 0, 'orig': collections.Counter()})
    stat = collections.Counter(); errs = []; other = collections.Counter(); nodocs = []
    with cf.ProcessPoolExecutor(max_workers=4) as ex:
        for i, r in enumerate(ex.map(work, files, chunksize=8), 1):
            if 'err' in r: errs.append(r); continue
            for o in r['other_fonts']: other[o] += 1
            if 'glyphs' not in r: stat['no_target_font'] += 1; nodocs.append(r['f']); continue
            stat['target_font'] += 1
            for h, n, o in r['glyphs']:
                if h is None: stat['unhashed_use'] += n; continue
                e = H[h]; e['use'] += n; e['docs'] += 1; e['orig'][o if o is not None else '<MISSING>'] += n
            if i % 500 == 0: print(i, f"{time.time()-t0:.0f}s", flush=True)
    out = {h: {'use': e['use'], 'docs': e['docs'], 'orig': e['orig'].most_common(6)} for h, e in H.items()}
    json.dump({'glyphs': out, 'stat': stat, 'errs': errs[:30], 'n_err': len(errs), 'other_fonts': other.most_common(40), 'no_target': nodocs}, open('stats.json', 'w', encoding='utf-8'), ensure_ascii=False)
    print("done", f"{time.time()-t0:.0f}s", dict(stat), "errors:", len(errs), "distinct outlines:", len(H))
