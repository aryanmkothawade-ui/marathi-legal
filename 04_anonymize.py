"""
Stage 4: PII anonymization  (rewritten — see anonymizer.py for the method)

Reads segmented documents, builds ONE entity registry per document (party header, advocates, judges, titled
mentions, addresses, optional NER, and a name gazetteer learned from the whole corpus), replaces every mention in
every section / metadata field, masks structured identifiers, runs a leak scan, and writes:

  <out-dir>/<doc_id>.json     anonymized document  (quality.anonymized is True only if the leak scan was clean)
  <log>                       public-safe log: counts and leak *types*, never real values
  <private-dir>/...           PRIVATE — real-name map (reversal key) and the learned name gazetteer.
                              Default: %LOCALAPPDATA%\\mldc_private  (outside the repo and outside OneDrive).

Policy switches (defaults in brackets):  --keep-judges [off: judges are anonymized]   --no-orgs   --no-locations
                                         --ner [off]   --require-ner   --mask-case-numbers [off]
Re-running skips documents already produced with the same signature (version + options + gazetteer).
"""
import os
import sys
import json
import hashlib
import argparse
import concurrent.futures as cf
from collections import Counter

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import anonymizer as A

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.environ.get("MLDC_BASE", os.path.dirname(HERE))


def default_private_dir():
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(root, "mldc_private")


_anon = None


def _init(opts, gazetteer):
    global _anon
    ner = None
    if opts["ner"]:
        import ner_adapter
        ner = ner_adapter.make_ner(scope_chars=opts["ner_scope"], labels=("Person",))
    cfg = A.Config(keep_judges=opts["keep_judges"], mask_orgs=not opts["no_orgs"], mask_locations=not opts["no_locations"],
                   mask_case_numbers=opts["mask_case_numbers"], use_gazetteer=True, ner=ner)
    _anon = A.Anonymizer(cfg, gazetteer)


