"""Re-extract every PDF from scratch (e.g. after changing glyph_map.json):

    python rebuild_raw.py <pdf-dir> <base-dir>

Equivalent to:  python 01b_fix_glyphs.py --pdf-dir <pdf-dir> --out-dir <base>/corpus/raw_text --force
"""
import os
import sys
import subprocess

if len(sys.argv) != 3:
    sys.exit(__doc__)
pdf_dir, base = sys.argv[1], os.path.abspath(sys.argv[2])
here = os.path.dirname(os.path.abspath(__file__))
subprocess.run([sys.executable, os.path.join(here, "01b_fix_glyphs.py"), "--pdf-dir", pdf_dir,
                "--out-dir", os.path.join(base, "corpus", "raw_text"),
                "--log", os.path.join(base, "corpus", "glyph_fix_log.json"), "--force"], check=True)
