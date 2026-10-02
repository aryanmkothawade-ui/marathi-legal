"""
Stage 2: Cleaning & Unicode Normalization
Reads raw extracted text files and produces clean, normalized text.
Key operations:
  - Strip control characters (found as artifacts in sample docs)
  - NFC Unicode normalization for Devanagari
  - Devanagari digit → Arabic digit normalization
  - Remove page number lines
  - Collapse whitespace
  - Filter too-short documents
  - Deduplicate by hash
Outputs to corpus/cleaned/
"""
import os
import sys
import re
import json
import unicodedata
import hashlib

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Indic NLP Normalizer ─────────────────────────────────────────────────────
# Handles Marathi-specific Unicode quirks beyond plain NFC:
# - Chandrabindu (ँ) vs Anusvara (ं) normalization
# - Nukta placement fixes
# - Visarga and vowel diacritic consistency
BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INDIC_RESOURCES = os.path.join(BASE_DIR, "indic_nlp_resources")
os.environ.setdefault('INDIC_RESOURCES_PATH', _INDIC_RESOURCES)

try:
    from indicnlp.normalize.indic_normalize import IndicNormalizerFactory
    _indic_normalizer = IndicNormalizerFactory().get_normalizer("mr")
    HAS_INDIC_NLP = True
except Exception:
    HAS_INDIC_NLP = False
    _indic_normalizer = None
IN_DIR    = os.path.join(BASE_DIR, "corpus", "raw_text")
OUT_DIR   = os.path.join(BASE_DIR, "corpus", "cleaned")
LOG_PATH  = os.path.join(BASE_DIR, "logs", "clean_log.json")

os.makedirs(OUT_DIR, exist_ok=True)

# ── Devanagari block constants ───────────────────────────────────────────────
DEVA_DIGITS = str.maketrans('०१२३४५६७८९', '0123456789')
DEVA_START, DEVA_END = 0x0900, 0x097F

# ── Compiled regex patterns ──────────────────────────────────────────────────
# Control characters to remove (everything < 0x20 except \n, \r, \t)
CTRL_RE      = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')
# Zero-width / invisible unicode
ZWS_RE       = re.compile(r'[\u200b\u200c\u200d\ufeff\u00ad\u2028\u2029]')
# Lone page numbers on their own line (1-3 digits, possibly padded)
PAGE_NUM_RE  = re.compile(r'^\s*\d{1,3}\s*$', flags=re.MULTILINE)
# Multiple spaces → single space
MULTI_SPC_RE = re.compile(r'[ \t]+')
# 3+ newlines → double newline
MULTI_NL_RE  = re.compile(r'\n{3,}')
# Repeated hyphen/dash lines (table separators)
SEP_LINE_RE  = re.compile(r'^[-_=]{5,}\s*$', flags=re.MULTILINE)


