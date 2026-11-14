#!/usr/bin/env python3
"""Build the Control Room data model (data/model.json) from the raw pulls in data/.

Revenue basis: Shopify TOTAL SALES (gross - discounts - returns + shipping + taxes), as Ryan asked (10 Nov 2026).
The PRM daily target is on a net basis, so it is moved onto the total basis with this year's
last-28-day total/net ratio. MER stays Shopify net / paid spend (measurement rule).

Inputs (data/):
  shopify_raw.json   first pull: LY net/gross/orders + funnel by hour (Oct 26 2025 - Jan 3 2026), products (P), lyDisc
  shopify_raw2.json  latest pull: today hourly total/net/gross/discounts/returns/orders, funnel, new vs returning,
                     LY hourly total_sales, utm_medium sessions (today + same day last week), product x hour, 28-day ratio, imgs
  google.json, meta.json, prm.json, spend_plan.json, snapshot.json, markers.json
Usage: compute.py [YYYY-MM-DD]
"""
import json, sys, datetime as dt
from zoneinfo import ZoneInfo
from pathlib import Path

D = Path(__file__).resolve().parent.parent / 'data'
TZ = ZoneInfo('America/Vancouver')
J = lambda n: json.load(open(D / n))
num = lambda x: float(x) if x not in (None, '') else 0.0

r1 = J('shopify_raw.json'); r2 = J('shopify_raw2.json'); r3 = J('shopify_raw3.json') if (D / 'shopify_raw3.json').exists() else {}
pulled = dt.datetime.fromisoformat(r2['pulled'].replace('Z', '+00:00')).astimezone(TZ)
today = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else pulled.date()
ly_day = today - dt.timedelta(days=364)
lw_day = today - dt.timedelta(days=7)
NOW = pulled.hour; DONE = NOW
MIN = pulled.minute

def loc(label):
    t = dt.datetime.fromisoformat(label.replace('Z', '+00:00')).astimezone(TZ)
    return t.date(), t.hour

def by_hour(pack, day, cols, key_col=None, key=None):
    c = pack['c']; out = {k: [0.0] * 24 for k in cols}
    for r in pack['r']:
        d, h = loc(r[0])
        if d != day: continue
        if key_col is not None and r[c.index(key_col)] != key: continue
        for k in cols: out[k][h] += num(r[c.index(k)])
    return out

def rows_by_hour(rows, day, idx):
    out = [0.0] * 24
    for r in rows:
        d, h = loc(r[0])
        if d == day: out[h] += num(r[idx])
    return out

def cum(a):
    o, t = [], 0.0
    for x in a: t += x; o.append(t)
    return o

def mono_share(a):
    """cumulative share made non-decreasing (net/total hours can be negative when returns post)"""
    c, t, m = [], 0.0, 0.0
    for x in a: t += x; m = max(m, t); c.append(m)
    end = c[-1] or 1
    c = [x / end for x in c]
    return [c[0]] + [c[i] - c[i - 1] for i in range(1, 24)], c

# ---------- today
S = by_hour(r2['tdT'], today, ['total_sales', 'net_sales', 'gross_sales', 'discounts', 'returns', 'orders'])
F = by_hour(r2['tdFn'], today, ['sessions', 'sessions_with_cart_additions', 'sessions_that_reached_checkout', 'sessions_that_completed_checkout'])
FK = {'sessions': 'sessions', 'atc': 'sessions_with_cart_additions', 'rc': 'sessions_that_reached_checkout', 'cc': 'sessions_that_completed_checkout'}

# ---------- last year (364 days back)
LY = {
    'total': rows_by_hour(r2['lyT'], ly_day, 1),
    'disc': rows_by_hour(r2['lyT'], ly_day, 2),
    'net': rows_by_hour(r1['lyS'], ly_day, 1),
    'gross': rows_by_hour(r1['lyS'], ly_day, 2),
    'orders': rows_by_hour(r1['lyS'], ly_day, 3),
    'sessions': rows_by_hour(r1['lyF'], ly_day, 1),
    'atc': rows_by_hour(r1['lyF'], ly_day, 2),
    'rc': rows_by_hour(r1['lyF'], ly_day, 3),
    'cc': rows_by_hour(r1['lyF'], ly_day, 4),
}

