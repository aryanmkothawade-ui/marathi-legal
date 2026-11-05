"""textclean: regressions for the bugs found in the old 02_clean.py."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import textclean as tc  # noqa: E402

P = tc.PAGE_SEP


def clean(*pages, **kw):
    return tc.clean_document(P.join(pages), **kw)


def test_paragraph_break_is_kept_after_words_ending_in_he():
    # old code merged "आहे\n\nदुसरा" because it joined after any word ending in हे/व/या
    out, _ = clean("अर्ज मंजूर आहे.\n\nदुसरा परिच्छेद सुरू होतो आणि चालू राहतो.")
    assert "\n\n" in out


def test_wrapped_lines_are_rejoined():
    long1 = "याचिकाकर्त्याने " + "शब्द " * 14 + "आणि त्यामुळे"
    out, _ = clean(long1 + "\nपुढील ओळ वाक्य पूर्ण करते.")
    assert "आणि त्यामुळे पुढील ओळ" in out


def test_word_ending_in_va_does_not_glue_lines():
    out, _ = clean("गाव\nपुणे\nजिल्हा")                # short header-like lines stay separate
    assert out.count("\n") >= 2


def test_page_numbers_removed_but_paragraph_numbers_kept():
    p1 = "1\nपहिला परिच्छेद येथे संपतो.\n2.\nदुसरा परिच्छेद."
    p2 = "2\nतिसरा परिच्छेद येथे आहे.\n3."
    out, st = clean(p1, p2)
    assert st["page_numbers"] >= 2
    assert "2. दुसरा परिच्छेद" in out


def test_form_feed_page_separator_survives_normalisation():
    _, st = clean("एक\nदोन", "तीन\nचार", "पाच")
    assert st["pages"] == 3


def test_repeated_header_removed():
    words = ["अपील", "याचिका", "निर्णय", "आदेश", "कलम"]
    pages = ["सुप्रीम कोर्ट रिपोर्ट्स [2020] 5\n%s विषयी वेगळे विवेचन येथे संपते." % w for w in words]
    out, st = clean(*pages)
    assert "सुप्रीम कोर्ट रिपोर्ट्स" not in out and st["repeated_headers"] == 5 and "विवेचन" in out


def test_translation_disclaimer_removed_as_block():
    text = "अस्वीकरण : हा निर्णय पक्षकारास त्याच्या मातृभाषेमध्ये समजण्यापुरताच मर्यादित आहे आणि तोच आदेशाच्या अंमलबजावणीकरिता वैध मानला जाईल.\nमुख्य मजकूर येथे आहे."
    out, st = clean(text)
    assert "अस्वीकरण" not in out and "मुख्य मजकूर" in out and st["boilerplate_removed"] == 1


def test_line_separator_becomes_newline_not_deleted():
    out, _ = clean("ओळ एक ओळ दोन")
    assert "ओळएक" not in out and "एकओळ" not in out


def test_devanagari_digits_converted_and_unknown_marks_counted():
    out, st = clean("कलम १२५ � आहे")
    assert "125" in out and st["unknown_glyph_marks"] == 1 and "�" not in out


def test_space_before_punctuation_fixed():
    out, _ = clean("आदेश दिला .")
    assert out.endswith("दिला.")


def test_near_duplicate_detection():
    a = " ".join("शब्द%d" % i for i in range(300))
    b = a + " अतिरिक्त"
    c = " ".join("वेगळा%d" % i for i in range(300))
    items = [("a", tc.simhash(a), 10), ("b", tc.simhash(b), 20), ("c", tc.simhash(c), 5)]
    dropped = tc.near_duplicates(items)
    assert dropped == {"a": "b"}


def test_devanagari_ratio():
    assert tc.devanagari_ratio("आणि") == 1.0
    assert tc.devanagari_ratio("abc") == 0.0
