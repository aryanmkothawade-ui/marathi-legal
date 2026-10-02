import json, os, sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = r'c:\Users\bigha\OneDrive\Desktop\marathi_legal_document'

print('=== FINAL CORPUS QUALITY CHECK ===')
for i in range(1, 6):
    path = os.path.join(BASE, 'corpus', 'segmented', f'{i}.json')
    with open(path, encoding='utf-8') as f:
        d = json.load(f)
    m = d['metadata']
    s = d['sections']
    q = d['quality']
    l = d['labels']
    print(f'\n--- Doc {i} ---')
    print(f'  court        : {m.get("court")}')
    print(f'  year         : {m.get("year")}')
    print(f'  case_type    : {m.get("case_type")}')
    print(f'  jurisdiction : {m.get("jurisdiction")}')
    print(f'  case_number  : {m.get("case_number")}')
    print(f'  ipc_sections : {m.get("ipc_sections")}')
    print(f'  doc_type     : {m.get("document_type")}')
    print(f'  outcome      : {l.get("outcome_normalized")}')
    print(f'  confidence   : {q.get("segmentation_confidence")}')
    print(f'  has_result   : {q.get("has_result_section")}')
    print(f'  sections     : {q.get("body_sections_filled")}/4')
    print(f'  citations    : {len(d.get("cited_cases", []))}')
    print(f'  header len   : {len(s.get("header",""))} chars')
    print(f'  facts len    : {len(s.get("facts",""))} chars')
    print(f'  pet_args len : {len(s.get("petitioner_arguments",""))} chars')
    print(f'  res_args len : {len(s.get("respondent_arguments",""))} chars')
    print(f'  judge_sum len: {len(s.get("judges_summary",""))} chars')
    result_preview = s.get("case_result","")[:150].strip()
    print(f'  case_result  : {repr(result_preview)}')
