"""
Stage 4: PII Anonymization — HLDC Paper Methodology (Marathi Adaptation)
Reads segmented JSON files and anonymizes PII in all text fields.

Replacements:
  - Person names       → <नाव>
  - Locations/places   → <ठिकाण>
  - Advocates names    → <वकील-नाव>
  - Judge names        → <न्यायाधीश>
  - Phone numbers      → <फोन>
  - Aadhaar numbers    → <ओळखपत्र>
  - PAN cards          → <ओळखपत्र>
  - Organizations      → <संस्था>

Saves anonymized JSON to corpus/anonymized/
Saves anonymization log to logs/anonymization_log.jsonl

KEY IMPROVEMENTS vs previous version:
  1. CHECKPOINT: skips already-anonymized documents (safe to re-run)
  2. LAZY NER LOAD: model loads once; if download fails → regex-only mode (no crash)
  3. PROGRESS COUNTER: [N/Total] so you know it's running
  4. BATCH LOG SAVE: log flushed every 100 docs to prevent data loss
"""
import os
import sys
import re
import json
import copy

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_DIR   = os.path.join(BASE_DIR, "corpus", "segmented")
OUT_DIR  = os.path.join(BASE_DIR, "corpus", "anonymized")
LOG_DIR  = os.path.join(BASE_DIR, "logs")
ANON_LOG = os.path.join(LOG_DIR, "anonymization_log.jsonl")

os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════
# NER MODEL — LAZY LOAD WITH GRACEFUL FALLBACK
# ═══════════════════════════════════════════════════════════════════════════
_ner_pipeline = None
_ner_loaded   = False

def get_ner_pipeline():
    """Load NER model once; return None if unavailable (triggers regex-only mode)."""
    global _ner_pipeline, _ner_loaded
    if _ner_loaded:
        return _ner_pipeline
    _ner_loaded = True
    try:
        from transformers import pipeline as hf_pipeline
        import torch
        device_id = 0 if torch.cuda.is_available() else -1
        _ner_pipeline = hf_pipeline(
            "ner",
            model="kananshah/marathi-legal-ner-finetuned",
            aggregation_strategy="simple",
            device=device_id
        )
        mode = "GPU (CUDA)" if device_id == 0 else "CPU"
        print(f"[+] NER model loaded on {mode}.")
    except Exception as e:
        print(f"[!] NER model unavailable ({type(e).__name__}: {e})")
        print("[!] Falling back to REGEX-ONLY anonymization (phones, Aadhaar, PAN, judge/advocate titles).")
        _ner_pipeline = None
    return _ner_pipeline


# ═══════════════════════════════════════════════════════════════════════════
# REGEX PATTERNS
# ═══════════════════════════════════════════════════════════════════════════

# Phone: Indian format (10 digits, optional +91 prefix)
PHONE_RE = re.compile(
    r'(?:\+91[\s\-]?)?(?:\(?0?\)?[\s\-]?)?[6-9]\d{9}\b'
)

# Aadhaar: 12 digits (possibly spaced in groups of 4)
AADHAAR_RE = re.compile(
    r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b'
)

# PAN card: 5 uppercase letters + 4 digits + 1 uppercase letter
PAN_RE = re.compile(
    r'\b[A-Z]{5}[0-9]{4}[A-Z]\b'
)

# Judge names: preceded by न्या. / न्यायमूर्ती / माननीय
JUDGE_TITLE_RE = re.compile(
    r'(?:न्या\.|न्यायमूर्ती|माननीय\s+न्यायमूर्ती|मा\.)\s+'
    r'([\u0900-\u097F]{2,}(?:\s+[\u0900-\u097F]{2,}){0,2})',
    re.IGNORECASE
)

# Advocate names: preceded by अॅड. / अधिवक्ता / वकील
ADVOCATE_TITLE_RE = re.compile(
    r'(?:अॅड\.|अधिवक्ता|वकील|Advocate|Adv\.)\s+'
    r'([\u0900-\u097FA-Z][^\n,;।]{2,25}?)(?=\s*[,\n।;]|$)',
    re.IGNORECASE
)

# Persons with श्री/श्रीमती titles
TITLE_PERSON_RE = re.compile(
    r'(?:श्री|श्रीमती|कुमारी|सौ\.?)\s+'
    r'([\u0900-\u097F]{2,}(?:\s+[\u0900-\u097F]{2,}){0,2})',
    re.IGNORECASE
)

# Major court city names to protect from over-anonymization
PROTECTED_CITIES = {'मुंबई', 'नागपूर', 'औरंगाबाद', 'पुणे', 'Mumbai', 'Nagpur', 'Pune'}


