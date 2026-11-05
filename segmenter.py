"""
segmenter — split a cleaned Marathi judgment into sections and extract its case details.

Replaces the logic of the old 03_segment.py. What changed and why
  * The cleaner now delivers one paragraph per line, so every rule works on paragraphs, not on raw line breaks.
  * Outcome: a sentence-level lexicon of real order phrasing (फेटाळण्यात येत आहे, याचिका अनुमत, निरपेक्ष, दोषमुक्त …)
    with negation handling, instead of five narrow patterns written for garbled text.
  * Operative part: located from the END of the judgment (signature lines stripped, disclaimer removed) and kept short;
    the old "last matching paragraph" rule often started it in the middle of the arguments.
  * Case details come from a lexicon of case types and from explicit "number / year" patterns in the header.
  * Three document families are recognised — High Court portal judgments, Supreme Court reported translations and
    everything else — because their headers differ completely.

Public API: segment_document(doc_id, text) -> dict   (same schema as before, plus a few new fields)
"""
import re

# ── helpers ──────────────────────────────────────────────────────────────────────────────────────
DEV = "ऀ-ॿ"
DANDA = "।"


def paragraphs_of(text):
    return [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]


def sentences_of(text):
    return [s.strip() for s in re.split(r"(?<=[.।;])\s+|\n+", text) if s.strip()]


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# OUTCOME
# ═════════════════════════════════════════════════════════════════════════════════════════════════
# Subjects of an order: the PROCEEDING that is being decided (never "the argument", "the option" …)
SUBJ = (r"(?:रिट\s+)?(?:याचिका(?:ंना|ना|ंचा|ंवर)?|याचिके(?:ला|स|चा)?|याचीका|पिटीशन|अपील(?:ास|ाला|ाचा|े|ांना)?|अपिल|अर्ज(?:ाला|ास|ाचा|ांना)?|दावा|दाव्या(?:ला|स)?|"
        r"पुनरीक्षण(?:\s+अर्ज(?:ाला|ास)?)?|पुनरिक्षण(?:\s+अर्ज(?:ाला|ास)?)?|पुनर्विलोकन|पुनरावलोकन|जामीन(?:\s+अर्ज)?|कंपनी\s+याचिका|लवाद\s+याचिका|अवमान\s+याचिका|"
        r"जनहित\s+याचिका)")
GAP = r"[^.\u0964;]{0,60}?"                                        # a few words between subject and verb, never across a sentence
DISMISS_V = r"(?:फेटाळ|खारि[जज]|खारीज|नामंजूर|नाकार)"
ALLOW_V = r"(?:मंजूर|अनुमत(?!ी)|(?<!अ)मान्य(?!ता|ते|ताप)|यशस्वी|निरपेक्ष)"
GRANT_N = r"(?:अनुमती|परवानगी|मान्यता)"                           # "याचिकेला अनुमती देण्यात येत आहे"
# the verb ending of an ORDER (present / passive-operative or a bare past verdict) — not of a narrative
END_OP = (r"(?:\S*ण्यात\s+(?:येत|येते|येतो|आले|आला|आली|आल्या|आहे|आहेत|येतात)|केल्या\s+जात\S*|फेटाळल्या|मंजूर\s+केल्या|केले\s+जात\S*|केली\s+जात\S*|केला\s+जात\S*|जाते|जातो|जातात|येते|येतो|येतात|"
          r"देतो|करतो|ठरवतो|केले(?![\u0900-\u097f])|केली(?![\u0900-\u097f])|केला(?![\u0900-\u097f])|आहे(?![\u0900-\u097f]))")
ORD_TAIL = r"(?:\.|\u0964|$|\s*[;,])"

