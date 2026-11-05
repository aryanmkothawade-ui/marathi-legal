import os, sys, json, concurrent.futures as cf
sys.stdout.reconfigure(encoding='utf-8')
from glyphlib import *; from render import render_glyph
from PIL import Image, ImageDraw, ImageFont
D = r"C:\Users\Aryan\OneDrive\Documents\internship\pdfs"
S = json.load(open('stats.json', encoding='utf-8'))
G = S['glyphs']; order = sorted(G, key=lambda h: -G[h]['use'])
NEEDED = set(order)
def scan(fn):
    out = []
    try:
        d = pymupdf.open(os.path.join(D, fn))
        for xr in target_fonts(d):
            for code, h in outline_hashes(d, xr).items():
                if h in NEEDED: out.append((h, fn, xr, code))
    except Exception:
        pass
    return out
if __name__ == '__main__':
    files = [f for f in sorted(os.listdir(D)) if f.lower().endswith('.pdf') and f not in set(S['no_target'])]
    rep = {}
    with cf.ProcessPoolExecutor(max_workers=4) as ex:
        for res in ex.map(scan, files, chunksize=10):
            for h, fn, xr, code in res: rep.setdefault(h, (fn, xr, code))
    miss = [h for h in order if h not in rep]; print("reps found:", len(rep), "missing:", len(miss))
    for h in miss[:5]: print(" missing", h, G[h]['use'])
    json.dump({h: rep[h] for h in order if h in rep}, open('reps.json', 'w'))
    order = [h for h in order if h in rep]; json.dump(order, open('order.json', 'w'))
    PER, COLS = 40, 8; cw, ch = 175, 150
    font = ImageFont.load_default()
    cache = {}
    for s in range(0, len(order), PER):
        sheet = Image.new('L', (cw * COLS, ch * (PER // COLS)), 255); dr = ImageDraw.Draw(sheet)
        for i, h in enumerate(order[s:s + PER]):
            fn, xr, code = rep[h]
            if fn not in cache:
                cache.clear(); cache[fn] = pymupdf.open(os.path.join(D, fn))
            buf = cache[fn].extract_font(xr)[3]
            im = render_glyph(buf, code, size=100)
            x, y = (i % COLS) * cw, (i // COLS) * ch
            if im: sheet.paste(im.resize((cw - 15, 94)), (x + 7, y + 30))
            top = G[h]['orig'][0]
            lab = ' '.join('%04X' % ord(c) for c in top[0]) if top[0] != '<MISSING>' else 'MISSING'
            dr.text((x + 4, y + 2), f"#{s+i}  use={G[h]['use']}", fill=0, font=font)
            dr.text((x + 4, y + 14), f"orig: {lab[:26]}", fill=0, font=font)
            dr.rectangle([x, y, x + cw - 1, y + ch - 1], outline=170)
        sheet.save(f'sheet_{s // PER:02d}.png')
    print("sheets:", (len(order) + PER - 1) // PER)
