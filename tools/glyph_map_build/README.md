# How `glyph_map.json` was built (provenance — not a maintained API)

`glyph_map.json` (repo root) maps **glyph outline hash → correct Unicode** for the fonts that have a broken
`/ToUnicode` table in the corpus PDFs (TiroDevaMarathi, NirmalaUI — simple TrueType and Type0 variants).
The production code that *uses* the map is `glyphfix.py` + `01b_fix_glyphs.py`. This folder is a snapshot of the
throw-away scripts used to *create* it, kept so the map can be audited and extended.

## Why outlines
Every PDF embeds a *subset* of the font and assigns glyph codes in its own order, so "code 19" is `न` in one PDF
and something else in the next. The outline of a glyph, however, is identical in every PDF using the same typeface,
so it is a stable key. The PDFs' own ToUnicode map is right for most glyphs and wrong/missing for others, so labels
were verified by eye rather than trusted.

## Steps that were run
1. `build_stats.py` / `build_stats2.py` — for every PDF: hash each glyph outline, read the PDF's own ToUnicode label,
   count usage. Output `stats.json` (TiroDeva docs) and `stats2.json` (NirmalaUI docs).
2. `make_sheets.py` / `make_sheets2.py` — render one example of each outline (most frequent first) onto contact
   sheets, annotated with the PDF's own label. `order*.json` / `reps*.json` give the index → hash / example PDF.
3. Every glyph with index below the "eye" cut-off (840 for TiroDeva, 360 for NirmalaUI — together >99.9 % of all
   glyph uses) was checked against the picture. Wrong or missing labels were written down in `exc.py` / `exc2.py`
   (index → correct string). Ambiguous shapes were resolved from real words with `ctx.py` / `ctx2.py`.
4. `build_map.py` + `build_map_all.py` — merge: eye-checked labels; for the rare tail, the PDF's own label only if
   ≥ 90 % of documents agree (`src: "vote"`); otherwise `null` (`src: "junk"`), which the stage reports as unknown.

## Special labels
| label | meaning | handled in |
|---|---|---|
| `«I»` | pre-base matra ि (drawn *before* the consonant) | `glyphfix.reorder` moves it after the next cluster |
| `«R»…` | reph (र्) glyph, optionally fused with a sign (`«R»ीं`) | `reorder` puts `र्` before the previous cluster |
| `«X»` | NirmalaUI dot glyph: a reph, unless it follows an anusvara | `reorder` |
| `null` | no trustworthy label | emitted as U+FFFD, counted in `unknown_share` |

## Extending the map
Run `01b_fix_glyphs.py`, then collect `unknown_hashes` from `glyph_fix_log.json`. Hashes that recur across many
documents are real glyphs missing from the map: render them (see `render.py`), label them, add them to
`glyph_map.json` (re-running the stage notices the changed map and reprocesses). Hashes found in only a few
documents usually come from PDFs that are corrupt at the source.

`glyphlib.py` is the early prototype of the library; the maintained version is `../../glyphfix.py`.
Index numbers in `exc*.py` refer to the `order*.json` snapshot next to them.
