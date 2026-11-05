"""glyphfix: visual -> logical reordering and glyph-map integrity."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import glyphfix as g  # noqa: E402

I, R = g.PRE_I, g.REPH


def fix(tokens):
    return g.reorder(tokens)[0]


def test_pre_base_i_moves_after_cluster():
    # visual: ि न   -> logical: नि
    assert fix([I, "न"]) == "नि"
    # visual: ि + क् + ष  -> logical: क्षि
    assert fix([I, "क्", "ष"]) == "क्षि"
    # ligature glyph counts as one cluster
    assert fix(["स", I, "द्र", "त"]) == "सद्रित"


def test_reph_moves_before_cluster():
    # visual: व + reph + ी -> logical: र्वी   (पूर्वी)
    assert fix(["पू", "व", R + "ी"]) == "पूर्वी"
    # सर्वोच्च: स व «R»ो च्च
    assert fix(["स", "व", R + "ो", "च्च"]) == "सर्वोच्च"


def test_reph_with_pre_base_i():
    # निर्विवाद: ि न | ि व reph | व ा द   -> नि र्वि वाद
    assert fix([I, "न", I, "व", R, "व", "ा", "द"]) == "निर्विवाद"


def test_nirmala_dot_glyph():
    X = g.XMARK
    assert fix([I, "न", "द", "े", X, I, "श", "त"]) == "निर्देशित"        # acts as a reph
    assert fix(["क", "ें", X, I, "द्र", "त"]) == "केंद्रित"          # redundant after an anusvara


def test_pre_base_i_with_attached_anusvara():
    assert fix([I + "ं", "स"]) == "सिं"


def test_unknown_glyph_is_marked_not_dropped():
    assert g.BAD in fix(["क", None, "त"])


def test_plain_text_untouched():
    assert fix(list("आणि न्यायालय")) == "आणि न्यायालय"


def test_glyph_map_integrity():
    path = os.path.join(os.path.dirname(__file__), "..", "glyph_map.json")
    labels = g.load_glyph_map(path)
    assert len(labels) > 2500
    for h, lab in labels.items():
        assert lab is None or isinstance(lab, str)
        if lab:
            assert "\x00" not in lab and not any(0xE000 <= ord(c) <= 0xF8FF for c in lab)
    raw = json.load(open(path, encoding="utf-8"))
    eye = sum(1 for v in raw.values() if v["src"] == "eye")
    assert eye > 1500                       # most labels were verified against the rendered glyphs