PATTERNS = {
    "partially_allowed": [
        re.compile(r"(?:अंशतः|अंशत:|काही\s+प्रमाणात|अंशिक(?:रित्या)?|वरील\s+अटींसह\s+अंशतः)" + GAP + r"(?:" + ALLOW_V + r"|" + GRANT_N + r")"),
        re.compile(SUBJ + GAP + r"(?:" + ALLOW_V + r"|" + GRANT_N + r")" + GAP + r"(?:अंशतः|अंशत:|काही\s+प्रमाणात)"),
    ],
    "remanded": [
        re.compile(r"(?:परत\s+(?:पाठव|पाठवि)\S*|पुनर्विचारासाठी|पुन्हा\s+(?:सुनावणी|निर्णय)\s+(?:घ|कर)|नव्याने\s+(?:सुनावणी|निर्णय|विचार)\s+(?:घ|कर)|रिमांड)"),
    ],
    "dismissed": [
        re.compile(SUBJ + GAP + DISMISS_V + r"\S*" + GAP + END_OP),
        re.compile(SUBJ + GAP + DISMISS_V + r"(?:ली|ले|ला|ल्या)" + ORD_TAIL),
        re.compile(r"(?:ते|त्या|ती|सर्व|दोन्ही|वरील|उपरोक्त)\s+" + DISMISS_V + r"\S*" + GAP + END_OP),
        re.compile(r"(?:गुणवत्ताहीन|गुणवत्ताविहीन|गुणवत्तारहित)" + GAP + DISMISS_V),
        re.compile(SUBJ + GAP + ALLOW_V + r"\S*\s*(?:करता\s+येणार\s+नाही|करण्यास\s+पात्र\s+नाही|करता\s+येत\s+नाही|करण्यात\s+येत\s+नाही)"),
        re.compile(r"हस्तक्षेप\s+करण्(?:याचे|यास|याची)?\s*(?:कोणतेही\s+)?(?:कारण|आवश्यकता|न्याय्य\s+कारण)[^.\u0964]{0,40}नाही"),
        re.compile(r"(?:शिक्षा|दोषसिद्धी|न्यायनिर्णय|हुकूमनामा|निवाडा)\s+(?:याद्वारे\s+)?(?:कायम|योग्य)\s+(?:ठेव|कर|ठरव)\S*\s+" + END_OP.replace(r"|आहे(?![\u0900-\u097f])", "")),
    ],
    "allowed": [
        re.compile(SUBJ + GAP + ALLOW_V + r"\S*" + GAP + END_OP),
        re.compile(SUBJ + GAP + ALLOW_V + r"(?:\s+केली|\s+केले|\s+केला)?" + ORD_TAIL),
        re.compile(SUBJ + GAP + GRANT_N + r"\s+(?:देण|देतो|आहे|दिल)\S*"),
        re.compile(r"(?:आदेश|निर्णय|न्यायनिर्णय|हुकूमनामा|निवाडा|शिक्षा|दोषसिद्धी|कारवाई|नोटीस)" + GAP + r"(?:रद्द(?:बातल)?|बाजूला\s+सार\S*)" + GAP + END_OP),
        re.compile(r"(?:निर्दोष|दोषमुक्त)\s+(?:मुक्त\s+)?(?:करण्यात|केले|केली|केला|ठरविण्यात|घोषित)"),
        re.compile(r"(?:न्यादेश|नियम|न्यायादेश)" + GAP + r"(?:निरपेक्ष|कायम)\s+(?:करण्यात|केला|केले|केली|ठेव|जात)"),
    ],
    "disposed": [
        re.compile(r"निकाली\s+(?:काढ|निघ)\S*"),
        re.compile(r"निपटार(?:ा|ले|ली)\s+(?:करण्यात|केला|केले|केली)"),
    ],
}
# earlier entries win when several are present in the SAME sentence
ORDER = ["partially_allowed", "remanded", "dismissed", "allowed", "disposed"]

# sentences that talk ABOUT a decision instead of making one
NARRATIVE_RE = re.compile(r"(?:गरज|आवश्यक|एकदा|मान्य\s+आहे|मान्य\s+असल|पाहिजे|यावे|यावी|यावा|व्हावे|व्हावी|आवाहन|कौतुक|आभार|मदत|च्या\s+(?:आदेशाद्वारे|निर्णयाद्वारे|निकालाद्वारे)|(?<![\u0900-\u097f])(?:जेव्हा|तेव्हा|जर)(?![\u0900-\u097f])|ज्यांनी|ज्याने|ज्यांच्या|(?![\u0900-\u097f])जो\s|(?![\u0900-\u097f])जी\s|(?![\u0900-\u097f])जे\s|होता(?![\u0900-\u097f])|होते(?![\u0900-\u097f])|होती(?![\u0900-\u097f])|होत्या(?![\u0900-\u097f])|नव्हता|नव्हते|नव्हती|ज्यात|ज्या\s+|असल्याचे|आढळ|नमूद|सादर\s+केले|युक्तिवाद|म्हण(?:ाले|णे|ून\s+सांगित)|"
                          r"असा\s+दावा|आग्रह|निवेदन|स्वीकारार्ह|अनुज्ञेय|ग्राह्य|शक्य\s+नाही|अवघड|निर्देश\s+द्याव|द्यावे|करावे|करावा|मागणी|विनंती|प्रार्थना)")
OTHER_FORUM_RE = re.compile(r"(?:मंडळाने|समितीने|अधिकाऱ्याने|आयुक्तांनी|प्रशासनाने|विभागाने|शासनाने|सरकारने|उच्च\s+न्यायालयाने|न्यायचौकशी\s+न्यायालयाने|न्यायाधिकरणाने|लवादाने|आयोगाने|प्राधिकरणाने|कनिष्ठ\s+न्यायालयाने|सर्वोच्च\s+न्यायालयाने|"
                            r"अपील\s+न्यायालयाने|दंडाधिकाऱ्यांनी|न्यायाधीशांनी)")