def devanagari_ratio(text: str) -> float:
    if not text:
        return 0.0
    deva = sum(1 for c in text if DEVA_START <= ord(c) <= DEVA_END)
    return deva / len(text)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean_text(raw: str) -> tuple[str, list]:
    """Apply all cleaning steps. Returns (cleaned_text, list_of_warnings)."""
    warnings = []
    text = raw

    # 1. Strip control characters (PDF encoding artifacts like \u0018, \u0012)
    ctrl_count = len(CTRL_RE.findall(text))
    if ctrl_count > 0:
        warnings.append(f"Removed {ctrl_count} control characters")
    text = CTRL_RE.sub('', text)

    # 2. Strip zero-width / invisible unicode
    text = ZWS_RE.sub('', text)

    # 3. NFC normalization — critical for Devanagari matra composition
    text = unicodedata.normalize('NFC', text)

    # 3b. Indic NLP normalization — Marathi-specific Unicode quirks
    #     (chandrabindu variants, nukta placement, visarga consistency)
    if HAS_INDIC_NLP and _indic_normalizer:
        text = _indic_normalizer.normalize(text)

    # 4. Devanagari digit → Arabic digit
    text = text.translate(DEVA_DIGITS)

    # 5. Remove lone page number lines
    text = PAGE_NUM_RE.sub('', text)

    # 6. Remove separator lines
    text = SEP_LINE_RE.sub('', text)

    # 6.5 Fix specific OCR / PDF extraction artifacts
    # The OCR engine frequently duplicates the letter 'ण'
    text = text.replace('णण', 'ण')
    
    # Fix specific broken words we found in the corpus
    text = text.replace('टंकलिखि\nत', 'टंकलिखित')
    text = text.replace('टंकलिखि\r\nत', 'टंकलिखित')
    text = text.replace('उपरोल्लेखि\nत', 'उपरोल्लेखित')
    text = text.replace('उपरोल्लेखि\r\nत', 'उपरोल्लेखित')
    
    # Fix spaced out headers
    text = text.replace('न्या य नि र्ण य', 'न्यायनिर्णय')
    text = text.replace('आ दे श', 'आदेश')
    
    # Known OCR Error Dictionary for systematically mangled Marathi legal terms
    ocr_fixes = {
        'अिुवाद': 'अनुवाद',
        'सवोच्च': 'सर्वोच्च',
        'न्यायाियात': 'न्यायालयात',
        'नदवार्ी': 'दिवाणी',
        'अलिकाररता': 'अधिकारिता',
        'िवाद यालचका': 'विवाद याचिका',
        'यालचका': 'याचिका',
        'यालचकाकताण': 'याचिकाकर्ता',
        'नवरुद्ध': 'विरुद्ध',
        'लिलमटेड': 'लिमिटेड',
        'ििंजय': 'धनंजय',
        'न्यायमूती': 'न्यायमूर्ती',
        'लशन्हाि': 'शिनहान',
        'कॅरोि': 'कॅरोल',
        'सनवणसेस': 'सर्व्हिसेस'
    }
    for broken, fixed in ocr_fixes.items():
        text = text.replace(broken, fixed)
    
    # Fix hard line breaks immediately following common Marathi conjunctions/words
    # This prevents sentences from being awkwardly split across lines.
    for word in ['आणि', 'किंवा', 'व', 'तसेच', 'म्हणून', 'कारण', 'या', 'ते', 'हे', 'निर्माण', 'ठिकाण', 'प्रमाण']:
        text = re.sub(rf'{word}\s*\n\s*', f'{word} ', text)

    # 7. Collapse horizontal whitespace
    text = MULTI_SPC_RE.sub(' ', text)

    # 8. Normalize line endings + collapse excessive newlines
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = MULTI_NL_RE.sub('\n\n', text)

    # 9. Strip leading/trailing whitespace per line
    lines = [line.rstrip() for line in text.split('\n')]
    text = '\n'.join(lines).strip()

    return text, warnings


def process_all():
    files = sorted([f for f in os.listdir(IN_DIR) if f.endswith(".txt")])
    log_entries = []
    seen_hashes = {}

    print("=" * 65)
    print("  MLDC -- Stage 2: Cleaning & Normalization")
    print("=" * 65)

    discarded = 0
    for fname in files:
        doc_id = os.path.splitext(fname)[0]
        in_path  = os.path.join(IN_DIR, fname)
        out_path = os.path.join(OUT_DIR, fname)

        with open(in_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        print(f"\n[>>] Cleaning: {fname}")

        cleaned, warnings = clean_text(raw_text)

        raw_chars   = len(raw_text)
        clean_chars = len(cleaned)
        deva_r      = devanagari_ratio(cleaned)
        h           = sha256(cleaned)

        # Filter: too short
        if clean_chars < 200:
            print(f"  [DISCARD] Too short ({clean_chars} chars)")
            log_entries.append({"doc_id": doc_id, "status": "discarded_short",
                                "clean_chars": clean_chars})
            discarded += 1
            continue

        # Filter: non-Marathi
        if deva_r < 0.30:
            print(f"  [DISCARD] Low Devanagari ratio ({deva_r:.2%})")
            log_entries.append({"doc_id": doc_id, "status": "discarded_language",
                                "devanagari_ratio": round(deva_r, 3)})
            discarded += 1
            continue

        # Check duplicate
        if h in seen_hashes:
            print(f"  [DUPLICATE] Same as {seen_hashes[h]}")
            log_entries.append({"doc_id": doc_id, "status": "duplicate_of",
                                "duplicate_of": seen_hashes[h]})
            discarded += 1
            continue
        seen_hashes[h] = doc_id

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(cleaned)

        print(f"  Raw chars   : {raw_chars}")
        print(f"  Clean chars : {clean_chars}  ({(raw_chars - clean_chars)} removed)")
        print(f"  Devanagari  : {deva_r:.1%}")
        if warnings:
            for w in warnings:
                print(f"  [NOTE] {w}")

        log_entries.append({
            "doc_id": doc_id,
            "status": "ok",
            "raw_chars": raw_chars,
            "clean_chars": clean_chars,
            "chars_removed": raw_chars - clean_chars,
            "devanagari_ratio": round(deva_r, 3),
            "sha256": h,
            "warnings": warnings,
        })

    ok_count = sum(1 for e in log_entries if e["status"] == "ok")
    print(f"\n{'=' * 65}")
    print(f"  Done. {ok_count} cleaned, {discarded} discarded/skipped.")
    print("=" * 65)

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log_entries, f, ensure_ascii=False, indent=2)
    print(f"[OK] Log saved: {LOG_PATH}")


if __name__ == "__main__":
    process_all()
