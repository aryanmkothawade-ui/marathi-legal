"""
textclean — cleaning of Marathi court-judgment text produced by 01b_fix_glyphs.py.

Input is one string per document with pages separated by "\\n\\f\\n". Output is a normalised document where
paragraphs are separated by a blank line, short header lines (party blocks, titles) stay on their own lines,
page furniture is gone, and invisible / corrupt characters are handled explicitly and counted.

Design notes (what changed versus the old 02_clean.py)
  * Runs on *repaired* text, so there is no `ocr_fixes` dictionary and no control-character deletion that eats letters.
  * Page furniture is found per document: lone page numbers and lines that repeat at the top/bottom of many pages.
  * The translation disclaimer is removed as a block, not word by word.
  * Wrapped lines are re-joined by line width + punctuation + numbering, never by a word list (the old
    "join after व/हे/या" regex merged paragraph breaks and glued unrelated lines).
  * U+2028/2029 become newlines instead of being deleted; ZWJ/ZWNJ are removed deliberately and counted.
"""
import re
import hashlib
import unicodedata

PAGE_SEP = "\n\f\n"
DEVA_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

# ── character level ──────────────────────────────────────────────────────────────────────────────
NEWLINE_LIKE_RE = re.compile(r"[  \u0085\x0b\x0c]")
ZERO_WIDTH_RE = re.compile(r"[​‌‍⁠﻿­]")
CTRL_RE = re.compile(r"[\x00-\x08\x0e-\x1f\x7f]")
SPACE_RE = re.compile(r"[ \t  -   　]+")
SPACE_BEFORE_PUNCT_RE = re.compile(r" +([,.;:!?।\)\]])")

# ── page furniture ───────────────────────────────────────────────────────────────────────────────
LONE_NUMBER_RE = re.compile(r"^[\(\[]?\d{1,4}[\)\]]?$")
FILE_STAMP_RE = re.compile(r"\.(?:docx?|odt|pdf|rtf)\s*$|^:::.*:::$|^Page\s+\d+\s+of\s+\d+$", re.I)
END_MARK_RE = re.compile(r"^[xX\-–—_=*\s]{5,}$|^\*{3,}$")
# Translation boilerplate: heading line + disclaimer block (spelling is stable now that glyphs are repaired).
TRANSLATION_NOTE_RE = re.compile(r"^\(?\s*इंग्रजी(?:त|मध्ये|\s+भाषेतील)?[^\n]{0,120}मराठी\s+(?:भाषेत\s+)?(?:अनुवाद|भाषांतर)[^\n]{0,20}$", re.M)
DISCLAIMER_RE = re.compile(r"अस्वीकरण\s*[:\-]?[\s\S]{0,900}?(?:वैध\s+मानला\s+जाईल|वैध\s+मानले\s+जाईल)\s*[\.\"”'’।]*", re.U)
REPEAT_MIN_PAGES = 3

# ── paragraph reconstruction ─────────────────────────────────────────────────────────────────────
NUMBERING_START_RE = re.compile(r"^(?:\(?\d{1,3}[\.\)]|\([a-zA-Zऀ-ॿ]{1,3}\)|[a-zA-Zऀ-ॿ]\)|[•\-–]\s)")
LONE_NUMBERING_RE = re.compile(r"^\(?\d{1,3}[\.\)]$|^\([a-zA-Zऀ-ॿ]{1,3}\)$")
SENTENCE_END_RE = re.compile(r"[।.?!:;\"”’\)\]]$")


def normalise_chars(text, keep_devanagari_digits=False):
    """Unicode-level clean-up. Returns (text, stats)."""
    st = {}
    text = unicodedata.normalize("NFC", text)
    text = NEWLINE_LIKE_RE.sub("\n", text)
    st["zero_width_removed"] = len(ZERO_WIDTH_RE.findall(text))
    text = ZERO_WIDTH_RE.sub("", text)
    st["ctrl_removed"] = len(CTRL_RE.findall(text))
    text = CTRL_RE.sub("", text)
    st["unknown_glyph_marks"] = text.count("�")
    text = text.replace("�", "")
    if not keep_devanagari_digits:
        text = text.translate(DEVA_DIGITS)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = SPACE_RE.sub(" ", text)
    text = unicodedata.normalize("NFC", text)
    return text, st


def _norm_line(line):
    return re.sub(r"\d+", "#", line.strip())


def strip_page_furniture(pages):
    """Remove lone page numbers and lines repeated at page tops/bottoms. Returns (list of line-lists, stats)."""
    pls = [[l.strip() for l in p.split("\n")] for p in pages]
    pls = [[l for l in pl if l] for pl in pls]
    counts = {}
    for pl in pls:
        seen = set()
        for l in pl[:2] + pl[-2:]:
            k = _norm_line(l)
            if len(k) < 110 and k not in seen:
                seen.add(k); counts[k] = counts.get(k, 0) + 1
    thresh = max(REPEAT_MIN_PAGES, int(0.3 * len(pls)))
    repeated = {k for k, c in counts.items() if c >= thresh and not LONE_NUMBER_RE.match(k) and not NUMBERING_START_RE.match(k)}
    removed = {"page_numbers": 0, "repeated_headers": 0, "file_stamps": 0, "end_marks": 0}
    out = []
    for pl in pls:
        keep = list(pl)
        # edge lines only (first/last 2): page numbers, stamps and repeated furniture
        i = 0
        while keep and i < 2 and i < len(keep):
            l = keep[i]
            if LONE_NUMBER_RE.match(l):
                keep.pop(i); removed["page_numbers"] += 1
            elif FILE_STAMP_RE.search(l):
                keep.pop(i); removed["file_stamps"] += 1
            elif _norm_line(l) in repeated:
                keep.pop(i); removed["repeated_headers"] += 1
            else:
                i += 1
        j = 0
        while keep and j < 2 and len(keep) > j:
            l = keep[-1 - j]
            if LONE_NUMBER_RE.match(l):
                keep.pop(-1 - j); removed["page_numbers"] += 1
            elif FILE_STAMP_RE.search(l):
                keep.pop(-1 - j); removed["file_stamps"] += 1
            elif _norm_line(l) in repeated:
                keep.pop(-1 - j); removed["repeated_headers"] += 1
            else:
                j += 1
        out.append(keep)
    return out, removed, sorted(repeated)


