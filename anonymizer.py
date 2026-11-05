"""
anonymizer — document-level PII removal for Marathi court judgments.

Why this replaces the old per-section, NER-only approach
  * Names are collected once per *document* (party header, advocates, judges, titled mentions, optional NER and a
    corpus-learned name gazetteer) into an entity registry, then every mention — in every section and metadata field —
    is replaced by one single-pass sweep. A name caught in one place can no longer leak in another.
  * Marathi attaches case endings directly to names (रमेशने, पाटीलांनी, देशमुखांच्या): the sweep matches alias + any
    known ending, and keeps the ending after the placeholder.
  * Placeholders keep the role (`<अर्जदार_1>`, `<प्रतिवादी_1>`, `<वकील_2>` …) so "who did what" survives.
  * Structured identifiers use validated patterns (Verhoeff for Aadhaar, digit boundaries for phones, ...).
  * The result is checked by a leak scanner; the document is only marked fully anonymized if the scan is clean.

Public API: Config, Anonymizer.anonymize_document(doc) -> (doc, report), build_gazetteer(docs) -> dict
"""
import re
import copy
import json
import unicodedata
from functools import lru_cache
from collections import Counter, defaultdict

VERSION = "2.0"
DEV = "ऀ-ॿ"
DEV_CHAR = "[" + DEV + "]"

# ── vocabulary ───────────────────────────────────────────────────────────────────────────────────
TITLES = ("श्रीमती", "श्रीमान", "सर्वश्री", "श्री", "सौ", "कुमारी", "कु", "डॉक्टर", "डॉ", "मेसर्स", "ॲड", "अॅड", "अधिवक्ता",
          "न्यायमूर्ती", "न्यायमूर्ति", "न्या", "जस्टीस", "मिस्टर", "मिसेस", "मिस", "कै", "स्व")
JUDGE_TITLES = {"न्यायमूर्ती", "न्यायमूर्ति", "न्या", "जस्टीस"}
ADVOCATE_TITLES = {"ॲड", "अॅड", "अधिवक्ता"}
ORG_TITLES = {"मेसर्स"}

# words that end a name or can never be part of one (case endings, particles, role nouns, verbs)
INFLECTIONS = sorted([
    "ांच्याकडून", "ांच्याकडे", "ांच्यासाठी", "ांच्यावर", "ांच्याविरुद्ध", "ांच्यासोबत", "ांच्यासह", "ांच्या", "ाच्या", "ांनाही", "ांनी", "ाने", "ाला",
    "ांना", "ाचा", "ाची", "ाचे", "ाचं", "ांचा", "ांची", "ांचे", "ाकडे", "ाकडून", "ासाठी", "ाशी", "ात", "ास", "ांस", "ानी", "ाही", "ाचीही", "ाचेही",
    "ने", "ला", "ना", "चा", "ची", "चे", "च्या", "त", "स", "ही", "च", "कडे", "कडून", "साठी", "शी", "वर", "सह", "सोबत", "मार्फत", "तर्फे", "चं", "नेही", "लाही",
], key=len, reverse=True)
STOP_WORDS = set("""
यांनी यांचे यांच्या यांना यांचा यांची याने यांस यास यासह यांसह यांच्यावर यांच्याकडे यांच्याविरुद्ध यांच्यासमोर यांच्याकडून यांच्यासाठी
आणि व तसेच तर की म्हणाले म्हणतात हजर उपस्थित विरुद्ध मार्फत तर्फे कडून कडे साठी सह सोबत हे हा ही ते ती तो या त्या त्याने तिने असे आहे आहेत होता होते होती
अर्जदार याचिकाकर्ता याचिकाकर्त्या अपीलकर्ता अपीलकर्त्या प्रतिवादी उत्तरवादी वादी आरोपी फिर्यादी तक्रारदार साक्षीदार वकील न्यायाधीश पोलीस पोलिस प्रत्यर्थी अर्जदारांचे
गैर क्रमांक क्र वय वर्ष व्यवसाय रा राहणार तालुका जिल्हा येथे येथील मधील मध्ये वरील खालील दिनांक रोजी जे जेजे एपीपी
राज्य सरकार न्यायालय खंडपीठ कंपनी लिमिटेड बँक संघ मंडळ महामंडळ आयोग प्राधिकरण समिती
""".split())
PUBLIC_BODY_WORDS = ("राज्य", "सरकार", "शासन", "भारत", "भारतीय", "महानगरपालिका", "नगरपालिका", "नगर परिषद", "ग्रामपंचायत", "पंचायत", "जिल्हा परिषद",
                     "न्यायालय", "पोलीस", "पोलिस", "आयोग", "प्राधिकरण", "मंडळ", "महामंडळ", "विभाग", "कार्यालय", "मंत्रालय", "विद्यापीठ", "रिझर्व्ह बँक",
                     "युनियन ऑफ इंडिया", "केंद्र", "महाराष्ट्र", "आयुक्त", "कलेक्टर", "जिल्हाधिकारी", "तहसीलदार", "सचिव", "संचालक", "अधिकारी", "सरकारी")
ORG_WORDS = ("लिमिटेड", "प्रायव्हेट", "कंपनी", "कॉर्पोरेशन", "बँक", "इंडस्ट्रीज", "एंटरप्रायझेस", "ट्रस्ट", "सोसायटी", "असोसिएशन", "फर्म", "ट्रेडर्स", "इन्फ्रा", "मेसर्स", "मर्यादित", "संस्था", "सहकारी", "कॉर्पोरेशन", "लि.")
ORG_LEGAL = {"लिमिटेड", "लि", "प्रायव्हेट", "प्रा", "मर्यादित", "कंपनी", "संस्था", "सोसायटी", "ट्रस्ट", "बँक", "असोसिएशन", "सहकारी"}
PROTECTED_PLACES = {"मुंबई", "नागपूर", "औरंगाबाद", "छत्रपती संभाजीनगर", "पुणे", "गोवा", "पणजी", "दिल्ली", "महाराष्ट्र", "भारत", "कोल्हापूर", "नाशिक", "मुंबई शहर"}
NON_PLACE_WORDS = {"ऑफिसर", "ऑफीसर", "इन्चार्ज", "प्रभारी", "निरीक्षक", "हवालदार", "अंमलदार", "उपनिरीक्षक", "न्यायालय", "न्यायालयात", "परिषद", "परिषदेचे", "सत्र", "दंडाधिकारी", "अधिकारी", "कार्यालय", "पोलीस", "पोलिस", "रुग्णालय", "न्यायाधीश", "न्यायालयाने",
                   "विधी", "आणि", "व", "हे", "या", "ते", "मध्ये", "येथे", "निबंधक", "सत्र", "कलेक्टर", "अधीक्षक"}
