"""
Optional NER booster for the anonymizer.

Measured on this project's CPU-only machine: l3cube-pune/marathi-ner runs at ~630 characters/second (6 threads), i.e.
about 70 hours for the whole corpus, and its raw entities contain sub-word fragments and cut-off names. So it is NOT
used as the main engine. It is wired in as an optional recall booster:

    anonymizer.Config(ner=ner_adapter.make_ner(scope_chars=4000))

Entities are expanded to whole words, fragments are discarded, and only Person entities (plus Location /
Organization when enabled) are returned. The registry then sweeps every mention of what NER found.

`ai4bharat/IndicNER` is a gated model (needs a Hugging Face login) and is therefore not the default.
"""
import re

DEV = "ऀ-ॿ"
_pipe = {}


def _pipeline(model_id):
    if model_id not in _pipe:
        import torch
        from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
        torch.set_num_threads(max(1, (torch.get_num_threads() or 2)))
        tok = AutoTokenizer.from_pretrained(model_id)
        model = AutoModelForTokenClassification.from_pretrained(model_id)
        _pipe[model_id] = pipeline("ner", model=model, tokenizer=tok, aggregation_strategy="simple", device=-1)
    return _pipe[model_id]


def _chunks(text, size=450):
    """Split at line ends / spaces so no word is cut; yields (offset, chunk)."""
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            cut = max(text.rfind("\n", start, end), text.rfind(" ", start + size // 2, end))
            end = cut if cut > start else end
        yield start, text[start:end]
        start = end


def _expand(text, s, e):
    while s > 0 and re.match(r"[" + DEV + r"]", text[s - 1]):
        s -= 1
    while e < len(text) and re.match(r"[" + DEV + r"]", text[e]):
        e += 1
    return s, e


def make_ner(model_id="l3cube-pune/marathi-ner", scope_chars=4000, labels=("Person",), min_len=3, batch_size=16):
    """Return a callable text -> [(start, end, label)] looking at the first `scope_chars` characters only
    (the party header and opening paragraphs, where names concentrate). scope_chars=None scans everything."""
    wanted = {l.lower() for l in labels}

    def ner(text):
        scope = text if not scope_chars else text[:scope_chars]
        pairs = list(_chunks(scope))
        if not pairs:
            return []
        results = _pipeline(model_id)([c for _, c in pairs], batch_size=batch_size)
        out, seen = [], set()
        for (off, chunk), ents in zip(pairs, results):
            for ent in ents:
                lab = ent["entity_group"]
                if lab.lower() not in wanted:
                    continue
                s, e = _expand(text, off + ent["start"], off + ent["end"])
                frag = text[s:e].strip()
                if len(frag) < min_len or (s, e) in seen or not re.match(r"[" + DEV + r"]", frag):
                    continue
                seen.add((s, e))
                out.append((s, e, "PER" if lab == "Person" else lab[:3].upper()))
        return out
    return ner
