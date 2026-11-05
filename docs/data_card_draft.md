# MLDC — Marathi Legal Document Corpus: data card (DRAFT)

Status: draft built from pipeline logs on 2026-10-10. Fields marked **[TO FILL]** need the human reviews
(`tools/make_review_sheet.py`, `make_outcome_sheet.py`, `make_extraction_sheet.py`, and the matching `score_*.py`).
Nothing marked **[TO FILL]** may be filled with an estimate that was not measured.

## 1. What it is
6,478 Marathi-language court judgments (translated), anonymized automatically, with sections, metadata and an outcome label.

| | |
|---|---|
| Documents / tokens | 6,478 / 18.8 M (median 2,179 tokens per document; 10th–90th percentile 710–5,395) |
| Source families | Bombay High Court judgments 3,137 (benches: Mumbai, Aurangabad, Nagpur, Kolhapur, Goa); Supreme Court reported-judgment translations 2,450; other 891 |
| Decision years | 1906–2025 (no year found for 272 documents). Heavily weighted to 1995–1996 (reported SC judgments) and 2021–2025 (HC) |
| Most common case types | Civil Appeal 1,941; Writ Petition 1,841; Criminal Appeal 665; Interim Application 192; SLP 117; first appeal 105; not identified 807 (12 %) |
| Other metadata coverage | order date 68 %; IPC sections 8 %; cited cases 28 % |
| Format | JSONL, schema 1.2: `metadata`, `parties` (placeholders only), `content` (full text, sections, cited cases), `labels`, `quality` |

Note for the paper: the corpus is **not** only Bombay High Court — about 38 % are Supreme Court translations. Describe it as such.

## 2. How it was built
1. **Collection**: 6,744 PDFs of translated judgments **[TO FILL: source site, collection dates, licence/terms]**.
2. **Text extraction with glyph recovery** (stage 1b). About 97 % of the PDFs use subset fonts whose Unicode map is broken (wrong or
   control characters, visual order of pre-base vowel signs and reph), so plain text extraction is corrupt. We replace the font map with
   a private-use identity map, hash each glyph outline, look up the correct Unicode for each outline in `glyph_map.json`
   (~3,000 shapes, labels verified by eye), and reorder visual to logical order. 6,743 of 6,744 PDFs extracted; 0.02 % of glyphs unlabeled.
   **[TO FILL: word error rate, plain vs recovered, from `score_extraction.py`]**
3. **Cleaning** (stage 2): NFC, removal of page numbers/headers/disclaimers, paragraph rebuilding, Devanagari→Arabic digits,
   exact + near-duplicate removal (SimHash, Hamming ≤ 6). 6,622 of 6,744 kept; rejected: 69 defective source, 32 duplicates,
   13 too short, 7 not Marathi.
4. **Segmentation** (stage 3, rule-based): header, headnote (SC), facts, petitioner and respondent arguments, reasoning, operative part;
   case type/number/year, bench, outcome with the evidence sentence.
5. **Anonymization** (stage 4, rule-based, no learned NER): document-level entity registry (header parties, advocates, judges, titled
   names, address places, corpus-learned name list), role-aware placeholders (`<अर्जदार_1>`, `<वकील_N>`, `<न्यायाधीश_N>`, `<व्यक्ती_N>`,
   `<संस्था_N>`, `<ठिकाण_N>`, `<फोन>`, `<ईमेल>`, `<ओळखपत्र>` …), plus a leak scan; 144 documents that still failed the scan were excluded.
   Anonymization is one-way; the name map is kept privately and is not distributed.

## 3. Measured quality
| What | Result |
|---|---|
| Extraction word error rate | plain **[TO FILL]** vs recovered **[TO FILL]** (n pages **[TO FILL]**) |
| Anonymizer recall / precision (excerpts) | **[TO FILL]** / **[TO FILL]** (n documents **[TO FILL]**, reviewers **[TO FILL]**) |
| Outcome label accuracy (population-weighted), per-class precision | **[TO FILL]** (n **[TO FILL]**) |
| Segmentation | automatic: 3,503 high / 2,917 medium / 58 low confidence; case type missing 12 %, case number 14 %, result section 6 %, outcome `unknown` 11 % (no human check) |

Pipeline label distribution: allowed 2,530; dismissed 2,245; unknown 724; disposed 617; partially allowed 265; remanded 97.

## 4. Known limitations (state these in the paper)
- Anonymization is automatic; report the measured recall above and do not claim "fully anonymized". Documents without a parsed header
  party (27 %) rely on titles, addresses and the learned name list.
- Outcome labels are rule-derived, not annotated; use `labels.outcome_evidence` to audit.
- Text is a **translation** into Marathi of the original judgments; terminology and errors of the translation carry over.
- ~45 documents have no word spaces in the source; ~23 source-defective PDFs and 1 unreadable PDF are excluded.
- Case type is wrong or too generic for some documents (e.g. an interim application labelled instead of the main proceeding).
- Year distribution is skewed by the sources; do not treat it as a sample of court output.

## 5. Ethics and release **[TO FILL by authors with supervisor]**
- Content is public court judgments about real people; re-identification risk remains after automatic anonymization.
- Judges and advocates are anonymized by default (`--keep-judges` changes this). Decide and document the choice.
- Release route: full text vs code + glyph map + data-use agreement. Licence/terms of the source site must be checked first.
- The anonymization map and learned name list are private and must never be distributed.

## 6. Intended use
Research on Marathi legal NLP: outcome prediction, case-type classification, section segmentation, retrieval, summarization.
Not for legal advice or for decisions about individuals.
