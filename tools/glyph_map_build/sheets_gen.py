"""usage: sheets_gen.py STATS.json PREFIX N  -> PREFIX_order.json and PREFIX_XX.png for the N most-used glyphs not yet labelled in glyph_map.json"""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8'); sys.path.insert(0, "C:/Users/Aryan/OneDrive/Desktop/internship/marathi-legal-document")
import glyphfix as g; pymupdf = g.pymupdf
from render import render_glyph, render_gid
from PIL import Image, ImageDraw, ImageFont
P = "C:/Users/Aryan/OneDrive/Documents/internship/pdfs/"
stats, prefix, N = sys.argv[1], sys.argv[2], int(sys.argv[3])
G = json.load(open(stats, encoding='utf-8'))['glyphs']
M = json.load(open("C:/Users/Aryan/OneDrive/Desktop/internship/marathi-legal-document/glyph_map.json", encoding='utf-8'))
order = [h for h in sorted(G, key=lambda h: -G[h]['use']) if not (h in M and M[h]['u'] is not None)][:N]
json.dump(order, open(prefix + '_order.json', 'w'))
PER, COLS, cw, ch = 40, 8, 175, 150; font = ImageFont.load_default(); cache = {}
for s in range(0, len(order), PER):
    sheet = Image.new('L', (cw * COLS, ch * (PER // COLS)), 255); dr = ImageDraw.Draw(sheet)
    for i, h in enumerate(order[s:s + PER]):
        fn, xr, kind, code = G[h]['rep']
        if fn not in cache: cache.clear(); cache[fn] = pymupdf.open(P + fn)
        buf = cache[fn].extract_font(xr)[3]
        im = render_glyph(buf, code, size=100) if kind == 's' else render_gid(buf, code, size=100)
        x, y = (i % COLS) * cw, (i // COLS) * ch
        if im: sheet.paste(im.resize((cw - 15, 94)), (x + 7, y + 30))
        top = G[h]['orig'][0][0]; lab = ' '.join('%04X' % ord(c) for c in top) if top != '<MISSING>' else ('MISSING' if kind == 's' else 'type0')
        dr.text((x + 4, y + 2), f"#{s+i} use={G[h]['use']} {G[h]['docs']}d", fill=0, font=font); dr.text((x + 4, y + 14), f"orig: {lab[:24]}", fill=0, font=font)
        dr.rectangle([x, y, x + cw - 1, y + ch - 1], outline=170)
    sheet.save(f'{prefix}_{s // PER:02d}.png')
print("glyphs:", len(order), "sheets:", (len(order) + PER - 1) // PER)
