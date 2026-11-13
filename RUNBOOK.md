# JD Black Friday Control Room: build kit and runbook

Status (10 Nov 2026): built and approved as a Claude artifact ("JD Black Friday Control Room", v5). Not yet on GitHub and no hourly task yet; Ryan is rolling out to a GitHub repo with an hourly scheduled task on 11 Nov.

Files in the project: `claude/bfcm-control-room-template.html` (page template, model injected at `/*__MODEL__*/`), `claude/bfcm-control-room-compute.py` (builds data/model.json), `claude/bfcm-control-room-build.py` (injects model into the template -> out/index.html). Put them back as `src/template.html`, `tools/compute.py`, `tools/build.py`, with a `data/` folder.

## Decisions (Ryan, 10 Nov)
- Revenue basis = Shopify **total sales**. PRM daily target (net basis, `peak_days.plan_net`) x this year's last-28-day total/net ratio. Hourly target = day target split by last year's same-day (364 days back) cumulative total-sales curve, made non-decreasing.
- MER = Shopify total sales / paid spend (Google + Meta live, plus Shop + Pinterest daily lines pro-rated). Floor 16x.
- All comparisons say "vs LY" (364-day shift), never vs last week.
- Funnel = Shopify-style share of sessions (sessions, added to cart, reached checkout, completed checkout) with step pills and LY dashed outlines, emoji badges.
- Dashboard view (TV) = header + scrolling Live bar (5 observations) + 3 pace cards + 6 KPI cards + revenue pacing chart that alternates running total / per hour every 45s. Sized off `--u: min(1vw,1.7vh)`.
- Trending = today so far vs each product's average for the previous 7 days to the same time of day; rules 2+ units, $300+ today, $150+ 7-day average; fill to 10 with big sellers that had little in the last 7 days. Top 10 products still show vs LY.
- KPI row (orders, AOV, conversion, sessions, new customers) runs to the same minute as the revenue card, vs LY to the same minute. Total revenue appears once (pace card), not in the KPI row.
- Live tab: pace cards, clickable KPI drill-downs (Esc / click away / Close), revenue pacing, spend (Total/Google/Meta, line chart like revenue), MER, funnel, top 10 + trending 10 (vs LY; breakout sellers fill to 10), order fulfilment (Open Order Snapshot: open orders always with value, age bar, region table).
- JESTA: proxy only (predicted net x JESTA/Shopify ratio, PRM gap_windows "Last 90 days"); actual hourly JESTA TBC pending Ryan's MPRD report request.