OUR_COURT_RE = re.compile(r"(?:हे\s+न्यायालय|आम्ही|मी(?![\u0900-\u097f])|माझ्या|आमच्या)")
UPHELD_NEG_RE = re.compile(r"(?:आदेश|निर्णय|न्यायनिर्णय|हुकूमनामा|दोषसिद्धी|शिक्षा|निवाडा)[^.\u0964]{0,50}(?:कायम\s+ठेव\S*|टिक\S*)[^.\u0964]{0,25}(?:शकत\s+नाही|शकणार\s+नाही|नाही)")


def is_order_sentence(sent):
    """A sentence that DECIDES something: not a narrative about an earlier decision, a prayer or a negation."""
    if NARRATIVE_RE.search(sent):
        return False
    if OTHER_FORUM_RE.search(sent) and not OUR_COURT_RE.search(sent):
        return False
    return True


NEG_VERB_RE = re.compile(r"(?:केला|केले|केली|करण्यात|जात|येत|आला|आले|आली)\s+नाही")


def classify_sentence(sent):
    if not is_order_sentence(sent):                       # narrative / prayer / other forum: never a verdict
        return None
    if UPHELD_NEG_RE.search(sent):
        return "allowed"
    first = {}
    if NEG_VERB_RE.search(sent) and any(rx.search(sent) for rx in PATTERNS["allowed"]) and not any(rx.search(sent) for rx in PATTERNS["dismissed"]):
        return "dismissed"
    for label in ORDER:
        for rx in PATTERNS[label]:
            m = rx.search(sent)
            if m and (label not in first or m.start() < first[label]):
                first[label] = m.start()
    if not first:
        return None
    if "partially_allowed" in first:
        return "partially_allowed"
    specific = {k: v for k, v in first.items() if k != "disposed"}
    pool = specific or first
    return min(pool, key=lambda k: pool[k])


def detect_outcome(result_text):
    """Outcome of an operative part. In an order the principal verdict comes first and consequential directions
    follow, so the FIRST verdict sentence decides — except that an explicit 'अंशतः मंजूर' anywhere wins.
    Returns dict(outcome_normalized, evidence, certainty, ...)."""
    out = {"outcome": "Unknown", "outcome_normalized": "unknown", "bail_granted": None, "remanded": False,
           "stay_granted": False, "evidence": "", "certainty": "none"}
    sents = sentences_of(result_text)[:80]
    if not sents:
        return out
    labelled = [(i, classify_sentence(s)) for i, s in enumerate(sents)]
    labelled = [(i, l) for i, l in labelled if l]
    if not labelled:
        return out
    present = {l for _, l in labelled}
    if "partially_allowed" in present:
        idx, label = next((i, l) for i, l in labelled if l == "partially_allowed")
    else:
        main = [(i, l) for i, l in labelled if l in ("allowed", "dismissed", "remanded")]
        idx, label = main[0] if main else labelled[0]               # "disposed" only when nothing more specific exists
    out["outcome_normalized"] = label
    out["outcome"] = label.replace("_", " ").capitalize()
    out["evidence"] = sents[idx][:240]
    out["certainty"] = "high" if len(present - {"disposed"}) <= 1 else "medium"
    out["remanded"] = "remanded" in present
    out["stay_granted"] = bool(re.search(r"(?:स्थगिती|स्थगन)\s+(?:मंजूर|देण्यात|दिली)", result_text))
    if re.search(r"जामीन", result_text):
        out["bail_granted"] = bool(re.search(r"जामीन[^.\u0964]{0,60}(?:मंजूर|दे(?:तो|ण्यात))", result_text)) and label != "dismissed"
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# OPERATIVE PART
# ═════════════════════════════════════════════════════════════════════════════════════════════════
_JUSTICE = r"(?:न्यायमूर्ती|न्यायमूर्ति|न्यायमुर्ती|न्यायमुर्ति|न्यायमूर्त्ती|न्यायाधीश)"
SIG_RE = re.compile(r"[\(\[]\s*(?:(?:" + _JUSTICE + r"|मा\.\s*" + _JUSTICE + r"|न्या\.?)\s*[.:]?\s+)?[^()\[\]\n]{2,60}?[,\s]*(?:जे\.?(?:\s*जे\.?)?|" + _JUSTICE + r")[\s.]*[\)\]]"
                    r"|[\(\[]\s*(?:" + _JUSTICE + r"|न्या\.?)\s*[.:]?\s+[^()\[\]\n]{3,60}[\)\]]"
                    r"|(?<=[.\u0964\s])[^\s.,()\[\]]{2,22}(?:\s[^\s.,()\[\]]{1,22}){0,3},\s*जे\.?(?:\s*जे\.?)?\s*$", re.M)
