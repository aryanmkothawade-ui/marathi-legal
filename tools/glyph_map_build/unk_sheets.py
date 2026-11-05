import sys, os, json, collections
sys.stdout.reconfigure(encoding='utf-8'); sys.path.insert(0, "C:/Users/Aryan/OneDrive/Desktop/internship/marathi-legal-document")
import glyphfix as g; pymupdf = g.pymupdf
from render import render_glyph, render_gid
from PIL import Image, ImageDraw, ImageFont
P = "C:/Users/Aryan/OneDrive/Documents/internship/pdfs/"
docs = json.load(open('unk_docs.json')); order = [h for h in json.load(open('unk_order.json')) if h != 'null'][:80]
found = {}
for h in order:
    for fn in docs[h]:
        d = pymupdf.open(P + fn)
        for xr, (bf, sub) in g.target_fonts(d).items():
            if sub == 'TrueType':
                for code, hh in g.outline_hashes(d, xr).items():
                    if hh == h: found[h] = (fn, xr, 'simple', code); break
            else:
                hs, n = g.type0_hashes(d, xr)
                for cid, hh in hs.items():
                    if hh == h: found[h] = (fn, xr, 'type0', cid); break
            if h in found: break
        if h in found: break
json.dump(found, open('unk_found.json', 'w')); print("located", len(found), "of", len(order))
PER, COLS, cw, ch = 40, 8, 175, 150; font = ImageFont.load_default(); hs = [h for h in order if h in found]
for s in range(0, len(hs), PER):
    sheet = Image.new('L', (cw * COLS, ch * (PER // COLS)), 255); dr = ImageDraw.Draw(sheet)
    for i, h in enumerate(hs[s:s + PER]):
        fn, xr, kind, key = found[h]; d = pymupdf.open(P + fn); buf = d.extract_font(xr)[3]
        im = render_glyph(buf, key, size=100) if kind == 'simple' else render_gid(buf, key, size=100)
        x, y = (i % COLS) * cw, (i // COLS) * ch
        if im: sheet.paste(im.resize((cw - 15, 94)), (x + 7, y + 30))
        dr.text((x + 4, y + 2), f"#{s+i} {h[:8]} {kind[:2]}", fill=0, font=font); dr.rectangle([x, y, x + cw - 1, y + ch - 1], outline=170)
    sheet.save(f'usheet_{s // PER}.png')
json.dump(hs, open('unk_hs.json', 'w')); print("sheets:", (len(hs) + PER - 1) // PER)