def _work(args):
    path, signature = args
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    out, rep = _anon.anonymize_document(doc)
    out["quality"]["anonymization"]["signature"] = signature
    return os.path.basename(path), out, rep


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in-dir", default=os.path.join(BASE_DIR, "corpus", "segmented"))
    ap.add_argument("--out-dir", default=os.path.join(BASE_DIR, "corpus", "anonymized"))
    ap.add_argument("--log", default=os.path.join(BASE_DIR, "logs", "anonymization_log.json"))
    ap.add_argument("--private-dir", default=default_private_dir())
    ap.add_argument("--keep-judges", action="store_true")
    ap.add_argument("--no-orgs", action="store_true")
    ap.add_argument("--no-locations", action="store_true")
    ap.add_argument("--mask-case-numbers", action="store_true")
    ap.add_argument("--ner", action="store_true", help="add the optional NER booster (slow on CPU)")
    ap.add_argument("--ner-scope", type=int, default=4000, help="characters per document given to NER (0 = all)")
    ap.add_argument("--require-ner", action="store_true", help="abort if NER cannot be loaded (fail closed)")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    for d in (a.out_dir, a.private_dir, os.path.dirname(a.log)):
        os.makedirs(d, exist_ok=True)
    opts = {"keep_judges": a.keep_judges, "no_orgs": a.no_orgs, "no_locations": a.no_locations,
            "mask_case_numbers": a.mask_case_numbers, "ner": a.ner, "ner_scope": a.ner_scope or None}

    if a.ner:                                                    # fail closed: never silently fall back to a weaker mode
        try:
            import ner_adapter
            ner_adapter._pipeline("l3cube-pune/marathi-ner")
        except Exception as e:
            if a.require_ner:
                sys.exit(f"[ABORT] NER requested but unavailable: {type(e).__name__}: {e}")
            print(f"[WARN] NER unavailable ({type(e).__name__}); continuing WITHOUT it", file=sys.stderr)
            opts["ner"] = False

    files = sorted(f for f in os.listdir(a.in_dir) if f.endswith(".json"))
    print("=" * 65 + "\n  MLDC -- Stage 4: PII Anonymization\n" + "=" * 65)
    print(f"  segmented documents: {len(files)}   workers: {a.workers}   NER: {'on' if opts['ner'] else 'off'}   judges: {'kept' if a.keep_judges else 'anonymized'}")

    docs = []
    for f in files:
        with open(os.path.join(a.in_dir, f), encoding="utf-8") as fh:
            docs.append(json.load(fh))
    gz = A.build_gazetteer(docs)
    gz_path = os.path.join(a.private_dir, "name_gazetteer.json")
    with open(gz_path, "w", encoding="utf-8") as fh:
        json.dump(gz, fh, ensure_ascii=False)
    print(f"  gazetteer: {len(gz['name_ratio'])} name tokens learned from {gz['n_docs']} documents (private)")
    del docs

    signature = hashlib.sha256((A.VERSION + json.dumps(opts, sort_keys=True) + hashlib.sha256(open(gz_path, 'rb').read()).hexdigest()).encode()).hexdigest()[:16]

    def up_to_date(fname):
        p = os.path.join(a.out_dir, fname)
        if a.force or not os.path.exists(p):
            return False
        try:
            with open(p, encoding="utf-8") as fh:
                return json.load(fh).get("quality", {}).get("anonymization", {}).get("signature") == signature
        except Exception:
            return False

    todo = [f for f in files if not up_to_date(f)]
    keep = set(files)
    for f in os.listdir(a.out_dir):                              # drop outputs whose source document no longer exists
        if f.endswith(".json") and f not in keep:
            os.remove(os.path.join(a.out_dir, f))
    print(f"  to process: {len(todo)}   already up to date: {len(files) - len(todo)}   signature: {signature}")

    map_path = os.path.join(a.private_dir, "anonymization_map.json")
    private = {}
    if os.path.exists(map_path) and not a.force:
        try:
            private = json.load(open(map_path, encoding="utf-8"))
        except Exception:
            private = {}
    public = {}
    if os.path.exists(a.log) and not a.force:
        try:
            public = {e["doc_id"]: e for e in json.load(open(a.log, encoding="utf-8"))}
        except Exception:
            public = {}

    done = 0
    with cf.ProcessPoolExecutor(max_workers=a.workers, initializer=_init, initargs=(opts, gz)) as ex:
        for fname, out, rep in ex.map(_work, [(os.path.join(a.in_dir, f), signature) for f in todo], chunksize=8):
            with open(os.path.join(a.out_dir, fname), "w", encoding="utf-8") as fh:
                json.dump(out, fh, ensure_ascii=False, indent=1)
            doc_id = out.get("doc_id", fname[:-5])
            private[doc_id] = {"entities": rep["entities"], "leaks": rep["leaks"]}
            public[doc_id] = {
                "doc_id": doc_id, "entities": rep["n_entities"], "header_parties": rep["header_parties_found"],
                "replacements": out["quality"]["pii_replacements"], "counts": rep["counts"],
                "leaks": len(rep["leaks"]), "leak_types": sorted({l[0] for l in rep["leaks"]}),
                "anonymized": out["quality"]["anonymized"],
            }
            done += 1
            if done % 500 == 0:
                print(f"  [{done}/{len(todo)}]", flush=True)

    with open(map_path, "w", encoding="utf-8") as fh:
        json.dump(private, fh, ensure_ascii=False)
    with open(a.log, "w", encoding="utf-8") as fh:
        json.dump(list(public.values()), fh, ensure_ascii=False, indent=1)

    rows = list(public.values())
    kinds = Counter()
    for r in rows:
        kinds.update(r["counts"])
    print("=" * 65)
    print(f"  documents: {len(rows)}   fully anonymized: {sum(r['anonymized'] for r in rows)}   with leaks: {sum(not r['anonymized'] for r in rows)}")
    print(f"  docs with no header party found: {sum(r['header_parties'] == 0 for r in rows)}")
    print("  replacements:", ", ".join(f"{k} {v}" for k, v in kinds.most_common(12)))
    print(f"[OK] anonymized -> {a.out_dir}\n[OK] public log -> {a.log}\n[!!] PRIVATE (do not share/commit): {a.private_dir}")


if __name__ == "__main__":
    main()