# ---------- targets
prm = J('prm.json'); pk = {r['date']: r for r in prm['peak_days']}; p = pk.get(today.isoformat(), {})
ratio = r2['ratio28'][0] / r2['ratio28'][1]                     # total / net, last 28 days this year
target_net = num(p.get('plan_net'))
target_day = target_net * ratio
shape, shape_c = mono_share(LY['total'])
target_h = [target_day * s for s in shape]

# funnel day targets: sessions and completed checkouts from the PRM plan; the two middle steps
# keep last year's proportions, scaled evenly so the steps multiply out to the planned conversion
ly_tot = {k: sum(LY[k]) for k in FK}
plan_s, plan_c = num(p.get('plan_sessions')), num(p.get('plan_chk'))
lr = [ly_tot['atc'] / ly_tot['sessions'], ly_tot['rc'] / ly_tot['atc'], ly_tot['cc'] / ly_tot['rc']]
f = ((plan_c / plan_s) / (lr[0] * lr[1] * lr[2])) ** (1 / 3) if plan_s and plan_c else 1
fun_day = {'sessions': plan_s}
fun_day['atc'] = fun_day['sessions'] * lr[0] * f
fun_day['rc'] = fun_day['atc'] * lr[1] * f
fun_day['cc'] = fun_day['rc'] * lr[2] * f
fun_target_sofar = {k: fun_day[k] * cum([x / (ly_tot[k] or 1) for x in LY[k]])[DONE - 1] for k in FK}

# ---------- forecast (total basis): completed hours / LY share of the day done by then
tot_c = cum(S['total_sales'])
def pred_at(h):           # prediction made with hours 0..h-1 complete
    if h < 4: return None
    sh = shape_c[h - 1]
    return tot_c[h - 1] / sh if sh > .03 else None
pred = pred_at(DONE) or target_day
pred_path = [{'h': h, 'v': round(pred_at(h), 2)} for h in range(4, DONE + 1) if pred_at(h)]
need_rest = max(0, target_day - tot_c[NOW]) / max(1, 24 - NOW - MIN / 60)

# ---------- spend
g = J('google.json'); m = J('meta.json'); plan = J('spend_plan.json').get(today.isoformat(), {})
pad = lambda a: (list(a) + [0] * 24)[:24]
G, Mt, LG, LM = pad(g['today']), pad(m['today']), pad(g['ly']), pad(m['ly'])
fixed_day = (plan.get('shop') or 0) + (plan.get('pinterest') or 0)
budget_day = plan.get('working') or plan.get('base') or 0
var_budget = max(0, budget_day - fixed_day)
gb, mb = plan.get('google') or 0, plan.get('meta') or 0
budget_g = var_budget * gb / ((gb + mb) or 1); budget_m = var_budget - budget_g
frac = (NOW + MIN / 60) / 24
fixed_now = fixed_day * frac
ly_sp = [a + b for a, b in zip(LG, LM)]
def share_c(a):
    t = sum(a) or 1; return cum([x / t for x in a])
g_done = sum(G[:DONE]); m_done = sum(Mt[:DONE])
def sp_fc(done, ly):  # forecast a channel with last year's hourly spend shape
    sh = share_c(ly)[DONE - 1]
    return done / sh if sh > .05 else done
fc_g, fc_m = sp_fc(g_done, LG), sp_fc(m_done, LM)
spend_so_far = sum(G) + sum(Mt) + fixed_now
spend_fc = fc_g + fc_m + fixed_day
net_so_far = sum(S['net_sales'])
net_fc = pred / ratio

# ---------- KPIs over completed hours, today vs LY
H = DONE
# today so far (incl. the hour in progress) vs last year to the same minute
st = lambda a: sum(a[:NOW + 1])
sl = lambda a: sum(a[:NOW]) + a[NOW] * MIN / 60
K = {
    'total': [st(S['total_sales']), sl(LY['total'])], 'net': [st(S['net_sales']), sl(LY['net'])],
    'gross': [st(S['gross_sales']), sl(LY['gross'])], 'orders': [st(S['orders']), sl(LY['orders'])],
    'disc': [st(S['discounts']), sl(r1.get('lyDisc', [0] * 24))],
    'sessions': [st(F['sessions']), sl(LY['sessions'])], 'atc': [st(F['sessions_with_cart_additions']), sl(LY['atc'])],
    'rc': [st(F['sessions_that_reached_checkout']), sl(LY['rc'])], 'cc': [st(F['sessions_that_completed_checkout']), sl(LY['cc'])],
    'spend': [st(G) + st(Mt), sl(ly_sp)],
}
K['aov'] = [(K['gross'][i] + K['disc'][i]) / K['orders'][i] if K['orders'][i] else 0 for i in (0, 1)]

