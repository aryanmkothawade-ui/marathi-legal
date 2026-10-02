"""
Stage 3: Document Segmentation — HLDC Paper Methodology (Marathi Adaptation)

Follows the HLDC paper pipeline exactly:
  Step 1 → Split Header / Body  (HLDC: header ends at dhara/thana; Marathi: ends at कोरम/दिनांक/तोंडी निर्णय)
  Step 2 → Extract Case Result from tail using reverse-scan (HLDC: tathyon keyword; Marathi: आदेश keyword)
  Step 3 → Extract Judge's Summary from body using paragraph-level regex annotation
  Step 4 → Remaining body = Facts & Arguments
  Step 5 → Case Type identification from case number prefix
  Step 6 → Outcome extraction from Case Result section
"""
import os, sys, re, json

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_DIR   = os.path.join(BASE_DIR, "corpus", "cleaned")
OUT_DIR  = os.path.join(BASE_DIR, "corpus", "segmented")
LOG_PATH = os.path.join(BASE_DIR, "logs", "segment_log.json")
os.makedirs(OUT_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────
# HEADER BOUNDARY MARKERS  (HLDC equivalent: dhara / thana)
# These phrases signal the END of the header section in Marathi HC docs
# ─────────────────────────────────────────────────────────────
HEADER_END_MARKERS = [
    re.compile(r'^\s*(?:तोंडी|मौखिक)\s+(?:निर्णय|न्यायनिर्णय|आदेश)\s*[:\.\u0903\u0964]?\s*(?:\(.*\))?\s*[:-]*\s*$', re.M | re.I),
    re.compile(r'^\s*(?:न्यायनिर्णय|निर्णय|निकाल)\s*[:\.\u0903\u0964]?\s*$', re.M | re.I),
    re.compile(r'^\s*आदेश\s*[:\u0903]\s*\(द्वारा', re.M | re.I),
    re.compile(r'^\s*(?:दिनांक|निदांक)\s*[:\u0903]\s*\n', re.M | re.I),
    re.compile(r'^\s*(?:कोरम|न्यायमंच|खंडपीठ)\s*[:\u0903]', re.M | re.I),
    re.compile(r'_+\s*\n', re.I),
]

# ─────────────────────────────────────────────────────────────
# CASE RESULT MARKERS — reverse-scan from document end
# (HLDC: searched for tathyon in reverse; we search for आदेश)
# ─────────────────────────────────────────────────────────────
# RESULT MARKERS — two tiers:
# Tier 1 (HIGH confidence): standalone आदेश lines — very precise
# Tier 2 (MEDIUM confidence): sentence-ending order phrases — catches Labour writs
#   where the order is embedded in a concluding paragraph, not a standalone line.
RESULT_START_MARKERS_HIGH = [
    re.compile(r'^\s*आदेश\s*[:\.\u0964]?\s*$', re.M | re.I),          # standalone "आदेश"
    re.compile(r'^\s*खालील\s+आदेश\s*[:\.\u0964]?\s*$', re.M | re.I),   # standalone "खालील आदेश"
    re.compile(r'^\s*म्हणून\s+आदेश\s*[:\.\u0964]?\s*$', re.M | re.I),  # standalone "म्हणून आदेश"
    re.compile(r'परिणामी.*?आम्ही\s+(?:खालील|पुढील|पुढी)\s+आदेश', re.I),
    re.compile(r'आम्ही\s+(?:खालील|पुढील|पुढी)\s+आदेश\s+(?:देतो|पारित)', re.I),
    re.compile(r'अपील\s+अंशतः\s+(?:मंजूर|यशस्वी)', re.I),
    re.compile(r'^\s*न्यायादेश\s*[:\.\u0964]?\s*$', re.M | re.I),
]

RESULT_START_MARKERS_MEDIUM = [
    # Sentence-ending order — for Labour writs, civil matters with no standalone आदेश line
    re.compile(r'(?:याचिका|अपील|अर्ज)\s+(?:मंजूर|फेटाळली|फेटाळले|खारीज|नामंजूर)\s+(?:जाते|केले|करतो|होते)\.?\s*$', re.M | re.I),
    re.compile(r'(?:याचिका|अपील)\s+(?:मंजूर|फेटाळली|खारीज)(?:\s+करण्यात\s+येत\s+आहे|\.?\s*$)', re.M | re.I),
    re.compile(r'(?:जामीन|Bail)\s+(?:मंजूर|नामंजूर|फेटाळला)', re.I),
    re.compile(r'(?:याचिका|अपील|अर्ज)\s+मंजूर\s+करणे\s+आवश्यक', re.I),
    re.compile(r'उपरोक्त\s+(?:परिस्थितीत|विवेचनावर)', re.I),
    re.compile(r'(?:याचिका|अपील)\s+(?:मंजूर|फेटाळली|खारीज)', re.I),
    re.compile(r'वरील\s+(?:कारणास्तव|विवेचनाच्या\s+आधारे)', re.I),
    re.compile(r'(?:म्हणून|त्यामुळे|परिणामी).*?(?:आदेश|मंजूर|फेटाळ)', re.I),
]

# Disclaimer boilerplate to strip from case_result
DISCLAIMER_RE = re.compile(
    r'अस्वीकरण[\s\S]*?(?:वैध\s+मानला\s+जाईल|x-x-x-x|\*{3,})',
    re.I
)

# ─────────────────────────────────────────────────────────────
# JUDGE'S SUMMARY MARKERS  (HLDC Appendix D.3 equivalent)
# ─────────────────────────────────────────────────────────────
JUDGE_SUMMARY_MARKERS = [
    re.compile(r'आमच्या\s+मते', re.I),
    re.compile(r'आम्ही\s+(?:पाहू|मानतो|असे\s+मत|असे\s+ठरवतो)', re.I),
    re.compile(r'(?:न्यायालया|खंडपीठा)(?:च्या|ंच्या)\s+मते', re.I),
    re.compile(r'विचार\s+(?:केला|केल्यानंतर)\s+असता', re.I),
    re.compile(r'सर्व\s+(?:बाबींचा|बाजूंचा|तथ्यांचा)\s+विचार', re.I),
    re.compile(r'वरील\s+(?:विवेचनावर|चर्चेवर|परिस्थितीत)', re.I),
    re.compile(r'उपरोक्त\s+(?:विवेचन|चर्चा|विश्लेषण)', re.I),
    re.compile(r'पक्षकारांच्या\s+(?:अभ्यासू|विद्वान)\s+वकिलांच(?:्या|ा)\s+(?:सल्ला|मदत)', re.I),
    re.compile(r'रेकॉर्डही\s+पाहिला', re.I),
    # Additional markers for Labour / Industrial writs (doc 2 type)
    re.compile(r'आमच्या\s+(?:निदर्शनास|विचारात|लक्षात)', re.I),
    re.compile(r'(?:न्यायालयाने|खंडपीठाने)\s+(?:विचार|पाहिले|तपासले)', re.I),
    re.compile(r'वरील\s+(?:कारणास्तव|विश्लेषणावरून|चर्चेनंतर)', re.I),
    re.compile(r'(?:आम्हाला|न्यायालयाला)\s+(?:असे|हे)\s+(?:वाटते|दिसते|आढळते)', re.I),
    re.compile(r'(?:साक्ष्य|पुरावा|रेकॉर्ड)\s+(?:पाहता|पाहिल्यास|तपासता)', re.I),
    re.compile(r'वरील\s+कारणास्तव', re.I),
    re.compile(r'(?:म्हणून|त्यामुळे).*?(?:आम्हाला|न्यायालयाला)', re.I),
]

# ─────────────────────────────────────────────────────────────
# OUTCOME DETECTION  (HLDC Appendix E equivalent)
# ─────────────────────────────────────────────────────────────
OUTCOME_MAP = {
    'partially_allowed': [re.compile(p, re.I) for p in [
        r'अंशतः\s+मंजूर',
        r'अपील\s+अंशतः',
        r'अंशतः\s+यशस्वी',
    ]],
    'allowed':   [re.compile(p, re.I) for p in [
        r'(?:याचिका|अपील|अर्ज)\s+मंजूर',
        r'प्रार्थना\s+(?:कलम|मंजूर)',
        r'(?:जामीन|Bail)\s+मंजूर',
        r'स्थगिती\s+मंजूर',
        r'नियम\s+निरपेक्ष',
        r'अपील\s+(?:मंजूर|मान्य)',
        r'आलिर्ण\s+आदेश\s+रद्द',         # "impugned order set aside" = allowed
    ]],
    'dismissed': [re.compile(p, re.I) for p in [
        r'(?:याचिका|अपील|अर्ज)\s+(?:फेटाळली|फेटाळले|खारीज|नामंजूर)',
        r'(?:जामीन|Bail)\s+(?:नामंजूर|फेटाळला)',
        r'याचिका\s+र्फेटाळली',
        r'हस्तक्षेप\s+करण्याचे\s+कोणतेही\s+न्याय',  # "no reason to interfere"
        r'हस्तक्षेपाचे\s+कारण\s+नाही',
    ]],
    'remanded':  [re.compile(p, re.I) for p in [
        r'परत\s+(?:पाठवले|पाठविले)',
        r'पुनर्विचारासाठी',
    ]],
}

# ─────────────────────────────────────────────────────────────
# PETITIONER ARGUMENT MARKERS
# ─────────────────────────────────────────────────────────────
PETITIONER_MARKERS = [
    re.compile(r'याचिकाकर्त्याचे\s+(?:प्रकरण|म्हणणे|असे)', re.I),
    re.compile(r'याचिकाकर्त्या(?:च्या|ंच्या|तर्फे)', re.I),
    re.compile(r'(?:अर्जदारा|वादी)(?:चे|ंचे|तर्फे)', re.I),
    re.compile(r'अपीलकर्त्या(?:चे|तर्फे|च्या)', re.I),
    re.compile(r'(?:तर्फे|बाजूने)\s+(?:असा\s+)?युक्तिवाद', re.I),
    re.compile(r'अभ्यासू\s+वकील\s+(?:श्री|अॅड)', re.I),
    re.compile(r'(?:याचिकाकत|यामिKकाकत)\s*[0-9]', re.I),
]

# ─────────────────────────────────────────────────────────────
# RESPONDENT ARGUMENT MARKERS
# ─────────────────────────────────────────────────────────────
RESPONDENT_MARKERS = [
    re.compile(r'प्रतिवादीं(?:च्या|चे|तर्फे|ंच्या|ंचे)', re.I),
    re.compile(r'प्रतिवादींच्या\s+वतीने', re.I),
    re.compile(r'सरकारी\s+वकिलांनी', re.I),
    re.compile(r'(?:विरोध|आक्षेप)\s+(?:केला|नोंदवला)', re.I),
    re.compile(r'उत्तरदात(?:ा|्यां)(?:तर्फे|चे|च्या)', re.I),
    re.compile(r'(?:अतिरिक्त|विद्वान)\s+सरकारी\s+वकील', re.I),  # Additional Govt counsel
    re.compile(r'प्रतिवादीचे\s+(?:म्हणणे|वकील)', re.I),
    re.compile(r'उत्तरवादीं?(?:नी|चे|च्या|साठी)', re.I),          # उत्तरवादी form (doc 4)
    re.compile(r'राज्याKे\s+(?:अतिरिक्त|विद्वान)', re.I),         # State counsel (garbled)
]

# ─────────────────────────────────────────────────────────────
# CASE TYPE IDENTIFICATION  (HLDC §3 "Case Type Identification")
# ─────────────────────────────────────────────────────────────
CASE_TYPE_MAP = [
    (re.compile(r'(?:रिट|Writ)\s+याचिका', re.I),       'Writ Petition'),
    (re.compile(r'(?:फौजदारी|क्रिमिनल)\s+अपील', re.I), 'Criminal Appeal'),
    (re.compile(r'Criminal\s+Appeal', re.I),            'Criminal Appeal'),
    (re.compile(r'सूट\s*(?:\(लॉज\.?\))?', re.I),         'Civil Suit'),
    (re.compile(r'Civil\s+Suit', re.I),                 'Civil Suit'),
    (re.compile(r'(?:दिवाणी|Civil)\s+अपील', re.I),     'Civil Appeal'),
    (re.compile(r'जामीन\s+अर्ज', re.I),                'Bail Application'),
    (re.compile(r'प्रथम\s+अपील', re.I),                'First Appeal'),
    (re.compile(r'मूळ\s+याचिका', re.I),                'Original Petition'),
    (re.compile(r'रीट\s+याचिका', re.I),                'Writ Petition'),
    (re.compile(r'Writ\s+Petition', re.I),              'Writ Petition'),
    # Labour / Industrial Disputes Act writs
    (re.compile(r'Industrial\s+Disputes\s+Act', re.I), 'Labour Writ Petition'),
    (re.compile(r'(?:कामगार|औद्योगिक)\s+(?:न्यायालय|विवाद)', re.I), 'Labour Writ Petition'),
    # Income Tax Appeals
    (re.compile(r'Income\s+Tax\s+(?:Appeal|Reference)', re.I), 'Income Tax Appeal'),
    (re.compile(r'आयकर\s+अपील', re.I),               'Income Tax Appeal'),
]

# ─────────────────────────────────────────────────────────────
# OUTCOME DETECTION  (HLDC Appendix E equivalent)
# ─────────────────────────────────────────────────────────────
# FIX 2: Added partially_allowed outcome for mixed results (e.g. doc 5)
OUTCOME_MAP = {
    'partially_allowed': [re.compile(p, re.I) for p in [
        r'अंशतः\s+मंजूर',
        r'अपील\s+अंशतः',
        r'अंशतः\s+यशस्वी',
    ]],
    'allowed':   [re.compile(p, re.I) for p in [
        r'(?:याचिका|अपील|अर्ज)\s+मंजूर',
        r'प्रार्थना\s+(?:कलम|मंजूर)',
        r'(?:जामीन|Bail)\s+मंजूर',
        r'स्थगिती\s+मंजूर',
        r'नियम\s+निरपेक्ष',
    ]],
    'dismissed': [re.compile(p, re.I) for p in [
        r'(?:याचिका|अपील|अर्ज)\s+(?:फेटाळली|फेटाळले|खारीज|नामंजूर)',
        r'(?:जामीन|Bail)\s+(?:नामंजूर|फेटाळला)',
        r'याचिका\s+र्फेटाळली',           # garbled OCR variant
    ]],
    'remanded':  [re.compile(p, re.I) for p in [
        r'परत\s+(?:पाठवले|पाठविले)',
        r'पुनर्विचारासाठी',
    ]],
}

YEAR_RE     = re.compile(r'\b(19\d{2}|20\d{2})\b')
CASE_NUM_RE = re.compile(r'(?:याचिका|अपील|सूट|क्रमांक|नंबर|क्र\.?)\s*(?:क्र\.?\s*)?(\d+(?:/\d+)?(?:\s*(?:ऑफ|ची|of|चे)\s*\d{4})?)', re.I)
# FIX 5 (date): Require day (1-31), month (1-12) — guards against address numbers like 5-1-767
DATE_RE     = re.compile(r'\b([12]?\d|3[01])[/\-\.]([01]?\d)[/\-\.](19\d{2}|20\d{2})\b')
COURT_RE    = re.compile(r'(?:मुंबई|नागपूर|औरंगाबाद|पुणे)\s+(?:येथील\s+)?उच्च\s+न्यायालय[ात]*', re.I)
# FIX 3: Expanded citation patterns — SCC, SCR, CLR, Marathi transliterations
CITATION_RE = [
    re.compile(r'\bAIR\s+\d{4}\s+\w+\s+\d+'),
    re.compile(r'\(\d{4}\)\s+\d+\s+SCC\s+\d+'),
    re.compile(r'\b\d{4}\s+SCC\s+\d+'),
    re.compile(r'\bSCR\s*[-–]\s*\d{4}'),
    re.compile(r'\(\d{4}\)\s+\d+\s+SCR\s+\d+'),          # (1961) 3 SCR 236
    re.compile(r'\d{4}\s*\(\d+\)\s*[A-Z]+LJ\s+\d+'),    # 2008 (2) CLR 1006
    re.compile(r'\d{4}\s*\(\d+\)\s*[A-Z]+LN\s+\d+'),    # LLN format
    re.compile(r'एस\.सी\.सी\.\s+\d+'),                   # Marathi SCC
    re.compile(r'एस\.सी\.आर\.\s*[-–]?\s*\d{4}'),         # Marathi SCR
    re.compile(r'\d+\s+आय\.\s*टी\.\s*आर\.\s+\d+'),       # I.T.R. (income tax)
    re.compile(r'Criminal\s+Appeal\s+(?:No\.?|Number)?\s*\d+/\d{4}'),
]

# ─────────────────────────────────────────────────────────────
# STEP 1: HEADER SPLIT
# HLDC approach: find the finishing word of header, segment there.
# Marathi: scan lines top-down for header-end markers.
# ─────────────────────────────────────────────────────────────
def split_header_body(text: str) -> tuple:
    lines = text.split('\n')
    header_end_idx = -1

    for i, line in enumerate(lines):
        for marker in HEADER_END_MARKERS:
            if marker.search(line):
                header_end_idx = i
                break
        if header_end_idx >= 0:
            break

    # Fallback: use विरुद्ध + 15 lines if no marker found
    if header_end_idx < 0:
        for i, line in enumerate(lines):
            if re.search(r'विरुद्ध|versus', line, re.I):
                header_end_idx = min(i + 15, len(lines) // 4)
                break

    # Hard fallback: first 20% of document
    if header_end_idx < 0:
        header_end_idx = max(10, len(lines) // 5)

    header = '\n'.join(lines[:header_end_idx + 1]).strip()
    body   = '\n'.join(lines[header_end_idx + 1:]).strip()
    return header, body

# ─────────────────────────────────────────────────────────────
# STEP 2: CASE RESULT — reverse-scan (HLDC tathyon approach)
# Scan from the END of the document for the first result marker.
# ─────────────────────────────────────────────────────────────
def extract_case_result(body: str) -> tuple:
    """Two-tier result detection:
    Tier 1 — HIGH confidence standalone आदेश line markers (very precise).
    Tier 2 — MEDIUM confidence sentence-ending order phrases.
    Tier 1 is tried first. Tier 2 only activates if Tier 1 finds nothing.
    Both tiers scan ALL paragraphs and take the LAST hit (last match wins),
    ensuring we get the actual final order, not a mid-document reference.
    """
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', body) if p.strip()]

    def _scan(markers):
        result_start = None
        for i, para in enumerate(paragraphs):
            for marker in markers:
                if marker.search(para):
                    result_start = i
                    break
        return result_start

    # Tier 1: standalone आदेश line
    result_start = _scan(RESULT_START_MARKERS_HIGH)

    # Tier 2: sentence-ending order phrases (Labour writs, inline orders)
    if result_start is None:
        result_start = _scan(RESULT_START_MARKERS_MEDIUM)

    if result_start is None:
        return body, ''  # genuinely no order section found

    main_body   = '\n\n'.join(paragraphs[:result_start])
    case_result = '\n\n'.join(paragraphs[result_start:])

    # Strip translation disclaimer boilerplate
    case_result = DISCLAIMER_RE.sub('', case_result).strip()

    return main_body, case_result

# ─────────────────────────────────────────────────────────────
# STEP 3: JUDGE'S SUMMARY — paragraph-level annotation
# HLDC: sentence-level regex; extend to paragraph level; iterate from end.
# ─────────────────────────────────────────────────────────────
def extract_judges_summary(body: str) -> tuple:
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', body) if p.strip()]
    labels = ['NONE'] * len(paragraphs)

    # Annotate each paragraph
    for i, para in enumerate(paragraphs):
        for marker in JUDGE_SUMMARY_MARKERS:
            if marker.search(para):
                labels[i] = 'JUDGES_SUMMARY'
                break

    # HLDC approach: iterate from end; mark NONE as JUDGES_SUMMARY
    # until we hit a paragraph that is clearly NOT summary
    found_summary = False
    for i in range(len(paragraphs) - 1, -1, -1):
        if labels[i] == 'JUDGES_SUMMARY':
            found_summary = True
        elif found_summary and labels[i] == 'NONE':
            # Check if it also matches a petitioner/respondent marker — if yes, stop
            is_arg = any(m.search(paragraphs[i]) for m in PETITIONER_MARKERS + RESPONDENT_MARKERS)
            if not is_arg:
                labels[i] = 'JUDGES_SUMMARY'
            else:
                break

    summary_paras = [p for p, l in zip(paragraphs, labels) if l == 'JUDGES_SUMMARY']
    facts_paras   = [p for p, l in zip(paragraphs, labels) if l == 'NONE']
    return '\n\n'.join(facts_paras), '\n\n'.join(summary_paras)

# ─────────────────────────────────────────────────────────────
# STEP 4: SPLIT FACTS & ARGUMENTS — petitioner vs respondent
# ─────────────────────────────────────────────────────────────
def split_facts_arguments(body: str) -> tuple:
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', body) if p.strip()]
    petitioner_paras, respondent_paras, facts_paras = [], [], []
    last_label = 'FACTS'

    for para in paragraphs:
        if any(m.search(para) for m in PETITIONER_MARKERS):
            last_label = 'PETITIONER'
        elif any(m.search(para) for m in RESPONDENT_MARKERS):
            last_label = 'RESPONDENT'
        # Assign by last known label (forward-fill, same as HLDC)
        if last_label == 'PETITIONER':
            petitioner_paras.append(para)
        elif last_label == 'RESPONDENT':
            respondent_paras.append(para)
        else:
            facts_paras.append(para)

    return ('\n\n'.join(facts_paras),
            '\n\n'.join(petitioner_paras),
            '\n\n'.join(respondent_paras))

# ─────────────────────────────────────────────────────────────
# SC JUDGMENT TRANSLATION FALLBACK PATTERNS
# Old SC judgment Marathi translations have no standard HC header.
# They begin with a citation block like:
#   "( इंग्रजी भाषेतील टंकलिखित न्यायनिर्णयाचा मराठी अनुवाद )"
#   [1960] 38 I.T.R. 85 (SC) OR (1961) 3 SCR 200
# ─────────────────────────────────────────────────────────────
_SC_TRANSLATION_RE = re.compile(
    r'(?:इंग्रजी\s+भाषेतील.*?(?:मराठी\s+अनुवाद|भाषांतर)'
    r'|टंकलिखित\s+न्यायनिर्णयाचा'
    r'|\[\d{4}\]\s+\d+\s+I\.T\.R\.'
    r'|\(\d{4}\)\s+\d+\s+(?:SCR|SCC)\s+\d+)',
    re.I | re.S
)
_SC_CITATION_META_RE = [
    re.compile(r'\[(\d{4})\]\s+\d+\s+I\.T\.R\.\s+(\d+)\s+\(SC\)', re.I),  # [1960] 38 I.T.R. 85 (SC)
    re.compile(r'\((\d{4})\)\s+\d+\s+SCR\s+\d+'),                            # (1961) 3 SCR 200
    re.compile(r'\((\d{4})\)\s+\d+\s+SCC\s+\d+'),                            # (2001) 3 SCC 100
    re.compile(r'\bAIR\s+(\d{4})\s+SC\s+\d+'),                               # AIR 1960 SC 1
]
_SC_CASE_NAME_RE = re.compile(
    r'^([^\n]{5,80})\s*\n\s*(?:विरुद्ध|[Vv]ersus|[Vv]\.)\s*\n\s*(.{5,80})',
    re.M
)
_SC_JUDGE_RE = re.compile(
    r'(?:न्यायमूर्ती|JUSTICE|Justice)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})',
    re.I
)

def _extract_sc_translation_meta(full_text: str, meta: dict) -> dict:
    """Fallback metadata extractor for old SC judgment Marathi translations.
    Populates court, year, case_number from citation block at top of document.
    """
    search_zone = full_text[:1500]  # citation always near top

    meta["court"] = "सर्वोच्च न्यायालय"  # Supreme Court
    meta["bench_location"] = "Delhi"
    meta["document_type"] = "SC Judgment Translation"

    # Extract year from citation
    for pat in _SC_CITATION_META_RE:
        m = pat.search(search_zone)
        if m:
            meta["year"] = int(m.group(1))
            meta["case_number"] = m.group(0).strip()
            break

    # Fallback year: any 4-digit year in first 500 chars
    if not meta["year"]:
        years = YEAR_RE.findall(full_text[:500])
        if years:
            meta["year"] = int(min(years))  # earliest year = year of judgment

    # Try to extract case name (petitioner vs respondent)
    m = _SC_CASE_NAME_RE.search(search_zone)
    if m and not meta["case_number"]:
        meta["case_number"] = f"{m.group(1).strip()} v. {m.group(2).strip()}"

    # Jurisdiction
    if any(kw in full_text[:2000] for kw in ['Income Tax', 'आयकर', 'I.T.R.']):
        meta["jurisdiction"] = "Tax"
        meta["case_type"]    = "Income Tax Appeal"
    elif any(kw in full_text[:2000] for kw in ['Criminal', 'फौजदारी', 'IPC']):
        meta["jurisdiction"] = "Criminal"
        meta["case_type"]    = "Criminal Appeal"
    else:
        meta["jurisdiction"] = "Civil"

    return meta


# ─────────────────────────────────────────────────────────────
# METADATA EXTRACTION
# ─────────────────────────────────────────────────────────────
def extract_metadata(header: str, full_text: str) -> dict:
    meta = {
        "court": None, "bench_location": "Mumbai",
        "case_type": None, "case_number": None,
        "year": None, "date_of_order": None,
        "jurisdiction": None, "ipc_sections": [],
        "document_type": "HC Judgment",
    }

    # ── Detect SC Translation format FIRST ─────────────────────
    if _SC_TRANSLATION_RE.search(full_text[:800]):
        return _extract_sc_translation_meta(full_text, meta)

    # ── Standard Bombay HC format ───────────────────────────────
    m = COURT_RE.search(header)
    if m:
        meta["court"] = m.group(0).strip()
        if 'नागपूर' in m.group(0): meta["bench_location"] = "Nagpur"
        elif 'औरंगाबाद' in m.group(0): meta["bench_location"] = "Aurangabad"
    else:
        # Fallback: search wider body for court name
        m2 = COURT_RE.search(full_text[:600])
        if m2:
            meta["court"] = m2.group(0).strip()

    for pat, label in CASE_TYPE_MAP:
        if pat.search(full_text[:800]):
            meta["case_type"] = label
            break

    m = CASE_NUM_RE.search(header)
    if m: meta["case_number"] = m.group(0).strip()

    # Year: prefer header; fallback to full_text first 400 chars
    years = YEAR_RE.findall(header)
    if years:
        meta["year"] = int(max(years))
    else:
        years = YEAR_RE.findall(full_text[:400])
        if years:
            meta["year"] = int(max(years))

    m = DATE_RE.search(header)
    if m:
        d, mo, y = m.groups()
        if len(y) == 2: y = "20" + y
        meta["date_of_order"] = f"{y}-{mo.zfill(2)}-{d.zfill(2)}"

    for kw, val in [('दिवाणी', 'Civil'), ('फौजदारी', 'Criminal'), ('क्रिमिनल', 'Criminal'),
                    ('कामगार', 'Labour'), ('औद्योगिक', 'Labour'), ('Industrial', 'Labour')]:
        if kw in header or kw in full_text[:500]:
            meta["jurisdiction"] = val
            break

    # IPC sections — भादंविकलम and English IPC §/Section
    sec_patterns = [
        r'भादंविकलम\s+([\d,\s]+(?:व\s+[\d,\s]+)*)',
        r'(?:IPC|भादंवि)\s*(?:§|Section|कलम)\s*([\d,\s]+)',
        r'(?:कलम|Section)\s+([\d,\s]+)',
    ]
    all_secs = []
    for sp in sec_patterns:
        for m in re.finditer(sp, full_text[:2000], re.I):
            nums = re.findall(r'\d+', m.group(1))
            all_secs.extend(nums)
    if all_secs:
        meta["ipc_sections"] = list(dict.fromkeys(n for n in all_secs if len(n) <= 3))

    return meta

def detect_outcome(result_text: str) -> dict:
    out = {"outcome": "Unknown", "outcome_normalized": "unknown",
           "bail_granted": None, "remanded": False, "stay_granted": False}
    for label, patterns in OUTCOME_MAP.items():
        for pat in patterns:
            if pat.search(result_text):
                out["outcome"] = label.capitalize()
                out["outcome_normalized"] = label
                if label == 'remanded': out["remanded"] = True
                return out
    return out

def extract_citations(text: str) -> list:
    found = []
    for pat in CITATION_RE:
        found.extend(pat.findall(text))
    return list(set(found))

# ─────────────────────────────────────────────────────────────
# FULL PIPELINE FOR ONE DOCUMENT
# ─────────────────────────────────────────────────────────────
def segment_document(doc_id: str, text: str) -> dict:
    # Step 1: Header / Body
    header, body = split_header_body(text)
    # Step 2: Case Result (reverse-scan)
    body_main, case_result = extract_case_result(body)
    # Step 3: Judge's Summary
    facts_and_args, judges_summary = extract_judges_summary(body_main)
    # Step 4: Facts vs Arguments
    facts, petitioner_args, respondent_args = split_facts_arguments(facts_and_args)
    # Metadata
    meta    = extract_metadata(header, text)
    outcome = detect_outcome(case_result)
    cites   = extract_citations(text)

    sections_filled = sum(1 for s in [facts, petitioner_args, respondent_args, judges_summary] if s.strip())
    has_result      = bool(case_result.strip())
    confidence      = "high" if (sections_filled >= 3 and has_result) else \
                      "medium" if (sections_filled >= 1 or has_result) else "low"

    return {
        "doc_id":   doc_id,
        "metadata": meta,
        "sections": {
            "header":               header,
            "facts":                facts,
            "petitioner_arguments": petitioner_args,
            "respondent_arguments": respondent_args,
            "judges_summary":       judges_summary,
            "case_result":          case_result,
        },
        "labels":      {**outcome},
        "cited_cases": cites,
        "quality": {
            "segmentation_complete":   has_result and sections_filled >= 2,
            "segmentation_confidence": confidence,
            "has_result_section":      has_result,
            "body_sections_filled":    sections_filled,
        },
    }

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def process_all():
    files = sorted(f for f in os.listdir(IN_DIR) if f.endswith(".txt"))
    log   = []

    print("=" * 65)
    print("  MLDC -- Stage 3: Segmentation (HLDC Paper Method)")
    print("  Header → Body → Case Result → Judge's Summary → Facts")
    print("=" * 65)

    for fname in files:
        doc_id = os.path.splitext(fname)[0]
        with open(os.path.join(IN_DIR, fname), encoding="utf-8") as f:
            text = f.read()

        print(f"\n[>>] {fname}")
        result = segment_document(doc_id, text)
        q, m   = result["quality"], result["metadata"]

        with open(os.path.join(OUT_DIR, f"{doc_id}.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"  Case type  : {m.get('case_type') or 'unknown'}")
        print(f"  Court      : {m.get('court') or 'unknown'}")
        print(f"  Year       : {m.get('year') or 'unknown'}")
        print(f"  Outcome    : {result['labels']['outcome']}")
        print(f"  Sections   : {q['body_sections_filled']}/4  |  Has result: {'Yes' if q['has_result_section'] else 'No'}")
        print(f"  Confidence : {q['segmentation_confidence'].upper()}")
        print(f"  Citations  : {len(result['cited_cases'])}")
        log.append({"doc_id": doc_id, **{k: q[k] for k in q}, "outcome": result["labels"]["outcome_normalized"]})

    high = sum(1 for e in log if e["segmentation_confidence"] == "high")
    med  = sum(1 for e in log if e["segmentation_confidence"] == "medium")
    low  = sum(1 for e in log if e["segmentation_confidence"] == "low")
    print(f"\n{'=' * 65}  Confidence: HIGH={high}  MEDIUM={med}  LOW={low}")

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(f"[OK] Log: {LOG_PATH}")

if __name__ == "__main__":
    process_all()