DISCLAIMER_TAIL_RE = re.compile(r"(?:\(?\s*अस्[वि]{1,2}कार?ण|\(?\s*अस्वीकरण|हा\s+निर्णय\s+पक्षकारास|इंग्रजी\s+भाषेतील\s+न्यायनिर्णय\s+हाच|x-x-x-x)[\s\S]*$")
ORDER_MARK_RE = re.compile(r"^(?:अंतिम\s+|खालील\s+|पुढील\s+|म्हणून\s+|त्यामुळे\s+|परिणामी\s+)?(?:आदेश|न्यायादेश|निष्कर्ष|निकाल)\s*[:\.\u0964\-–]*$")
ORDER_INTRO_RE = re.compile(r"(?:खालील|पुढील|अंतिम)\s+(?:आदेश|निर्देश)|आदेश\s+(?:देतो|देत\s+आहोत|पारित\s+करतो|देणे\s+योग्य)|निर्दश\s+देण्यात\s+येत")
SUBORDER_RE = re.compile(r"^\s*(?:\([अ-ह]{1,2}\)|\([ivx]+\)|[अ-ह]\)|\(\d+\)|\d+\)|[a-z]\))\s")


def strip_tail(text):
    """Remove the translation disclaimer and everything after the judges' signature block. Returns (main, tail)."""
    text = DISCLAIMER_TAIL_RE.sub("", text).rstrip()
    cut = None
    for m in SIG_RE.finditer(text):
        if m.start() >= 0.5 * len(text) or len(text) - m.start() < 1500:
            cut = m.start(); break
    if cut is not None and cut > 200:
        return text[:cut].rstrip(), text[cut:]
    return text, ""


def find_operative(main_paras, max_chars=7000):
    """Index of the first paragraph of the operative part (the order), or None."""
    n = len(main_paras)
    if n == 0:
        return None
    lo = max(0, int(n * 0.5) - 1)
    # 1. an explicit marker line / introduction in the second half — the LAST one wins
    start = None
    for i in range(lo, n):
        p = main_paras[i]
        if ORDER_MARK_RE.match(p) or (len(p) < 700 and ORDER_INTRO_RE.search(p)):
            start = i
    if start is not None:
        return start
    # 2. otherwise anchor on the last paragraph that holds a verdict sentence, and extend over the short order paragraphs before it
    anchor = None
    for i in range(n - 1, lo - 1, -1):
        if any(classify_sentence(se) for se in sentences_of(main_paras[i])):
            anchor = i; break
    if anchor is None:
        return None
    start = anchor
    total = len(main_paras[anchor])
    while start > 0 and anchor - start < 8:
        prev = main_paras[start - 1]
        if (SUBORDER_RE.match(prev) or ORDER_INTRO_RE.search(prev) or len(prev) < 350) and total + len(prev) <= max_chars:
            start -= 1; total += len(prev)
        else:
            break
    return start


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# DOCUMENT FAMILY, COURT, CASE DETAILS
# ═════════════════════════════════════════════════════════════════════════════════════════════════
MONTHS = {"जानेवारी": 1, "फेब्रुवारी": 2, "मार्च": 3, "एप्रिल": 4, "मे": 5, "जून": 6, "जुलै": 7, "ऑगस्ट": 8, "सप्टेंबर": 9,
          "ऑक्टोबर": 10, "नोव्हेंबर": 11, "डिसेंबर": 12}
_MONTH_ALT = "|".join(MONTHS)