def remove_boilerplate(text):
    """Remove translation heading + disclaimer blocks. Returns (text, count)."""
    n = len(DISCLAIMER_RE.findall(text)) + len(TRANSLATION_NOTE_RE.findall(text))
    text = DISCLAIMER_RE.sub("", text)
    text = TRANSLATION_NOTE_RE.sub("", text)
    return text, n


def _typical_width(lines):
    lens = sorted(len(l) for l in lines if len(l) >= 40)
    if not lens:
        return 90
    return lens[int(0.9 * (len(lens) - 1))]


def build_paragraphs(lines):
    """Re-join wrapped lines. Returns list of (unit_text, is_short)."""
    W = max(40, _typical_width(lines))
    units = []
    cur = None
    for l in lines:
        if cur is None:
            cur = l; continue
        prev = cur
        join = True
        if NUMBERING_START_RE.match(l) and not LONE_NUMBERING_RE.match(prev):
            join = False
        elif LONE_NUMBERING_RE.match(prev):
            join = True
        elif len(prev) < 0.62 * W:
            join = False
        elif SENTENCE_END_RE.search(prev) and len(prev) < 0.93 * W:
            join = False
        if join:
            cur = prev + " " + l
        else:
            units.append(cur); cur = l
    if cur is not None:
        units.append(cur)
    return [(u, len(u) < 0.62 * W) for u in units]


def assemble(units):
    """Blank line between paragraphs; single newline inside blocks of short header-like lines."""
    out = []
    for i, (u, short) in enumerate(units):
        if i:
            pu, pshort = units[i - 1]
            out.append("\n" if (short and pshort and not NUMBERING_START_RE.match(u)) else "\n\n")
        out.append(u)
    return "".join(out)


def tidy(text):
    text = SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(l.strip() for l in text.split("\n"))
    # lines that carry no letters at all (stray punctuation / separators)
    text = "\n".join(l for l in text.split("\n") if not l or re.search(r"[ऀ-ॿA-Za-z0-9]", l))
    return text.strip()


def clean_document(raw, keep_devanagari_digits=False):
    """Full cleaning of one document string. Returns (cleaned_text, stats)."""
    raw_pages = raw.split(PAGE_SEP) if PAGE_SEP in raw else raw.split("\f")   # split BEFORE form-feeds are normalised away
    st = {}
    pages = []
    for p in raw_pages:
        pt, pst = normalise_chars(p, keep_devanagari_digits)
        pages.append(pt)
        for k, v in pst.items():
            st[k] = st.get(k, 0) + v
    st["pages"] = len(pages)
    pls, removed, repeated = strip_page_furniture(pages)
    st.update(removed)
    st["repeated_header_patterns"] = repeated[:5]
    joined = "\n".join("\n".join(pl) for pl in pls)
    joined, st["boilerplate_removed"] = remove_boilerplate(joined)
    lines = [l.strip() for l in joined.split("\n") if l.strip()]
    lines = [l for l in lines if not END_MARK_RE.match(l)]
    units = build_paragraphs(lines)
    cleaned = tidy(assemble(units))
    st["paragraphs"] = cleaned.count("\n\n") + 1 if cleaned else 0
    return cleaned, st


# ── quality / dedup helpers ──────────────────────────────────────────────────────────────────────
def devanagari_ratio(text):
    deva = sum(1 for c in text if "ऀ" <= c <= "ॿ")
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    return deva / max(deva + latin, 1)


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def simhash(text, n=3, bits=64):
    """64-bit SimHash over word n-grams (near-duplicate detection)."""
    import numpy as np
    words = text.split()
    if len(words) < n:
        words = words + [""] * (n - len(words))
    buf = b"".join(hashlib.md5(" ".join(words[i:i + n]).encode("utf-8")).digest()[:8] for i in range(len(words) - n + 1))
    h = np.frombuffer(buf, dtype=">u8").astype(np.uint64)
    ones = ((h[:, None] >> np.arange(bits, dtype=np.uint64)) & np.uint64(1)).sum(axis=0)
    out = 0
    for b in np.nonzero(ones * 2 > len(h))[0]:
        out |= 1 << int(b)
    return out


def hamming(a, b):
    return bin(a ^ b).count("1")


def near_duplicates(items, max_dist=6):
    """items: list of (doc_id, simhash, priority). Returns {dropped_doc: kept_doc}. Higher priority is kept."""
    bands = {}
    for idx, (_, h, _) in enumerate(items):
        for b in range(4):
            bands.setdefault((b, (h >> (16 * b)) & 0xFFFF), []).append(idx)
    parent = list(range(len(items)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for members in bands.values():
        if len(members) < 2 or len(members) > 200:
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                if find(a) != find(b) and hamming(items[a][1], items[b][1]) <= max_dist:
                    parent[find(a)] = find(b)
    groups = {}
    for i in range(len(items)):
        groups.setdefault(find(i), []).append(i)
    dropped = {}
    for g in groups.values():
        if len(g) > 1:
            keep = max(g, key=lambda i: items[i][2])
            for i in g:
                if i != keep:
                    dropped[items[i][0]] = items[keep][0]
    return dropped
