"""
glyphfix — recover correct Marathi Unicode from PDFs whose embedded fonts have a broken ToUnicode map.

Problem
-------
Most court PDFs in this corpus were produced with subset TrueType fonts (TiroDevaMarathi, NirmalaUI)
whose /ToUnicode CMap is incomplete or wrong:
  * unmapped glyphs come out as control characters   (अनुवाद  ->  अ\\x13ुवाद)
  * some glyphs are mapped to the wrong string        (ण -> "र्ण",  pre-base ि -> "लि"/"नि")
  * the glyph->code assignment is different in every PDF (subset fonts), so a fixed table cannot work.
Text is also stored in *visual* order (pre-base ि and reph come out in the wrong place).

Method
------
1. Replace the ToUnicode of every affected font with an identity map into the Unicode Private Use Area
   (one 256-code block per font).  MuPDF then returns exact glyph codes with its own layout / reading order.
2. Hash the outline of every glyph in the embedded font.  The outline is identical in every PDF that uses
   the same typeface, so  outline_hash -> correct Unicode  can be labelled once (glyph_map.json).
3. Substitute PUA codes by their labels and reorder visual -> logical Unicode (pre-base ि, reph).

Public API:  load_glyph_map(path) -> labels,  extract_pdf(path, labels) -> dict
"""
import io
import re
import json
import hashlib
import logging

try:
    import pymupdf
except ImportError:                                    # older PyMuPDF
    import fitz as pymupdf
from fontTools.ttLib import TTFont

pymupdf.TOOLS.mupdf_display_errors(False)
logging.getLogger("fontTools").setLevel(logging.ERROR)

TARGETS = ("TiroDeva", "Tiro Deva", "NirmalaUI", "Nirmala UI", "ArialUnicodeMS", "Mangal", "Lohit", "SegoeUI", "CIDFont")  # BaseFont substrings of the affected typefaces
PUA_BASE = 0xE000
MAX_FONTS = 24                                         # simple fonts: 24 blocks of 256 codes in U+E000..U+F7FF
SPUA_BASE = 0xF0000                                    # Type0 fonts: one 64K block each in U+F0000..U+FFFFF
MAX_TYPE0 = 16
PRE_I = "«I»"                                # label: pre-base matra i (belongs AFTER the next cluster)
REPH = "«R»"                                 # label prefix: reph (belongs BEFORE the previous cluster)
XMARK = "«X»"                              # label: dot glyph that is a reph, unless it follows an anusvara
HALANT = "्"
BAD = "�"                                         # emitted for glyphs that have no trustworthy label
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# ── fonts ────────────────────────────────────────────────────────────────────────────────────────
def target_fonts(doc):
    """{font_xref: (basefont, 'TrueType'|'Type0')} for every affected font object in the document."""
    out = {}
    for pg in doc:
        for x in pg.get_fonts(full=True):
            if x[0] not in out and x[2] in ("TrueType", "Type0") and any(t in x[3] for t in TARGETS):
                out[x[0]] = (x[3], x[2])
    return out


def _glyph_hash(glyf, hmtx, name):
    coords, ends, _ = glyf[name].getCoordinates(glyf)
    if len(coords) == 0:
        return "E%d" % hmtx[name][0]                   # empty (space-like) glyph, keyed by advance width
    return hashlib.md5((str(list(coords)) + str(list(ends))).encode()).hexdigest()[:12]


def outline_hashes(doc, xref):
    """{code: outline_hash} for a simple TrueType font (single-byte code -> glyph via its cmap)."""
    try:
        font = TTFont(io.BytesIO(doc.extract_font(xref)[3]))
        glyf, hmtx, tables = font["glyf"], font["hmtx"], font["cmap"].tables
    except Exception:
        return {}
    code2glyph = {}
    for t in tables:
        for c, g in t.cmap.items():
            code2glyph.setdefault(c & 0xFF if c > 255 else c, g)
    out = {}
    for code, g in code2glyph.items():
        try:
            out[code] = _glyph_hash(glyf, hmtx, g)
        except Exception:
            continue
    return out


