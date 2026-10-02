"""
Stage 1: Text Extraction (High-Volume Optimized)
Extracts clean text from thousands of native & scanned PDFs using PyMuPDF and Tesseract.
Uses multiprocessing and checkpointing for massive speedups.
Outputs one .txt file per document to corpus/raw_text/
"""
import os
import sys
import json
import hashlib
import re
import concurrent.futures

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

try:
    import pymupdf as fitz
except ImportError:
    import fitz

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR   = os.path.join(BASE_DIR, "pdfs")
OUT_DIR   = os.path.join(BASE_DIR, "corpus", "raw_text")
LOG_PATH  = os.path.join(BASE_DIR, "logs", "extract_log.json")
TESSDATA_DIR = os.path.join(BASE_DIR, "tessdata")

try:
    import pytesseract
    from PIL import Image, ImageOps, ImageFilter
    import io
    HAS_TESSERACT = True
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
except ImportError:
    HAS_TESSERACT = False

os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

_GARBLE_RE = re.compile(r'[a-zA-Z0-9#€&%_`@$^*<>{}\[\]|~\x00-\x08\x0b\x0c\x0e-\x1f\x7f][\u0900-\u097F]|[\u0900-\u097F][a-zA-Z0-9#€&%_`@$^*<>{}\[\]|~\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

def detect_pdf_quality(text: str) -> str:
    """Return 'native' or 'scanned_ocr' based on garble ratio in Devanagari context."""
    if len(text) < 100:
        return 'native'
    deva_chars  = len(re.findall(r'[\u0900-\u097F]', text))
    garble_hits = len(_GARBLE_RE.findall(text))
    if deva_chars == 0:
        return 'native'
    garble_ratio = garble_hits / deva_chars
    return 'scanned_ocr' if garble_ratio > 0.20 else 'native'


def preprocess_image(img):
    """Basic enhancements: grayscale, autocontrast, sharpen, threshold for better OCR."""
    gray = ImageOps.grayscale(img)
    gray = ImageOps.autocontrast(gray)
    gray = gray.filter(ImageFilter.SHARPEN)
    # Simple threshold
    gray = gray.point(lambda x: 0 if x < 128 else 255, '1')
    return gray


def extract_pdf(pdf_path: str) -> dict:
    """Extract all text from a native PDF, page by page."""
    doc = fitz.open(pdf_path)
    pages_text = []
    total_chars = 0

    for i, page in enumerate(doc):
        text = page.get_text("text")
        pages_text.append({"page": i + 1, "text": text})
        total_chars += len(text.strip())

    full_text = "\n".join(p["text"] for p in pages_text)
    doc.close()
    pdf_quality = detect_pdf_quality(full_text)

    return {
        "page_count":  len(pages_text),
        "total_chars": total_chars,
        "full_text":   full_text,
        "pages":       pages_text,
        "pdf_quality": pdf_quality,
    }


def extract_pdf_ocr(pdf_path: str) -> dict:
    """Extract text from a scanned PDF using Tesseract OCR with notebook enhancements."""
    doc = fitz.open(pdf_path)
    pages_text = []
    total_chars = 0

    config = f'--tessdata-dir "{TESSDATA_DIR}" --oem 1 --psm 3'
    
    for i, page in enumerate(doc):
        # Render page as a high-res image (dpi=300 recommended for OCR)
        pix = page.get_pixmap(dpi=300)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        
        # Apply notebook enhancements
        img = preprocess_image(img)
        
        # Run OCR
        try:
            text = pytesseract.image_to_string(img, lang='mar', config=config)
        except Exception as e:
            if "tesseract is not installed" in str(e).lower() or isinstance(e, pytesseract.TesseractNotFoundError):
                raise RuntimeError("Tesseract CLI not installed or not in PATH")
            raise e
            
        pages_text.append({"page": i + 1, "text": text})
        total_chars += len(text.strip())

    full_text = "\n".join(p["text"] for p in pages_text)
    doc.close()

    return {
        "page_count":  len(pages_text),
        "total_chars": total_chars,
        "full_text":   full_text,
        "pages":       pages_text,
        "pdf_quality": "scanned_ocr_fixed",
    }


def compute_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def process_single_pdf(fname: str, pdf_dir: str, out_dir: str) -> dict:
    """Worker function for multiprocessing."""
    doc_id = os.path.splitext(fname)[0]
    out_path = os.path.join(out_dir, f"{doc_id}.txt")
    
    # Checkpoint: Skip if already extracted AND the text is not garbled
    if os.path.exists(out_path):
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                existing_text = f.read()
            if detect_pdf_quality(existing_text) == 'native':
                return {"file": fname, "doc_id": doc_id, "status": "skipped_exists", "out_path": out_path}
        except Exception:
            pass # If reading fails, just re-extract
        # If it falls through here, it means it's garbled and needs OCR re-extraction!

    path = os.path.join(pdf_dir, fname)
    
    try:
        result = extract_pdf(path)
        
        # If native extraction is garbled, use OCR if available
        if result.get("pdf_quality") == "scanned_ocr":
            if HAS_TESSERACT:
                result = extract_pdf_ocr(path)
            else:
                if os.path.exists(out_path):
                    os.remove(out_path)
                return {"file": fname, "doc_id": doc_id, "status": "skipped_garbled", "error": "Garbled font mapping detected. Tesseract not installed. Document skipped."}
                
    except Exception as e:
        return {"file": fname, "doc_id": doc_id, "status": "error", "error": str(e)}

    text_hash = compute_sha256(result["full_text"])
    
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result["full_text"])

    return {
        "file": fname,
        "doc_id": doc_id,
        "status": "ok",
        "page_count": result["page_count"],
        "total_chars": result["total_chars"],
        "pdf_quality": result.get('pdf_quality', 'native'),
        "sha256": text_hash,
        "out_path": out_path,
    }