# (regex, canonical type) — most specific first; the type whose phrase is found LAST in the title block is the proceeding being decided
CASE_TYPES = [
    (r"जनहित\s+याचिका", "Public Interest Litigation"),
    (r"फौजदारी\s+रिट\s+(?:याचिका|पिटीशन|पिटिशन)|क्रिमिनल\s+रिट", "Criminal Writ Petition"),
    (r"रिट\s+(?:याचिका|पिटीशन|पिटिशन|पिटीशन)|Writ\s+Petition", "Writ Petition"),
    (r"लवाद\s+याचिका|आर्बिट्रेशन\s+पिटीशन", "Arbitration Petition"),
    (r"अवमान\s+(?:याचिका|अर्ज)", "Contempt Petition"),
    (r"कंपनी\s+(?:याचिका|अपील|अर्ज)", "Company Petition"),
    (r"मृत्युपत्र\s+याचिका", "Testamentary Petition"),
    (r"विशेष\s+अनुमती\s+याचिका", "Special Leave Petition"),
    (r"हस्तांतरण\s+याचिका", "Transfer Petition"),
    (r"(?:अटकपूर्व|अग्रिम)\s+जामीन|जामीन\s+अर्ज", "Bail Application"),
    (r"फौजदारी\s+पुनरी?क्षण|फौजदारी\s+पुनरिक्षण", "Criminal Revision Application"),
    (r"दिवाणी\s+पुनरी?क्षण|दिवाणी\s+पुनरिक्षण", "Civil Revision Application"),
    (r"पुनर्विलोकन\s+(?:याचिका|अर्ज)|पुनरावलोकन\s+(?:याचिका|अर्ज)", "Review Petition"),
    (r"फौजदारी\s+अपील", "Criminal Appeal"),
    (r"आयकर\s+अपील|Income\s+Tax\s+Appeal", "Income Tax Appeal"),
    (r"लेटर्स\s+पेटंट\s+अपील", "Letters Patent Appeal"),
    (r"(?:पहिले|प्रथम)\s+अपील", "First Appeal"),
    (r"(?:दुसरे|द्वितीय)\s+अपील", "Second Appeal"),
    (r"दिवाणी\s+अपील", "Civil Appeal"),
    (r"किरकोळ\s+(?:याचिका|अर्ज)|मिसलेनियस", "Miscellaneous Petition"),
    (r"अंतरिम\s+अर्ज|अंतरीम\s+अर्ज", "Interim Application"),
    (r"फौजदारी\s+अर्ज", "Criminal Application"),
    (r"दिवाणी\s+अर्ज", "Civil Application"),
    (r"दिवाणी\s+दावा|सामान्य\s+दावा|दावा\s+क्र", "Civil Suit"),
    (r"औद्योगिक\s+(?:न्यायालय|विवाद)|कामगार\s+न्यायालय", "Labour Matter"),
    (r"(?:याचिका)\s+(?:क्रमांक|क्र\b)", "Petition"),
    (r"अपील\s+(?:क्रमांक|क्र\b)", "Appeal"),
]
CASE_TYPES = [(re.compile(p, re.I), name) for p, name in CASE_TYPES]
NUM_AFTER = (r"\s*(?:\([^)\n]{0,25}\)\s*)?(?:क्र(?:मांक|\.)?|क्रं\.?|नंबर|No\.?)?\s*[.:\-–—]?\s*(?:\([^)\n]{0,25}\)\s*)?"
             r"(\d{1,6}(?:\s*[-–]\s*\d{1,6})?)[/\s]*(?:ऑफ|चा|of)?[/\s]*(\d{4})?")
YEAR_BEFORE = r"(\d{4})\s*(?:चा|चे|ची|च्या|चं)\s*(?:\S+\s*){0,4}$"

HC_RE = re.compile(r"(?:मुंबई|नागपूर|औरंगाबाद|छत्रपती\s+संभाजीनगर|गोवा|पणजी|कोल्हापूर)?[^\n]{0,40}उच्च\s+न्यायालय")
SC_RE = re.compile(r"सर्वोच्च\s+न्यायालय|Supreme\s+Court")
CITATION_HEAD_RE = re.compile(r"^\s*[\[\(]\s*\d{4}\s*[\]\)]\s*\d*\s*(?:एस\.?\s?सी\.?\s?(?:आर|सी)|S\.?C\.?[RC])|^\s*\d{4}\s*[\(\[]|एस\.\s?सी\.\s?आर\.|एस\.\s?सी\.\s?सी\.|आय\.?\s?टी\.?\s?आर")


SC_CITE_RE = re.compile(r"\[\s*\d{4}\s*\]|\(\s*\d{4}\s*\)\s*\d+\s*(?:एस|S|SCC|SCR)|एस\.?\s?सी\.?\s?आर|S\.?\s?C\.?\s?R\b|आय\.?\s?टी\.?\s?आर|सर्वोच्च\s+न्यायालय\s+अहवाल|\bSCR\b|\bSCC\b")
HC_TITLE_RE = re.compile(r"(?:मुंबई|मा\.\s*उच्च)[^\n]{0,40}उच्च\s+न्यायालय|उच्च\s+न्यायालय[^\n]{0,30}(?:मुंबई|नागपूर|औरंगाबाद|गोवा)|खंडपीठ")


def detect_family(header, text):
    head = header[:400]
    if SC_RE.search(head[:250]) or SC_CITE_RE.search(head[:200]):
        return "SC_reported"
    if HC_TITLE_RE.search(head[:450]):
        return "HC"
    if re.search(r"टंकलिखित|भाषांतर|अनुवाद", head[:300]) and not HC_TITLE_RE.search(head):
        return "SC_reported"                               # a translated reported judgment without a Bombay title
    if re.search(r"उच्च\s+न्यायालय", head[:300]):
        return "HC"
    return "other"


JURIS_RE = re.compile(r"(?:अपील(?:ीय)?|अपिलीय|मूळ|न्याय)\s*(?:न्यायाधिकारक्षेत्र|अधिकारक्षेत्र|अधिकारिता|अधिकार\s+क्षेत्र|अधिकारीता)\s*[:\-–.]?\s*")


