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
3. **Meta** `meta.json`: JD_CANADA 1101395547052286, level ad_account, breakdown hourly_stats_aggregated_by_advertiser_time_zone, today and the LY date.
4. **PRM** `prm.json`: peak_days, gap_windows, day_shape parsed from jd-ecomm/jd-revenue-model index.html.
5. **Spend plan** `spend_plan.json`: "Copy of JD Sports - BFCM Spend Planning" (15eiTzseJdeVC0HVzcRLrOUeyGWr-X4BAGy1oTgaEV9g), Daily Plan tab: working plan (col U), google/meta/shop/pinterest.
6. **Open orders** `snapshot.json`: latest "VCS_JDSF - Open Order Snapshot" xlsx from reports@jdcanada.ca (Gmail RAW), Detail sheet regions + Master sites.
7. **Markers** `markers.json`: Klaviyo campaign send times today (Attentive has no sends since June 2026).

Then `python3 tools/compute.py [YYYY-MM-DD]` and `python3 tools/build.py`. Fonts: publish fonts/ForeverForwardSans-Headline.woff2 next to index.html (copy from the Brand Kit Test artifact).
