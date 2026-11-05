import json, sys
sys.stdout.reconfigure(encoding='utf-8')
from exc4 import EXC4
G = json.load(open('stats4.json', encoding='utf-8'))['glyphs']; order = json.load(open('s4_order.json'))
p = "C:/Users/Aryan/OneDrive/Desktop/internship/marathi-legal-document/glyph_map.json"; M = json.load(open(p, encoding='utf-8'))
EYE = 240; n = {'eye': 0, 'vote': 0, 'junk': 0}; miss = []
for i, h in enumerate(order):
    g = G[h]; top, c = g['orig'][0]; share = c / sum(x for _, x in g['orig'])
    if i in EXC4: lab, s = EXC4[i], 'eye'
    elif top != '<MISSING>' and g['orig'][0][0] != '': lab, s = top, 'eye'            # checked by eye (all 240)
    else: lab, s = None, 'junk'; miss.append(i)
    n[s] += 1; M[h] = {'u': lab, 'src': s, 'docs': g['docs'], 'use': g['use']}
# glyphs beyond the checked range: trust the PDF label only if >=90% agree and seen in >=3 docs
rest = [h for h in G if h not in order and not (h in M and M[h]['u'] is not None)]
for h in rest:
    g = G[h]; top, c = g['orig'][0]; share = c / sum(x for _, x in g['orig'])
    if top != '<MISSING>' and share >= 0.9 and g['docs'] >= 3: M[h] = {'u': top, 'src': 'vote', 'docs': g['docs'], 'use': g['use']}; n['vote'] += 1
    elif h not in M: M[h] = {'u': None, 'src': 'junk', 'docs': g['docs'], 'use': g['use']}; n['junk'] += 1
# a stand-alone ि glyph is always the pre-base form (drawn before its consonant)
conv = 0
for h, e in M.items():
    if e['u'] == 'ि': e['u'] = I_; conv += 1
print("applied:", n, "| unlabeled inside reviewed range:", miss, "| bare ि -> pre-base:", conv, "| entries:", len(M))
json.dump(M, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