def parse_date(text):
    """Latest plausible date written as 12.03.2024 / 12/03/2024 / 12 मार्च 2024 / मार्च 12, 2024."""
    found = []
    for m in re.finditer(r"\b([0-3]?\d)[./\-]([01]?\d)[./\-]((?:19|20)\d{2})\b", text):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= d <= 31 and 1 <= mo <= 12:
            found.append((m.start(), "%04d-%02d-%02d" % (y, mo, d)))
    for m in re.finditer(r"\b([0-3]?\d)\s+(" + _MONTH_ALT + r")[,\s]+((?:19|20)\d{2})\b", text):
        found.append((m.start(), "%04d-%02d-%02d" % (int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))))
    for m in re.finditer(r"(" + _MONTH_ALT + r")\s+([0-3]?\d)\s*,\s*((?:19|20)\d{2})", text):
        found.append((m.start(), "%04d-%02d-%02d" % (int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))))
    return sorted(found)[-1][1] if found else None


def extract_case_details(header, text_start=None, first=False):
    """case_type / case_number / case_year from the title block of the header."""
    title = header[:900]
    cut = re.search(r"(?m)^(?:\s*(?:\d{1,2}[\.\)]\s*)?[^\n]{0,80}(?:\bवय\b|विरुद्ध|\bवि\.))", title)
    title = title[:cut.start()] if cut and cut.start() > 40 else title
    best = None
    for rx, name in CASE_TYPES:
        for m in rx.finditer(title):
            if best is None or m.start() >= best[0]:
                best = (m.start(), m.end(), name)
        if best and rx is not CASE_TYPES[0][0] and best[2] not in ("Petition", "Appeal"):
            pass
    # the most specific type found anywhere wins over the generic 'Petition' / 'Appeal'
    specific = [(m.start(), m.end(), name) for rx, name in CASE_TYPES[:-2] for m in rx.finditer(title)]
    if specific:
        best = (min if first else max)(specific, key=lambda t: t[0])
    number = year = None
    if best:
        m = re.compile(NUM_AFTER).match(title, best[1])
        if m:
            number = m.group(1).replace(" ", "")
            year = m.group(2)
        if not year:
            pre = re.search(YEAR_BEFORE, title[:best[1]])
            year = pre.group(1) if pre else None
        if not number:
            m2 = re.search(r"(?:क्र(?:मांक|\.)?|नंबर)\s*[.:]?\s*(\d{1,6})(?:\s*/\s*(\d{4}))?", title[best[1]:best[1] + 60])
            if m2:
                number, year = m2.group(1), year or m2.group(2)
    return {"case_type": best[2] if best else None, "case_number": number, "case_year": int(year) if year and 1900 <= int(year) <= 2099 else None}



# ═════════════════════════════════════════════════════════════════════════════════════════════════
# SECTIONS
# ═════════════════════════════════════════════════════════════════════════════════════════════════
def is_body_para(p):
    """First paragraph of the judgment text itself (as opposed to the party / title block of the header)."""
    if "\n" in p.strip():
        return False
    if re.match(r"^\(?\d{1,3}[\.\)]\s", p) and len(p) >= 140:
        return True
    return len(p) >= 260