def type0_hashes(doc, xref):
    """({cid: outline_hash}, n_cids) for a Type0 (two-byte) font; CIDToGIDMap Identity or stream."""
    try:
        font = TTFont(io.BytesIO(doc.extract_font(xref)[3]))
        glyf, hmtx, order = font["glyf"], font["hmtx"], font.getGlyphOrder()
        desc = int(re.findall(r"(\d+) 0 R", doc.xref_get_key(xref, "DescendantFonts")[1])[0])
        c2g = doc.xref_get_key(desc, "CIDToGIDMap")
    except Exception:
        return {}, 0
    gid_hash = {}
    for gid, name in enumerate(order):
        try:
            gid_hash[gid] = _glyph_hash(glyf, hmtx, name)
        except Exception:
            continue
    if c2g[0] == "xref":                               # explicit CID -> GID table (2 bytes per CID)
        data = doc.xref_stream(int(c2g[1].split()[0]))
        out = {}
        for cid in range(len(data) // 2):
            gid = int.from_bytes(data[2 * cid:2 * cid + 2], "big")
            if gid in gid_hash:
                out[cid] = gid_hash[gid]
        return out, len(data) // 2
    return gid_hash, len(order)                        # Identity: cid == gid


def _pua_cmap(block):
    lo = PUA_BASE + 0x100 * block
    return ("/CIDInit/ProcSet findresource begin 12 dict begin begincmap /CMapName/Adobe-Identity-UCS def "
            "/CMapType 2 def 1 begincodespacerange <00> <FF> endcodespacerange "
            "1 beginbfrange <00> <FF> <%04X> endbfrange endcmap CMapName currentdict /CMap defineresource pop end end"
            % lo).encode()


def inject_pua(doc, xrefs):
    """Point each affected font's ToUnicode at its own PUA block. Index in `xrefs` == block number."""
    for block, xref in enumerate(xrefs):
        new = doc.get_new_xref()
        doc.update_object(new, "<< >>")
        doc.update_stream(new, _pua_cmap(block))
        doc.xref_set_key(xref, "ToUnicode", "%d 0 R" % new)


def _utf16(cp):
    cp -= 0x10000
    return "%04X%04X" % (0xD800 + (cp >> 10), 0xDC00 + (cp & 0x3FF))


def _pua_cmap_type0(block, n):
    base = SPUA_BASE + 0x10000 * block
    rows = ["<%04X> <%04X> <%s>" % (k * 256, min(k * 256 + 255, 0xFFFF), _utf16(base + k * 256))
            for k in range((min(n, 0x10000) + 255) // 256)]
    return ("/CIDInit/ProcSet findresource begin 12 dict begin begincmap /CMapName/Adobe-Identity-UCS def "
            "/CMapType 2 def 1 begincodespacerange <0000> <FFFF> endcodespacerange %d beginbfrange %s endbfrange "
            "endcmap CMapName currentdict /CMap defineresource pop end end" % (len(rows), " ".join(rows))).encode()


# ── glyph map ────────────────────────────────────────────────────────────────────────────────────
def load_glyph_map(path):
    """-> {outline_hash: label or None}.  None = no trustworthy label (junk / defective-PDF glyph)."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {h: v["u"] for h, v in raw.items()}


def map_sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


# ── visual -> logical reordering ─────────────────────────────────────────────────────────────────
def _is_cons(ch):
    return "क" <= ch <= "ह" or "क़" <= ch <= "य़" or ch == "ऱ"


def reorder(tokens):
    """tokens: glyph labels / plain chars in visual order -> (logical string, orphan_pre_i, orphan_reph)."""
    out, cstart, i, n = [], None, 0, len(tokens)
    orphan_i = orphan_r = 0
    while i < n:
        t = tokens[i]
        if t is None:                                   # unlabeled glyph
            out.append(BAD); cstart = None; i += 1; continue
        if t == XMARK:                                  # NirmalaUI dot glyph drawn before a pre-base ि
            if out and out[-1] == "ं":
                i += 1; continue
            t = REPH
        if t.startswith(PRE_I):                         # emit the following consonant cluster, then ि (+ attached signs)
            tail = t[len(PRE_I):]
            j, cluster = i + 1, []
            while j < n and tokens[j] and _is_cons(tokens[j][0]):
                cluster.append(tokens[j]); j += 1
                if not cluster[-1].endswith(HALANT):
                    break
            if cluster:
                cstart = len(out); out.extend("".join(cluster)); out.append("ि"); out.extend(tail); i = j
            else:
                out.append("ि"); out.extend(tail); orphan_i += 1; i += 1
            continue
        if t.startswith(REPH):                          # reph (+ optional attached signs): र् goes first
            if cstart is None:
                orphan_r += 1
            pos = cstart if cstart is not None else len(out)
            out[pos:pos] = list("र" + HALANT)
            out.extend(t[len(REPH):]); i += 1; continue
        if t and _is_cons(t[0]):
            if not (out and out[-1] == HALANT):         # a half-form before us continues the same cluster
                cstart = len(out)
        elif t and not ("ऀ" <= t[0] <= "ॿ"):
            cstart = None
        out.extend(t); i += 1
    return "".join(out), orphan_i, orphan_r


# ── extraction ───────────────────────────────────────────────────────────────────────────────────
def _word_anomalies(text):
    """Words that begin with a dependent vowel sign / virama / anusvara — impossible in valid Marathi."""
    words = text.split()
    bad = sum(1 for w in words if "ऀ" <= w[0] <= "ः" or "ऺ" <= w[0] <= "्" or w[0] == "ॢ")
    return bad, len(words)


def _set_tounicode(doc, xref, cmap_bytes):
    new = doc.get_new_xref()
    doc.update_object(new, "<< >>")
    doc.update_stream(new, cmap_bytes)
    doc.xref_set_key(xref, "ToUnicode", "%d 0 R" % new)


def extract_pdf(path, labels):
    """Extract one PDF. Returns dict with 'pages' (list of str) and quality metrics."""
    doc = pymupdf.open(path)
    simple, type0, unfixed = [], [], 0
    for xref, (_, sub) in target_fonts(doc).items():
        if sub == "TrueType":
            h = outline_hashes(doc, xref)
            if h and len(simple) < MAX_FONTS:
                simple.append((xref, h)); continue
        else:
            h, n = type0_hashes(doc, xref)
            if h and len(type0) < MAX_TYPE0:
                type0.append((xref, h, n)); continue
        unfixed += 1                                    # could not hash / too many fonts: left as the PDF has it
    res = {"n_pages": len(doc), "fonts_fixed": len(simple) + len(type0), "fonts_unfixed": unfixed,
           "glyph_tokens": 0, "unknown_tokens": 0, "orphan_pre_i": 0, "orphan_reph": 0}
    unknown_hashes = {}
    if not simple and not type0:
        pages = [p.get_text("text") for p in doc]
        res["method"] = "native"
    else:
        for b, (xref, _) in enumerate(simple):
            _set_tounicode(doc, xref, _pua_cmap(b))
        for b, (xref, _, n) in enumerate(type0):
            _set_tounicode(doc, xref, _pua_cmap_type0(b, n))
        fixed = doc          # extract from the modified document in memory (re-saving drops the change on some PDFs)
        pages = []
        hi = PUA_BASE + 0x100 * len(simple)
        for pg in fixed:
            lines = []
            for line in pg.get_text("text").split("\n"):
                toks = []
                for ch in line:
                    o = ord(ch)
                    if PUA_BASE <= o < hi:
                        h = simple[(o - PUA_BASE) >> 8][1].get((o - PUA_BASE) & 0xFF)
                    elif SPUA_BASE <= o < SPUA_BASE + 0x10000 * len(type0):
                        h = type0[(o - SPUA_BASE) >> 16][1].get((o - SPUA_BASE) & 0xFFFF)
                    else:
                        toks.append(ch); continue
                    label = labels.get(h)
                    res["glyph_tokens"] += 1
                    if label is None:
                        res["unknown_tokens"] += 1
                        unknown_hashes[h] = unknown_hashes.get(h, 0) + 1
                    toks.append(label)
                s_, oi, orr = reorder(toks)
                res["orphan_pre_i"] += oi; res["orphan_reph"] += orr
                lines.append(s_)
            pages.append("\n".join(lines))
        res["method"] = "glyphfix"
    doc.close()
    full = "\n".join(pages)
    bad, words = _word_anomalies(full)
    res.update({
        "pages": pages,
        "chars": len(full.strip()),
        "ctrl_chars_left": len(CTRL_RE.findall(full)),
        "word_anomalies_per_10k": round(10000 * bad / max(words, 1), 1),
        "unknown_share": round(res["unknown_tokens"] / max(res["glyph_tokens"], 1), 5),
        "unknown_hashes": dict(sorted(unknown_hashes.items(), key=lambda kv: -kv[1])[:30]),
    })
    return res