def nr(pack, day):
    o = {'New': [0, 0, 0], 'Returning': [0, 0, 0]}
    c = pack['c']
    for r in pack['r']:
        d, h = loc(r[0])
        if d != day or h >= H: continue
        k = r[c.index('new_or_returning_customer')]
        if k in o:
            o[k][0] += num(r[c.index('total_sales')]); o[k][1] += num(r[c.index('net_sales')]); o[k][2] += num(r[c.index('orders')])
    return o
NR = {'today': nr(r2['tdNR2'], today), 'ly': nr(r2['lyNR2'], ly_day)}

# ---------- products: today's totals from product x hour, titles / stock / last week from the first pull
meta = {str(x[0]): x for x in r1['P']}
agg = {}
for r in r2['pH']['r']:
    d, h = loc(r[1])
    if d != today: continue
    a = agg.setdefault(str(r[0]), {'total': 0, 'gross': 0, 'units': 0, 'hours': [0.0] * 24})
    a['total'] += num(r[2]); a['gross'] += num(r[3]); a['units'] += num(r[4]); a['hours'][h] += num(r[3])
imgs = r2.get('imgs', {})
# last year's sales per product over the same part of the day (completed hours + the share of the current hour)
lyp = {}
for r in r3.get('lyPH', {}).get('r', []):
    d, h = loc(r[1])
    if d != ly_day or h > NOW: continue
    w_ = MIN / 60 if h == NOW else 1
    lyp[str(r[0])] = lyp.get(str(r[0]), 0) + num(r[2]) * w_
lyh = {}
for r in r3.get('lyPH', {}).get('r', []):
    d, h = loc(r[1])
    if d == ly_day: lyh.setdefault(str(r[0]), [0.0] * 24)[h] += num(r[2])
import re
LP = {}
lpk = r2.get('lp') or {}
if lpk.get('c'):
    ci = {k: lpk['c'].index(k) for k in lpk['c']}
    for r in lpk['r']:
        m_ = re.search(r'/products/([^/?#]+)', str(r[ci['landing_page_path']] or ''))
        if not m_: continue
        a_ = LP.setdefault(m_.group(1).lower(), [0, 0, 0, 0])
        for i_, k in enumerate(['sessions', 'sessions_with_cart_additions', 'sessions_that_reached_checkout', 'sessions_that_completed_checkout']):
            a_[i_] += num(r[ci[k]])
P = []
for pid, a in agg.items():
    x = meta.get(pid)
    if not x: continue
    _, t, net, gross0, units0, orders, lw, lwu, inv, handle, img = x
    stock = None
    if inv is not None:
        stock = 'out' if inv <= 0 else ('low' if inv < 15 or inv < 3 * max(a['units'], 0) else None)
    P.append({'id': pid, 't': t, 'gross': round(a['gross'], 2), 'total': round(a['total'], 2), 'units': int(a['units']),
              'ly': round(lyp.get(pid, 0), 2), 'inv': inv, 'h': handle, 'img': imgs.get(pid) or '', 'stock': stock, 'hours': [round(v, 2) for v in a['hours']],
              'lyh': [round(v, 2) for v in lyh.get(pid, [0.0] * 24)], 'lp': LP.get((handle or '').lower())})
P.sort(key=lambda p: -p['gross'])
top = P[:10]
# trending: today so far vs the average of the previous 7 days to the same time of day (Ryan, 10 Nov 2026)
p7 = J('p7.json')['p7'] if (D / 'p7.json').exists() else {}
for q in P:
    q['avg7'] = round((p7.get(q['id']) or [0, 0])[0], 2)