PETITIONER_ROLES = ("अर्जदार", "याचिकाकर्ता", "याचिकाकर्ते", "अपीलकर्ता", "अपीलकर्ते", "वादी", "फिर्यादी", "तक्रारदार", "अपीलार्थी", "याचिकाकर्त्या", "अपीलकर्त्या")
RESPONDENT_ROLES = ("गैर-अर्जदार", "गैर अर्जदार", "प्रतिवादी", "प्रत्यर्थी", "उत्तरवादी", "उत्तरदाता", "प्रतिवादीगण", "विरोधी पक्ष", "प्रतिवादीं")
REPORTER_RE = re.compile(r"\b(?:AIR|SCC|SCR|ALL|MLJ|BOM|Cri\.?\s*L\.?J|एआयआर|एससीसी|एस\.\s?सी\.\s?सी|एस\.\s?सी\.\s?आर|आय\.\s?ए\.\s?आर)\b|\(\d{4}\)\s*\d+\s*[A-Zअ-ह]|\[\d{4}\]\s*\d+")

ROLE_TAGS = {"PETITIONER": "अर्जदार", "RESPONDENT": "प्रतिवादी", "ADVOCATE": "वकील", "JUDGE": "न्यायाधीश",
             "PERSON": "व्यक्ती", "ORG": "संस्था", "LOC": "ठिकाण"}

