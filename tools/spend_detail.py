#!/usr/bin/env python3
"""Campaign detail for the spend channel drill-down (Ryan, 12 Nov 2026: "click a spend channel to see its campaigns and hourly ROAS").

Inputs are saved connector results, unchanged:
  --pace   Google Sheets values of 'JD Ads - Intraday & Alerts' campaign_pace!A1:V200 (list of rows, header first)
  --dash   values of dash_campaigns!A1:S200 (for "Budget used today": "17% of $9,000")
  --curve  values of hourly_curve!A1:Y25 (needs hour, value_today, value_ly: Google conversion value, running totals)
  --meta   Meta ads_get_ad_entities ad_entities list: level campaign, date_preset today, fields
           id, name, amount_spent, omni_purchase_values, omni_purchase, purchase_roas, daily_budget, effective_status,
           filter amount_spent > 0, sort amount_spent_descending, limit 50
Writes data/campaigns.json. Any input left out keeps that part of the previous file.
usage: python3 tools/spend_detail.py --pace p.json --dash d.json --curve c.json --meta m.json --updated "YYYY-MM-DD HH:MM"
"""
import json, re, argparse
from pathlib import Path

D = Path(__file__).resolve().parent.parent / 'data'
ap = argparse.ArgumentParser()
for k in ('pace', 'dash', 'curve', 'meta', 'updated'): ap.add_argument('--' + k)
a = ap.parse_args()
out = json.loads((D / 'campaigns.json').read_text()) if (D / 'campaigns.json').exists() else {'google': [], 'meta': []}
f = lambda x: float(x) if x not in (None, '') else None
L = lambda p: json.loads(Path(p).read_text())
CH = {'SHOPPING': 'Shopping', 'SEARCH': 'Search', 'PERFORMANCE_MAX': 'Performance Max', 'DEMAND_GEN': 'Demand Gen', 'VIDEO': 'Video', 'DISPLAY': 'Display'}

if a.pace:
    rows = L(a.pace); h = rows[0]; ix = {k: h.index(k) for k in h}
    bud = {}
    if a.dash:
        dr = L(a.dash); dh = dr[0]; bi = dh.index('Budget used today')
        for r in dr[1:]:
            m = re.search(r'of \$([\d,\.]+)', r[bi] if len(r) > bi else '')
            if m: bud[r[0]] = float(m.group(1).replace(',', ''))
    g = []
    for r in rows[1:]:
        r = r + [''] * (len(h) - len(r)); v = lambda k: f(r[ix[k]])
        sp, sly = v('spend_today') or 0, v('spend_ly_today') or 0
        if not sp and not sly: continue
        g.append({'n': r[ix['campaign']], 'ch': CH.get(r[ix['channel']], r[ix['channel']].title()), 'sp': sp, 'roas': v('roas_today'),
                  'norm_sp': v('spend_normal_today'), 'norm_roas': v('roas_normal_today'), 'sp_ly': sly or None, 'roas_ly': v('roas_ly_today'),
                  'bud': bud.get(r[ix['campaign']]), 'thru': int(v('through_hour') or 0)})
    out['google'] = sorted(g, key=lambda x: -(x['sp'] or 0))
if a.curve:
    rows = L(a.curve); h = rows[0]
    vt, vl = h.index('value_today'), h.index('value_ly')
    out['g_value_cum'] = [f(r[vt]) if len(r) > vt else None for r in rows[1:25]]
    out['g_value_ly_cum'] = [f(r[vl]) if len(r) > vl else None for r in rows[1:25]]
if a.meta:
    m = []
    for e in L(a.meta):
        val = lambda k: f((e.get(k) or {}).get('value')) if isinstance(e.get(k), dict) else f(e.get(k))
        sp = val('amount_spent') or 0
        if not sp: continue
        rev = val('omni_purchase_values') or 0
        m.append({'n': e.get('name'), 'ch': 'Meta', 'sp': sp, 'roas': round(rev / sp, 2) if sp else None, 'rev': rev,
                  'buys': f(e.get('omni_purchase')), 'bud': val('daily_budget'), 'status': e.get('effective_status')})
    out['meta'] = sorted(m, key=lambda x: -x['sp'])
if a.updated: out['updated'] = a.updated
(D / 'campaigns.json').write_text(json.dumps(out, separators=(',', ':')))
print('campaigns.json: google', len(out.get('google', [])), 'meta', len(out.get('meta', [])))
