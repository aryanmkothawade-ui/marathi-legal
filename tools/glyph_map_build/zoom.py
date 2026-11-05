import sys, json, pymupdf
sys.stdout.reconfigure(encoding='utf-8'); pymupdf.TOOLS.mupdf_display_errors(False)
from render import render_glyph
from PIL import Image, ImageDraw, ImageFont
D = r"C:\Users\Aryan\OneDrive\Documents\internship\pdfs"
order = json.load(open('order.json')); reps = json.load(open('reps.json'))
idxs = [int(a) for a in sys.argv[2:]]; out = sys.argv[1]
cols = 5; cw, ch = 280, 240
sheet = Image.new('L', (cw * cols, ch * ((len(idxs) + cols - 1) // cols)), 255); dr = ImageDraw.Draw(sheet)
for k, i in enumerate(idxs):
    fn, xr, code = reps[order[i]]; d = pymupdf.open(f"{D}\{fn}"); buf = d.extract_font(xr)[3]
    im = render_glyph(buf, code, size=230)
    x, y = (k % cols) * cw, (k // cols) * ch
    if im: sheet.paste(im.resize((cw - 10, int((cw - 10) * im.height / im.width))), (x + 5, y + 18))
    dr.text((x + 6, y + 3), f"#{i}", fill=0); dr.rectangle([x, y, x + cw - 1, y + ch - 1], outline=160)
sheet.save(out)