RULES = {'min_units': 2, 'min_sales': 300, 'min_avg7': 150}
tr = [dict(q, g=q['gross'] / q['avg7'] - 1) for q in P if q['units'] >= RULES['min_units'] and q['gross'] >= RULES['min_sales'] and q['avg7'] >= RULES['min_avg7']]
trending = sorted([q for q in tr if q['g'] > 0], key=lambda q: -q['g'])[:10]
if len(trending) < 10:   # always show 10: fill with sellers that had (almost) nothing in the last 7 days
    seen = {q['id'] for q in trending}
    fill = [dict(q, g=None) for q in P if q['id'] not in seen and q['avg7'] < RULES['min_avg7'] and q['gross'] >= RULES['min_sales'] and q['units'] >= RULES['min_units']]
    trending += sorted(fill, key=lambda q: -q['gross'])[:10 - len(trending)]
new_in = [q for q in P if not q['ly'] and q['gross'] >= RULES['min_sales'] and q['units'] >= RULES['min_units']][:5]

# ---------- channel sessions (utm_medium) today and same day last week
def utm(pack, day):
    o = {}
    c = pack['c']
    for r in pack['r']:
        d, h = loc(r[0])
        if d != day: continue
        k = r[c.index('utm_medium')] or 'none'
        o.setdefault(k, [0.0] * 24)[h] += num(r[c.index('sessions')])
    return o
U, UW = utm(r2['utmT'], today), (utm(r3['utmL'], ly_day) if r3.get('utmL') else utm(r2['utmW'], lw_day))

# ---------- ticker: observations for the last full hour, ranked by how far they move
lh = DONE - 1
hl = lambda h: (f"{h % 12 or 12}{'am' if h < 12 else 'pm'}")
obs = []
def pc(a, b): return (a / b - 1) if b else None
em_d, em_w = sum(U.get('email', [0])[:H]), sum(UW.get('email', [0])[:H])
if em_w:
    d = pc(em_d, em_w); obs.append({'k': 'Email', 'txt': f"Email traffic {'up' if d >= 0 else 'down'} {abs(d):.0%} vs LY: {int(em_d):,} sessions so far", 'w': abs(d), 'tone': 'up' if d >= 0 else 'down'})
sms_d, sms_w = sum(U.get('sms', [0])[:H]), sum(UW.get('sms', [0])[:H])
if sms_w:
    d = pc(sms_d, sms_w); obs.append({'k': 'SMS', 'txt': f"SMS traffic {'up' if d >= 0 else 'down'} {abs(d):.0%} vs LY", 'w': abs(d) * .8, 'tone': 'up' if d >= 0 else 'down'})
paid_d = sum(U.get('cpc', [0])[:H]) + sum(U.get('cpm', [0])[:H]); paid_w = sum(UW.get('cpc', [0])[:H]) + sum(UW.get('cpm', [0])[:H])
if paid_w:
    d = pc(paid_d, paid_w); obs.append({'k': 'Paid', 'txt': f"Paid traffic {'up' if d >= 0 else 'down'} {abs(d):.0%} vs LY ({int(paid_d):,} sessions)", 'w': abs(d) * .7, 'tone': 'up' if d >= 0 else 'down'})
best = max(P, key=lambda q: q['hours'][lh]) if P else None
if best and best['hours'][lh] > 0:
    hour_tot = sum(q['hours'][lh] for q in P) or 1
    obs.append({'k': 'Product', 'txt': f"{best['t'].split(' / ')[0]} led the {hl(lh)} hour: ${best['hours'][lh]:,.0f}, {best['hours'][lh] / hour_tot:.0%} of the hour's sales", 'w': .5, 'tone': 'up', 'img': best['img']})
if trending and trending[0]['g'] is not None:
    q = trending[0]; obs.append({'k': 'Trending', 'txt': f"{q['t'].split(' / ')[0]} up {q['g']:.0%} on its 7-day average", 'w': min(1, q['g']), 'tone': 'up', 'img': q['img']})
