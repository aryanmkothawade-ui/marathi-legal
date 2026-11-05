import json, sys
sys.stdout.reconfigure(encoding='utf-8')
tiro = json.load(open('glyph_map.json', encoding='utf-8'))
from exc2 import EXC2
S = json.load(open('stats2.json', encoding='utf-8'))['glyphs']; order = json.load(open('order2.json'))
EYE_MAX = 360; out = dict(tiro); n = {'eye': 0, 'vote': 0, 'junk': 0}; overlap = 0
for i, h in enumerate(order):
    g = S[h]; top, c = g['orig'][0]; share = c / sum(x for _, x in g['orig'])
    if i in EXC2: lab, s = EXC2[i], 'eye'
    elif i < EYE_MAX: lab, s = (None if top == '<MISSING>' else top), 'eye'
    elif top != '<MISSING>' and share >= 0.9 and g['docs'] >= 3: lab, s = top, 'vote'
    else: lab, s = None, 'junk'
    n[s] += 1
    if h in out: overlap += 1; continue
    out[h] = {'u': lab, 'src': s, 'docs': g['docs'], 'use': g['use']}
print("nirmala:", n, "overlap with tiro:", overlap, "total entries:", len(out))
dst = r"C:\Users\Aryan\OneDrive\Desktop\internship\marathi-legal-document\glyph_map.json"
json.dump(out, open(dst, 'w', encoding='utf-8'), ensure_ascii=False, indent=0); print("written", dst)
