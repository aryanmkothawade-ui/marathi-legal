"""anonymizer: regression tests for every leak / false positive found in the old 04_anonymize.py."""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import anonymizer as A  # noqa: E402

HEADER = """मुंबई उच्च न्यायालयातील
नागपूर खंडपीठात
2025 चा फौजदारी अर्ज (एपीएल) क्रमांक 1128

1. मिर्झा अस्लम बेग रशीद बेग,
वय: 29 वर्ष, व्यवसाय: मजूर,
रा. प्रभाग क्र.1, जामा मशिद जवळ,
तालुका मालेगाव, जिल्हा वाशिम.

2. शेख शफीक शेख बरकत,
वय: 45 वर्ष, व्यवसाय: मजूर,
..... अर्जदार
विरुद्ध

1. महाराष्ट्र राज्य,
मार्फत पोलिस स्टेशन ऑफिसर,
तेल्हारा पोलीस ठाणे,

2. राहुल पोपटराव तायडे (तक्रारदार)
वय: 42 वर्ष, व्यवसाय: पोलीस हवालदार,
.... गैर-अर्जदार
श्री. एस. व्ही. सिरपूरकर, अर्जदारांचे वकील.
श्रीमती स्नेहा धोटे, एपीपी गैर-अर्जदार क्रमांक 1 / राज्यांसाठी.
कोरम: उर्मिला जोशी-फाळके आणि
नंदेश एस. देशपांडे, जे. जे.
निकाल: (पर उर्मिला जोशी-फाळके, जे.)"""

REAL_NAMES = ["मिर्झा", "अस्लम", "रशीद", "शफीक", "बरकत", "पोपटराव", "तायडे", "सिरपूरकर", "धोटे", "फाळके", "देशपांडे", "नंदेश",
              "मालेगाव", "वाशिम", "तेल्हारा", "रमेश", "देशमुख"]


def make_doc(facts, **extra):
    d = {"doc_id": "t", "sections": {"header": HEADER, "facts": facts, "case_result": "आदेश\nअर्ज फेटाळला."},
         "metadata": {"case_number": "1128"}, "cited_cases": []}
    d.update(extra)
    return d


def run(facts, **cfg):
    out, rep = A.Anonymizer(A.Config(**cfg)).anonymize_document(make_doc(facts))
    text = "\n".join(out["sections"].values())
    return out, rep, text


def verhoeff_number(prefix):
    inv = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]
    c = 0
    for i, d in enumerate(reversed(prefix + "0")):
        c = A._V_D[c][A._V_P[i % 8][int(d)]]
    return prefix + str(inv[c])


# ── structured identifiers ──────────────────────────────────────────────────────────────────────
def test_phone_does_not_eat_longer_ids_or_neighbours():
    _, _, t = run("CNR क्रमांक MHAU019876543210 व 9876543210 आहे.")
    assert "MHAU019876543210" in t and "व <फोन>" in t
    assert not re.search(r"(?<![\dA-Z])9876543210(?!\d)", t)               # the phone is gone, the CNR still contains the digits


def test_year_sequence_is_not_an_aadhaar():
    _, _, t = run("मुदत 2023 2024 2025 पर्यंत वाढवली.")
    assert "2023 2024 2025" in t and "<ओळखपत्र>" not in t


def test_valid_aadhaar_is_masked():
    num = verhoeff_number("23456789012")
    assert A.verhoeff_ok(num)
    _, _, t = run("आधार क्रमांक %s %s %s आहे." % (num[:4], num[4:8], num[8:]))
    assert num not in t.replace(" ", "") and "<ओळखपत्र>" in t


def test_other_structured_identifiers():
    _, _, t = run("ईमेल ramesh@gmail.com, वाहन MH12AB1234, पिन 411001, खाते क्रमांक 123456789012345, दूरध्वनी 020-25671234, PAN ABCDE1234F, जन्मतारीख 12/03/1990.")
    for raw in ("ramesh@gmail.com", "MH12AB1234", "411001", "123456789012345", "020-25671234", "ABCDE1234F", "12/03/1990"):
        assert raw not in t, raw


# ── names ───────────────────────────────────────────────────────────────────────────────────────
def test_title_with_period_is_caught():
    _, _, t = run("श्री. रमेश पाटील यांनी अर्ज केला.")
    assert "रमेश" not in t and "पाटील" not in t and "यांनी अर्ज केला" in t       # the verb is not swallowed


def test_advocate_followed_by_verb():
    _, _, t = run("अॅड. सुनील देशमुख यांनी युक्तिवाद केला.")
    assert "देशमुख" not in t and "यांनी युक्तिवाद केला" in t


def test_header_party_is_swept_everywhere_including_metadata_and_citations():
    doc = make_doc("मिर्झा अस्लम बेग रशीद बेग यांनी अर्ज केला. नंतर अस्लमने साक्ष दिली. शफीकला अटक झाली.")
    doc["metadata"]["case_number"] = "शफीक वि. राज्य"
    doc["cited_cases"] = ["मिर्झा बेग वि. महाराष्ट्र"]
    out, rep = A.Anonymizer(A.Config()).anonymize_document(doc)
    blob = str(out["sections"]) + str(out["metadata"]) + str(out["cited_cases"])
    for n in REAL_NAMES:
        assert n not in blob, n
    assert out["quality"]["anonymized"] is True and not rep["leaks"]