## Data pulls each run (files in data/)
1. **Shopify** (built-in browser on Ryan's PC, admin.shopify.com/store/jdsports-ca/analytics): CSRF from `meta[name=csrf-token]`, POST `/store/jdsports-ca/admin/api/2025-10/graphql.json` `shopifyqlQuery`. Hour labels are UTC; convert with America/Vancouver (UTC-7 all year since 2026).
   - `shopify_raw2.json`: tdT (`FROM sales SHOW total_sales, net_sales, gross_sales, discounts, returns, orders GROUP BY hour SINCE today UNTIL today`), tdFn (sessions funnel by hour), tdNR2 (total/net/orders by hour, new_or_returning_customer), lyT (total_sales, discounts by hour for 2025-10-26..2026-01-03 in 14-day chunks, row cap 1000), utmT/utmW (sessions by hour, utm_medium), pH (product_id x hour today), lyNR2, ratio28 (`total_sales, net_sales SINCE -28d UNTIL -1d`), imgs (product thumbnails as data URIs, `_240x` Shopify CDN).
   - `shopify_raw.json`: lyS / lyF (LY net/gross/orders and funnel by hour, same range), P (product meta: id, title, net, gross, units, orders, lw, lwu, totalInventory, handle, img), lyDisc.
   - `shopify_raw3.json`: lyPH (product_id x hour on the LY day), utmL (utm_medium x hour on the LY day).
   - `p7.json`: product_id x hour for each of the previous 7 days (one query per day, LIMIT 10000), summed to the current local time of day, divided by 7.
   - Export from the page in <=240K-character slices (javascript_exec results save to a file when large).
2. **Google** `google.json`: sheet "JD Ads - Intraday & Alerts" (1Esg8PD8A36gBrjYdqFMf5Jsoa1IFejFK4PUrmBvD_6o), tab hourly_curve: spend_today cumulative -> hourly, spend_ly_hour, updated_at. Updates near the top of each hour.
3. **Meta** `meta.json`: JD_CANADA 1101395547052286, level ad_account, breakdown hourly_stats_aggregated_by_advertiser_time_zone, today and the LY date (fields amount_spent, omni_purchase_values). Keys: today (spend by hour), today_value (purchase value by hour), ly (spend by hour), ly_value (purchase value by hour on the LY date, null -> 0), ly_date, tz, pulled.
3b. **Campaign detail** `campaigns.json` (spend channel drill-down, added 12 Nov 2026). Save each connector result unchanged to a file, then run `python3 tools/spend_detail.py --pace pace.json --dash dash.json --curve curve.json --meta metac.json --updated "<NOW HH:MM>"`:
   - pace.json: Google Sheets get_values `campaign_pace!A1:V200` of 1Esg8PD8A36gBrjYdqFMf5Jsoa1IFejFK4PUrmBvD_6o (the `values` array).
   - dash.json: `dash_campaigns!A1:S200` (budget column "Budget used today").
   - curve.json: `hourly_curve!A1:Y25` (value_today / value_ly running totals, for Google ROAS by hour).
   - metac.json: Meta ads_get_ad_entities `ad_entities` list: level campaign, date_preset today, fields id, name, amount_spent, omni_purchase_values, omni_purchase, purchase_roas, daily_budget, effective_status; filter amount_spent GREATER_THAN 0; sort amount_spent_descending; limit 50.
   A failed part keeps the previous file's part; name it in the 'done' message.
4. **PRM** `prm.json`: peak_days, gap_windows, day_shape parsed from jd-ecomm/jd-revenue-model index.html.
5. **Spend plan** `spend_plan.json`: "Copy of JD Sports - BFCM Spend Planning" (15eiTzseJdeVC0HVzcRLrOUeyGWr-X4BAGy1oTgaEV9g), Daily Plan tab: working plan (col U), google/meta/shop/pinterest.
6. **Open orders** `snapshot.json`: latest "VCS_JDSF - Open Order Snapshot" xlsx from reports@jdcanada.ca (Gmail RAW), Detail sheet regions + Master sites.
7. **Markers** `markers.json`: Klaviyo campaign send times today (Attentive has no sends since June 2026).

Then `python3 tools/compute.py [YYYY-MM-DD]` and `python3 tools/build.py`. Fonts: publish fonts/ForeverForwardSans-Headline.woff2 next to index.html (copy from the Brand Kit Test artifact).

## Hourly run tools (added 12 Nov 2026, first scheduled run)
- `tools/pull_today.js`: paste into the Shopify analytics page (built-in browser), then `await __pull({ly:'<LY day>', p7:<first run of day>, lyFill:<LY day missing from caches>, lyFun:<shopify_raw3.json fdevL has no rows for the LY day>, known:[ids in shopify_raw2 imgs], named:[all ids in shopify_raw.json P]})`. It also returns fdev / fref (sessions funnel by hour x device / referrer_source, today), fdevL / frefL (same on the LY day when lyFun), and product titles + CDN thumbnails for each hour's top 8 sellers (newP). CSRF comes from the page's `"csrfToken"` script JSON (the meta tag no longer exists). With p7, it returns raw `p7raw`; reduce it in the page to `__out.p7` before export (see the 12 Nov run: sum gross to the current local time, /7, plus full-day /7), then `__slice(null,i)` padded with `' '.repeat(60000)`.
- `tools/merge_pull.py pull.json`: replaces today keys in shopify_raw2.json (incl. lp, fdev, fref), appends LY-day lyNR2/lyPH/utmL/fdevL/frefL rows not already cached, adds new product meta to P and thumbnails to imgs, writes p7.json.
- `tools/snapshot.py file.xlsx "YYYY-MM-DD HH:MM"`: Open Order Snapshot attachment (Gmail RAW) -> data/snapshot.json (Detail regions, top 6 Master sites by over-3-day orders as watch).
- Note: the static caches held lyNR2/lyPH/utmL for 2025-11-11 only, so each new day's first run pulls that LY day (lyFill:true).

## Click-throughs (Ryan, 12 Nov 2026)
- Revenue chart: click any hour -> hour detail (sales vs target and LY, orders, AOV, conversion, new customer share, top 8 sellers that hour, sessions by UTM medium vs LY, sends). Arrows step through hours. Model keys: hourtop, nrh.
- Spend: click Google or Meta in the channel list -> campaigns (spend, budget used, ROAS today, normal and LY for Google) and spend + ROAS by hour vs LY. Model key: camp (from data/campaigns.json and meta.json today_value / ly_value).
- Funnel: click a step -> split by device or traffic source (Shopify referrer_source), today vs LY to the same minute. Model key: fsplit.
- Ticker (Dashboard view): click an item -> Live view with the product, hour, funnel split or spend detail open. Ticker items carry `go`.
- Product rows -> product drill-down (landing-page funnel); fulfilment regions -> stores; KPI cards -> hourly view; chart notes collapse to short pills.
- Auto-refresh: tools/build.py writes data/version.json (a stamp of the built page). Every open page reads it once a minute with caching off and reloads itself when it changes, keeping the same view. Always commit data/version.json with index.html.
- Refresh pulse (Ryan, 12 Nov 2026): when a page reloads itself for new data, a yellow glow rises from the bottom of the screen for about 3 seconds. It lives in the standalone cr-refresh script (sessionStorage flag cr_pulse set just before the reload). Test with `__crRefresh.pulse()` in the console. The header says when the next update is due (about :10 past the hour).

## Cloud pull through the Shopify connector (added 13 Nov 2026, tested 12:54 PT)
Same ShopifyQL as tools/pull_today.js, no work PC or browser needed. Tested against the 12:05 browser pull: every completed hour matched to the cent.
1. `python3 tools/connector_pull.py plan` says which packs are needed (p7 on the first run of the day, lyFill / lyFun when the LY caches lack the day).
2. `python3 tools/connector_pull.py query today` (and `p7`, `lyfill` when needed) prints {query, variables}. Pass both exactly to the Shopify connector's graphql_query. The answer is saved to a tool-results file (the today pack is padded so it always spills); never retype it.
3. `python3 tools/connector_pull.py query products --today <today file>`, run it the same way.
4. `python3 tools/connector_pull.py assemble --today F [--p7 F] [--lyfill F] --products F --out pull.json`, then merge_pull.py, compute.py, build.py as usual.
Thumbnails are CDN links (the cloud cannot fetch cdn.shopify.com to embed them).

## New vs returning (Ryan, 13 Nov 2026)
- Pack `tdNR3` (today) and cache `lyNR3` (shopify_raw3.json): `FROM sales SHOW customers, orders, gross_sales, discounts,
  total_sales GROUP BY hour, new_or_returning_customer`. lyNR3 was filled once for 13 Nov 2025 to 4 Jan 2026 (2,543 rows),
  so the hourly runs only pull today's; plan() still asks for lyFill if a day is missing.
- The fifth card is now New / returning customers (counts, vs LY to the same minute). Clicking it opens customers by hour.
- Revenue (click the Total revenue card), Orders and AOV drill-downs have an All / New & returning switch: two lines today,
  same two dashed for last year. AOV per segment = (gross sales less discounts) ÷ orders, the headline AOV basis.
- tools/pull_today.js (work-PC fallback) does not pull these yet; the page falls back to the old revenue-share card without them.