cvr_h, cvr_ly = (F['sessions_that_completed_checkout'][lh] / F['sessions'][lh] if F['sessions'][lh] else 0), (LY['cc'][lh] / LY['sessions'][lh] if LY['sessions'][lh] else 0)
if cvr_ly:
    d = (cvr_h - cvr_ly) * 100; obs.append({'k': 'Conversion', 'txt': f"Conversion {cvr_h:.2%} in the {hl(lh)} hour, {abs(d):.2f} pts {'above' if d >= 0 else 'below'} last year", 'w': abs(d) / 0.5, 'tone': 'up' if d >= 0 else 'down'})
gap_now = tot_c[NOW] - (sum(target_h[:NOW]) + target_h[NOW] * MIN / 60)
obs.append({'k': 'Pace', 'txt': f"${abs(gap_now):,.0f} {'ahead of' if gap_now >= 0 else 'behind'} target. Rest of day needs ${need_rest:,.0f} an hour (last year ran ${sum(LY['total'][NOW:]) / max(1, 24 - NOW):,.0f})", 'w': .9, 'tone': 'up' if gap_now >= 0 else 'down'})
outs = [q for q in P[:40] if q['stock'] == 'out']
if outs:
    q = outs[0]; obs.append({'k': 'Stock', 'txt': f"{q['t'].split(' / ')[0]} is out of stock after ${q['gross']:,.0f} today", 'w': .85, 'tone': 'down', 'img': q['img']})
must = [o for o in obs if o['k'] in ('Pace', 'Email')]
rest = sorted([o for o in obs if o['k'] not in ('Pace', 'Email')], key=lambda o: -o['w'])
ticker = must + rest[:5 - len(must)]

# ---------- chart annotations: sends + hours that moved far from target
markers = J('markers.json') if (D / 'markers.json').exists() else {'today': []}
notes = [{'h': x['h'] + x.get('m', 0) / 60, 'label': f"{x.get('kind', 'Send')}: {x['name']}", 'type': 'send'} for x in markers.get('today', [])]
for h in range(H):
    t = target_h[h]; a = S['total_sales'][h]
    if t > 1500 and a < .55 * t and S['gross_sales'][h] >= .8 * LY['gross'][h]:
        notes.append({'h': h + .5, 'label': f"Returns hit {hl(h)}", 'type': 'alert'})
    elif t > 1500 and a > 1.6 * t:
        notes.append({'h': h + .5, 'label': f"Spike {hl(h)}: ${a:,.0f}", 'type': 'good'})
sends = [n for n in notes if n['type'] == 'send']
flags = [n for n in notes if n['type'] != 'send']
alerts = [n for n in flags if n['type'] == 'alert'][-2:] + [n for n in flags if n['type'] == 'good'][-1:]
notes = sorted(sends + alerts, key=lambda n: n['h'])

# ---------- hour drill-down (click an hour on the revenue chart): top sellers, new vs returning, by hour
hourtop = []
for h in range(NOW + 1):
    items = sorted(((pid, a['hours'][h]) for pid, a in agg.items() if a['hours'][h] > 0), key=lambda x: -x[1])[:8]
    row = []
    for pid, g_ in items:
        x = meta.get(pid)
        row.append({'id': pid, 't': x[1] if x else f'Product {pid}', 'img': (x[10] if x else '') or '', 'h': x[9] if x else '', 'g': round(g_, 2)})
    hourtop.append(row)
units_h = {}
for r in r2['pH']['r']:
    d, h = loc(r[1])
    if d == today: units_h[(str(r[0]), h)] = units_h.get((str(r[0]), h), 0) + num(r[4])
for h, row in enumerate(hourtop):
    for it in row: it['u'] = int(units_h.get((it['id'], h), 0))
def nr_h(pack, day):
    o = {'New': [0.0] * 24, 'Returning': [0.0] * 24, 'New_o': [0.0] * 24, 'Returning_o': [0.0] * 24}
    c = pack['c']
    for r in pack['r']:
        d, h = loc(r[0])
        k = r[c.index('new_or_returning_customer')]
        if d != day or k not in ('New', 'Returning'): continue
        o[k][h] += num(r[c.index('total_sales')]); o[k + '_o'][h] += num(r[c.index('orders')])
    return {k: R2_(v) for k, v in o.items()}