# ── structured identifiers ───────────────────────────────────────────────────────────────────────
_V_D = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6], [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
        [5, 9, 8, 7, 6, 0, 4, 3, 2, 1], [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
_V_P = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2], [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
        [4, 2, 8, 6, 5, 7, 3, 9, 0, 1], [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]


def verhoeff_ok(num):
    c = 0
    for i, d in enumerate(reversed(num)):
        c = _V_D[c][_V_P[i % 8][int(d)]]
    return c == 0


PHONE_RE = re.compile(r"(?<![\d\w])(?:(?:\+|00)?91[\s\-]?)?[6-9]\d{9}(?![\d\w])|(?<![\d\w])(?:(?:\+|00)?91[\s\-]?)?[6-9]\d{4}[\s\-]\d{5}(?![\d\w])")
LANDLINE_RE = re.compile(r"(?<![\d\w])\(?0\d{2,4}\)?[\s\-]\d{6,8}(?![\d\w])")
EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")
URL_RE = re.compile(r"(?:https?://|www\.)\S+")
AADHAAR_RE = re.compile(r"(?<![\d\w])[2-9]\d{3}[\s\-]?\d{4}[\s\-]?\d{4}(?![\d\w])")
AADHAAR_CUE_RE = re.compile(r"आधार|Aadhaar|Aadhar|UID", re.I)
PAN_RE = re.compile(r"(?<![A-Z0-9])[A-Z]{5}\d{4}[A-Z](?![A-Z0-9])")
VEHICLE_RE = re.compile(r"(?<![A-Z0-9])[A-Z]{2}[\s\-]?\d{1,2}[\s\-]?[A-Z]{1,3}[\s\-]?\d{4}(?![A-Z0-9])")
IFSC_RE = re.compile(r"(?<![A-Z0-9])[A-Z]{4}0[A-Z0-9]{6}(?![A-Z0-9])")
GSTIN_RE = re.compile(r"(?<![A-Z0-9])\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z\d](?![A-Z0-9])")
ACCOUNT_RE = re.compile(r"((?:खाते|खात्याचा|खाता|खात्यात|A/c|a/c|Account|account)[^\n\d]{0,25})((?<!\d)\d{9,18}(?!\d))")
PIN_RE = re.compile(r"((?:पिन|PIN|Pin|पिनकोड)[^\n\d]{0,12})((?<!\d)[1-9]\d{5}(?!\d))")
DOB_RE = re.compile(r"((?:जन्म\s?(?:तारीख|दिनांक|तिथी)|DOB|जन्मतिथि)[^\n\d]{0,15})(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4})")
YEAR_LIKE_RE = re.compile(r"^(?:19|20)\d{2}$")

# ── names ────────────────────────────────────────────────────────────────────────────────────────
TITLE_ALT = "|".join(sorted(TITLES, key=len, reverse=True))
TITLE_RE = re.compile(r"(?<![" + DEV + r"])(" + TITLE_ALT + r")(?:\.[ \t]*|[ \t]+)(?=[" + DEV + r"A-Z])")
TOKEN_RE = re.compile(r"[ \t]*([" + DEV + r"][" + DEV + r"\-]*\.?|[A-Z][A-Za-z\-]*\.?)")
SUFFIX_RE = "(?:" + "|".join(re.escape(s) for s in INFLECTIONS) + ")"
HONORIFIC_RE = "(?:साहेब|साहेबांनी|साहेबांना|साहेबांचे|साहेबांच्या|भाई|बाई|ताई|दादा|अण्णा|मॅडम)"
TRAIL_RE = re.compile(r"^(?:" + SUFFIX_RE + r"){0,2}(?:ही|च|देखील)?$")


@lru_cache(maxsize=400_000)
def strip_inflection(tok):
    """रमेशने -> रमेश  (only when a sensible stem of >= 3 characters is left)."""
    for s in INFLECTIONS:
        if tok.endswith(s) and len(tok) - len(s) >= 3:
            return tok[:-len(s)]
    return tok


ROLE_PREFIXES = ("अपीलकर्त", "याचिकाकर्त", "अर्जदार", "प्रतिवादी", "उत्तरवादी", "उत्तरार्थी", "उत्तरार्थ", "प्रत्यर्थी", "अपीलार्थी", "वादी",
                 "आरोपी", "फिर्यादी", "तक्रारदार", "साक्षीदार", "वकील", "न्यायाधीश", "न्यायमूर्ती", "न्यायालय", "पोलीस", "पोलिस", "सरकार",
                 "शासन", "विभाग", "अधिकारी", "कार्यालय", "कंपनी", "बँक", "मालक", "भाडेकरू", "कामगार", "व्यवस्थापन", "संस्था", "महामंडळ",
                 "मंडळ", "आयुक्त", "निबंधक", "उपनिबंधक", "दिवाणी", "फौजदारी", "प्लॉट", "फ्लॅट", "कलम", "अधिनियम", "कायदा", "याचिका", "अपील",
                 "निर्णय", "आदेश", "क्रमांक", "प्रकरण", "पक्षकार", "प्रतिज्ञापत्र")
PRONOUN_PREFIXES = ("यां", "त्यां", "आम्ह", "आपल", "स्वत", "त्याच", "त्यास", "तिच", "तिला")
STOP_WORDS |= set("प्रति प्रतिनिधित्व नाही नाहीत आहेत असल्याने असल्याचे केले केली केला झाले झाली झाला दिले दिली दिला घर प्लॉट फ्लॅट".split())
NON_PLACE_WORDS |= {"ठिकाण", "ठिकाणी", "पत्ता", "शहर", "पालिका", "नगरपालिका", "महानगरपालिका", "परिषद", "ग्रामपंचायत", "पोस्ट", "तालुक्यातील", "जिल्ह्यातील", "घर", "प्लॉट", "फ्लॅट", "नाही", "नाहीत", "न्यायाधीशांनी", "न्यायाधीशांच्या", "उपनिबंधक", "निबंधक"}


def plausible_token(tok, common=frozenset(), ratio=None):
    """Could this word be (part of) a personal name or place name? Filters role words, pronouns, inflected stems,
    function words — the junk that made the first version mask ordinary words like नाही / अपीलकर्त्याने."""
    b = tok.rstrip(".")
    if tok.endswith(".") and 1 <= len(b) <= 2 and b not in STOP_WORDS:
        return True                                       # an initial: "ए.", "एस."
    if len(b) < 2 or b in STOP_WORDS or b in TITLES or b.isdigit():
        return False
    if b.startswith(ROLE_PREFIXES) or b.startswith(PRONOUN_PREFIXES):
        return False
    if b in common and (ratio or {}).get(b, 0) < 0.5:
        return False
    st = strip_inflection(b)
    if st != b and (st.startswith(ROLE_PREFIXES) or st.startswith(PRONOUN_PREFIXES) or st in STOP_WORDS):
        return False
    return True


def read_name(text, pos, max_tokens=4, common=frozenset(), name_ratio=None):
    """Read a person name starting at text[pos]. Returns (tokens, end_pos).
    Stops at punctuation and at the first word that cannot be part of a name."""
    toks, end = [], pos
    for _ in range(max_tokens):
        m = TOKEN_RE.match(text, end)
        if not m:
            break
        raw = m.group(1)
        if not plausible_token(raw, common, name_ratio):
            break
        toks.append(raw); end = m.end()
        if text[m.end():m.end() + 1] in ",;:()।":
            break
    if toks and not toks[-1].endswith("."):
        toks[-1] = strip_inflection(toks[-1])
    return toks, end


def name_key_tokens(tokens):
    return [t.rstrip(".") for t in tokens if len(t.rstrip(".")) >= 2]


# ── configuration ────────────────────────────────────────────────────────────────────────────────
class Config:
    def __init__(self, keep_judges=False, mask_orgs=True, mask_locations=True, mask_case_numbers=False,
                 use_gazetteer=True, gazetteer_min_ratio=0.25, ner=None):
        self.keep_judges = keep_judges
        self.mask_orgs = mask_orgs
        self.mask_locations = mask_locations
        self.mask_case_numbers = mask_case_numbers
        self.use_gazetteer = use_gazetteer
        self.gazetteer_min_ratio = gazetteer_min_ratio
        self.ner = ner               # optional callable: text -> list of (start, end, label)


# ── registry ─────────────────────────────────────────────────────────────────────────────────────
class Entity:
    def __init__(self, role, tokens, source):
        self.role = role
        self.names = {" ".join(name_key_tokens(tokens))}
        self.tokens = expand_tokens(name_key_tokens(tokens))
        self.source = {source}
        self.placeholder = None
        self.firsts = set()
        self.rest = set()
        self._track(tokens)

    def _track(self, tokens):
        toks = name_key_tokens(tokens)
        if len(toks) >= 2:
            self.firsts.add(toks[0]); self.rest |= expand_tokens(toks[1:])
        elif toks:
            self.rest |= expand_tokens(toks)           # a lone token counts as an ordinary alias

    def merge(self, tokens, role, source):
        self.names.add(" ".join(name_key_tokens(tokens)))
        self.tokens |= expand_tokens(name_key_tokens(tokens))
        self.source.add(source)
        self._track(tokens)
        order = ["PETITIONER", "RESPONDENT", "ADVOCATE", "JUDGE", "ORG", "LOC", "PERSON"]
        if order.index(role) < order.index(self.role):
            self.role = role


def expand_tokens(toks):
    """Hyphenated surnames (जोशी-फाळके) are also known by their parts."""
    out = set(toks)
    for t in toks:
        if "-" in t:
            out |= {p for p in t.split("-") if len(p) >= 2}
    return out


def _variants(tok):
    out = {tok}
    if tok.endswith("ील") and len(tok) > 4:
        out.add(tok[:-2] + "ल")                       # पाटील -> पाटल(ांनी)
    return out


class Registry:
    def __init__(self, common_words=frozenset()):
        self.entities = []
        self.common = common_words
        self.token_owner = {}

    def add(self, tokens, role, source):
        toks = name_key_tokens(tokens)
        if not toks:
            return None
        tset = expand_tokens(toks)
        target = None
        for e in self.entities:
            if e.role in ("ORG", "LOC") and role not in ("ORG", "LOC"):
                continue
            common = tset & e.tokens
            if common and (len(common) >= min(2, len(tset)) or (len(tset) == 1 and toks[0] in e.tokens)):
                target = e; break
        if target is None:
            target = Entity(role, tokens, source); self.entities.append(target)
        else:
            target.merge(tokens, role, source)
        for t in tset:
            self.token_owner.setdefault(t, target)
        return target

    def number(self):
        counters = Counter()
        for e in self.entities:
            counters[e.role] += 1
            e.placeholder = "<%s_%d>" % (ROLE_TAGS[e.role], counters[e.role])

    def alias_map(self):
        """alias string -> entity.  Multi-token aliases always; single tokens only if not a common word."""
        amap = {}
        for e in self.entities:
            for nm in sorted(e.names, key=len, reverse=True):
                parts = nm.split()
                cands = {nm}
                if len(parts) >= 3:
                    cands.add(parts[0] + " " + parts[-1])
                for i in range(len(parts) - 1):
                    cands.add(parts[i] + " " + parts[i + 1])
                for c in cands:
                    amap.setdefault(c, e)
                    head, _, last = c.rpartition(" ")
                    for v in _variants(last):                  # पाटील -> पाटल (before ांनी, ांच्या ...)
                        amap.setdefault((head + " " + v).strip(), e)
            for t in e.tokens:
                if len(t) >= 3 and t not in self.common and t not in STOP_WORDS and t not in TITLES:
                    # a bare first name of a lawyer/judge would also hit other people with that first name
                    if e.role in ("ADVOCATE", "JUDGE") and t in e.firsts and t not in e.rest:
                        continue
                    for v in _variants(t):
                        amap.setdefault(v, e)
        return amap


def build_sweeper(amap):
    """One compiled regex for all aliases, longest first; returns (regex)."""
    if not amap:
        return None
    def body(keys):                                   # initials may carry a dot: "एस. व्ही."
        return "|".join(re.escape(a).replace(r"\ ", r"\.?[ \t]+") for a in sorted(keys, key=len, reverse=True))
    ending = "(?:" + HONORIFIC_RE + ")?" + SUFFIX_RE + r"{0,2}(?:ही|च|देखील)?"
    multi = [a for a in amap if " " in a]
    single = [a for a in amap if " " not in a]
    parts = []
    if multi:        # several words: safe to cut even when an unfamiliar ending follows (पाटीलसाहेब -> <..>साहेब)
        parts.append(r"(?P<m>" + body(multi) + r")(?:\.(?=[ \t]))?(?P<ms>" + ending + r")")
    if single:       # one word: must end exactly (or with a known case ending) so रामायण is not hit by राम
        parts.append(r"(?P<s>" + body(single) + r")(?:\.(?=[ \t]))?(?P<ss>" + ending + r")(?![" + DEV + r"])")
    return re.compile(r"(?<![" + DEV + r"A-Za-z0-9])(?:" + "|".join(parts) + r")")


# ── anonymizer ───────────────────────────────────────────────────────────────────────────────────
class Anonymizer:
    def __init__(self, config=None, gazetteer=None):
        self.cfg = config or Config()
        self.gz = gazetteer or {}
        self.common = set(self.gz.get("common_words", []))
        self.name_ratio = self.gz.get("name_ratio", {})
        self.name_docs = self.gz.get("name_docs", {})
        self.place_docs = self.gz.get("place_docs", {})

    # --- seed extraction -------------------------------------------------------------------------
    SIDE_LINE_RE = re.compile(r"^[^\w]{0,12}(?:विरुद्ध|विरूद्ध|विरुध्द|विरूध्द|वि\.|v/s|vs\.?)[^\w]{0,12}$", re.I)
    INLINE_VS_RE = re.compile(r"\s(?:विरुद्ध|विरूद्ध|विरुध्द|विरूध्द|वि\.)\s")
    HEADER_END_RE = re.compile(r"^(?:कोरम|न्यायमंच|खंडपीठ|राखीव|जाहीर|सुनावणी|न्यायनिर्णय|निर्णय|निकाल|आदेश|दिनांक|निदांक|तोंडी|उपस्थित|समोर)(?![" + DEV + r"])")
    CASE_HEAD_RE = re.compile(r"क्रमांक|क्र\.|न्यायालय|अधिकार|खंडपीठ|याचिका|अपील|अर्ज|रिट|दिवाणी|फौजदारी|सत्र|\d{4}|\[|\]")
    TAIL_RE = re.compile(r"\s*(?:आणि|व)\s+(?:इतर|अन्य|आणखी\s+\S+|दुसरा|दुसरी|इतरांनी)\b.*$|\s*इत्यादी.*$|\s*\.{2,}.*$|\s*…+.*$")
    KIN_RE = re.compile(r"\s+(?:पुत्र|पुत्री|पत्नी|कन्या|सुपुत्र|सुपुत्री|चिरंजीव|मुलगा|मुलगी)\s+")
    NAME_END_RE = re.compile(r"[,\(;]|\s+वय(?![" + DEV + r"])|\s+मार्फत(?![" + DEV + r"])|\s+व्यवसाय(?![" + DEV + r"])|\s+रा\.|\s+राहणार|\s+तर्फे|\s+तर्फ(?![" + DEV + r"])|\s+उर्फ(?![" + DEV + r"])|\s+ऊर्फ(?![" + DEV + r"])")

    def seeds_from_header(self, header):
        """Parties (by side of 'विरुद्ध'), advocates and judges from the party header."""
        out = []
        lines = [l.strip() for l in header.split("\n") if l.strip()]
        out += self._parties(lines)
        out += self._advocates_and_judges(lines)
        return out

    def _party_names(self, lines, role, strong_idx=frozenset()):
        """Names from the lines of one side of the case. Lines whose index is in `strong_idx` sit right next to the
        "विरुद्ध" marker and are parties by position."""
        res = []
        i, n = 0, len(lines)
        first_free_line_taken = False
        while i < n:
            ln = lines[i]
            cidx = i
            i += 1
            if self.HEADER_END_RE.match(ln) or ("वकील" in ln and TITLE_RE.search(ln)):
                break
            m = re.match(r"^\(?(\d{1,3})[\.\)]\s*(.*)$", ln)
            numbered = bool(m)
            cand = m.group(2).strip() if m else ln
            ln_has_age = bool(re.search(r"(?:^|[\s,])वय(?![" + DEV + r"])\s*[:ः]?\s*\d", cand))
            if numbered and not cand and i < n:                     # lone number, the name is on the next line
                cand = lines[i]; cidx = i; i += 1
            nxt = lines[i] if i < n else ""
            has_age_next = bool(re.match(r"^(?:वय|वयः|age|रा\.|राहणार)(?![" + DEV + r"])", nxt))
            is_roleonly = bool(re.fullmatch(r"[\.\s…\(\)]*(?:" + "|".join(map(re.escape, PETITIONER_ROLES + RESPONDENT_ROLES)) + r")[\.\s\)]*", cand))
            if not cand or is_roleonly:
                continue
            if self.CASE_HEAD_RE.search(cand) and not (numbered or has_age_next):
                continue
            if not (numbered or has_age_next or (not first_free_line_taken and len(cand.split()) <= 9 and not re.search(r"\d", cand))):
                continue
            first_free_line_taken = True
            head = self.NAME_END_RE.split(cand, maxsplit=1)[0].strip(" .:-–")
            head = self.TAIL_RE.sub("", head).strip(" .:-–")
            head = re.sub(r"^(?:" + TITLE_ALT + r")\.?\s*", "", head)
            if not head or any(w in head for w in PUBLIC_BODY_WORDS) or head.startswith("मार्फत"):
                continue
            if len(head.split()) > 8:                                     # a sentence, not a name
                continue
            is_org = any(w in head for w in ORG_WORDS)
            kin = bool(self.KIN_RE.search(head))
            strong_cue = has_age_next or kin or ln_has_age or cidx in strong_idx                 # an age line / "X पुत्र Y" prove it is a person
            for k, part in enumerate(self.KIN_RE.split(head)):          # "X पुत्र Y Z": the party and the father
                for sub in re.split(r"\s+(?:आणि|व)\s+", part):
                    toks = [t for t in re.split(r"\s+", sub) if re.match(r"^[" + DEV + r"A-Za-z][" + DEV + r"A-Za-z\.\-]*$", t)]
                    if is_org:                                             # keep the distinctive words, drop the legal form
                        toks = [t for t in toks if t.rstrip(".") not in ORG_LEGAL and t.rstrip(".") not in STOP_WORDS and len(t.rstrip(".")) >= 2]
                    elif any(not plausible_token(t, self.common, self.name_ratio) for t in toks):
                        continue                                           # one non-name word means the phrase is not a name
                    toks = toks[:6]
                    if not toks or sum(len(t.rstrip(".")) for t in toks) < 3:
                        continue
                    # without a strong cue the words must be attested as names somewhere in the corpus
                    evidence = sum(1 for t in toks if self.name_ratio.get(t.rstrip("."), 0) >= 0.15)
                    if self.name_ratio and not strong_cue and not is_org and evidence == 0:
                        continue
                    res.append((toks, role if k == 0 else "PERSON", is_org and k == 0, "header_party"))
        return res

    def _parties(self, lines):
        vs = next((i for i, l in enumerate(lines) if self.SIDE_LINE_RE.match(l)), None)
        if vs is not None:
            left, right = lines[max(0, vs - 40):vs], lines[vs + 1:vs + 60]
            return (self._party_names(left, "PETITIONER", frozenset(range(max(0, len(left) - 3), len(left))))
                    + self._party_names(right, "RESPONDENT", frozenset(range(0, 3))))
        else:
            idx = next((i for i, l in enumerate(lines) if self.INLINE_VS_RE.search(l)), None)
            if idx is None:
                return self._parties_by_role_lines(lines)
            a, b = self.INLINE_VS_RE.split(lines[idx], maxsplit=1)
            left, right = lines[max(0, idx - 3):idx] + [a], [b] + lines[idx + 1:idx + 40]
        return (self._party_names(left, "PETITIONER", frozenset(range(max(0, len(left) - 3), len(left))))
                + self._party_names(right, "RESPONDENT", frozenset(range(0, 3))))

    def _parties_by_role_lines(self, lines):
        """Fallback when the header has no 'विरुद्ध': blocks that end with a role line ('..... अर्जदार')."""
        out, block = [], []
        roles_alt = "|".join(map(re.escape, sorted(PETITIONER_ROLES + RESPONDENT_ROLES, key=len, reverse=True)))
        role_line = re.compile(r"^[\.…\s\(]{0,}\s*(" + roles_alt + r")(?![" + DEV + r"])")
        for ln in lines:
            m = role_line.match(ln)
            if m and (len(ln) < 40 or ln.lstrip().startswith((".", "…"))):
                role = "PETITIONER" if m.group(1) in PETITIONER_ROLES else "RESPONDENT"
                out += self._party_names(block, role)
                block = []
            else:
                block.append(ln)
        return out

    def _advocates_and_judges(self, lines):
        out = []
        for idx, ln in enumerate(lines):
            if ("वकील" in ln or "एपीपी" in ln or "ए.पी.पी" in ln or "अधिवक्ता" in ln) and TITLE_RE.search(ln):
                for m in TITLE_RE.finditer(ln):
                    toks, _ = read_name(ln, m.end(), common=self.common, name_ratio=self.name_ratio)
                    if toks:
                        out.append((toks, "ADVOCATE", False, "header_advocate"))
            jm = re.match(r"^(?:कोरम|न्यायमंच|खंडपीठ|निकाल|निर्णय)\s*[:\-]\s*(?:\(?\s*पर\s+)?(.+)$", ln)
            if jm:
                chunk = jm.group(1)
                nxt = lines[idx + 1] if idx + 1 < len(lines) else ""
                if re.search(r"(?:आणि|व|,)\s*$", chunk) and nxt:          # the bench continues on the next line
                    chunk = chunk + " " + nxt
                for part in re.split(r"\s+आणि\s+|\s+व\s+|;", chunk):
                    part = re.sub(r"(?:,\s*)?(?:जे\.\s*जे\.|जे\.)[\s\),\.]*$", "", part).strip(" ,()")
                    toks, _ = read_name(part, 0, common=self.common, name_ratio=self.name_ratio)
                    if toks:
                        out.append((toks, "JUDGE", False, "header_judge"))
            jl = re.match(r"^(.{3,80}?),\s*(?:जे\.\s*जे\.|जे\.)\s*\)?\s*$", ln)   # "<name>, जे." anywhere in the header
            if jl:
                label_free = re.sub(r"^(?:कोरम|न्यायमंच|खंडपीठ|निकाल|निर्णय)\s*[:\-]\s*", "", jl.group(1))
                toks, _ = read_name(re.sub(r"^\(?\s*(?:पर\s+)?", "", label_free), 0, common=self.common, name_ratio=self.name_ratio)
                if toks:
                    out.append((toks, "JUDGE", False, "header_judge"))
        return out

    def seeds_from_text(self, text):
        out = []
        for m in TITLE_RE.finditer(text):
            title = m.group(1)
            toks, _ = read_name(text, m.end(), common=self.common, name_ratio=self.name_ratio)
            if not toks or not any(len(t.rstrip(".")) >= 3 for t in toks):        # initials alone are not a name
                continue
            if title in JUDGE_TITLES:
                role = "JUDGE"
            elif title in ADVOCATE_TITLES:
                role = "ADVOCATE"
            elif title in ORG_TITLES:
                role = "ORG"
            else:
                role = "PERSON"
            out.append((toks, role, False, "title"))
        return out

    def seeds_from_gazetteer(self, text):
        """Untitled names: runs of words that the corpus statistics say are used as names."""
        if not self.cfg.use_gazetteer or not self.name_ratio:
            return []
        min_r = self.cfg.gazetteer_min_ratio
        out = []
        for line in text.split("\n"):
            if REPORTER_RE.search(line):
                continue
            run = []
            prev_end = None

            def flush():
                if len(run) >= 2:
                    out.append((list(run), "PERSON", False, "gazetteer"))
                elif len(run) == 1 and self.name_ratio.get(run[0], 0) >= 0.8 and self.name_docs.get(run[0], 0) >= 6:
                    out.append((list(run), "PERSON", False, "gazetteer"))
            for m in re.finditer(r"[" + DEV + r"]{2,}(?:-[" + DEV + r"]+)?", line):
                raw = m.group(0)
                tok = raw if self.name_ratio.get(raw, 0) >= min_r else strip_inflection(raw)
                ok = (plausible_token(tok, self.common, self.name_ratio) and self.name_ratio.get(tok, 0) >= min_r
                      and self.name_docs.get(tok, 0) >= 3)
                adjacent = prev_end is not None and line[prev_end:m.start()].strip(" \t") == ""
                if ok and (not run or adjacent):
                    run.append(tok)
                else:
                    flush(); run = [tok] if ok else []
                prev_end = m.end()
            flush()
        return out

    # --- structured identifiers ------------------------------------------------------------------
    def redact_structured(self, text, counts):
        def sub(rx, tag, key, guard=None, group=0):
            def f(m):
                if guard and not guard(m, text):
                    return m.group(0)
                counts[key] += 1
                return m.group(0)[: m.start(group) - m.start()] + tag + m.group(0)[m.end(group) - m.start():] if group else tag
            return rx.sub(f, text)
        text = sub(EMAIL_RE, "<ईमेल>", "email")
        text = sub(URL_RE, "<दुवा>", "url")
        text = sub(GSTIN_RE, "<ओळखपत्र>", "gstin")
        text = sub(PAN_RE, "<ओळखपत्र>", "pan")
        text = sub(IFSC_RE, "<बँक-कोड>", "ifsc")

        def aadhaar_guard(m, t):
            digits = re.sub(r"\D", "", m.group(0))
            groups = re.findall(r"\d{4}", digits)
            if all(YEAR_LIKE_RE.match(g) for g in groups):
                return False
            ctx = t[max(0, m.start() - 40):m.start()]
            return verhoeff_ok(digits) or bool(AADHAAR_CUE_RE.search(ctx))
        text = sub(AADHAAR_RE, "<ओळखपत्र>", "aadhaar", aadhaar_guard)
        text = sub(PHONE_RE, "<फोन>", "phone")
        text = sub(LANDLINE_RE, "<फोन>", "phone")
        text = sub(VEHICLE_RE, "<वाहन-क्र>", "vehicle", lambda m, t: bool(re.search(r"\d", m.group(0))) and not re.fullmatch(r"[A-Z]{2}\s?\d{4}", m.group(0)))
        text = sub(ACCOUNT_RE, "<खाते-क्र>", "account", group=2)
        text = sub(PIN_RE, "<पिन>", "pincode", group=2)
        text = sub(DOB_RE, "<जन्मतारीख>", "dob", group=2)
        return text

    # --- locations -------------------------------------------------------------------------------
    LOC_CUE_RE = re.compile(r"(?<![" + DEV + r"])(तालुका|तहसील|ता\.|जिल्हा|जि\.|रा\.|राहणार|मौजे|मु\.\s?पो\.|पोलीस ठाणे|पोलिस ठाणे|पोलीस स्टेशन|पोलिस स्टेशन)[ \t]+(?=[" + DEV + r"])")
    POLICE_AFTER_RE = re.compile(r"(?<![" + DEV + r"])([" + DEV + r"]{3,})[ \t]+(?:पोलीस|पोलिस)[ \t]+(?:ठाणे|स्टेशन)")
    STRONG_CUES = ("तालुका", "तहसील", "जिल्हा", "रा.", "राहणार", "मौजे")

    def _place_ok(self, tok):
        tok = tok.rstrip(".")
        if len(tok) < 3 or tok in PROTECTED_PLACES or tok in NON_PLACE_WORDS or tok in self.common:
            return False
        if not plausible_token(tok, self.common, self.name_ratio):
            return False
        if self.place_docs and self.place_docs.get(tok, 0) < 2:        # corpus-attested place names only
            return False
        return True

    def _place_candidate(self, raw):
        """The place-name form of `raw` (itself, or with a case ending removed), or None."""
        b = raw.rstrip(".")
        if b in STOP_WORDS or b in NON_PLACE_WORDS or b.startswith(ROLE_PREFIXES) or b.startswith(PRONOUN_PREFIXES):
            return None
        for cand in (b, strip_inflection(b)):
            if self._place_ok(cand):
                return cand
        return None

    def seeds_from_locations(self, text):
        out = []
        for m in self.POLICE_AFTER_RE.finditer(text):            # "तेल्हारा पोलीस ठाणे" (place before the cue)
            cand = self._place_candidate(m.group(1))
            if cand:
                out.append(([cand], "LOC", False, "address"))
        for m in self.LOC_CUE_RE.finditer(text):
            toks, pos = [], m.end()
            for _ in range(3):
                t = TOKEN_RE.match(text, pos)
                if not t:
                    break
                raw = t.group(1)
                if raw.rstrip(".") in ("तालुका", "जिल्हा", "रा", "ता", "जि", "प्रभाग", "क्र", "रस्ता", "नगर", "कॉलनी", "रोड"):
                    break
                cand = self._place_candidate(raw)
                if not cand:
                    break
                toks.append(cand)
                pos = t.end()
                if raw.endswith(".") or text[t.end():t.end() + 1] in (",", ";", ":", "(", ")", "।", "\n", ""):      # a full stop ends the place
                    break
            if toks and " ".join(toks) not in PROTECTED_PLACES:
                out.append((toks, "LOC", False, "address"))
        return out

    # --- main ------------------------------------------------------------------------------------
    def build_registry(self, texts, header):
        reg = Registry(common_words=self.common)
        full = "\n".join(texts)
        seeds = self.seeds_from_header(header) if header else []
        for item in seeds:
            toks, role, is_org, src = item
            if role in ("PETITIONER", "RESPONDENT") and is_org and not self.cfg.mask_orgs:
                continue
            reg.add(toks, "ORG" if (is_org and role in ("PETITIONER", "RESPONDENT")) else role, src)
        for toks, role, is_org, src in self.seeds_from_text(full):
            if role == "JUDGE" and self.cfg.keep_judges:
                continue
            if role == "ORG" and not self.cfg.mask_orgs:
                continue
            reg.add(toks, role, src)
        if self.cfg.mask_locations:
            for toks, role, _, src in self.seeds_from_locations(full):
                reg.add(toks, "LOC", src)
        for toks, role, _, src in self.seeds_from_gazetteer(full):
            reg.add(toks, role, src)
        if self.cfg.ner:
            for toks, role in self._ner_seeds(full):
                reg.add(toks, role, "ner")
        if self.cfg.keep_judges:
            reg.entities = [e for e in reg.entities if e.role != "JUDGE"]
        reg.number()
        return reg

    def _ner_seeds(self, text):
        out = []
        for s, e, label in self.cfg.ner(text):
            frag = text[s:e].strip()
            if REPORTER_RE.search(text[max(0, s - 60):e + 60]):
                continue
            toks = [t for t in re.split(r"\s+", frag) if re.match(r"^[" + DEV + r"]{2,}", t)]
            toks = [strip_inflection(t) for t in toks][:5]
            if not toks or all(t in STOP_WORDS for t in toks):
                continue
            if label.upper().startswith(("PER", "B-PER", "I-PER")):
                out.append((toks, "PERSON"))
            elif label.upper().startswith(("LOC", "B-LOC", "I-LOC")) and self.cfg.mask_locations and " ".join(toks) not in PROTECTED_PLACES:
                out.append((toks, "LOC"))
            elif label.upper().startswith(("ORG", "B-ORG", "I-ORG")) and self.cfg.mask_orgs and not any(w in frag for w in PUBLIC_BODY_WORDS):
                out.append((toks, "ORG"))
        return out

    def apply(self, text, sweeper, amap, counts):
        if not text or not text.strip():
            return text

        def rep(m):
            gd = m.groupdict()
            raw, suffix = (gd.get("m"), gd.get("ms")) if gd.get("m") else (gd.get("s"), gd.get("ss"))
            alias = re.sub(r"\.?[ \t]+", " ", raw)
            e = amap.get(alias) or amap.get(raw)
            if e is None:
                return m.group(0)
            counts["entity:" + e.role] += 1
            suffix = suffix or ""
            if suffix and "ा" <= suffix[0] <= "ौ" or suffix[:1] in ("ं", "ः"):
                suffix = " य" + suffix                       # पाटलांनी -> <व्यक्ती_1> यांनी (no dangling vowel sign)
            return e.placeholder + suffix
        if sweeper:
            text = sweeper.sub(rep, text)
        return self.redact_structured(text, counts)

    def anonymize_text_fields(self, fields, header=""):
        """fields: dict name -> text.  Returns (new_fields, registry, counts)."""
        reg = self.build_registry(list(fields.values()), header)
        amap = reg.alias_map()
        sweeper = build_sweeper(amap)
        counts = Counter()
        return {k: self.apply(v, sweeper, amap, counts) for k, v in fields.items()}, reg, counts, (sweeper, amap)

    # --- leak scan -------------------------------------------------------------------------------
    def leak_scan(self, text, reg):
        leaks = []
        reported = set()
        for alias, e in reg.alias_map().items():
            if (e.role == "JUDGE" and self.cfg.keep_judges) or len(alias) < 3:
                continue
            # a one-word alias is only a leak as a whole word / with a known case ending (भारती is not भारतीय);
            # a multi-word alias is also flagged when glued to an unfamiliar ending
            multi = " " in alias
            tail = "" if multi else r"(?:" + HONORIFIC_RE + r")?(?:" + SUFFIX_RE + r"{0,2}(?:ही|च|देखील)?)(?![" + DEV + r"])"
            if re.search(r"(?<![" + DEV + r"])" + re.escape(alias).replace(r"\ ", r"\.?[ 	]+") + tail, text) and (e.placeholder, alias) not in reported:
                reported.add((e.placeholder, alias)); leaks.append(("name", alias))
        for rx, key in ((EMAIL_RE, "email"), (PAN_RE, "pan"), (PHONE_RE, "phone"), (GSTIN_RE, "gstin")):
            if rx.search(text):
                leaks.append((key, rx.search(text).group(0)))
        for m in AADHAAR_RE.finditer(text):
            d = re.sub(r"\D", "", m.group(0))
            if verhoeff_ok(d) and not all(YEAR_LIKE_RE.match(g) for g in re.findall(r"\d{4}", d)):
                leaks.append(("aadhaar", m.group(0))); break
        for m in TITLE_RE.finditer(text):                      # a titled name that survived
            toks, _ = read_name(text, m.end(), common=self.common, name_ratio=self.name_ratio)
            if toks and any(len(t.rstrip(".")) >= 3 for t in toks) and not toks[0].startswith("<"):
                leaks.append(("titled_name", m.group(1) + " " + " ".join(toks))); break
        return leaks

    def anonymize_document(self, doc):
        """doc: segmented document dict. Returns (anonymized_doc, report)."""
        out = copy.deepcopy(doc)
        sections = out.get("sections", {})
        meta = out.get("metadata", {})
        header = sections.get("header", "") or ""
        fields = {("s:" + k): v for k, v in sections.items() if isinstance(v, str)}
        for k, v in meta.items():
            if isinstance(v, str):
                fields["m:" + k] = v
        for i, c in enumerate(out.get("cited_cases", []) or []):
            if isinstance(c, str):
                fields["c:%d" % i] = c
        new, reg, counts, _ = self.anonymize_text_fields(fields, header)
        for k, v in new.items():
            kind, name = k.split(":", 1)
            if kind == "s":
                sections[name] = v
            elif kind == "m":
                meta[name] = v
            elif kind == "c":
                out["cited_cases"][int(name)] = v
        leaks = self.leak_scan("\n".join(new.values()), reg)
        parties = defaultdict(list)
        for e in reg.entities:
            if e.role in ("PETITIONER", "RESPONDENT", "ADVOCATE", "JUDGE"):
                parties[e.role.lower()].append(e.placeholder)
        out["parties"] = dict(parties)
        report = {
            "entities": [{"placeholder": e.placeholder, "role": e.role, "names": sorted(e.names), "tokens": sorted(e.tokens), "sources": sorted(e.source)} for e in reg.entities],
            "counts": dict(counts),
            "n_entities": len(reg.entities),
            "leaks": leaks,
            "header_parties_found": sum(1 for e in reg.entities if "header_party" in e.source),
        }
        out.setdefault("quality", {})
        out["quality"]["anonymized"] = not leaks
        out["quality"]["anonymization"] = {
            "version": VERSION, "ner": bool(self.cfg.ner), "gazetteer": bool(self.name_ratio and self.cfg.use_gazetteer),
            "replacements": int(sum(counts.values())), "entities": len(reg.entities), "leaks_found": len(leaks),
            "keep_judges": self.cfg.keep_judges,
        }
        out["quality"]["pii_replacements"] = int(sum(counts.values()))
        return out, report


# ── corpus-level gazetteer ───────────────────────────────────────────────────────────────────────
def build_gazetteer(docs, top_common=1200, min_df_ratio=0.12):
    """Learn from the corpus which words are used as names / places. `docs` is a list of segmented documents.
    Only high-precision seeds count (party header, advocates, judges, titled names). Document frequency is counted
    for the raw word AND its inflection-stripped stem, so a stem like 'अपीलकर्त्य' (from अपीलकर्त्याने) is correctly
    seen as an ordinary word. The result contains real names: keep it private."""
    docs = list(docs)
    tok_docs = Counter()
    texts = []
    for d in docs:
        sections = d.get("sections", {})
        text = "\n".join(v for v in sections.values() if isinstance(v, str))
        texts.append(text)
        words = set(re.findall(r"[" + DEV + r"]{2,}(?:-[" + DEV + r"]+)?", text))
        tok_docs.update(words | {strip_inflection(w) for w in words})
    # "common" = frequent AND widespread (function words, legal boilerplate); a surname seen in a few % of documents is not
    common = {w for w, c in tok_docs.most_common(top_common) if c >= min_df_ratio * len(docs)}
    an = Anonymizer(Config(use_gazetteer=False), {"common_words": list(common)})
    name_docs, place_docs = Counter(), Counter()
    strong = re.compile(r"(?<![" + DEV + r"])(?:तालुका|तहसील|जिल्हा|रा\.|राहणार|मौजे)[ \t]+([" + DEV + r"]{3,})")
    hp_titles = {"श्री", "श्रीमती", "कुमारी", "कु", "सौ", "डॉ", "डॉक्टर", "ॲड", "अॅड", "न्यायमूर्ती", "मेसर्स"}
    for d, text in zip(docs, texts):
        names = set()
        for toks, role, is_org, src in an.seeds_from_header(d.get("sections", {}).get("header", "") or ""):
            if role in ("PETITIONER", "RESPONDENT", "ADVOCATE", "JUDGE") and not is_org:
                names |= set(name_key_tokens(toks))
        for m in TITLE_RE.finditer(text):
            if m.group(1) not in hp_titles:
                continue
            toks, _ = read_name(text, m.end(), common=common)
            keys = [t for t in name_key_tokens(toks) if plausible_token(t, common)]
            if len(keys) >= 2 or (len(keys) == 1 and len(keys[0]) >= 4):
                names |= set(keys)
        name_docs.update(t for t in names if len(t) >= 2)
        place_docs.update({strip_inflection(w) for w in strong.findall(text)} | set(strong.findall(text)))
    ratio = {t: round(n / max(tok_docs[t], 1), 3) for t, n in name_docs.items()}
    return {"n_docs": len(docs), "common_words": sorted(common), "name_ratio": ratio, "name_docs": dict(name_docs),
            "place_docs": {t: n for t, n in place_docs.items() if n >= 2}}
