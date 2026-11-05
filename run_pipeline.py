"""
Run the whole MLDC pipeline (or a slice of it) with one command.

    python run_pipeline.py --base D:\\mldc_work --pdf-dir D:\\pdfs                  # everything
    python run_pipeline.py --base D:\\mldc_sample --pdf-dir D:\\pdfs --limit 25     # small trial run
    python run_pipeline.py --base ... --pdf-dir ... --from-stage 2 --to-stage 3    # only stages 2 and 3

Stages
  1  01b_fix_glyphs.py   PDF -> repaired text            <base>/corpus/raw_text
  2  02_clean.py         cleaning / paragraphs / dedup   <base>/corpus/cleaned
  3  03_segment.py       header / facts / arguments ...  <base>/corpus/segmented
  4  04_anonymize.py     PII removal                     <base>/corpus/anonymized   (+ private files outside the repo)
  5  05_structure.py     final JSONL corpus              <base>/corpus/final

Always use a separate --base for trial runs so they never mix with the real corpus.
"""
import os
import sys
import time
import argparse
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="working folder for all outputs")
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--limit", type=int, default=0, help="only the first N pdfs (trial run)")
    ap.add_argument("--from-stage", type=int, default=1)
    ap.add_argument("--to-stage", type=int, default=5)
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--private-dir", help="where stage 4 keeps its private files (default: %%LOCALAPPDATA%%\\mldc_private)")
    ap.add_argument("--ner", action="store_true")
    ap.add_argument("--keep-judges", action="store_true")
    a = ap.parse_args()

    base = os.path.abspath(a.base)
    env = dict(os.environ, MLDC_BASE=base, PYTHONIOENCODING="utf-8")
    w = ["--workers", str(a.workers)] if a.workers else []
    glyph_log = os.path.join(base, "corpus", "glyph_fix_log.json")
    stages = {
        1: ["01b_fix_glyphs.py", "--pdf-dir", a.pdf_dir, "--out-dir", os.path.join(base, "corpus", "raw_text"), "--log", glyph_log] + w + (["--limit", str(a.limit)] if a.limit else []),
        2: ["02_clean.py", "--glyph-log", glyph_log] + w,
        3: ["03_segment.py"],
        4: ["04_anonymize.py"] + w + (["--private-dir", a.private_dir] if a.private_dir else []) + (["--ner"] if a.ner else []) + (["--keep-judges"] if a.keep_judges else []),
        5: ["05_structure.py"],
    }
    for n in range(a.from_stage, a.to_stage + 1):
        cmd = [sys.executable, os.path.join(HERE, stages[n][0])] + stages[n][1:]
        print(f"\n>>> stage {n}: {stages[n][0]}", flush=True)
        t = time.time()
        r = subprocess.run(cmd, env=env, cwd=HERE)
        print(f"<<< stage {n} finished in {time.time() - t:.0f}s (exit {r.returncode})", flush=True)
        if r.returncode:
            sys.exit(f"stage {n} failed — fix it, then resume with --from-stage {n}")
    print("\nDone. Final corpus:", os.path.join(base, "corpus", "final", "mldc_v1.jsonl"))


if __name__ == "__main__":
    main()