def process_all(pdf_dir: str, out_dir: str):
    if not os.path.exists(pdf_dir):
        print(f"[!] Error: Directory {pdf_dir} does not exist. Please place PDFs there.")
        return

    all_pdfs = sorted([f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")
                   and f not in ("paper.pdf",)])

    print("=" * 65)
    print(f"  MLDC -- Stage 1: Text Extraction (Processing {len(all_pdfs)} PDFs in Batches)")
    print("=" * 65)

    log_entries = []   # Only current run entries (fresh each run)
    seen_hashes = set()

    # Read existing log ONLY to restore seen_hashes for duplicate detection
    # We do NOT append old entries into log_entries so summary counts stay accurate
    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH, "r", encoding="utf-8") as f:
                old_logs = json.load(f)
                for entry in old_logs:
                    if "sha256" in entry:
                        seen_hashes.add(entry["sha256"])
        except json.JSONDecodeError:
            pass

    BATCH_SIZE = 1500
    
    # Multiprocessing (Safe Mode to avoid maxing out CPU)
    # We use at most half of the available CPU cores to keep the computer responsive for other tasks.
    max_workers = max(1, os.cpu_count() // 2) if os.cpu_count() else 2
    print(f"[*] Starting extraction using {max_workers} worker processes (Leaving CPU overhead free)...")
    
    for i in range(0, len(all_pdfs), BATCH_SIZE):
        batch_pdfs = all_pdfs[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (len(all_pdfs) + BATCH_SIZE - 1) // BATCH_SIZE
        
        print(f"\n[*] --- Starting Batch {batch_num}/{total_batches} (PDFs {i + 1} to {min(i + BATCH_SIZE, len(all_pdfs))}) ---")
        
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_single_pdf, fname, pdf_dir, out_dir): fname for fname in batch_pdfs}
            
            for idx, future in enumerate(concurrent.futures.as_completed(futures), 1):
                fname = futures[future]
                try:
                    res = future.result()
                    
                    status = res["status"]
                    if status == "skipped_exists":
                        print(f"[Batch {batch_num}: {idx}/{len(batch_pdfs)}] [SKIP] {fname} (Already extracted)")
                    elif status == "skipped_garbled":
                        print(f"[Batch {batch_num}: {idx}/{len(batch_pdfs)}] [DROP] {fname} (Garbled font mapping - Skipped)")
                    elif status == "ok":
                        h = res["sha256"]
                        if h in seen_hashes:
                            res["status"] = "duplicate"
                            print(f"[Batch {batch_num}: {idx}/{len(batch_pdfs)}] [WARN] {fname} (DUPLICATE content)")
                        else:
                            seen_hashes.add(h)
                            print(f"[Batch {batch_num}: {idx}/{len(batch_pdfs)}] [OK] {fname} ({res['pdf_quality'].upper()}, {res['total_chars']} chars)")
                    elif status == "error":
                        print(f"[Batch {batch_num}: {idx}/{len(batch_pdfs)}] [ERROR] {fname}: {res['error']}")
                    
                    # Only append newly processed results to the memory log so we can save it
                    if status != "skipped_exists":
                        log_entries.append(res)
                        
                except Exception as exc:
                    print(f"[Batch {batch_num}: {idx}/{len(batch_pdfs)}] [FATAL] {fname} generated an exception: {exc}")

        # Save logs after EVERY batch to prevent data loss and free memory
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(log_entries, f, ensure_ascii=False, indent=2)
        print(f"[*] Batch {batch_num} completed and logs saved.")

    print(f"\n{'=' * 65}")
    ok_count = sum(1 for e in log_entries if e.get('status') == 'ok')
    dup_count = sum(1 for e in log_entries if e.get('status') == 'duplicate')
    err_count = sum(1 for e in log_entries if e.get('status') == 'error')
    drop_count = sum(1 for e in log_entries if e.get('status') == 'skipped_garbled')
    
    print(f"  Done. Processed {len(all_pdfs)} PDFs.")
    print(f"  {ok_count} newly extracted")
    print(f"  {dup_count} marked duplicate")
    print(f"  {drop_count} dropped (garbled fonts)")
    print(f"  {err_count} errors.")
    print("=" * 65)
    print(f"[OK] Final log saved: {LOG_PATH}")
    return log_entries


if __name__ == "__main__":
    process_all(PDF_DIR, OUT_DIR)