R2_ = lambda a: [round(x, 2) for x in a]
NRH = {'today': nr_h(r2['tdNR2'], today), 'ly': nr_h(r2['lyNR2'], ly_day)}
# new vs returning by hour: customers, orders, gross, discounts, total sales (Ryan, 13 Nov 2026: customer counts on the card,
# and a New & returning split on the Revenue, Orders and AOV drill-downs)
def nr3(pack, day):
    keys = ['customers', 'orders', 'gross_sales', 'discounts', 'total_sales']
    o = {s: {k: [0.0] * 24 for k in keys} for s in ('New', 'Returning')}
    if not pack or not pack.get('c'): return None
    c = pack['c']
    for r in pack['r']:
        d, h = loc(r[0])
        s_ = r[c.index('new_or_returning_customer')]
        if d != day or s_ not in o: continue
        for k in keys: o[s_][k][h] += num(r[c.index(k)])
    return {s_: {k: R2_(v) for k, v in m.items()} for s_, m in o.items()}
NR3 = {'today': nr3(r2.get('tdNR3'), today), 'ly': nr3(r3.get('lyNR3'), ly_day)}

# ---------- funnel split by device and traffic source (click a funnel step), today vs LY to the same minute
FSK = ['sessions', 'sessions_with_cart_additions', 'sessions_that_reached_checkout', 'sessions_that_completed_checkout']
def fsplit(pack, day, dim, ly=False):
    o = {}
    if not pack or not pack.get('c'): return o
    c = pack['c']
    for r in pack['r']:
        d, h = loc(r[0])
        if d != day or h > NOW: continue
        w_ = (MIN / 60 if (ly and h == NOW) else 1)
        k = r[c.index(dim)] or 'unknown'
        a_ = o.setdefault(k, [0.0, 0.0, 0.0, 0.0])
        for i_, kk in enumerate(FSK): a_[i_] += num(r[c.index(kk)]) * w_
    return {k: [round(v) for v in a_] for k, a_ in o.items()}
FSPLIT = {'dev': {'today': fsplit(r2.get('fdev'), today, 'session_device_type'), 'ly': fsplit(r3.get('fdevL'), ly_day, 'session_device_type', True)},
          'ref': {'today': fsplit(r2.get('fref'), today, 'referrer_source'), 'ly': fsplit(r3.get('frefL'), ly_day, 'referrer_source', True)}}

# ---------- spend channel drill-down: campaigns + hourly conversion value (ROAS by hour)
CA = J('campaigns.json') if (D / 'campaigns.json').exists() else {}
def dif(c_):
    c_ = [x for x in (c_ or [])]; o, prev = [], 0.0
    for v in c_[:24]:
        if v is None: o.append(None); continue
        o.append(round(v - prev, 2)); prev = v
    return (o + [None] * 24)[:24]
CAMP = {'google': CA.get('google', []), 'meta': CA.get('meta', []), 'updated': CA.get('updated'),
        'gv': dif(CA.get('g_value_cum')), 'gvl': dif(CA.get('g_value_ly_cum')),
        'mv': [round(num(x), 2) for x in (m.get('today_value') or [])], 'mvl': [round(num(x), 2) for x in (m.get('ly_value') or [])]}

# ---------- ticker: where each item jumps to when clicked
listed = {q['id'] for q in top + trending}; extra = []
for t_ in ticker:
    k = t_['k']
    if k in ('Product', 'Trending', 'Stock'):
        pid = next((q['id'] for q in P if t_['txt'].startswith(q['t'].split(' / ')[0])), None)
        t_['go'] = f'p:{pid}' if pid else 'products'
        if pid and pid not in listed and pid not in {q['id'] for q in extra}: extra.append(next(q for q in P if q['id'] == pid))
    elif k == 'Pace': t_['go'] = 'rev'
    elif k == 'Conversion': t_['go'] = 'funnel'
    elif k in ('Email', 'SMS'): t_['go'] = 'funnel:ref'
    elif k == 'Paid': t_['go'] = 'spend'

