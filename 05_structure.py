"""
Stage 5: Build Final JSONL Corpus
Reads anonymized JSON files and assembles the final MLDC corpus.
Each document becomes one JSON line in corpus/final/mldc_v1.jsonl
Also produces a human-readable index CSV.
"""
import os
import sys
import json
import csv
import re
from datetime import date

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_DIR      = os.path.join(BASE_DIR, "corpus", "anonymized")
OUT_DIR     = os.path.join(BASE_DIR, "corpus", "final")
JSONL_PATH  = os.path.join(OUT_DIR, "mldc_v1.jsonl")
INDEX_PATH  = os.path.join(OUT_DIR, "mldc_v1_index.csv")
LOG_PATH    = os.path.join(BASE_DIR, "logs", "structure_log.json")

os.makedirs(OUT_DIR, exist_ok=True)

SCHEMA_VERSION   = "1.0"
COLLECTION_DATE  = str(date.today())


def count_tokens(text: str) -> int:
    """Approximate token count by splitting on whitespace."""
    return len(text.split())


def is_code_mixed(text: str) -> bool:
    """Check if text contains significant Latin content (English mixed in)."""
    if not text:
        return False
    latin = sum(1 for c in text if c.isalpha() and ord(c) < 128)
    return (latin / len(text)) > 0.02  # >2% Latin chars = code-mixed


def build_full_text(sections: dict) -> str:
    """Concatenate all sections into a single clean full-text string."""
    order = [
        "header", "facts", "petitioner_arguments",
        "respondent_arguments", "cited_cases_text",
        "judges_summary", "unclassified_body", "case_result"
    ]
    parts = []
    for key in order:
        val = sections.get(key, "")
        if val and val.strip():
            parts.append(val.strip())
    return "\n\n".join(parts)


def build_corpus_entry(doc: dict, seq_num: int) -> dict:
    """Build a standardized corpus JSON entry from an anonymized doc."""
    meta     = doc.get("metadata", {})
    sections = doc.get("sections", {})
    labels   = doc.get("labels", {})
    quality  = doc.get("quality", {})
    parties  = doc.get("parties", {})

    full_text   = build_full_text(sections)
    token_count = count_tokens(full_text)
    code_mixed  = is_code_mixed(full_text)

    # Generate a clean doc_id
    year     = meta.get("year") or "0000"
    bench    = (meta.get("bench_location") or "MH").upper()[:3]
    case_t   = (meta.get("case_type") or "MISC").replace(" ", "")[:4].upper()
    doc_id   = f"MLDC-{bench}-{case_t}-{year}-{seq_num:04d}"

    entry = {
        "doc_id": doc_id,
        "schema_version": SCHEMA_VERSION,

        "source": {
            "original_filename":  doc.get("doc_id", "") + ".pdf",
            "collection_date":    COLLECTION_DATE,
            "pdf_type":           "native",
            "ocr_engine":         None,
            "page_count":         None,   # can be enriched from extract log
        },

        "metadata": {
            "court":              meta.get("court")          or "मुंबई उच्च न्यायालय",
            "bench_location":     meta.get("bench_location") or "Mumbai",
            "jurisdiction":       meta.get("jurisdiction"),
            "case_type":          meta.get("case_type"),
            "case_number":        meta.get("case_number"),
            "year":               meta.get("year"),
            "date_of_order":      meta.get("date_of_order"),
            "ipc_sections":       meta.get("ipc_sections", []),
            "state":              "Maharashtra",
            "language":           "Marathi",
            "code_mixed":         code_mixed,
            "code_mix_language":  "English" if code_mixed else None,
        },

        "parties": {
            "petitioner":           parties.get("petitioner"),
            "respondent":           parties.get("respondent"),
            "petitioner_advocate":  parties.get("petitioner_advocate"),
            "respondent_advocate":  parties.get("respondent_advocate"),
        },

        "content": {
            "full_text":    full_text,
            "token_count":  token_count,
            "sections": {
                "header":               sections.get("header", ""),
                "facts":                sections.get("facts", ""),
                "petitioner_arguments": sections.get("petitioner_arguments", ""),
                "respondent_arguments": sections.get("respondent_arguments", ""),
                "cited_cases_text":     sections.get("cited_cases_text", ""),
                "judges_summary":       sections.get("judges_summary", ""),
                "case_result":          sections.get("case_result", ""),
            },
            "cited_cases":   doc.get("cited_cases", []),
        },

        "labels": {
            "outcome":            labels.get("outcome"),
            "outcome_normalized": labels.get("outcome_normalized"),
            "bail_granted":       labels.get("bail_granted"),
            "bail_amount_inr":    labels.get("bail_amount_inr"),
            "remanded":           labels.get("remanded", False),
            "stay_granted":       labels.get("stay_granted", False),
        },

        "quality": {
            "anonymized":              quality.get("anonymized", True),
            "pii_replacements":        quality.get("pii_replacements", 0),
            "duplicate":               False,
            "segmentation_complete":   quality.get("segmentation_complete", False),
            "segmentation_confidence": quality.get("segmentation_confidence", "low"),
            "has_result_section":      quality.get("has_result_section", False),
            "token_count":             token_count,
            "manual_review_required":  quality.get("segmentation_confidence") == "low",
            "pipeline_warnings":       [],
        }
    }

    return entry