# ═══════════════════════════════════════════════════════════════════════════
# ANONYMIZATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class Anonymizer:
    def __init__(self):
        self.replacements = []  # for logging

    def _log(self, doc_id, original, replaced, method):
        self.replacements.append({
            "doc_id": doc_id,
            "original": original,
            "replaced": replaced,
            "method": method
        })

    def anonymize_text(self, text: str, doc_id: str) -> tuple:
        """Anonymize all PII in text using Regex + optional NER.
        Returns (anonymized_text, replacement_count).
        """
        if not text or not text.strip():
            return text, 0

        count = 0

        # ── STEP 1: Structural Regex PII (highest confidence) ──────────────

        def replace_phone(m):
            nonlocal count
            self._log(doc_id, m.group(0), '<फोन>', 'regex_phone')
            count += 1
            return '<फोन>'
        text = PHONE_RE.sub(replace_phone, text)

        def replace_aadhaar(m):
            nonlocal count
            orig = m.group(0)
            digits_only = re.sub(r'[\s\-]', '', orig)
            if len(digits_only) == 12:
                self._log(doc_id, orig, '<ओळखपत्र>', 'regex_aadhaar')
                count += 1
                return '<ओळखपत्र>'
            return orig
        text = AADHAAR_RE.sub(replace_aadhaar, text)

        def replace_pan(m):
            nonlocal count
            self._log(doc_id, m.group(0), '<ओळखपत्र>', 'regex_pan')
            count += 1
            return '<ओळखपत्र>'
        text = PAN_RE.sub(replace_pan, text)

        # ── STEP 2: NER Model (if available) ───────────────────────────────
        ner = get_ner_pipeline()
        if ner:
            try:
                # Chunk text to avoid 512 token limit
                def chunk_text(t, max_len=500):
                    # 500 chars is around 100-150 words, comfortably under the 512 subword token limit
                    chunks = []
                    start = 0
                    while start < len(t):
                        max_char_len = min(len(t) - start, max_len)
                        if start + max_char_len >= len(t):
                            chunks.append((t[start:], start))
                            break
                            
                        # Try to split at a newline first
                        split_at = t.rfind('\n', start, start + max_char_len)
                        if split_at <= start + (max_char_len // 2): # If no newline in the last half
                            # Fallback to a space
                            split_at = t.rfind(' ', start, start + max_char_len)
                            
                        if split_at <= start:
                            split_at = start + max_char_len
                            
                        chunks.append((t[start:split_at], start))
                        start = split_at
                    return chunks

                chunks = chunk_text(text)
                chunk_strs = [c[0] for c in chunks]
                chunk_offsets = [c[1] for c in chunks]

                all_entities = []
                if chunk_strs:
                    try:
                        batch_ents = ner(chunk_strs, batch_size=16)
                        # Normalise pipeline output (single vs multi)
                        if len(chunk_strs) == 1 and batch_ents and isinstance(batch_ents[0], dict):
                            batch_ents = [batch_ents]
                        for i, chunk_ents in enumerate(batch_ents):
                            offset = chunk_offsets[i]
                            if not isinstance(chunk_ents, list):
                                continue
                            for ent in chunk_ents:
                                ent['start'] += offset
                                ent['end'] += offset
                                all_entities.append(ent)
                    except Exception as ce:
                        print(f"  [!] NER batch failed on {doc_id}: {ce}")

                # Sort in reverse order so replacements don't shift indices
                entities = sorted(all_entities, key=lambda x: x['start'], reverse=True)

                for ent in entities:
                    label = ent.get('entity_group', ent.get('entity', ''))
                    start, end = ent['start'], ent['end']
                    word = ent.get('word', text[start:end])

                    # Protect major court cities
                    if word in PROTECTED_CITIES and \
                       ('उच्च न्यायालय' in text or 'खंडपीठ' in text):
                        continue

                    replacement = None
                    label_up = label.upper()
                    if 'PER' in label_up or 'PERSON' in label_up:
                        replacement = '<नाव>'
                    elif 'LOC' in label_up or 'LOCATION' in label_up:
                        replacement = '<ठिकाण>'
                    elif any(k in label_up for k in ('ORG', 'ORGANIZATION', 'COURT')):
                        replacement = '<संस्था>'

                    if replacement:
                        original_str = text[start:end]
                        self._log(doc_id, original_str, replacement, f'ner_{label}')
                        count += 1
                        text = text[:start] + replacement + text[end:]

            except Exception as e:
                print(f"  [!] NER failed on {doc_id}: {e}")

        # ── STEP 3: Fallback Title Regex (catches what NER missed) ─────────

        def replace_judge(m):
            nonlocal count
            full_match = m.group(0)
            name_part  = m.group(1)
            if '<' not in name_part:
                self._log(doc_id, name_part, '<न्यायाधीश>', 'title_judge')
                count += 1
                return full_match.replace(name_part, '<न्यायाधीश>')
            return full_match
        text = JUDGE_TITLE_RE.sub(replace_judge, text)

        def replace_advocate(m):
            nonlocal count
            full_match = m.group(0)
            name_part  = m.group(1)
            if len(name_part.strip()) > 2 and '<' not in name_part:
                self._log(doc_id, name_part, '<वकील-नाव>', 'title_advocate')
                count += 1
                return full_match.replace(name_part, '<वकील-नाव>')
            return full_match
        text = ADVOCATE_TITLE_RE.sub(replace_advocate, text)

        def replace_titled_person(m):
            nonlocal count
            full_match = m.group(0)
            name_part  = m.group(1)
            if '<' not in name_part:
                self._log(doc_id, name_part, '<नाव>', 'title_person')
                count += 1
                return full_match.replace(name_part, '<नाव>')
            return full_match
        text = TITLE_PERSON_RE.sub(replace_titled_person, text)

        return text, count

    def anonymize_document(self, doc: dict) -> tuple:
        """Anonymize all text fields in a segmented document dict.
        Returns (anonymized_doc, total_replacement_count).
        """
        result = copy.deepcopy(doc)
        doc_id = doc.get("doc_id", "unknown")
        total  = 0

        for section_key in result.get("sections", {}):
            text = result["sections"][section_key]
            if isinstance(text, str) and text.strip():
                anon, n = self.anonymize_text(text, doc_id)
                result["sections"][section_key] = anon
                total += n

        parties = result.get("parties", {})
        for field in ("petitioner", "respondent", "petitioner_advocate", "respondent_advocate"):
            if field in parties and isinstance(parties[field], str):
                anon, _ = self.anonymize_text(parties[field], doc_id)
                result["parties"][field] = anon

        result.setdefault("quality", {})
        result["quality"]["anonymized"]       = True
        result["quality"]["pii_replacements"] = total

        return result, total


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def process_all():
    all_files = sorted(f for f in os.listdir(IN_DIR) if f.endswith(".json"))
    total     = len(all_files)

    # ── Determine which files still need processing (CHECKPOINT) ───────────
    todo = []
    skip = 0
    for fname in all_files:
        out_path = os.path.join(OUT_DIR, fname)
        if os.path.exists(out_path):
            skip += 1
        else:
            todo.append(fname)

    print("=" * 65)
    print("  MLDC -- Stage 4: PII Anonymization (HLDC Paper Method)")
    print("=" * 65)
    print(f"  Total segmented docs : {total}")
    print(f"  Already anonymized   : {skip}  (checkpoint — will SKIP)")
    print(f"  To process now       : {len(todo)}")
    print("=" * 65)

    if not todo:
        print("[OK] All documents already anonymized. Nothing to do.")
        return

    # Trigger NER load (with fallback) before the loop
    get_ner_pipeline()

    anonymizer       = Anonymizer()
    total_replacements = 0
    LOG_BATCH        = 100   # flush log every N docs

    for idx, fname in enumerate(todo, start=1):
        doc_id   = os.path.splitext(fname)[0]
        in_path  = os.path.join(IN_DIR, fname)
        out_path = os.path.join(OUT_DIR, fname)

        try:
            with open(in_path, "r", encoding="utf-8") as f:
                doc = json.load(f)
        except Exception as e:
            print(f"[{idx}/{len(todo)}] [ERROR] {fname}: cannot read — {e}")
            continue

        print(f"[{idx}/{len(todo)}] Anonymizing: {fname}", end="  ", flush=True)
        try:
            result, n = anonymizer.anonymize_document(doc)
        except Exception as e:
            print(f"\n  [ERROR] anonymization failed: {e}")
            continue

        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"\n  [ERROR] cannot write output: {e}")
            continue

        total_replacements += n
        print(f"→ {n} replacements")

        # Flush log every LOG_BATCH docs to prevent data loss
        if idx % LOG_BATCH == 0:
            with open(ANON_LOG, "a", encoding="utf-8") as lf:
                for entry in anonymizer.replacements:
                    lf.write(json.dumps(entry, ensure_ascii=False) + "\n")
            anonymizer.replacements.clear()
            print(f"  [LOG] Flushed anonymization log at {idx} docs.")

    # Final log flush
    if anonymizer.replacements:
        with open(ANON_LOG, "a", encoding="utf-8") as lf:
            for entry in anonymizer.replacements:
                lf.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\n{'=' * 65}")
    print(f"  Processed this run      : {len(todo)}")
    print(f"  Total PII replacements  : {total_replacements}")
    print(f"  Avg per doc             : {total_replacements // max(len(todo), 1)}")
    print("=" * 65)
    print(f"[OK] Anonymized files in : {OUT_DIR}")
    print(f"[OK] Log appended to     : {ANON_LOG}")
    print("[!] NOTE: Log contains original PII — keep private.")


if __name__ == "__main__":
    process_all()
