# MLDC — Stage 1b Results: Glyph-Recovery Text Extraction

Date: 2026-10-04 · Corpus: 6,744 Bombay High Court PDFs (Marathi, 1.9 GB)

## 1. Problem

Plain text extraction from the corpus produced corrupted Marathi. 97% of the PDFs embed subset fonts
(TiroDevaMarathi, NirmalaUI, Mangal) whose built-in letter table (`/ToUnicode`) is incomplete or wrong:

| Symptom | Example (wrong → correct) |
|---|---|
| Unmapped glyphs come out as control characters | `अ\x13ुवाद` → `अनुवाद` |
| Glyphs mapped to the wrong letters | `आलिर्ण` → `आणि`, `अलिधनि\x13यम` → `अधिनियम` |
| Glyph codes differ in every PDF | the same letter has a different code in each file |
| Text stored in visual order | pre-base `ि` and the `र्` hook out of place |

The previous cleaning step deleted the control characters, which permanently removed letters, and patched a few
words with a hand-written dictionary.

## 2. Method

1. Replace each affected font's letter table with an identity map, so every glyph reports its exact code.
2. Fingerprint each glyph by its outline, which is identical across PDFs using the same typeface.
3. Label each outline once with its correct Unicode (`glyph_map.json`, 2,030 shapes; 1,174 checked by eye
   against rendered images, the rest by cross-document agreement).
4. Substitute labels and reorder from visual to logical Unicode.
5. Write one text file per PDF and a per-document quality log.

Covers both simple (one-byte) and Type0 (two-byte) font variants.

## 3. Results — full corpus

| Metric | Value |
|---|---|
| PDFs processed | 6,744 |
| Extracted successfully | 6,743 (99.98%) |
| Pages / characters | 129,984 / 158.2 million |
| Glyphs processed | 112.6 million |
| Glyphs with no label | 49,770 (0.044%) |
| Repaired by glyph recovery / native text | 6,585 / 158 |
| **Top quality tier** (no invalid word starts, no leftover corruption) | **5,966 (88.5%)** |
| Flagged `needs_review` | 173 (2.6%) |
| Flagged `source_defective` (corrupt PDF) | 59 (0.9%) |

## 4. Before vs after — first 400 documents

| Metric | Before | After |
|---|---|---|
| Documents with corrupted characters | 287 (72%) | 16 (4%) |
| Control characters in text | 394,840 | 342 |
| Invalid word starts per 10k words | 269.4 | 1.4 |
| `आलिर्ण` (wrong for `आणि`) | 16,881 | 0 |
| `अलिधनि` (wrong for `अधिनियम`) | 476 | 0 |
| `यालचका` (wrong for `याचिका`) | 53 | 0 |
| `न्यायालय` — occurrences / documents containing it | 8,149 / 253 | 13,803 / 398 |
| `सर्वोच्च` | 368 / 57 | 1,862 / 234 |
| `याचिका` | 2,033 / 96 | 9,495 / 320 |
| `अधिनियम` | 448 / 68 | 2,790 / 260 |
| `अनुवाद` | 226 / 135 | 719 / 397 |

Notes: "Before" is plain PyMuPDF text through the old `02_clean.py`. Verified against rendered page images:
decoded text matches the printed page letter for letter. Two later fixes (Type0 fonts, in-memory extraction)
are included in the "After" figures for `यालचका`, invalid word starts and the document-level counts above.

## 5. Known remaining issues

| Issue | Scale | Status |
|---|---|---|
| Mangal / Mangal-Bold fonts: same bug, glyphs not yet labeled | ~40 documents | next |
| Frequent unlabeled glyph shapes | ~12 shapes, listed in log `unknown_hashes` | next |
| Vowel signs stored before the consonant (Lohit, Mangal, "Nirmala UI") | ~130 documents, flagged | planned |
| PDFs corrupt at the source (render as overprinted junk) | 59 documents, flagged `source_defective` | not recoverable |
| Unreadable PDF | 1 | none |

## 6. Deliverables (in `marathi-legal-document/`)

| File | Purpose |
|---|---|
| `glyphfix.py` | recovery logic |
| `01b_fix_glyphs.py` | stage script — resumable, `--only`, `--force`, quality log |
| `glyph_map.json` | outline → Unicode table |
| `tools/glyph_map_build/` | scripts and README used to build and extend the map |
| `.gitignore` | keeps PDFs, extracted text and logs out of GitHub |

Outputs: `Documents/internship/corpus/raw_text/*.txt` (pages separated by `\n\f\n`) and `glyph_fix_log.json`.

## 7. Next steps

1. Label Mangal and the frequent unknown glyphs.
2. Rewrite the cleaning stage on the repaired text.
3. Rebuild the anonymizer (document-level entity registry, role-aware placeholders, leak scanner, gold set).

Open decisions: anonymize judges and advocates? One-way anonymization or reversible with a key?
