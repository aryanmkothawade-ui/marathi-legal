# MLDC — Marathi Legal Documents Corpus pipeline

Turns court-judgment PDFs (Bombay High Court, Marathi) into a clean, anonymized, structured corpus.

```
PDF ──01b──► raw_text ──02──► cleaned ──03──► segmented ──04──► anonymized ──05──► final/mldc_v1.jsonl
     repair      clean+dedup      split into          remove personal      JSONL + index
     the text                     sections            information
```

| Stage | File | What it does |
|---|---|---|
| 1b | `01b_fix_glyphs.py` (+ `glyphfix.py`, `glyph_map.json`) | Repairs text from PDFs whose fonts have a broken letter table (see *Why stage 1b exists*) |
| 2 | `02_clean.py` (+ `textclean.py`) | Normalisation, page headers/footers, translation disclaimer, paragraph rebuild, duplicates |
| 3 | `03_segment.py` | Header / facts / arguments / judge's summary / case result, metadata, outcome |
| 4 | `04_anonymize.py` (+ `anonymizer.py`) | Entity registry → replaces names, places, IDs; leak scan |
| 5 | `05_structure.py` | Final JSONL + CSV index (only fully anonymized documents) |

## Run it

```bash
pip install -r requirements.txt
# whole thing, one command (use a separate --base for trial runs):
python run_pipeline.py --base D:\mldc_work --pdf-dir D:\pdfs
python run_pipeline.py --base D:\mldc_trial --pdf-dir D:\pdfs --limit 25       # 25 PDFs only
```

---

# How to test it yourself

You do not need to trust the numbers in the reports — each layer can be checked in a minute.

## 1. Automated tests (30 seconds)

```bash
python -m pytest tests -q
```
Expected: `57 passed`. These contain the exact cases that went wrong earlier (page numbers eating paragraphs,
`श्री.` with a dot, Aadhaar-looking years, glued CNR numbers, …). If you change code and a test turns red, you broke
something that used to work.

## 2. Extraction — compare one PDF against the printed page

```bash
python tools/spot_check.py "D:\pdfs\502012024170909.pdf" --page 2 --png page.png
```
Shows the **before** (plain extraction, control characters visible as `<0x13>`) and the **after** text, plus an image
of the page. Open `page.png` and read it against the AFTER text — they should match letter for letter. Try several
PDFs: pick random ones from your `pdfs` folder. A few PDFs are broken at the source (about 0.3 %); the tool prints the
document's quality numbers so you can see when that is the case.

## 3. Cleaning — look at the result

