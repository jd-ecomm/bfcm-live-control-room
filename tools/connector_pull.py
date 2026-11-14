#!/usr/bin/env python3
"""Shopify pull for the Control Room through the Shopify connector (cloud, no work PC). Added 13 Nov 2026.

Same ShopifyQL as tools/pull_today.js, sent as ONE aliased GraphQL call per pack through the connector's
graphql_query tool, so each answer is large enough to be saved to a tool-results file (never retyped).

  python3 tools/connector_pull.py plan                 -> which packs this run needs (JSON)
  python3 tools/connector_pull.py query today          -> {"query":..., "variables":...} for graphql_query
  python3 tools/connector_pull.py query p7             -> previous 7 days product x hour (first run of the day)
  python3 tools/connector_pull.py query lyfill         -> LY-day packs missing from the caches
  python3 tools/connector_pull.py query products --today <saved today file>   -> product titles + images
  python3 tools/connector_pull.py assemble --today F [--p7 F] [--lyfill F] [--products F] --out pull.json
then python3 tools/merge_pull.py pull.json as before.

A saved file is the tool-results file the connector call produced (a JSON list of {type,text}); a plain JSON
file holding the GraphQL answer also works. Hour labels are UTC, exactly as in the browser pull.
"""
import json, sys, argparse, datetime as dt
from pathlib import Path

D = Path(__file__).resolve().parent.parent / 'data'
PT = dt.timezone(dt.timedelta(hours=-7))          # Vancouver, UTC-7 all year since 1 Nov 2026
NOW = dt.datetime.now(PT)
TODAY = NOW.date()
LY = TODAY - dt.timedelta(days=364)
T = 'SINCE today UNTIL today'
NR3 = 'SHOW customers, orders, gross_sales, discounts, total_sales GROUP BY hour, new_or_returning_customer'   # 13 Nov 2026
FS = 'SHOW sessions, sessions_with_cart_additions, sessions_that_reached_checkout, sessions_that_completed_checkout'
J = lambda n: json.loads((D / n).read_text()) if (D / n).exists() else {}


def packs():
    L = f'SINCE {LY} UNTIL {LY}'
    today = {
        'tdT': f'FROM sales SHOW total_sales, net_sales, gross_sales, discounts, returns, orders GROUP BY hour {T} ORDER BY hour',
        'tdFn': f'FROM sessions {FS} GROUP BY hour {T} ORDER BY hour',
        'tdNR2': f'FROM sales SHOW total_sales, net_sales, orders GROUP BY hour, new_or_returning_customer {T} ORDER BY hour',
        'utmT': f'FROM sessions SHOW sessions GROUP BY hour, utm_medium {T} ORDER BY hour LIMIT 10000',
        'pH': f'FROM sales SHOW total_sales, gross_sales, net_items_sold GROUP BY product_id, hour {T} LIMIT 10000',
        'lp': f'FROM sessions {FS} GROUP BY landing_page_path {T} ORDER BY sessions DESC LIMIT 5000',
        'fdev': f'FROM sessions {FS} GROUP BY hour, session_device_type {T} ORDER BY hour LIMIT 1000',
        'fref': f'FROM sessions {FS} GROUP BY hour, referrer_source {T} ORDER BY hour LIMIT 1000',
        'rt': 'FROM sales SHOW total_sales, net_sales SINCE -28d UNTIL -1d',
        'tdNR3': f'FROM sales {NR3} {T} ORDER BY hour',
    }
    if plan()['lyFun']:
        today['fdevL'] = f'FROM sessions {FS} GROUP BY hour, session_device_type {L} ORDER BY hour LIMIT 1000'
        today['frefL'] = f'FROM sessions {FS} GROUP BY hour, referrer_source {L} ORDER BY hour LIMIT 1000'
    lyfill = {
        'lyNR2': f'FROM sales SHOW total_sales, net_sales, orders GROUP BY hour, new_or_returning_customer {L} ORDER BY hour',
        'lyPH': f'FROM sales SHOW gross_sales, net_items_sold GROUP BY product_id, hour {L} LIMIT 10000',
        'utmL': f'FROM sessions SHOW sessions GROUP BY hour, utm_medium {L} ORDER BY hour LIMIT 10000',
        'lyNR3': f'FROM sales {NR3} {L} ORDER BY hour',
    }
    p7 = {f'd{n}': f'FROM sales SHOW gross_sales GROUP BY product_id, hour SINCE {TODAY - dt.timedelta(days=n)} UNTIL {TODAY - dt.timedelta(days=n)} LIMIT 10000'
          for n in range(1, 8)}
    return {'today': today, 'lyfill': lyfill, 'p7': p7}