snap = J('snapshot.json') if (D / 'snapshot.json').exists() else None
gw = prm['gap_windows']; w = next((x for x in gw if x['window'].startswith('Last 90')), gw[0])
jr = num(w['jesta']) / num(w['shopify_net'])
R2 = lambda a: [round(x, 2) for x in a]
model = {
    'date': today.isoformat(), 'ly_date': ly_day.isoformat(), 'lw_date': lw_day.isoformat(),
    'pulled': pulled.strftime('%Y-%m-%d %H:%M'), 'now_h': NOW, 'now_m': MIN, 'done_h': DONE,
    'peak': [w for w in (json.loads((D / 'peak.json').read_text()).get('windows', []) if (D / 'peak.json').exists() else []) if w.get('date') == today.isoformat()],
    'phase': next((x['phase'] for x in prm['day_shape'] if x['date'] == today.isoformat()), ''),
    'ratio': round(ratio, 4), 'target_net': round(target_net, 2), 'target_day': round(target_day, 2),
    'ly_total_day': round(sum(LY['total']), 2),
    'pred': round(pred, 2), 'pred_path': pred_path, 'need_rest': round(need_rest, 2),
    'prm_forecast_total': round(num(p.get('net_o')) * ratio, 2),
    'hours': {'total': R2(S['total_sales']), 'net': R2(S['net_sales']), 'gross': R2(S['gross_sales']), 'returns': R2(S['returns']),
              'disc': R2(S['discounts']), 'orders': S['orders'], 'target': R2(target_h),
              'ly_total': R2(LY['total']), 'ly_net': R2(LY['net']), 'ly_orders': LY['orders'],
              'sessions': F['sessions'], 'atc': F['sessions_with_cart_additions'], 'rc': F['sessions_that_reached_checkout'], 'cc': F['sessions_that_completed_checkout'],
              'ly_sessions': LY['sessions'], 'ly_atc': LY['atc'], 'ly_rc': LY['rc'], 'ly_cc': LY['cc'],
              'google': R2(G), 'meta': R2(Mt), 'ly_google': R2(LG), 'ly_meta': R2(LM)},
    'kpi': K, 'nr': NR,
    'funnel': {'day': {k: round(v) for k, v in fun_day.items()}, 'sofar': {k: round(v) for k, v in fun_target_sofar.items()}},
    'spend': {'budget_day': budget_day, 'budget_g': round(budget_g, 2), 'budget_m': round(budget_m, 2), 'fixed_day': fixed_day,
              'fixed_now': round(fixed_now, 2), 'so_far': round(spend_so_far, 2), 'forecast': round(spend_fc, 2),
              'g_so_far': round(sum(G), 2), 'm_so_far': round(sum(Mt), 2), 'fc_g': round(fc_g, 2), 'fc_m': round(fc_m, 2),
              'day_type': plan.get('type'), 'google_updated': g.get('updated_at'), 'meta_updated': m.get('pulled')},
    # MER = Shopify TOTAL sales / paid spend (Ryan, 10 Nov 2026), not net
    'mer': {'live': round(tot_c[NOW] / spend_so_far, 2) if spend_so_far else None, 'forecast': round(pred / spend_fc, 2) if spend_fc else None,
            'ly': round(K['total'][1] / K['spend'][1], 2) if K['spend'][1] else None, 'floor': 16, 'rev_so_far': round(tot_c[NOW], 2)},
    'jesta': {'ratio': round(jr, 4), 'window': w['window'], 'expected': round(net_fc * jr, 2), 'status': 'TBC'},
    'products': {'top': top, 'trending': trending, 'extra': extra, 'new': [q['t'] for q in new_in], 'rules': RULES},
    'utm': {'today': {k: R2(v) for k, v in U.items()}, 'ly': {k: R2(v) for k, v in UW.items()}},
    'ticker': ticker, 'notes': notes, 'snapshot': snap, 'lp_ok': bool(LP),
    'hourtop': hourtop, 'nrh': NRH, 'nr3': NR3, 'fsplit': FSPLIT, 'camp': CAMP,
}
json.dump(model, open(D / 'model.json', 'w'), separators=(',', ':'))
print(json.dumps({k: model[k] for k in ['pulled', 'target_day', 'pred', 'need_rest', 'ratio', 'funnel', 'mer', 'notes']}, indent=1))
print(json.dumps([t['txt'] for t in ticker], indent=1))
print('total so far', round(tot_c[NOW]), 'spend', model['spend']['so_far'], model['spend']['forecast'])