After a run, open any file in `<base>\corpus\cleaned\`. Check: no stray page numbers inside sentences, paragraphs
separated by a blank line, the party block on separate lines, no "अस्वीकरण …" disclaimer. The log
`<base>\logs\clean_log.json` lists, per document, what was removed and why a document was rejected
(`rejected_short`, `rejected_language`, `rejected_defective`, `duplicate`, `near_duplicate`).

## 4. Anonymization — try your own text, then audit real output

**Try text** (no corpus needed):
```bash
python tools/try_anonymizer.py                     # built-in demo
python tools/try_anonymizer.py --header h.txt --body b.txt
```
Paste a real-looking header and body. Look at *ENTITIES FOUND*. A name in the body that is **not** listed there was
missed — that is the thing to report.

**Audit real output** — the real test is a human reading anonymized documents:
1. Open ~20 random files in `<base>\corpus\anonymized\*.json` and read `sections.header` and `sections.facts`.
2. Look for any real name, village, phone number or ID that survived. Note the file and the word.
3. Look for over-masking: ordinary words replaced by `<…>` tags.
4. `quality.anonymized` must be `false` for any document where the built-in leak scan found something; those are not
   copied into the final corpus.

The public log `<base>\logs\anonymization_log.json` contains counts and leak *types* only. The real-name map and the
learned name list are kept **outside** the repo and OneDrive, in `%LOCALAPPDATA%\mldc_private\` — never share that
folder.

## 5. Policy switches you can flip and re-test

| Question | Switch |
|---|---|
| Keep judges' names? | `04_anonymize.py --keep-judges` (default: judges are anonymized) |
| Keep private companies' names? | `--no-orgs` |
| Keep villages / police stations? | `--no-locations` |
| Add the NER model (slow, off by default) | `--ner` (see `ner_adapter.py` for the measured speed) |

---

# Why stage 1b exists

About 97 % of the PDFs embed subset fonts (TiroDevaMarathi, NirmalaUI, Mangal, Lohit …) whose built-in letter table
is incomplete or wrong, so ordinary extraction produces `अ\x13ुवाद` instead of `अनुवाद`. The codes also differ in
every PDF and the text is in visual order. Stage 1b identifies each glyph by its outline (identical in every PDF using
the same typeface), looks up the correct letter in `glyph_map.json`, and reorders to proper Unicode.
Details: `glyphfix.py` docstring and `tools/glyph_map_build/README.md`. Results: `docs/stage1b_results.md`.

# Latest full run (6,744 PDFs)

| Stage | Result |
|---|---|
| 1b extraction | 6,743 extracted; 93.8 % in the top quality tier; 0.02 % unlabeled glyphs |
| 2 cleaning | 6,622 kept; rejected: 69 defective, 17 + 15 duplicates, 13 too short, 7 not Marathi |
| 3 segmentation | 6,622 segmented: 3,606 high / 2,957 medium / 59 low confidence; case type missing 12 %, case number 14 %, result section 6 %, outcome `unknown` 11 % |
| 4 anonymization | 6,478 fully anonymized, 144 withheld because the leak scan flagged them (2.2 %) |
| 5 final corpus | **6,478 documents, 18.8 M tokens** (`corpus/final/mldc_v1.jsonl`) |

Quality of the anonymizer is a measured trade-off, not a proof: party names were recognised from the header in about
69 % of documents (the rest are mostly institutional parties or unusual headers); in the others names are still caught
through titles, addresses and the corpus-learned name list. Only a human read-through (section 4 above) can tell you
the real miss rate.

# Known limits (honest list)

- ~0.3 % of PDFs are corrupt at the source (they render as overprinted junk) → flagged `source_defective`, excluded.
- Names that never appear with a title, in the party header, in an address, or in the learned name list can still be
  missed by the anonymizer; the optional NER model finds some of these but is far too slow for the full corpus on a CPU.
- Segmentation (stage 3) was redesigned (`segmenter.py`) and is still rule-based. Before: case type missing 44 %, case
  number 38 %, outcome `unknown` 46 %. Now: 12 %, 14 %, 11 %. The outcome label was checked only by reading samples
  (about 75 % of `allowed` and most `dismissed` were right); there is no human-labelled gold set, so treat
  `outcome_normalized` as a noisy label and use `labels.outcome_evidence` (the sentence it was based on) to verify.
  About 45 documents have no word spaces left in the source and are segmented poorly.
- Tests cover the logic, not the whole corpus: always spot-check real output (sections 2–4 above).

# Human review sheets (for measuring real quality)

Each sheet is a self-contained HTML page written to `review/` (git-ignored: it contains court text). The reviewer marks
errors in the browser and downloads a CSV, which the matching script turns into numbers.

| Measures | Build the sheet | Score the CSV |
|---|---|---|
| Anonymizer recall / precision | `python tools/make_review_sheet.py` | `python tools/score_review.py anonymizer_review_results.csv` |
| Outcome label accuracy | `python tools/make_outcome_sheet.py` | `python tools/score_outcome.py outcome_review_results.csv` |
| Extraction word error rate (plain vs recovered) | `python tools/make_extraction_sheet.py` | `python tools/score_extraction.py extraction_review_results.csv` |

A draft data card with the empty fields these reviews will fill is in `docs/data_card_draft.md`.
