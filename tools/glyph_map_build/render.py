import io
from PIL import Image, ImageDraw, ImageFont, ImageChops
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen

class Flat(BasePen):
    def __init__(self, gs):
        super().__init__(gs); self.contours = []; self.cur = None
    def _moveTo(self, p): self.cur = [p]
    def _lineTo(self, p): self.cur.append(p)
    def _qCurveToOne(self, p1, p2):
        p0 = self.cur[-1]
        for i in range(1, 9):
            t = i / 8; self.cur.append(((1-t)**2*p0[0]+2*(1-t)*t*p1[0]+t*t*p2[0], (1-t)**2*p0[1]+2*(1-t)*t*p1[1]+t*t*p2[1]))
    def _curveToOne(self, p1, p2, p3):
        p0 = self.cur[-1]
        for i in range(1, 9):
            t = i / 8; a=(1-t)**3; b=3*(1-t)**2*t; c=3*(1-t)*t*t; d=t**3
            self.cur.append((a*p0[0]+b*p1[0]+c*p2[0]+d*p3[0], a*p0[1]+b*p1[1]+c*p2[1]+d*p3[1]))
    def _closePath(self):
        if self.cur: self.contours.append(self.cur); self.cur = None
    _endPath = _closePath

def render_glyph(font_bytes, code, size=120, upm_ascent=0.95, descent=0.45):
    f = TTFont(io.BytesIO(font_bytes)); gs = f.getGlyphSet(); upm = f['head'].unitsPerEm
    code2g = {}
    for t in f['cmap'].tables:
        for c, g in t.cmap.items(): code2g.setdefault(c & 0xFF if c > 255 else c, g)
    g = code2g.get(code)
    if g is None: return None
    pen = Flat(gs); gs[g].draw(pen)
    adv = f['hmtx'][g][0]
    W = int(size * 1.6); H = size
    sc = size / (upm * (upm_ascent + descent)); base = int(H * upm_ascent / (upm_ascent + descent))
    ox = (W - adv * sc) / 2
    img = Image.new('1', (W, H), 0)
    for cont in (c for c in pen.contours if len(c) >= 3):
        m = Image.new('1', (W, H), 0)
        ImageDraw.Draw(m).polygon([(ox + x * sc, base - y * sc) for x, y in cont], fill=1)
        img = ImageChops.logical_xor(img, m)
    return img.convert('L').point(lambda v: 255 - v * 255)  # black glyph on white