def test_roles_are_kept_in_placeholders():
    out, _, t = run("मिर्झाने सांगितले. तायडे हजर.")
    assert "<अर्जदार_1>" in t and "<प्रतिवादी_1>" in t
    assert out["parties"]["petitioner"] == ["<अर्जदार_1>", "<अर्जदार_2>"] and out["parties"]["respondent"] == ["<प्रतिवादी_1>"]


def test_case_ending_is_kept_and_no_dangling_vowel_sign():
    _, _, t = run("श्री रमेश पाटील हजर. रमेश पाटलांनी सांगितले. रमेशने नकार दिला.")
    assert "<व्यक्ती_1> यांनी सांगितले" in t and "<व्यक्ती_1>ने नकार" in t
    assert not re.search(r">[ा-ौं]", t)


def test_initials_with_dots_are_matched():
    out, rep, t = run("श्री. एस. व्ही. सिरपूरकर यांनी युक्तिवाद केला.")
    assert "सिरपूरकर" not in out["sections"]["header"] and "सिरपूरकर" not in t


def test_public_bodies_and_courts_are_kept():
    _, _, t = run("मुंबई उच्च न्यायालय आणि महाराष्ट्र राज्य यांनी तायडे यांना बोलावले.")
    assert "मुंबई उच्च न्यायालय" in t and "महाराष्ट्र राज्य" in t


def test_judges_follow_the_policy_switch():
    out, _, t = run("न्यायमूर्ती उर्मिला जोशी-फाळके यांनी निर्णय दिला.")
    assert "फाळके" not in t and "<न्यायाधीश_1>" in t
    out2, _, t2 = run("न्यायमूर्ती उर्मिला जोशी-फाळके यांनी निर्णय दिला.", keep_judges=True)
    assert "फाळके" in out2["sections"]["facts"] and out2["parties"].get("judge") is None


def test_places_in_addresses_are_masked_but_police_station_prefix_cues_work():
    _, _, t = run("रा. मालेगाव, तालुका वाशिम. तेल्हारा पोलीस ठाणे येथे तक्रार.")
    assert "मालेगाव" not in t and "तेल्हारा" not in t and "पोलीस ठाणे" in t


def test_multi_word_alias_is_cut_even_with_unfamiliar_ending():
    out, rep, t = run("श्री रमेश पाटील हजर. रमेश पाटीलसाहेब आले.")
    assert "पाटील" not in t and "<व्यक्ती_1>साहेब" in t and out["quality"]["anonymized"] is True


def test_honorific_endings_are_masked():
    _, _, t = run("शफीकसाहेब आले आणि शफीकसाहेबांनी सही केली.")
    assert "शफीक" not in t


def test_leak_scan_catches_what_the_sweep_missed():
    class NoSweep(A.Anonymizer):          # simulate a sweeper failure: names are registered but not replaced
        def apply(self, text, sweeper, amap, counts):
            return text
    out, rep = NoSweep(A.Config()).anonymize_document(make_doc("शफीक आले."))
    assert out["quality"]["anonymized"] is False and rep["leaks"]
    assert out["quality"]["anonymization"]["leaks_found"] == len(rep["leaks"])


def test_leak_scan_does_not_confuse_names_with_longer_words():
    # भारती (a name) must not be reported as leaked just because 'भारतीय' (Indian) is in the text
    doc = make_doc("भारतीय संविधान आणि विभाग येथे.")
    doc["sections"]["header"] = HEADER.replace("शेख शफीक शेख बरकत", "सुनीता भारती")
    out, rep = A.Anonymizer(A.Config()).anonymize_document(doc)
    assert "भारतीय संविधान" in out["sections"]["facts"] and not rep["leaks"]


def test_report_marks_mode_and_version():
    out, _, _ = run("काही नाही.")
    q = out["quality"]["anonymization"]
    assert q["version"] == A.VERSION and q["ner"] is False


# ── corpus gazetteer ────────────────────────────────────────────────────────────────────────────
def test_gazetteer_finds_untitled_names():
    docs = []
    for i in range(24):
        if i % 4 == 0:                       # the name is used as a name in a quarter of the corpus
            h = HEADER.replace("मिर्झा अस्लम बेग रशीद बेग", "सुनील शिंदे")
            facts = "श्री सुनील शिंदे हजर. शब्द%d" % i
        else:
            h, facts = HEADER, "सर्वसाधारण मजकूर आहे. शब्द%d" % i
        docs.append({"doc_id": str(i), "sections": {"header": h, "facts": facts}})
    gz = A.build_gazetteer(docs, top_common=5, min_df_ratio=0.9)
    assert gz["name_ratio"].get("शिंदे", 0) > 0.5
    an = A.Anonymizer(A.Config(), gz)
    out, rep = an.anonymize_document({"doc_id": "x", "sections": {"header": "", "facts": "आरोपी सुनील शिंदे याने मारहाण केली."}, "metadata": {}, "cited_cases": []})
    assert "शिंदे" not in out["sections"]["facts"]
