"""Core helpers: PUA-injected extraction + glyph outline hashing for broken subset fonts."""
import io, re, hashlib, logging
import pymupdf
from fontTools.ttLib import TTFont
pymupdf.TOOLS.mupdf_display_errors(False)
logging.getLogger('fontTools').setLevel(logging.ERROR)
PUA_BASE = 0xE000
TARGETS = ('TiroDeva', 'NirmalaUI', 'ArialUnicodeMS')   # BaseFont substrings of affected typefaces
TARGET = 'TiroDeva'

def target_fonts(doc):
    """{font_xref: basefont} for every affected font object in the document."""
    out = {}
    for pg in doc:
        for x in pg.get_fonts(full=True):
            if any(t in x[3] for t in TARGETS) and x[2] == 'TrueType' and x[0] not in out:
                out[x[0]] = x[3]
    return out

def parse_tounicode(doc, xref, max_bytes=200_000):
    """Original ToUnicode as {code: unicode_str} for single-byte codes; {} if absent/oversized."""
    k = doc.xref_get_key(xref, "ToUnicode")
    if k[0] != 'xref': return {}
    data = doc.xref_stream(int(k[1].split()[0]))
    if len(data) > max_bytes: return {}
    data = data.decode('latin1'); m = {}
    for blk in re.findall(r'beginbfchar(.*?)endbfchar', data, re.S):
        for a, b in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', blk):
            try:
                code = int(a, 16)
                if code > 0xFF: continue
                m[code] = bytes.fromhex(b if len(b) % 4 == 0 else b.zfill(len(b) + 4 - len(b) % 4)).decode('utf-16-be', 'replace')
            except (ValueError, OverflowError): pass
    for blk in re.findall(r'beginbfrange(.*?)endbfrange', data, re.S):
        for a, b, c in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', blk):
            try:
                a, b, base = int(a, 16), int(b, 16), int(c, 16)
                for i in range(a, min(b, 0xFF) + 1):
                    try: m[i] = chr(base + i - a)
                    except (ValueError, OverflowError): pass
            except (ValueError, OverflowError): pass
    return m

def outline_hashes(doc, xref):
    """{code: outline_hash} from the embedded subset font (code -> glyph via its cmap)."""
    try:
        buf = doc.extract_font(xref)[3]
        f = TTFont(io.BytesIO(buf)); glyf = f['glyf']; hmtx = f['hmtx']; cmap_tables = f['cmap'].tables
    except Exception:
        return {}
    code2g = {}
    for t in cmap_tables:
        for c, g in t.cmap.items():
            code2g.setdefault(c & 0xFF if c > 255 else c, g)
    out = {}
    for code, g in code2g.items():
        try:
            coords, ends, _ = glyf[g].getCoordinates(glyf)
        except Exception:
            continue
        if len(coords) == 0:
            h = 'E%d' % hmtx[g][0]                      # empty glyph (space-like): keyed by advance
        else:
            h = hashlib.md5((str(list(coords)) + str(list(ends))).encode()).hexdigest()[:12]
        out[code] = h
    return out

def pua_cmap(block):
    lo = PUA_BASE + 0x100 * block
    return ("/CIDInit/ProcSet findresource begin 12 dict begin begincmap "
            "/CMapName/Adobe-Identity-UCS def /CMapType 2 def "
            "1 begincodespacerange <00> <FF> endcodespacerange "
            "1 beginbfrange <00> <FF> <%04X> endbfrange endcmap CMapName currentdict /CMap defineresource pop end end"
            % lo).encode()

def inject_pua(doc):
    """Replace ToUnicode of affected fonts with PUA identity maps. Returns [font_xref,...]; index = PUA block."""
    xrefs = list(target_fonts(doc))
    for blk, xr in enumerate(xrefs):
        new = doc.get_new_xref()
        doc.update_object(new, "<< >>")
        doc.update_stream(new, pua_cmap(blk))
        doc.xref_set_key(xr, "ToUnicode", "%d 0 R" % new)
    return xrefs