def has_day(pack, day):
    """True if a cached pack holds rows for the local day `day` (UTC hour labels, local = UTC-7)."""
    if not pack or not pack.get('r'):
        return False
    off = 8 if day < dt.date(2026, 11, 1) else 7   # last year Vancouver was on PST (UTC-8) in November
    lo = dt.datetime.combine(day, dt.time(off), dt.timezone.utc)
    hi = lo + dt.timedelta(days=1)
    for r in pack['r']:
        for v in r[:2]:
            try:
                t = dt.datetime.fromisoformat(str(v).replace('Z', '+00:00'))
                if t.tzinfo and lo <= t < hi:
                    return True
            except ValueError:
                pass
    return False


def peak(at=None):
    """Peak Mode window covering NOW (or `at`), from data/peak.json; None outside every window."""
    at = at or NOW
    try:
        ws = json.loads((Path(__file__).resolve().parent.parent / 'data' / 'peak.json').read_text()).get('windows', [])
    except Exception:
        return None
    hm = at.strftime('%H:%M')
    return next((w for w in ws if w.get('date') == str(at.date()) and w['from'] <= hm < w['to']), None)


def plan():
    r2, r3, p7 = J('shopify_raw2.json'), J('shopify_raw3.json'), J('p7.json')
    return {
        'today': str(TODAY), 'ly': str(LY), 'now': NOW.strftime('%H:%M'),
        'p7': not str(p7.get('cut', '')).endswith(str(TODAY - dt.timedelta(days=1))[5:]),
        'lyFill': not (has_day(r2.get('lyNR2'), LY) and has_day(r3.get('lyPH'), LY) and has_day(r3.get('utmL'), LY) and has_day(r3.get('lyNR3'), LY)),
        'lyFun': not has_day(r3.get('fdevL'), LY),
    }


def gql(aliases, pad=None):
    """One aliased shopifyqlQuery call. `pad` re-runs a big query so the answer always spills to a file."""
    items = dict(aliases)
    if pad:
        items['pad'] = pad
    names = list(items)
    head = ', '.join(f'${k}: String!' for k in names)
    body = ' '.join(f'{k}: shopifyqlQuery(query: ${k}) {{ tableData {{ columns {{ name }} rows }} parseErrors }}' for k in names)
    return {'query': f'query({head}) {{ {body} }}', 'variables': items}


def load(path):
    raw = json.loads(Path(path).read_text())
    if isinstance(raw, list):   # tool-results file: [{type, text}, ...]
        txt = next(x['text'] for x in raw if x.get('text', '').lstrip().startswith('{'))
        raw = json.loads(txt)
    if raw.get('errors'):
        raise SystemExit('GraphQL errors: ' + json.dumps(raw['errors'])[:500])
    return raw['data']


def table(d, k):
    x = d.get(k)
    if not x:
        return None
    if x.get('parseErrors'):
        raise SystemExit(f'ShopifyQL parse error in {k}: ' + json.dumps(x['parseErrors'])[:300])
    c = [col['name'] for col in x['tableData']['columns']]
    return {'c': c, 'r': [[row.get(n) for n in c] for row in x['tableData']['rows']]}


def product_ids(today_file):
    d = load(today_file)
    pH = table(d, 'pH')
    known = set(J('shopify_raw2.json').get('imgs', {}))
    named = {str(p[0]) for p in J('shopify_raw.json').get('P', [])}
    g, hb = {}, {}
    for pid, hour, tot, gross, units in pH['r']:
        g[pid] = g.get(pid, 0) + float(gross or 0)
        hb.setdefault(hour, {})[pid] = hb.get(hour, {}).get(pid, 0) + float(gross or 0)
    top = {pid for m in hb.values() for pid, _ in sorted(m.items(), key=lambda kv: -kv[1])[:8]}
    big = [pid for pid in g if g[pid] >= 300]
    want = [pid for pid in big if pid not in known] + [pid for pid in top if pid not in named and pid not in known]
    return [p for p in dict.fromkeys(want) if p][:120], g


