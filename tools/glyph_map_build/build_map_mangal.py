import json, sys
sys.stdout.reconfigure(encoding='utf-8')
from exc3 import EXC3
S = json.load(open('stats3.json', encoding='utf-8'))['glyphs']; order = json.load(open('order3.json'))
dst = r"C:\Users\Aryan\OneDrive\Desktop\internship\marathi-legal-document\glyph_map.json"
M = json.load(open(dst, encoding='utf-8')); EYE_MAX = 320; n = {'eye': 0, 'vote': 0, 'junk': 0}; overlap = 0
miss = [i for i in range(EYE_MAX) if S[order[i]]['orig'][0][0] == '<MISSING>' and i not in EXC3]
print("MISSING without label (idx<320):", miss)
for i, h in enumerate(order):
    g = S[h]; top, c = g['orig'][0]; share = c / sum(x for _, x in g['orig'])
    if i in EXC3: lab, s = EXC3[i], 'eye'
    elif i < EYE_MAX: lab, s = (None if top == '<MISSING>' else top), 'eye'
    elif top != '<MISSING>' and share >= 0.9 and g['docs'] >= 3: lab, s = top, 'vote'
    else: lab, s = None, 'junk'
    n[s] += 1
    if h in M: overlap += 1; continue
    M[h] = {'u': lab, 'src': s, 'docs': g['docs'], 'use': g['use']}
print("mangal:", n, "overlap:", overlap, "map entries:", len(M))
json.dump(M, open(dst, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
