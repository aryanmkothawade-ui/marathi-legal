"""segmenter: regressions for every wrong outcome / missed field found while auditing real documents."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import segmenter as G  # noqa: E402


# ── outcome: real order phrasing ────────────────────────────────────────────────────────────────
def test_clear_verdicts():
    cases = {
        "अपील फेटाळले जाते.": "dismissed",
        "याचिका फेटाळण्यात आली.": "dismissed",
        "रिट याचिका मंजूर करण्यात आली आहे.": "allowed",
        "त्यामुळे याचिका खारिज करण्यात येत आहे.": "dismissed",
        "अपीले मंजूर करण्यात येत आहेत.": "allowed",
        "रिट याचिकेला अनुमती देण्यात येत आहे.": "allowed",
        "या अपिलांना मान्यता दिली जाते आणि उच्च न्यायालयाचा न्यायनिर्णय रद्दबातल केला जात आहे.": "allowed",
        "वरील अटींमध्ये हा न्यादेश कायम केला जातो.": "allowed",
        "त्या अटींमध्ये नियम निरपेक्ष केला जातो.": "allowed",
        "ते फेटाळण्यात येत आहेत.": "dismissed",
        "रिट याचिका निकाली काढण्यात येत आहे.": "disposed",
        "अपीले फेटाळल्या जातात.": "dismissed",
    }
    for text, expected in cases.items():
        assert G.classify_sentence(text) == expected, text


def test_partial_allowance_beats_plain_allowance():
    assert G.classify_sentence("याचिकांना अंशतः परवानगी दिली जाते.") == "partially_allowed"
    assert G.classify_sentence("अपीलाला अंशतः परवानगी दिली जाते.") == "partially_allowed"


def test_negated_upheld_means_allowed():
    assert G.classify_sentence("आक्षेपित आदेश कायम ठेवला जाऊ शकत नाही.") == "allowed"


def test_first_clause_decides_in_a_mixed_sentence():
    # appeal allowed (order set aside); the respondent's writ in the lower forum is the one that is dismissed
    assert G.classify_sentence("त्यानुसार आम्ही आक्षेपित आदेश बाजूला सारतो आणि उत्तरार्थीची रिट याचिका फेटाळण्यात येत आहे.") == "allowed"


def test_narrative_about_an_earlier_decision_is_not_a_verdict():
    for text in ("हुकूमनामा धारकाने अपील केले, ज्यांनी आदेशाद्वारे अपील मंजूर केले.",
                 "मंडळाने ही याचिका फेटाळली.",
                 "अर्ज केला, जो फेटाळण्यात आला होता.",
                 "हे स्पष्टीकरण स्वीकारार्ह नव्हते.",
                 "लाड यांचा युक्तिवाद मान्य करणे अवघड आहे.",
                 "नियमितीकरणाचे असे निर्देश अनुज्ञेय नसेल.",
                 "51 सवलत दाव्यांना मान्यता देण्याचे निर्देश द्यावेत.",
                 "1991 रोजी वैद्यक परिषदेने तयार केलेल्या संहितेस मान्यता देण्यात आली होती."):
        assert G.classify_sentence(text) is None, text


def test_prayer_is_not_a_verdict():
    assert G.classify_sentence("याचिकाकर्त्याने आदेश रद्द करण्याची विनंती केली आहे.") is None


def test_outcome_uses_the_first_verdict_of_the_order():
    block = "1. अपील फेटाळले जाते.\n\n2. खर्चाबाबत आदेश नाही.\n\n3. प्रलंबित अर्ज निकाली काढण्यात येतात."
    out = G.detect_outcome(block)
    assert out["outcome_normalized"] == "dismissed" and "फेटाळले" in out["evidence"]


def test_unknown_when_nothing_decides():
    assert G.detect_outcome("पुढील सुनावणी 12 तारखेला होईल.")["outcome_normalized"] == "unknown"


# ── operative part ──────────────────────────────────────────────────────────────────────────────
def test_signature_and_later_notes_are_cut():
    text = ("1. तथ्ये येथे आहेत आणि ती पुरेशी लांब आहेत. " * 12 + "\n\n2. त्यामुळे अपील फेटाळले जाते.\n\n(न्यायमूर्ती अ. ब. क्षत्रिय)\n\n"
            "3. निकालानंतर स्थगितीची मागणी करण्यात आली. ती मंजूर करण्यात येते.")
    main, tail = G.strip_tail(text)
    assert "स्थगितीची" not in main and "फेटाळले" in main and tail


def test_bare_name_comma_je_signature_is_cut():
    text = ("तथ्ये. " * 100) + "\n\nत्यामुळे अपील मंजूर केले जाते.\n\nमिलिंद एन. जाधव, जे.\n\nनंतर निवेदन आले."
    main, _ = G.strip_tail(text)
    assert "निवेदन" not in main


def test_operative_part_starts_at_the_order_not_at_the_arguments():
    paras = ["अपीलकर्त्याच्या वकिलांनी युक्तिवाद केला आणि खूप मुद्दे मांडले. " * 8] * 6 + ["आदेश", "1. अपील मंजूर करण्यात येते."]
    assert G.find_operative(paras) == 6


# ── case details ────────────────────────────────────────────────────────────────────────────────
def test_case_type_number_year():
    cases = [
        ("2021 ची मृत्युपत्र याचिका क्रमांक 109\nमध्ये\n2024 ची किरकोळ याचिका (एल) क्रमांक 6300", ("Miscellaneous Petition", "6300", 2024)),
        ("रिट पिटीशन नंबर 15694 ऑफ 2023 मेसर्स सिद्धी", ("Writ Petition", "15694", 2023)),
        ("1993 चे दुसरे अपील क्रमांक 296\n1. अनुसया", ("Second Appeal", "296", 1993)),
        ("आयकर अपील क्रमांक 225 / 2002", ("Income Tax Appeal", "225", 2002)),
        ("(फौजदारी अपील क्र. 1286 - 1287 / 2015)", ("Criminal Appeal", "1286-1287", 2015)),
    ]
    for header, (ct, num, year) in cases:
        d = G.extract_case_details(header)
        assert (d["case_type"], d["case_number"], d["case_year"]) == (ct, num, year), header


def test_dates():
    assert G.parse_date("निकाल 12.03.2024") == "2024-03-12"
    assert G.parse_date("5 डिसेंबर 2023") == "2023-12-05"
    assert G.parse_date("फेब्रुवारी 9,1999") == "1999-02-09"


def test_family_detection():
    assert G.detect_family("[2013] 17 एस.सी.आर. 380\nमारवाडी पंचायत वि. पंजाब राज्य", "") == "SC_reported"
    assert G.detect_family("मुंबई उच्च न्यायालय\nनागपूर खंडपीठ\nरिट याचिका क्र 332", "") == "HC"


# ── whole documents ─────────────────────────────────────────────────────────────────────────────
def _hc_doc():
    header = "मुंबई उच्च न्यायालय\nदिवाणी अपीलीय अधिकारिता\nदिवाणी अपील क्रमांक 512 / 2024\n\n1. अ ब क,\nवय: 40 वर्ष,\n..... अपीलकर्ता\nविरुद्ध\n1. ड इ फ,\n..... प्रतिवादी"
    facts = "1. या प्रकरणातील तथ्ये अशी आहेत की अपीलकर्त्याने जमीन विकत घेतली होती आणि त्यावरून वाद निर्माण झाला. " * 4
    pet = "2. अपीलकर्त्याचे विद्वान वकील यांनी युक्तिवाद केला की हुकूमनामा चुकीचा आहे आणि तो रद्द व्हावा. " * 4
    resp = "3. प्रतिवादीचे विद्वान वकील यांनी युक्तिवाद केला की हुकूमनामा योग्य आहे आणि अपील फेटाळावे. " * 4
    reason = "4. आमच्या मते, सर्व बाबींचा विचार करता, निचल्या न्यायालयाचा निष्कर्ष चुकीचा आहे असे आम्हाला वाटते. " * 4
    return "\n\n".join([header, facts, pet, resp, reason, "आदेश", "1. अपील मंजूर करण्यात येते.", "(न्यायमूर्ती अ. ब. क्षत्रिय)"])


def test_segment_a_high_court_document():
    r = G.segment_document("t", _hc_doc())
    m, s = r["metadata"], r["sections"]
    assert (m["family"], m["case_type"], m["case_number"], m["case_year"]) == ("HC", "Civil Appeal", "512", 2024)
    assert r["labels"]["outcome_normalized"] == "allowed"
    assert "मंजूर" in s["case_result"] and "न्यायमूर्ती" not in s["case_result"]
    assert "अपीलकर्त्याचे विद्वान वकील" in s["petitioner_arguments"] and "प्रतिवादीचे विद्वान वकील" in s["respondent_arguments"]
    assert "आमच्या मते" in s["judges_summary"] and "तथ्ये अशी आहेत" in s["facts"]
    assert r["quality"]["segmentation_confidence"] == "high"


def test_a_whole_judgment_in_one_paragraph_is_not_mistaken_for_a_headnote():
    one = "प्रकरणातील तथ्ये - अपीलकर्ता - उत्तरवादी - तथ्ये – आदेश - " + "तपशील येथे दिला आहे. " * 40 + "त्यानुसार अपील अनुमत करण्यात येते."
    r = G.segment_document("t", "[1999] 3 एस.सी.आर. 100\nअ वि. ब\n\n" + one)
    assert r["sections"]["headnote"] == "" and r["labels"]["outcome_normalized"] == "allowed"


def test_obligation_and_past_admission_are_not_verdicts():
    for text in ("शिक्षेचा निर्णय रद्द करण्याची गरज आहे.", "हे मान्य आहे.", "एकदा मान्य केले."):
        assert G.classify_sentence(text) is None, text


def test_case_number_after_dash_and_double_slash():
    d = G.extract_case_details("रिट याचिका क्रमांक – 9989 / / 2021\n\n1. शरणजीत")
    assert (d["case_type"], d["case_number"], d["case_year"]) == ("Writ Petition", "9989", 2021)