def reduce_p7(d):
    cut_h = NOW.hour + NOW.minute / 60
    acc = {}
    days = []
    for n in range(1, 8):
        t = table(d, f'd{n}')
        days.append(str(TODAY - dt.timedelta(days=n)))
        for pid, hour, gross in t['r'] if t else []:
            h = (dt.datetime.fromisoformat(hour.replace('Z', '+00:00')).astimezone(PT)).hour
            v = float(gross or 0)
            part = v if h + 1 <= cut_h else (v * (cut_h - h) if h < cut_h else 0)
            a = acc.setdefault(pid, [0.0, 0.0])
            a[0] += part
            a[1] += v
    return {'p7': {k: [round(a / 7, 2), round(b / 7, 2)] for k, (a, b) in acc.items()},
            'cut': f'cut to {NOW.strftime("%H:%M")} local, avg of {min(days)}..{max(days)}'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd')
    ap.add_argument('which', nargs='?')
    for k in ('today', 'p7', 'lyfill', 'products', 'out'):
        ap.add_argument('--' + k)
    a = ap.parse_args()
    P = packs()
    if a.cmd == 'plan':
        print(json.dumps(plan()))
    elif a.cmd == 'peak':   # Peak Mode: {"active": bool, "window": {...}} for the quarter-hour runs
        w = peak()
        print(json.dumps({'active': bool(w), 'now': NOW.strftime('%Y-%m-%d %H:%M'), 'window': w}))
    elif a.cmd == 'query' and a.which in ('today', 'lyfill', 'p7'):
        pad = None if a.which == 'p7' else P['today']['pH']   # p7 and lyfill are big already; pad today so it spills
        print(json.dumps(gql(P[a.which], pad=pad if a.which == 'today' else None)))
    elif a.cmd == 'query' and a.which == 'products':
        ids, _ = product_ids(a.today)
        q = gql({'pad': P['today']['pH']})
        q['query'] = q['query'].replace('query($pad: String!) {',
            'query($pad: String!, $ids: [ID!]!) { nodes(ids: $ids) { ... on Product { id title handle totalInventory featuredMedia { preview { image { url } } } } }')
        q['variables']['ids'] = ['gid://shopify/Product/' + i for i in ids]
        print(json.dumps(q))
    elif a.cmd == 'assemble':
        d = load(a.today)
        o = {k: table(d, k) for k in ('tdT', 'tdFn', 'tdNR2', 'tdNR3', 'utmT', 'pH', 'lp', 'fdev', 'fref', 'fdevL', 'frefL')}
        o = {k: v for k, v in o.items() if v is not None}
        o['ratio28'] = [float(x) for x in table(d, 'rt')['r'][0]]
        if a.lyfill:
            dl = load(a.lyfill)
            for k in ('lyNR2', 'lyPH', 'utmL', 'lyNR3'):
                o[k] = table(dl, k)
        if a.p7:
            o['p7'] = reduce_p7(load(a.p7))
        o['newP'], o['imgs'] = [], {}
        if a.products:
            _, g = product_ids(a.today)
            for n in load(a.products).get('nodes') or []:
                if not n:
                    continue
                pid = n['id'].split('/')[-1]
                url = (((n.get('featuredMedia') or {}).get('preview') or {}).get('image') or {}).get('url') or ''
                import re
                sized = lambda s: re.sub(r'(\.[a-z]+)(\?|$)', rf'_{s}x\1\2', url, count=1, flags=re.I) if url else ''
                o['newP'].append([pid, n['title'], 0, 0, 0, 0, 0, 0, n.get('totalInventory'), n['handle'], sized(120)])
                if url and g.get(pid, 0) >= 300:
                    o['imgs'][pid] = sized(240)   # CDN link (the cloud cannot fetch images to embed them)
        o['pulled'] = dt.datetime.now(dt.timezone.utc).isoformat()
        Path(a.out).write_text(json.dumps(o, separators=(',', ':')))
        print(json.dumps({k: (len(v['r']) if isinstance(v, dict) and 'r' in v else (len(v) if hasattr(v, '__len__') else v))
                          for k, v in o.items() if k != 'pulled'}))
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
