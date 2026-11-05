import json, sys
sys.stdout.reconfigure(encoding='utf-8')
from exc import EXC
S = json.load(open('stats.json', encoding='utf-8'))['glyphs']; order = json.load(open('order.json'))
EYE_MAX = 840                                   # glyphs with idx < this were checked by eye
out = {}; src = {'eye': 0, 'vote': 0, 'junk': 0, 'unk': 0}
for i, h in enumerate(order):
    g = S[h]; top, n = g['orig'][0]; share = n / sum(c for _, c in g['orig'])
    if i in EXC:
        lab = EXC[i]; s = 'junk' if lab is None else 'eye'
    elif i < EYE_MAX:
        lab = None if top == '<MISSING>' else top; s = 'eye'     # checked by eye, PDF's own label was right
    elif top != '<MISSING>' and share >= 0.9 and g['docs'] >= 3:
        lab = top; s = 'vote'
    else:
        lab = None; s = 'junk' if g['docs'] < 10 else 'unk'
    src[s] += 1
    out[h] = {'u': lab, 'src': s, 'docs': g['docs'], 'use': g['use']}
json.dump(out, open('glyph_map.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
print(src); print("labelled by eye:", src['eye'], "of", len(order))
unl = [(i, S[order[i]]['docs'], S[order[i]]['use']) for i, h in enumerate(order) if out[h]['u'] is None and out[h]['src'] in ('unk',)]
print("unlabelled with docs>=10:", unl[:30])