def process_all():
    files = sorted([f for f in os.listdir(IN_DIR) if f.endswith(".json")])
    log_entries = []

    print("=" * 65)
    print("  MLDC -- Stage 5: Building Final JSONL Corpus")
    print("=" * 65)

    corpus_entries = []
    csv_rows       = []

    for i, fname in enumerate(files, start=1):
        in_path = os.path.join(IN_DIR, fname)
        with open(in_path, "r", encoding="utf-8") as f:
            doc = json.load(f)

        entry = build_corpus_entry(doc, i)
        corpus_entries.append(entry)

        print(f"\n[>>] Structuring: {fname}")
        print(f"  Doc ID      : {entry['doc_id']}")
        print(f"  Case type   : {entry['metadata'].get('case_type') or 'unknown'}")
        print(f"  Tokens      : {entry['content']['token_count']}")
        print(f"  Outcome     : {entry['labels'].get('outcome_normalized') or 'unknown'}")
        print(f"  Confidence  : {entry['quality']['segmentation_confidence'].upper()}")

        csv_rows.append({
            "doc_id":        entry["doc_id"],
            "case_type":     entry["metadata"].get("case_type", ""),
            "year":          entry["metadata"].get("year", ""),
            "bench":         entry["metadata"].get("bench_location", ""),
            "outcome":       entry["labels"].get("outcome_normalized", ""),
            "token_count":   entry["content"]["token_count"],
            "has_result":    entry["quality"]["has_result_section"],
            "confidence":    entry["quality"]["segmentation_confidence"],
            "anon_count":    entry["quality"]["pii_replacements"],
        })

        log_entries.append({
            "doc_id":      entry["doc_id"],
            "original_id": doc.get("doc_id"),
            "status":      "ok",
        })

    # Write JSONL
    with open(JSONL_PATH, "w", encoding="utf-8") as f:
        for entry in corpus_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Write CSV index
    if csv_rows:
        with open(INDEX_PATH, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=csv_rows[0].keys())
            writer.writeheader()
            writer.writerows(csv_rows)

    print(f"\n{'=' * 65}")
    print(f"  Total documents in corpus : {len(corpus_entries)}")
    print(f"  Total tokens              : {sum(r['token_count'] for r in csv_rows)}")
    avg = sum(r['token_count'] for r in csv_rows) // max(len(csv_rows), 1)
    print(f"  Avg tokens per document   : {avg}")
    print("=" * 65)
    print(f"[OK] Corpus saved : {JSONL_PATH}")
    print(f"[OK] Index saved  : {INDEX_PATH}")

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log_entries, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    process_all()
