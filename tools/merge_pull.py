#!/usr/bin/env python3
"""Merge a pull_today.js result (JSON file) into data/.
Today keys replace shopify_raw2.json; LY-day packs (lyNR2, lyPH, utmL) are appended to the caches for days not
already present; new product meta is appended to shopify_raw.json P; thumbnails merged into imgs; p7 written if present.
usage: python3 tools/merge_pull.py pull.json"""
import json, sys
from pathlib import Path
D = Path(__file__).resolve().parent.parent / 'data'
o = json.loads(Path(sys.argv[1]).read_text())
J = lambda n: json.loads((D / n).read_text())
W = lambda n, x: (D / n).write_text(json.dumps(x, separators=(',', ':')))
r1, r2, r3 = J('shopify_raw.json'), J('shopify_raw2.json'), J('shopify_raw3.json')

for k in ['tdT', 'tdFn', 'tdNR2', 'utmT', 'pH', 'ratio28']:
    r2[k] = o[k]
r2.setdefault('imgs', {}).update(o.get('imgs') or {})
r2['pulled'] = o['pulled']
r2['lp'] = o.get('lp')   # landing-page funnel today (None if the query failed)

def add(store, key, pack):
    if not pack: return
    cur = store.get(key)
    if not cur: store[key] = pack; return
    keys = {(r[0], r[1]) for r in cur['r']}   # (hour, key) or (product_id, hour)
    cur['r'] += [r for r in pack['r'] if (r[0], r[1]) not in keys]
add(r2, 'lyNR2', o.get('lyNR2'))
add(r3, 'lyPH', o.get('lyPH'))
add(r3, 'utmL', o.get('utmL'))

ids = {str(x[0]) for x in r1['P']}
r1['P'] += [p for p in o.get('newP') or [] if str(p[0]) not in ids]

W('shopify_raw.json', r1); W('shopify_raw2.json', r2); W('shopify_raw3.json', r3)
if o.get('p7'):
    W('p7.json', o['p7'])
print('merged', o['pulled'], 'P', len(r1['P']), 'imgs', len(r2['imgs']))