def split_header(paras):
    for i, p in enumerate(paras):
        if is_body_para(p):
            return i
    return min(len(paras), max(1, len(paras) // 5))


def split_headnote(paras, family):
    """Supreme Court translations start with a catchword summary (headnote). Returns number of leading paragraphs.
    A headnote never contains the verdict and is never the whole judgment."""
    if family != "SC_reported":
        return 0
    n = 0
    for p in paras[:3]:
        dashes = p.count(" - ") + p.count(" – ") + p.count("–")
        has_verdict = any(classify_sentence(se) for se in sentences_of(p)[-6:])
        if dashes >= 3 and len(p) > 200 and not has_verdict and len(paras) - (n + 1) >= 2:
            n += 1
        else:
            break
    return n


def _marks(*alts):
    return [re.compile(a) for a in alts]


_PETI = r"(?<![" + DEV + r"])(?:याचिकाकर्त|अपीलकर्त|अर्जदार|वादी|अपीलार्थी)"
_RESP = r"(?<![" + DEV + r"])(?:प्रतिवादी|उत्तरवादी|उत्तरार्थी|प्रत्यर्थी|राज्य|सरकारी|शासनाच्या|एजीपी|ए\.?\s?पी\.?\s?पी)"
_ARG = r"(?:वकील|अधिवक्ता|युक्तिवाद|निवेदन|म्हणणे|सादर\s+केले|प्रतिपादन|बाजू|वतीने|तर्फे|तर्फ)"
PETITIONER_MARKERS = _marks(_PETI + r"[^\n.]{0,70}" + _ARG, r"(?:याचिकाकर्त|अपीलकर्त|अर्जदार)\S*\s+(?:वतीने|तर्फे)")
RESPONDENT_MARKERS = _marks(_RESP + r"[^\n.]{0,70}" + _ARG, r"(?:प्रतिवादी|उत्तरवादी|उत्तरार्थी|प्रत्यर्थी)\S*\s+(?:वतीने|तर्फे)")
REASONING_MARKERS = _marks(r"आमच्या\s+मते", r"माझ्या\s+मते", r"आम्ही\s+(?:पाहिले|पाहतो|विचार|मानतो|नोंद|तपासले|विश्लेषण)", r"(?:न्यायालया|खंडपीठा)च्या\s+मते",
                           r"सर्व\s+(?:बाबींचा|बाजूंचा|तथ्यांचा)\s+विचार", r"वरील\s+(?:विवेचन|चर्चा|कारणास्तव|विश्लेषण|परिस्थितीत)", r"उपरोक्त\s+(?:विवेचन|चर्चा|विश्लेषण|परिस्थितीत)",
                           r"विचारार्थ\s+(?:मुद्दे|प्रश्न)", r"कायद्याची\s+(?:स्थिती|तत्त्वे)", r"रेकॉर्ड\s+(?:पाहिले|तपासले)")


def _chunks(paras, limit=1500, target=800):
    """(text, source_paragraph_index). Very long paragraphs (typical of translated Supreme Court judgments, which are
    a few giant paragraphs) are cut at sentence boundaries so the markers can tell facts, arguments and reasoning apart."""
    out = []
    for i, p in enumerate(paras):
        if len(p) <= limit:
            out.append((p, i)); continue
        cur = ""
        for se in sentences_of(p):
            if cur and len(cur) + len(se) > target:
                out.append((cur, i)); cur = se
            else:
                cur = (cur + " " + se).strip()
        if cur:
            out.append((cur, i))
    return out


def split_body(paras):
    """HLDC-style forward fill: facts until an argument marker, then that side's arguments; from the first reasoning
    marker onwards the text is the court's reasoning."""
    chunks = _chunks(paras)
    labels, last = [], "FACTS"
    for p, _ in chunks:
        window = p[:350]
        if any(m.search(window) for m in PETITIONER_MARKERS):
            last = "PETITIONER"
        elif any(m.search(window) for m in RESPONDENT_MARKERS):
            last = "RESPONDENT"
        labels.append(last)
    first_reason = next((i for i, (p, _) in enumerate(chunks) if any(m.search(p[:500]) for m in REASONING_MARKERS)), None)
    if first_reason is not None:
        for i in range(first_reason, len(chunks)):
            labels[i] = "REASON"
    out = {"FACTS": [], "PETITIONER": [], "RESPONDENT": [], "REASON": []}
    prev_label = prev_src = None
    for (p, src), l in zip(chunks, labels):
        if out[l] and l == prev_label and src == prev_src:
            out[l][-1] += " " + p                               # same original paragraph, same section: undo the cut
        else:
            out[l].append(p)
        prev_label, prev_src = l, src
    sep = "\n\n"
    return (sep.join(out["FACTS"]), sep.join(out["PETITIONER"]), sep.join(out["RESPONDENT"]), sep.join(out["REASON"]))


# ── citations / sections of law (kept from the previous version) ───────────────────────────────────
CITATION_RE = [
    re.compile(r"\bAIR\s+\d{4}\s+\w+\s+\d+"), re.compile(r"\(\d{4}\)\s+\d+\s+SCC\s+\d+"), re.compile(r"\b\d{4}\s+SCC\s+\d+"),
    re.compile(r"\(\d{4}\)\s+\d+\s+SCR\s+\d+"), re.compile(r"\d{4}\s*\(\d+\)\s*[A-Z]+LJ\s+\d+"), re.compile(r"एस\.\s?सी\.\s?सी\.\s+\d+"),
    re.compile(r"\[\d{4}\]\s+\d+\s+(?:एस\.\s?सी\.\s?आर\.|SCR|I\.T\.R\.)\s*\d+"), re.compile(r"\(\d{4}\)\s+\d+\s+(?:एस\.\s?सी\.\s?सी\.|एस\.\s?सी\.\s?आर\.)\s*\d+"),
]


def extract_citations(text):
    found = []
    for rx in CITATION_RE:
        found.extend(rx.findall(text))
    return list(dict.fromkeys(found))


def extract_sections_of_law(text):
    secs = []
    for sp in (r"(?:भादंवि|भारतीय\s+दंड\s+संहिता|आयपीसी|IPC|भारतीय\s+न्याय\s+संहिता|बीएनएस)[^.\n]{0,40}?(?:कलम|Section|§)\s*([\d,\s/()]+)",
               r"(?:कलम|Section)\s+(\d{1,3}(?:\s*[,/]\s*\d{1,3})*)\s*(?:सह|आणि|अंतर्गत)?[^.\n]{0,25}(?:भादंवि|आयपीसी|IPC|भारतीय\s+दंड)"):
        for m in re.finditer(sp, text[:6000], re.I):
            secs.extend(re.findall(r"\d{1,3}", m.group(1)))
    return list(dict.fromkeys(n for n in secs if len(n) <= 3))[:15]


def jurisdiction_of(case_type, text):
    ct = case_type or ""
    if any(k in ct for k in ("Criminal", "Bail")):
        return "Criminal"
    if "Tax" in ct:
        return "Tax"
    if "Labour" in ct or re.search(r"औद्योगिक\s+विवाद|कामगार\s+न्यायालय|Industrial\s+Disputes", text[:3000]):
        return "Labour"
    if any(k in ct for k in ("Civil", "Appeal", "Suit", "Testamentary", "Company", "Arbitration")):
        return "Civil"
    if any(k in ct for k in ("Writ", "Public Interest")):
        return "Constitutional"
    return None


def bench_of(header):
    h = header[:500]
    if re.search(r"नागपूर\s+खंडपीठ|नागपूर\s+येथील", h):
        return "Nagpur"
    if re.search(r"औरंगाबाद|छत्रपती\s+संभाजीनगर", h):
        return "Aurangabad"
    if re.search(r"गोवा|पणजी", h):
        return "Goa"
    if re.search(r"कोल्हापूर", h):
        return "Kolhapur"
    return "Mumbai"


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# ONE DOCUMENT
# ═════════════════════════════════════════════════════════════════════════════════════════════════
def segment_document(doc_id, text):
    main, tail = strip_tail(text)
    paras = paragraphs_of(main)
    h_end = split_header(paras)
    header_paras, body_paras = paras[:h_end], paras[h_end:]
    header = "\n\n".join(header_paras)
    family = detect_family(header or text[:400], text)
    n_head = split_headnote(body_paras, family)
    headnote = "\n\n".join(body_paras[:n_head])
    body_paras = body_paras[n_head:]
    st = find_operative(body_paras)
    result_paras = body_paras[st:] if st is not None else []
    judgment_paras = body_paras[:st] if st is not None else body_paras
    facts, pet, resp, reasoning = split_body(judgment_paras)
    case_result = "\n\n".join(result_paras)
    outcome = detect_outcome(case_result)

    det = extract_case_details(header or text[:900])
    if not det["case_type"] or not det["case_number"]:     # SC / older styles: the title line sits after the headnote
        det2 = {"case_type": None}
        m = JURIS_RE.search(main[:20000])
        if m:                                              # "दिवाणी अपीलीय अधिकारिता: दिवाणी अपील क्र. 3809/1984"
            det2 = extract_case_details(main[m.end():m.end() + 260], first=True)
        if not det2["case_type"]:
            det2 = extract_case_details(main[:12000], first=True)
        if det2["case_type"] and (not det["case_type"] or det2["case_number"]):
            det = {**det2, "case_type": det["case_type"] or det2["case_type"]} if det["case_type"] else det2
    date_of_order = parse_date(header[:1200]) or parse_date(main[-600:])
    court = "सर्वोच्च न्यायालय" if family == "SC_reported" else "मुंबई उच्च न्यायालय"
    cit = re.search(r"[\[\(]\s*((?:19|20)\d{2})\s*[\]\)]", header[:200])
    decision_year = int(date_of_order[:4]) if date_of_order else (int(cit.group(1)) if cit else det["case_year"])
    citation = None
    if family == "SC_reported":
        cm = re.search(r"[\[\(]\s*\d{4}\s*[\]\)]\s*\d*\s*\S+\s*\S*\s*\d+", header[:160])
        citation = cm.group(0) if cm else None
    meta = {
        "court": court, "bench_location": bench_of(header) if family != "SC_reported" else "Delhi",
        "case_type": det["case_type"], "case_number": det["case_number"], "case_year": det["case_year"],
        "year": decision_year, "date_of_order": date_of_order, "jurisdiction": jurisdiction_of(det["case_type"], main),
        "ipc_sections": extract_sections_of_law(main),
        "document_type": {"HC": "HC Judgment", "SC_reported": "SC Judgment Translation"}.get(family, "Other Judgment"),
        "family": family, "citation": citation,
    }
    filled = sum(1 for s_ in (facts, pet, resp, reasoning) if s_.strip())
    has_result = bool(case_result.strip())
    core = sum(bool(x) for x in (meta["case_type"], meta["case_number"], meta["year"], outcome["outcome_normalized"] != "unknown"))
    confidence = "high" if (has_result and core >= 3 and filled >= 2) else "medium" if (has_result or core >= 2) else "low"
    return {
        "doc_id": doc_id, "metadata": meta,
        "sections": {"header": header, "headnote": headnote, "facts": facts, "petitioner_arguments": pet, "respondent_arguments": resp,
                     "judges_summary": reasoning, "case_result": case_result},
        "labels": {k: outcome[k] for k in ("outcome", "outcome_normalized", "bail_granted", "remanded", "stay_granted")},
        "outcome_evidence": {"sentence": outcome["evidence"], "certainty": outcome["certainty"]},
        "cited_cases": extract_citations(main),
        "quality": {"segmentation_complete": has_result and filled >= 2, "segmentation_confidence": confidence,
                    "has_result_section": has_result, "body_sections_filled": filled, "core_fields_found": core},
    }
