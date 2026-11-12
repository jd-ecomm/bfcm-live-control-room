// Control Room: today-only Shopify pulls. Paste into the Shopify admin analytics page (built-in browser), then:
//   await __pull({ly: 'YYYY-MM-DD', p7: true|false, lyFill: true|false})   -> sizes; results in window.__out
//   __slice(key, i)  -> 240K-character slices of JSON.stringify(window.__out[key])
// Rows come back in the cache format {c:[cols], r:[[...]]}; hour labels are UTC.
(() => {
  const s = [...document.scripts].find(x => /"csrfToken"/.test(x.textContent));
  const meta = document.querySelector('meta[name=csrf-token]');
  window.__csrf = meta ? meta.content : ((s && s.textContent.match(/"csrfToken":"([^"]+)"/)) || [])[1];
  const API = '/store/jdsports-ca/admin/api/2025-10/graphql.json';
  const gql = async (query, variables) => {
    const r = await fetch(API, {method: 'POST', headers: {'content-type': 'application/json', 'x-csrf-token': window.__csrf}, body: JSON.stringify({query, variables})});
    return r.json();
  };
  window.__ql = async (q) => {
    const j = await gql('query($q:String!){shopifyqlQuery(query:$q){tableData{columns{name} rows} parseErrors}}', {q});
    const d = j.data && j.data.shopifyqlQuery;
    if (!d || (d.parseErrors && d.parseErrors.length)) throw new Error('ShopifyQL failed: ' + q + ' :: ' + JSON.stringify(d ? d.parseErrors : j.errors).slice(0, 300));
    const c = d.tableData.columns.map(x => x.name);
    return {c, r: d.tableData.rows.map(row => c.map(k => row[k]))};
  };
  const day = (n) => { const t = new Date(Date.now() - 7 * 3600e3 - n * 864e5); return t.toISOString().slice(0, 10); };
  window.__pull = async ({ly, p7 = false, lyFill = false, known = []} = {}) => {
    const T = 'SINCE today UNTIL today';
    const o = {};
    o.tdT = await __ql(`FROM sales SHOW total_sales, net_sales, gross_sales, discounts, returns, orders GROUP BY hour ${T} ORDER BY hour`);
    o.tdFn = await __ql(`FROM sessions SHOW sessions, sessions_with_cart_additions, sessions_that_reached_checkout, sessions_that_completed_checkout GROUP BY hour ${T} ORDER BY hour`);
    o.tdNR2 = await __ql(`FROM sales SHOW total_sales, net_sales, orders GROUP BY hour, new_or_returning_customer ${T} ORDER BY hour`);
    o.utmT = await __ql(`FROM sessions SHOW sessions GROUP BY hour, utm_medium ${T} ORDER BY hour LIMIT 10000`);
    o.pH = await __ql(`FROM sales SHOW total_sales, gross_sales, net_items_sold GROUP BY product_id, hour ${T} LIMIT 10000`);
    // landing-page funnel today, for the product drill-down (Ryan, 12 Nov 2026); non-fatal if ShopifyQL rejects it
    try { o.lp = await __ql(`FROM sessions SHOW sessions, sessions_with_cart_additions, sessions_that_reached_checkout, sessions_that_completed_checkout GROUP BY landing_page_path ${T} ORDER BY sessions DESC LIMIT 5000`); }
    catch (e) { o.lpErr = String(e.message || e).slice(0, 300); }
    const rt = await __ql('FROM sales SHOW total_sales, net_sales SINCE -28d UNTIL -1d');
    o.ratio28 = rt.r[0].map(Number);
    if (lyFill && ly) {   // LY-day packs missing from the static caches (new_or_returning, product x hour, utm x hour)
      const L = `SINCE ${ly} UNTIL ${ly}`;
      o.lyNR2 = await __ql(`FROM sales SHOW total_sales, net_sales, orders GROUP BY hour, new_or_returning_customer ${L} ORDER BY hour`);
      o.lyPH = await __ql(`FROM sales SHOW gross_sales, net_items_sold GROUP BY product_id, hour ${L} LIMIT 10000`);
      o.utmL = await __ql(`FROM sessions SHOW sessions GROUP BY hour, utm_medium ${L} ORDER BY hour LIMIT 10000`);
    }
    if (p7) {   // previous 7 days product x hour (gross), raw rows; summed/averaged in python
      o.p7raw = {};
      for (let n = 1; n <= 7; n++) { const d = day(n); o.p7raw[d] = (await __ql(`FROM sales SHOW gross_sales GROUP BY product_id, hour SINCE ${d} UNTIL ${d} LIMIT 10000`)).r; }
    }
    // product meta + thumbnails for today's sellers not already known (gross >= 300 today)
    const g = {}; o.pH.r.forEach(r => { g[r[0]] = (g[r[0]] || 0) + Number(r[3]); });
    const want = Object.keys(g).filter(id => g[id] >= 300 && !known.includes(id)).slice(0, 60);
    o.newP = []; o.imgs = {};
    for (let i = 0; i < want.length; i += 25) {
      const ids = want.slice(i, i + 25).map(id => 'gid://shopify/Product/' + id);
      const j = await gql('query($ids:[ID!]!){nodes(ids:$ids){... on Product{id title handle totalInventory featuredMedia{preview{image{url}}}}}}', {ids});
      for (const n of (j.data && j.data.nodes) || []) {
        if (!n) continue;
        const id = n.id.split('/').pop(); const url = n.featuredMedia && n.featuredMedia.preview && n.featuredMedia.preview.image && n.featuredMedia.preview.image.url;
        o.newP.push([id, n.title, 0, 0, 0, 0, 0, 0, n.totalInventory, n.handle, url || '']);
        if (url) {
          try {
            const u = url.replace(/(\.[a-z]+)(\?|$)/i, '_240x$1$2');
            const b = await (await fetch(u)).blob();
            o.imgs[id] = await new Promise(res => { const f = new FileReader(); f.onload = () => res(f.result); f.readAsDataURL(b); });
          } catch (e) { /* no thumbnail */ }
        }
      }
    }
    o.pulled = new Date().toISOString();
    window.__out = o;
    return Object.fromEntries(Object.entries(o).map(([k, v]) => [k, JSON.stringify(v).length]));
  };
  window.__slice = (k, i) => JSON.stringify(k ? window.__out[k] : window.__out).slice(i * 240000, (i + 1) * 240000);
  return 'pull_today ready, csrf ' + !!window.__csrf;
})();
