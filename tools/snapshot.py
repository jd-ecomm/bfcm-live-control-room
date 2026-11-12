#!/usr/bin/env python3
"""Open Order Snapshot xlsx -> data/snapshot.json.  usage: python3 tools/snapshot.py file.xlsx "YYYY-MM-DD HH:MM" (email time, PT)"""
import json, sys
from pathlib import Path
import openpyxl
K = ['lt24', 'd1_2', 'd2_3', 'gt3', 'hold', 'open', 'open_pct', 'value', 'ot_mtd', 'shipped_mtd', 'shipped_pct',
     'decl_pct', 'decl_mtd', 'decl_rate', 'shipped_today', 'ot_today', 'decl_today', 'days_complete']
wb = openpyxl.load_workbook(sys.argv[1], data_only=True)
def rows(ws):
    out = []
    for r in ws.iter_rows(min_row=4, values_only=True):
        if not r[0] or r[0] in ('Site', 'Region'): continue
        out.append(dict(name=str(r[0]).strip(), **{k: float(v or 0) for k, v in zip(K, r[1:19])}))
    return out
regions = rows(wb['Detail'])
sites = [s for s in rows(wb['Master']) if not s['name'].endswith('Total')]
watch = sorted(sites, key=lambda s: (-s['gt3'], -s['open']))[:6]
D = Path(__file__).resolve().parent.parent / 'data'
REG = json.loads((D / 'stores.json').read_text())
for s in sites:
    code = s['name'].split('-')[0].strip()
    s['region'] = REG.get(code, 'Warehouse' if not code.isdigit() else 'Other')
(D / 'snapshot.json').write_text(json.dumps({'as_of': sys.argv[2], 'regions': regions, 'watch': watch, 'sites': sites}))
print('snapshot', sys.argv[2], [(r['name'], r['open']) for r in regions])
