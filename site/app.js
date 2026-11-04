"use strict";
/* Grail — one page, routed by the address bar: #/<game>/<view>/<param> */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
const money = v => v == null || isNaN(v) ? "—" : (Math.abs(v) >= 100 ? "$" + Math.round(v).toLocaleString() : "$" + v.toFixed(2));
const pct = (v, plus = true) => v == null ? "—" : (plus && v > 0 ? "+" : "") + (v * 100).toFixed(Math.abs(v) < 0.1 ? 1 : 0) + "%";
const chg = v => v == null ? '<span class="faint">—</span>' : `<span class="${v > 0 ? "up" : v < 0 ? "down" : ""}">${v > 0 ? "+" : ""}${v.toFixed(1)}%</span>`;
const oneIn = n => n == null ? "—" : n < 1.05 ? "most boxes" : n < 10 ? `1 in ${n.toFixed(1)} boxes` : `1 in ${Math.round(n).toLocaleString()} boxes`;
const fmtDate = d => d ? new Date(d + "T12:00").toLocaleDateString(undefined, {month: "short", day: "numeric", year: "numeric"}) : "—";
const store = {get(k){try{return localStorage.getItem(k)}catch(e){return null}}, set(k,v){try{localStorage.setItem(k,v)}catch(e){}}};
const SOURCE = {official: '<span class="chip good plain">Publisher</span>', community: '<span class="chip warn plain">Community estimate</span>', assumed: '<span class="chip bad plain">Our assumption</span>'};
const ZONE = {good_msrp: "good", good_low: "good", normal: "", high: "bad", new: "plain"};
// "no recent sales": the price is only what sellers ask. "price falling": listings are well under the last sale.
const flags = c => (c.no_sale ? ' <span class="chip warn plain" title="No recent sales: the price shown is only what sellers are asking">no recent sales</span>' : "")
  + (c.falling && !c.no_sale ? ' <span class="chip plain" title="The cheapest listing is well under the last sale, so the price is probably dropping">price falling</span>' : "")
  + (c.other_set ? ` <span class="chip plain" title="Carries ${esc(c.other_set)} numbering, so it isn't counted in this set's box value">${esc(c.other_set)} card</span>` : "");
const zoneChip = (z, label) => z ? `<span class="chip ${ZONE[z] ?? ""}">${esc(label || z)}</span>` : "";
const quietChip = (z, label) => z && z !== "normal" ? zoneChip(z, label) + '<div style="height:6px"></div>' : "";

const S = {games: [], game: null, summary: {}, cards: {}, sets: {}, charts: {}, route: {}, years: {}};
// "Origins (2025)": set names carry their release year, unless the name already has one
function yearOf(code){ return S.years[S.route.game]?.[code] || ""; }
function withYear(name, code, year){
  const y = year || yearOf(code);
  return !y || /\b(19|20)\d{2}\b/.test(name || "") ? (name || "") : `${name} (${y})`;
}
const setLabel = (name, code, year) => esc(withYear(name, code, year));
const setHTML = (name, code, year) => { const t = withYear(name, code, year); return t === name ? esc(name) : `${esc(name)} <span class="yr">(${esc(year || yearOf(code))})</span>`; };

/* ---------------- data ---------------- */
const getJSON = url => fetch(url + (url.includes("games.json") ? "?t=" + Date.now() : "?v=" + encodeURIComponent(S.build || "")), {cache: "no-cache"})
  .then(r => { if (!r.ok) throw new Error(url + " " + r.status); return r.json(); });
async function summary(g){
  if (!S.summary[g]){
    S.summary[g] = await getJSON(`data/${g}/summary.json`);
    S.years[g] = Object.fromEntries(S.summary[g].sets.map(x => [x.code, x.year]));
  }
  return S.summary[g];
}
async function cards(g){ return S.cards[g] ||= await getJSON(`data/${g}/cards.json`); }
async function setFile(g, code){
  const sm = await summary(g);
  const s = sm.sets.find(x => x.code === code);
  if (!s) return null;
  return S.sets[g + ":" + code] ||= await getJSON(`data/${g}/${s.file}`);
}

/* ---------------- tiny components ---------------- */
function css(name){ return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
function palette(){ return ["--c1","--c2","--c3","--c4","--c5","--c6","--c7","--c8"].map(css); }
function chart(id, cfg){
  if (S.charts[id]) S.charts[id].destroy();
  if (typeof Chart === "undefined" || !document.getElementById(id)) return; // chart library didn't load; tables still work
  Chart.defaults.color = css("--muted"); Chart.defaults.borderColor = css("--line"); Chart.defaults.font.family = "Inter, system-ui, sans-serif";
  cfg.options = Object.assign({responsive: true, maintainAspectRatio: false, interaction: {mode: "index", intersect: false},
    plugins: {legend: {labels: {boxWidth: 12, boxHeight: 12}}}}, cfg.options || {});
  S.charts[id] = new Chart(document.getElementById(id), cfg);
}
const moneyTicks = {ticks: {callback: v => "$" + Number(v).toLocaleString()}};
const tipMoney = {callbacks: {label: c => `${c.dataset.label}: ${money(c.raw?.y ?? c.raw)}`}};

function thumb(c){
  return c.image
    ? `<img class="thumb" loading="lazy" src="${esc(c.image)}" alt="" ${c.standin ? 'title="TCGplayer has no photo of this version yet, so this shows the same card\'s other printing"' : ""} onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'thumb'}))">`
    : `<div class="thumb" title="No photo on TCGplayer yet"></div>`;
}
function art(src, cls = ""){
  return src ? `<img class="${cls}" loading="lazy" src="${esc(src)}" alt="" onerror="this.style.visibility='hidden'">` : `<div class="ph ${cls}"></div>`;
}
// Where today's price sits between its 90-day low and high, with MSRP marked.
function range(low, high, now, msrp){
  if (low == null || high == null || now == null) return '<span class="faint small">Building history</span>';
  const lo = Math.min(low, now), hi = Math.max(high, now), span = hi - lo || 1;
  // keep the 12px dot and 2px MSRP mark fully inside the bar, even at the very ends
  const f = v => Math.max(0, Math.min(1, (v - lo) / span));
  const at = v => `calc(6px + (100% - 12px) * ${f(v).toFixed(4)})`;
  const msrpIn = msrp != null && msrp >= lo && msrp <= hi;
  const note = msrp != null && !msrpIn ? `<span class="faint">MSRP ${money(msrp)} is ${msrp < lo ? "below" : "above"} this range</span>` : "";
  return `<div class="range" title="Last 90 days: ${money(low)} to ${money(high)}${msrp ? `. MSRP ${money(msrp)}` : ""}">
    <div class="track">${msrpIn ? `<span class="msrp" style="left:${at(msrp)}" title="MSRP ${money(msrp)}"></span>` : ""}<span class="dot" style="left:${at(now)}"></span></div>
    <div class="ends"><span>${money(lo)}</span><span>${money(hi)}</span></div>${note ? `<div class="range-note">${note}</div>` : ""}</div>`;
}
function spark(vals, w = 110, h = 30){
  if (!vals || vals.length < 2) return "";
  const lo = Math.min(...vals), hi = Math.max(...vals), sp = hi - lo || 1;
  const pts = vals.map((v, i) => `${(i / (vals.length - 1) * w).toFixed(1)},${(h - 2 - (v - lo) / sp * (h - 4)).toFixed(1)}`).join(" ");
  const up = vals[vals.length - 1] >= vals[0];
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="${up ? "var(--good)" : "var(--bad)"}" stroke-width="1.75" stroke-linejoin="round"/></svg>`;
}
function dots(share){
  const n = Math.round((share ?? 0) * 100);
  return `<div class="dots" role="img" aria-label="${n} out of 100 boxes">${Array.from({length: 100}, (_, i) => `<i class="${i < n ? "win" : ""}"></i>`).join("")}</div>`;
}
function shareAtLeast(q, x){
  const n = q.length - 1;
  if (x <= q[0]) return 1; if (x > q[n]) return 0;
  for (let i = 1; i <= n; i++) if (q[i] >= x){ const f = q[i] === q[i-1] ? 0 : (x - q[i-1]) / (q[i] - q[i-1]); return 1 - (i - 1 + f) / n; }
  return 0;
}
// Sortable table: cols = [{key,label,num,sort:(row)=>value,html:(row)=>string,cls}]
function table(el, rows, cols, opts = {}){
  let key = opts.sort || null, dir = opts.dir || -1, shown = opts.page || 100;
  const draw = () => {
    const c = cols.find(c => c.key === key);
    const list = c ? [...rows].sort((a, b) => { const x = c.sort(a), y = c.sort(b); return (x == null) - (y == null) || (x < y ? -dir : x > y ? dir : 0); }) : rows;
    el.innerHTML = `<div class="table-scroll"><table class="data"><thead><tr>${cols.map(c => `<th class="${c.num ? "num" : ""} ${c.cls || ""}" ${c.sort ? `data-sort="${c.key}"` : ""}>${c.label}${key === c.key ? `<span class="arrow">${dir > 0 ? "▲" : "▼"}</span>` : ""}</th>`).join("")}</tr></thead>
      <tbody>${list.slice(0, shown).map((r, i) => `<tr class="${opts.onRow ? "click" : ""}" data-i="${rows.indexOf(r)}">${cols.map(c => `<td class="${c.num ? "num" : ""} ${c.cls || ""}">${c.html(r)}</td>`).join("")}</tr>`).join("") ||
      `<tr><td colspan="${cols.length}" class="empty">${opts.empty || "Nothing to show."}</td></tr>`}</tbody></table></div>
      ${list.length > shown ? `<div class="more"><button class="btn">Show ${Math.min(100, list.length - shown)} more of ${list.length - shown}</button></div>` : ""}`;
    $$("th[data-sort]", el).forEach(th => th.onclick = () => { const k = th.dataset.sort; dir = key === k ? -dir : -1; key = k; draw(); });
    $(".more button", el)?.addEventListener("click", () => { shown += 100; draw(); });
    if (opts.onRow) $$("tbody tr[data-i]", el).forEach(tr => tr.onclick = e => { if (e.target.closest("a")) return; opts.onRow(rows[+tr.dataset.i]); });
  };
  draw();
}

/* ---------------- routing ---------------- */
function parse(){
  const [g, view, ...rest] = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  const game = S.games.find(x => x.id === g)?.id || store.get("game") || S.games[0]?.id;
  return {game, view: view || "today", param: rest.join("/") || null};
}
const go = (view, param, game = S.route.game) => { location.hash = `#/${game}/${view}${param ? "/" + encodeURIComponent(param) : ""}`; };
const href = (view, param, game = S.route.game) => `#/${game}/${view}${param ? "/" + encodeURIComponent(param) : ""}`;

async function render(){
  const r = S.route = parse();
  store.set("game", r.game);
  $("#games").innerHTML = S.games.map(g => `<a role="tab" href="#/${g.id}/${r.view === "set" ? "sets" : r.view}" class="${g.id === r.game ? "on" : ""}">${esc(g.name)}</a>`).join("");
  const tabView = r.view === "set" ? "sets" : r.view === "card" ? "cards" : r.view;
  $$("#tabs a").forEach(a => { a.href = href(a.dataset.view); a.classList.toggle("on", a.dataset.view === tabView); if (a.classList.contains("on")) a.scrollIntoView({block: "nearest", inline: "center"}); });
  Object.values(S.charts).forEach(c => c.destroy()); S.charts = {};
  const v = $("#view");
  try {
    const sm = await summary(r.game);
    $("#stamp").textContent = `${sm.name} prices from ${fmtDate(sm.stale_since || sm.price_date)}.`;
    $("#stale")?.remove();
    if (sm.stale_since) $("#view").insertAdjacentHTML("beforebegin", `<div id="stale" class="wrap"><div class="alert">⚠️ TCGplayer's prices didn't update today. Everything here is from ${fmtDate(sm.stale_since)}.</div></div>`);
    document.title = `${sm.name} · Grail`;
    const views = {today: viewToday, sets: viewSets, set: viewSet, sealed: viewSealed, cards: viewCards, card: viewCards, movers: viewMovers, how: viewHow};
    await (views[r.view] || viewToday)(v, sm, r.param);
    if (r.view === "card" && r.param) openCard(r.game, r.param);
  } catch (e) {
    console.error(e);
    v.innerHTML = `<p class="pad muted">Couldn't load the prices. Try refreshing the page.</p>`;
  }
}

/* ---------------- Today ---------------- */
async function viewToday(v, sm){
  const t = sm.today;
  const alerts = (t.alerts || []).map(a => `<div class="alert"><span>${a.type === "upcoming" ? "📅" : "✨"}</span><div>${a.type === "upcoming" ? `<b>${setHTML(a.name, a.set)}</b> releases ${fmtDate(a.release)}.` : esc(a.text)}${a.price ? ` ${esc(a.kind || "Pre-orders")} at ${money(a.price)}${a.msrp ? ` vs ${money(a.msrp)} MSRP` : ""}.` : ""}</div></div>`).join("");
  const signal = r => `<a class="signal" href="${href("set", r.set)}">${art(r.image)}<div>
      <div class="t" title="${esc(r.name)}">${esc(r.name)}</div><div class="small muted">${setLabel(r.set_name, r.set)} · ${esc(r.kind_label)}</div>
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:4px 0"><span class="p">${money(r.market)}</span>${zoneChip(r.zone, r.zone_label)}</div>
      ${range(r.low90, r.high90, r.market, r.msrp)}
      <div class="small muted" style="margin-top:4px">${r.msrp ? `${pct(r.vs_msrp)} vs MSRP · ` : ""}You'd pay about ${money(r.buy_cost)} with tax and shipping</div></div></a>`;
  const chase = c => `<button class="cardtile" data-card="${c.id}" data-set="${esc(c.set)}">${c.image ? `<img loading="lazy" src="${esc(c.image)}" alt="">` : '<div class="ph"></div>'}
      <div class="t">${esc(c.name)}</div><div class="small muted">${setLabel(c.set_name, c.set)}</div>
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-top:4px"><b class="num">${money(c.price)}</b><span class="small muted">low ${money(c.low90)}</span></div></button>`;
  v.innerHTML = `
    <section style="margin-top:22px"><h1>${esc(sm.name)} today</h1>
      <p class="lead" style="margin-top:6px">Sealed products at a good price, chase cards near their lows, and whether any box is worth opening. Prices from ${fmtDate(sm.price_date)}.</p>${alerts}</section>
    <h2>Good prices on sealed right now</h2>
    <p class="note">At or below MSRP, or within ${Math.round(sm.zones.near_low_pct * 100)}% of the lowest price in the last 90 days.</p>
    <div class="grid g3">${t.buy_signals.map(signal).join("") || `<div class="panel empty">Nothing is near its 90-day low or at MSRP today.</div>`}</div>
    <h2>Chase cards near their 90-day low</h2>
    <div class="tiles">${t.chase_near_low.map(chase).join("") || `<div class="panel empty" style="grid-column:1/-1">No $20+ chase cards are near their lows today.</div>`}</div>
    <div class="grid g2" style="margin-top:8px">
      <div><h2>Worth opening?</h2><div id="t-open"></div></div>
      <div><h2>Biggest sealed moves this week</h2><div id="t-moves"></div></div>
    </div>`;
  table($("#t-open"), t.open_value, [
    {key: "name", label: "Set", html: s => `<a href="${href("set", s.code)}"><b>${setHTML(s.name, s.code)}</b></a>`},
    {key: "box", label: "Box", num: 1, html: s => money(s.box)},
    {key: "net", label: "You'd pocket", num: 1, html: s => money(s.box_net)},
    {key: "beat", label: "Pays for itself", num: 1, sort: s => s.beat_market, html: s => Math.round((s.beat_market || 0) * 100) + "%"},
  ], {empty: "No box values for this game yet."});
  table($("#t-moves"), t.sealed_moves, [
    {key: "name", label: "Product", html: r => `<a href="${href("set", r.set)}">${esc(r.name)}</a>`},
    {key: "p", label: "Price", num: 1, html: r => money(r.market)},
    {key: "c", label: "7 days", num: 1, html: r => chg(r.change_7d)},
  ], {empty: "Not enough history for weekly moves yet."});
  $$("[data-card]", v).forEach(b => b.onclick = () => openCard(sm.game, b.dataset.card, b.dataset.set));
}

/* ---------------- Sets browser ---------------- */
async function viewSets(v, sm){
  const groupKey = s => sm.group_by === "era" ? (s.era || "Other") : (s.year || "Upcoming");
  const groups = [];
  for (const s of sm.sets){ const k = groupKey(s); let g = groups.find(x => x.k === k); if (!g) groups.push(g = {k, sets: []}); g.sets.push(s); }
  const open = new Set(JSON.parse(store.get("open-" + sm.game) || "null") || groups.slice(0, 2).map(g => g.k));
  const tile = s => {
    const h = s.hero || {};
    return `<a class="settile" href="${href("set", s.code)}"><div class="art">${art(s.image)}
        ${!s.released ? '<span class="chip info plain badge">Pre-order</span>' : s.ev ? '<span class="chip plain badge">Box value</span>' : s.ev_hold ? '<span class="chip warn plain badge">Being checked</span>' : ""}</div>
      <div class="body"><div class="t">${setHTML(s.name, s.code, s.year)}</div><div class="meta">${esc(s.code)} · ${fmtDate(s.release)}</div>
      ${h.zone && h.zone !== "new" && h.zone !== "normal" ? `<div>${zoneChip(h.zone, h.zone_label)}</div>` : ""}
      <div class="row"><div><div class="price">${money(h.market ?? h.low)}</div><div class="meta">${esc(h.kind_label || "")}</div></div>${spark(h.spark)}</div></div></a>`;
  };
  const yrs = g => { const ys = g.sets.map(s => s.year).filter(Boolean).sort(); return ys.length ? (ys[0] === ys[ys.length - 1] ? ys[0] : `${ys[0]}–${ys[ys.length - 1]}`) : ""; };
  v.innerHTML = `<div style="margin-top:22px"><h1>${esc(sm.name)} sets</h1>
      <p class="lead" style="margin-top:6px">${sm.sets.length} sets, newest first${sm.group_by === "era" ? ", grouped by era" : ", grouped by year"}. Each tile shows the main sealed product's price over recent months.</p></div>
    <div class="filters"><input id="set-q" type="search" placeholder="Find a set by name, code or year…" autocomplete="off"></div>
    <div id="set-groups"></div>`;
  const draw = q => {
    const n = q.trim().toLowerCase();
    $("#set-groups").innerHTML = groups.map(g => {
      const list = g.sets.filter(s => !n || (s.name + " " + s.code + " " + (s.year || "")).toLowerCase().includes(n));
      if (!list.length) return "";
      const isOpen = n || open.has(g.k);
      return `<section class="era"><div class="era-head"><h2>${esc(g.k)}</h2><span class="muted small">${sm.group_by === "era" ? yrs(g) + " · " : ""}${g.sets.length} set${g.sets.length > 1 ? "s" : ""}</span>
        ${n ? "" : `<button class="btn" data-toggle="${esc(g.k)}" style="margin-left:auto;padding:4px 10px">${isOpen ? "Hide" : "Show"}</button>`}</div>
        ${isOpen ? `<div class="settiles">${list.map(tile).join("")}</div>` : ""}</section>`;
    }).join("") || `<div class="panel empty">No set matches “${esc(q)}”.</div>`;
    $$("[data-toggle]").forEach(b => b.onclick = () => { const k = b.dataset.toggle; open.has(k) ? open.delete(k) : open.add(k); store.set("open-" + sm.game, JSON.stringify([...open])); draw($("#set-q").value); });
  };
  $("#set-q").oninput = e => draw(e.target.value);
  draw("");
}

/* ---------------- Set detail ---------------- */
async function viewSet(v, sm, code){
  const d = await setFile(sm.game, code);
  if (!d){ v.innerHTML = `<p class="pad">That set isn't listed. <a href="${href("sets")}">See all sets</a>.</p>`; return; }
  const s = sm.sets.find(x => x.code === code);
  const hero = d.sealed.find(r => r.id === (d.canonical.box ?? d.canonical.etb ?? d.canonical.bundle ?? d.canonical.pack)) || d.sealed[0] || {};
  const b = hero;
  const bench = b.bench;
  v.innerHTML = `
    <a class="back" href="${href("sets")}">← All ${esc(sm.name)} sets</a>
    <div class="sethead"><div class="art">${art(d.image)}</div><div>
      <h1>${setHTML(d.name, d.code)}</h1>
      <div class="meta"><span class="muted">${[d.era, d.code, d.released ? "Released " + fmtDate(d.release) : "Releases " + fmtDate(d.release)].filter(Boolean).map(esc).join(" · ")}</span>
      ${d.print_status ? `<span class="chip info plain">${esc(d.print_status)}</span>` : ""}${!d.released ? '<span class="chip info plain">Pre-order</span>' : ""}</div></div></div>

    <h2>Is now a good time to buy?</h2>
    <div class="buybox">
      <div class="panel main">
        <div class="sub">${esc(b.kind_label || "Sealed")} · market price</div>
        <div class="big">${money(b.market ?? b.low)}</div>
        <div style="margin:8px 0 12px">${zoneChip(b.zone, b.zone_label)}</div>
        ${range(b.low90, b.high90, b.market, b.msrp)}
        <div class="kpis" style="grid-template-columns:1fr 1fr;margin-bottom:0">
          <div><div class="sub">You'd pay</div><b class="num">${money(b.buy_cost)}</b><div class="sub">cheapest listing + tax + shipping</div></div>
          ${b.msrp ? `<div><div class="sub">vs MSRP ${money(b.msrp)}</div><b class="num">${pct(b.vs_msrp)}</b><div class="sub">${b.annualized != null ? pct(b.annualized) + " per year since release" : "per-year rate after 90 days"}</div></div>`
            : `<div><div class="sub">vs its 90-day low</div><b class="num">${pct(b.vs_low90)}</b><div class="sub">no MSRP on file for this set</div></div>`}
          <div><div class="sub">Last 30 days</div><b class="num">${chg(b.change_30d)}</b></div>
          <div><div class="sub">If you sold it</div><b class="num">${money(b.net_if_sold)}</b><div class="sub">after fees and shipping</div></div>
        </div>
      </div>
      <div class="panel"><div class="chart-box"><canvas id="c-price"></canvas></div></div>
    </div>
    <div class="grid g2" style="margin-top:14px">
      <div><h3>Cheapest way to get packs</h3><div id="ways"></div><p class="note">Includes tax and shipping. Elite Trainer Boxes also come with sleeves, dice and other extras, so their per-pack cost looks higher.</p></div>
      <div><h3>Compared with other places for the money</h3>${benchHTML(bench, sm)}</div>
    </div>
    ${d.ev_hold ? `<h2>Is it worth opening?</h2><div class="alert">⚠️ <div><b>This set's box value is being checked</b> and is hidden until it passes: ${d.ev_hold.map(esc).join("; ")}. Prices and buy timing above are unaffected.</div></div>`
      : d.modeled ? ripHoldHTML(d) + openingHTML(d, b) : `<h2>Opening value</h2><div class="panel pad-in muted">There's no reliable pack data for this set, so it gets buy timing and card prices but no box value.</div>`}
    <h2>Chase cards</h2>
    <p class="note">The most valuable cards in the set. "Pull it" is what you'd expect to spend opening boxes until you hit that exact card, after selling everything else you pull.</p>
    <div id="chase"></div>
    <h2>Every sealed ${esc(d.name)} product</h2>
    <div id="sealed-list"></div>
    ${d.modeled ? `<h2>Pack odds used</h2><div class="table-scroll"><table class="data"><thead><tr><th>What</th><th>Rate</th><th>Source</th></tr></thead><tbody>
      ${d.odds_notes.map(o => `<tr><td>${esc(o.what)}</td><td>${esc(o.rate)}</td><td>${SOURCE[o.source] || esc(o.source)}</td></tr>`).join("")}</tbody></table></div>
      <p class="note">Cards in this set's box math: ${Object.entries(d.card_counts).map(([k, n]) => `${n} ${esc(k.toLowerCase())}`).join(", ")}. Every card of the same rarity is treated as equally likely.</p>` : ""}`;

  // price chart with MSRP and the 90-day range
  const ser = b.series || [];
  if (ser.length > 1){
    const p = palette();
    chart("c-price", {type: "line", data: {labels: ser.map(x => x[0]), datasets: [
      {label: `${b.kind_label} price`, data: ser.map(x => x[1]), borderColor: p[0], backgroundColor: p[0], pointRadius: ser.length < 20 ? 3 : 0, borderWidth: 2, tension: .2},
      ...(b.msrp ? [{label: "MSRP", data: ser.map(() => b.msrp), borderColor: p[2], borderDash: [5, 4], pointRadius: 0, borderWidth: 1.5}] : []),
    ]}, options: {scales: {x: {ticks: {maxTicksLimit: 7}}, y: moneyTicks}, plugins: {tooltip: tipMoney}}});
  } else $("#c-price").closest(".chart-box").innerHTML = '<p class="empty">Price history builds up with each daily update.</p>';

  table($("#ways"), d.ways_to_buy, [
    {key: "l", label: "Buy as", html: w => `<a href="${esc(w.url)}" target="_blank" rel="noopener">${esc(w.label)}</a>`},
    {key: "n", label: "Packs", num: 1, html: w => w.packs},
    {key: "c", label: "You'd pay", num: 1, html: w => money(w.buy_cost)},
    {key: "pp", label: "Per pack", num: 1, html: (w, i) => `<b>${money(w.per_pack)}</b>`},
  ], {empty: "No sealed prices yet."});

  if (d.modeled && !d.ev_hold){ setupOpening(d, b); setupRipHold(d); }
  table($("#chase"), d.chase, chaseCols(d), {onRow: c => openCard(sm.game, c.id, d.code, d), page: 12});
  table($("#sealed-list"), d.sealed, sealedCols(sm, false), {sort: "price"});
}

function benchHTML(bench, sm){
  if (!bench) return `<div class="panel pad-in muted">Shown once a product has been out for 90 days and has an MSRP.</div>`;
  const t = sm.benchmark_tax;
  const row = (label, v, after) => `<tr><td>${label}</td><td class="num"><b>${pct(v)}</b></td><td class="num">${after == null ? "—" : pct(after)}</td></tr>`;
  return `<div class="table-scroll"><table class="data"><thead><tr><th>Same money since release (${Math.round(bench.days / 30.4)} months)</th><th class="num">Return</th><th class="num">After federal tax</th></tr></thead><tbody>
    ${row("This product, bought at MSRP", bench.sealed, bench.after_tax.sealed)}
    ${bench.spy != null ? row("S&amp;P 500 index fund", bench.spy, bench.after_tax.spy) : ""}
    ${bench.tbill != null ? row("Treasury bills", bench.tbill, bench.after_tax.tbill) : ""}</tbody></table></div>
    <p class="note">Sealed is valued at today's market price, before selling fees. Taxed at ${Math.round(t.collectibles_tax * 100)}% for collectibles, ${Math.round(t.stock_tax * 100)}% for stocks and ${Math.round(t.interest_tax * 100)}% for interest, assuming you held over a year. The S&amp;P figure is price only, without dividends.</p>`;
}

function ripHoldHTML(d){
  if (!d.rip_or_hold || !d.rip_or_hold.length) return "";
  const warn = [];
  if (d.concentration) warn.push(`<b>${Math.round(d.concentration.share * 100)}%</b> of an average box's value comes from one card, <b>${esc(d.concentration.name)}</b>. If its price drops, so does the whole box value.`);
  if (d.no_sale_share > 0.05) warn.push(`<b>${Math.round(d.no_sale_share * 100)}%</b> of the box value comes from cards with no recent sales. Those are valued at the typical price for their rarity, not their asking price.`);
  return `<h2>Rip or hold?</h2>
    <p class="note">What you'd pay delivered, what's inside on average, and your return if you open it, next to how holding it sealed has done. "Held sealed" is what already happened, not a forecast.</p>
    ${warn.map(w => `<div class="alert">⚠️ <div>${w}</div></div>`).join("")}
    <div id="riphold"></div>`;
}

function setupRipHold(d){
  table($("#riphold"), d.rip_or_hold, [
    {key: "l", label: "Buy", html: r => `<b>${esc(r.label)}</b><div class="sub small muted">${r.packs.toLocaleString()} pack${r.packs > 1 ? "s" : ""}</div>`},
    {key: "p", label: "You'd pay", num: 1, html: r => money(r.pay)},
    {key: "e", label: "EV (cards inside)", num: 1, cls: "hide-md", html: r => money(r.ev)},
    {key: "n", label: "EV after selling", num: 1, html: r => money(r.ev_net)},
    {key: "r", label: "Return if you rip", num: 1, html: r => `<b class="${r.rip_return >= 0 ? "up" : "down"}">${pct(r.rip_return)}</b>`},
    {key: "c", label: "Chance a rip profits", num: 1, html: r => Math.round(r.chance_profit * 100) + "%"},
    {key: "h", label: "Held sealed", num: 1, html: r => r.hold ? `<span class="${r.hold.change >= 0 ? "up" : "down"}">${pct(r.hold.change)}</span><div class="sub small muted">since ${fmtDate(r.hold.since)}${r.hold.per_year != null ? ` · ${pct(r.hold.per_year)}/yr` : ""}</div>` : '<span class="faint">—</span>'},
  ]);
}

function openingHTML(d, b){
  return `<h2>Is it worth opening?</h2>
    <div class="paid"><label for="paid"><b>What I paid for a box</b></label><input id="paid" type="number" min="1" step="1">
      <button class="btn" data-paid="${b.market || ""}">Market ${money(b.market)}</button>${b.msrp ? `<button class="btn" data-paid="${b.msrp}">MSRP ${money(b.msrp)}</button>` : ""}
      ${b.buy_cost ? `<button class="btn" data-paid="${b.buy_cost}">Cheapest delivered ${money(b.buy_cost)}</button>` : ""}</div>
    <div class="buybox">
      <div class="panel main"><div class="sub">You'd pocket from an average box</div><div class="big" id="o-net"></div><div class="sub" id="o-net-h"></div>
        <div style="margin-top:16px" class="sub">Out of 100 boxes, how many pay for themselves</div>
        <div style="display:flex;gap:16px;align-items:center;margin-top:6px"><div id="o-dots"></div><div><div class="big" id="o-beat"></div><div class="sub" id="o-beat-h"></div></div></div></div>
      <div class="panel pad-in"><div class="kpis" id="o-kpis" style="margin:0"></div><div class="verdict" id="o-verdict"></div></div>
    </div>
    <div class="grid g2" style="margin-top:14px">
      <div><h3>Where a box's value comes from</h3><div id="contrib"></div>
        ${d.top10_share != null ? `<p class="note"><b>${Math.round(d.top10_share * 100)}%</b> of an average box's value comes from the set's 10 most valuable cards. The higher this is, the more a box's value depends on a few cards holding their price.</p>` : ""}</div>
      <div><h3>How often you hit</h3><div id="hits"></div></div>
    </div>
    ${d.ev_series && d.ev_series.length > 1 ? `<h3>Box value over time</h3><div class="panel"><div class="chart-box"><canvas id="c-ev"></canvas></div></div>` : ""}`;
}

function setupOpening(d, b){
  const key = "paid-" + S.route.game + "-" + d.code;
  const saved = parseFloat(store.get(key));
  const inp = $("#paid");
  inp.value = (!isNaN(saved) ? saved : (b.market || d.msrp?.box || 100)).toFixed(2);
  const e = d.ev, n = d.sim.net, st = d.sim.sticker;
  const update = () => {
    const paid = parseFloat(inp.value) || b.market || d.msrp?.box;
    store.set(key, String(paid));
    const beat = shareAtLeast(n.quantiles, paid), beatSt = shareAtLeast(st.quantiles, paid);
    $("#o-net").textContent = money(e.box_net);
    $("#o-net-h").innerHTML = `after TCGplayer fees, shipping and bulk · <b>${pct(e.box_net / paid - 1)}</b> on ${money(paid)}`;
    $("#o-dots").innerHTML = dots(beat);
    $("#o-beat").textContent = Math.round(beat * 100);
    $("#o-beat-h").textContent = `${Math.round(beatSt * 100)} before selling costs`;
    $("#o-kpis").innerHTML = [
      ["Average value inside", money(e.box_sticker), "at market prices"],
      ["Typical box", money(n.median), "half do better, half worse"],
      ["Bad box / great box", `${money(n.p10)} / ${money(n.p90)}`, "1 in 10 below / above"],
      ["Sell it sealed instead", money(d.open_vs_hold.sell_sealed_net), "today's market, after fees"],
    ].map(([k, v, h]) => `<div class="kpi"><div class="k">${k}</div><div class="v">${v}</div><div class="h">${h}</div></div>`).join("");
    const gap = e.box_net - paid;
    $("#o-verdict").innerHTML = `<b>${esc(d.open_vs_hold.verdict)}</b> At ${money(paid)}, an average box ${gap >= 0 ? "makes" : "loses"} about ${money(Math.abs(gap))} once you sell the cards.`;
  };
  inp.oninput = update;
  $$("[data-paid]").forEach(btn => btn.onclick = () => { inp.value = (+btn.dataset.paid).toFixed(2); update(); });
  update();
  const max = Math.max(...d.contrib.map(c => c.box_sticker));
  table($("#contrib"), d.contrib, [
    {key: "l", label: "Cards", html: c => esc(c.label)},
    {key: "s", label: "Market", num: 1, html: c => money(c.box_sticker)},
    {key: "n", label: "Pocket", num: 1, html: c => money(c.box_net)},
    {key: "b", label: "", cls: "hide-sm", html: c => `<div class="bar" style="width:${(c.box_sticker / max * 100).toFixed(1)}%"></div>`},
  ]);
  table($("#hits"), d.hit_odds, [
    {key: "l", label: "Hit", html: h => esc(h.label)},
    {key: "p", label: "Per box", num: 1, html: h => h.per_box.toFixed(h.per_box < 1 ? 2 : 1)},
    {key: "c", label: "Chance in a box", num: 1, html: h => Math.round(h.chance_in_box * 100) + "%"},
    {key: "a", label: "About", num: 1, html: h => h.per_box >= 1 ? `${h.per_box.toFixed(1)} per box` : oneIn(h.boxes_per_hit)},
  ]);
  if (d.ev_series && d.ev_series.length > 1){
    const p = palette();
    chart("c-ev", {type: "line", data: {labels: d.ev_series.map(r => r[0]), datasets: [
      {label: "Box price", data: d.ev_series.map(r => r[3]), borderColor: p[0], pointRadius: 0, borderWidth: 2, spanGaps: true},
      {label: "Average value inside", data: d.ev_series.map(r => r[1]), borderColor: p[1], pointRadius: 0, borderWidth: 2},
      {label: "You'd pocket", data: d.ev_series.map(r => r[2]), borderColor: p[2], pointRadius: 0, borderWidth: 2},
    ]}, options: {scales: {x: {ticks: {maxTicksLimit: 7}}, y: moneyTicks}, plugins: {tooltip: tipMoney}}});
  }
}

function chaseCols(d){
  return [
    {key: "name", label: "Card", sort: c => c.name, html: c => `<div class="namecell">${thumb(c)}<div><div>${esc(c.name)}</div><div class="sub">${esc(c.kind)} ${c.number ? "· " + esc(c.number) : ""}${flags(c)}</div></div></div>`},
    {key: "price", label: "Price", num: 1, sort: c => c.price, html: c => `<b>${money(c.price)}</b>`},
    {key: "zone", label: "Buy timing", sort: c => c.low90 ? c.price / c.low90 : null, html: c => `${quietChip(c.zone, c.zone_label)}${range(c.low90, c.high90, c.price)}`},
    ...(d.modeled ? [
      {key: "odds", label: "Odds", num: 1, sort: c => c.boxes_per_hit, html: c => `${oneIn(c.boxes_per_hit)}<div class="sub small muted only-sm">${c.pull_boxes >= 2 && c.pull_cost > 0 ? "Pull ≈ " + money(c.pull_cost) : ""}</div>`},
      {key: "bvp", label: "Buy it vs pull it", cls: "hide-sm", sort: c => c.pull_cost, html: c => `<div class="buyvs">${pullText(c)}</div>`},
    ] : []),
  ];
}

function pullText(c){
  const buy = `Buy: <b>${money(c.buy_cost)}</b>`;
  if (c.pull_cost == null) return buy;
  if (c.pull_boxes < 2) return `${buy}<br>Usually in a box`;
  if (c.pull_cost <= 0) return `${buy}<br>Pull: boxes pay for themselves on average`;
  return `${buy}<br>Pull: <b>${money(c.pull_cost)}</b> over ~${Math.round(c.pull_boxes).toLocaleString()} boxes`;
}

function sealedCols(sm, withSet){
  return [
    {key: "name", label: "Product", sort: r => r.name, html: r => `<div class="namecell">${r.image ? `<img class="thumb" style="object-fit:contain" loading="lazy" src="${esc(r.image)}" alt="">` : ""}<div><a href="${withSet ? href("set", r.set) : esc(r.url)}" ${withSet ? "" : 'target="_blank" rel="noopener"'}>${esc(r.name)}</a>
      <div class="sub">${withSet ? setLabel(r.set_name, r.set) + " · " : ""}${esc(r.kind_label)}${r.presale ? " · pre-order" : ""}</div></div></div>`},
    {key: "price", label: "Price", num: 1, sort: r => r.market ?? r.low, html: r => `<b>${money(r.market ?? r.low)}</b>`},
    {key: "zone", label: "Buy timing", sort: r => r.low90 ? r.market / r.low90 : null, html: r => `${quietChip(r.zone, r.zone_label)}${range(r.low90, r.high90, r.market, r.msrp)}`},
    {key: "pay", label: "You'd pay", num: 1, cls: "hide-md", sort: r => r.buy_cost, html: r => money(r.buy_cost)},
    {key: "msrp", label: "vs MSRP", num: 1, sort: r => r.vs_msrp, html: r => pct(r.vs_msrp)},
    {key: "yr", label: "Per year", num: 1, cls: "hide-md", sort: r => r.annualized, html: r => r.annualized == null ? '<span class="faint">—</span>' : pct(r.annualized)},
    {key: "spy", label: "S&amp;P 500 same time", num: 1, cls: "hide-md", sort: r => r.bench?.spy, html: r => r.bench?.spy == null ? '<span class="faint">—</span>' : pct(r.bench.spy)},
    {key: "d30", label: "30 days", num: 1, sort: r => r.change_30d, html: r => chg(r.change_30d)},
  ];
}

/* ---------------- Sealed ---------------- */
async function viewSealed(v, sm){
  const kinds = [["box", "Boxes"], ["etb", "Elite Trainer Boxes"], ["bundle", "Bundles"], ["case", "Cases"], ["pack", "Packs"], ["all", "Everything"]]
    .filter(([k]) => k === "all" || sm.sealed.some(r => r.kind === k));
  let kind = store.get("sealed-kind-" + sm.game) || "box";
  if (!kinds.some(([k]) => k === kind)) kind = kinds[0][0];
  const eras = [...new Set(sm.sets.map(s => s.era).filter(Boolean))];
  const withLife = sm.sets.filter(s => s.hero?.lifecycle?.length > 1);
  let picked = new Set(JSON.parse(store.get("life-" + sm.game) || "null") || withLife.slice(0, 6).map(s => s.code));
  v.innerHTML = `<div style="margin-top:22px"><h1>Sealed tracker</h1>
      <p class="lead" style="margin-top:6px">Every sealed product against MSRP and against its own last 90 days. "Per year" turns the gain over MSRP into a yearly rate once a product has been out 90 days.</p></div>
    <h2>Price by days since release</h2>
    <p class="note">Each set's ${sm.packs.box ? "booster box" : "main product"} lined up by how long it's been out, so you can see where a new set sits compared with older sets at the same age.</p>
    <div class="filters" id="life-pick">${withLife.map(s => `<button class="btn ${picked.has(s.code) ? "primary" : ""}" data-code="${esc(s.code)}" style="padding:4px 10px">${setLabel(s.name, s.code, s.year)}</button>`).join("")}</div>
    <div class="panel"><div class="chart-box tall"><canvas id="c-life"></canvas></div></div>
    <h2>All sealed products</h2>
    <div class="filters"><div class="seg" id="kind">${kinds.map(([k, l]) => `<button data-k="${k}" class="${k === kind ? "on" : ""}">${l}</button>`).join("")}</div>
      ${eras.length > 1 ? `<select id="era"><option value="">Every era</option>${eras.map(e => `<option>${esc(e)}</option>`).join("")}</select>` : ""}
      <label class="check"><input type="checkbox" id="goodonly"> Only good prices</label></div>
    <div id="sealed-table"></div>`;
  const drawLife = () => {
    const p = palette();
    const sets = withLife.filter(s => picked.has(s.code));
    chart("c-life", {type: "line", data: {datasets: sets.map((s, i) => ({label: withYear(s.name, s.code, s.year), data: s.hero.lifecycle.map(([x, y]) => ({x, y})),
      borderColor: p[i % p.length], backgroundColor: p[i % p.length], pointRadius: s.hero.lifecycle.length < 15 ? 3 : 0, borderWidth: 2, tension: .2}))},
      options: {interaction: {mode: "nearest", intersect: false}, scales: {x: {type: "linear", title: {display: true, text: "Days since release"}, min: 0}, y: moneyTicks},
        plugins: {tooltip: {callbacks: {title: c => `Day ${c[0].raw.x}`, label: c => `${c.dataset.label}: ${money(c.raw.y)}`}}}}});
  };
  $$("#life-pick button").forEach(b => b.onclick = () => { const c = b.dataset.code; picked.has(c) ? picked.delete(c) : picked.add(c); b.classList.toggle("primary"); store.set("life-" + sm.game, JSON.stringify([...picked])); drawLife(); });
  drawLife();
  const draw = () => {
    const era = $("#era")?.value, good = $("#goodonly").checked;
    const rows = sm.sealed.filter(r => (kind === "all" || r.kind === kind) && (!era || r.era === era) && (!good || (r.zone || "").startsWith("good")));
    table($("#sealed-table"), rows, sealedCols(sm, true), {sort: "price", empty: "No products match."});
  };
  $$("#kind button").forEach(b => b.onclick = () => { kind = b.dataset.k; store.set("sealed-kind-" + sm.game, kind); $$("#kind button").forEach(x => x.classList.toggle("on", x === b)); draw(); });
  $("#era")?.addEventListener("change", draw); $("#goodonly").onchange = draw;
  draw();
}

/* ---------------- Cards ---------------- */
async function viewCards(v, sm){
  v.innerHTML = `<div style="margin-top:22px"><h1>Card prices</h1><p class="lead" style="margin-top:6px">Search any card. Tap one for its price history, 90-day range and pull odds.</p></div>
    <div class="filters"><input id="q" type="search" placeholder="Search a card…" autocomplete="off">
      <select id="c-set"><option value="">Every set</option>${sm.sets.map(s => `<option value="${esc(s.code)}">${setLabel(s.name, s.code, s.year)}</option>`).join("")}</select>
      <select id="c-sort"><option value="price">Highest price</option><option value="d7">Biggest 7-day rise</option><option value="d7down">Biggest 7-day drop</option><option value="low">Closest to 90-day low</option><option value="name">Name</option></select>
      <label class="check"><input type="checkbox" id="c-low"> Only near 90-day low</label></div>
    <div id="card-table"><p class="muted">Loading cards…</p></div>`;
  const all = await cards(sm.game);
  const d7 = c => c.prices?.[c.printing]?.d7;
  const draw = () => {
    const q = $("#q").value.trim().toLowerCase(), set = $("#c-set").value, sort = $("#c-sort").value, low = $("#c-low").checked;
    let rows = all.filter(c => (!q || c.name.toLowerCase().includes(q)) && (!set || c.set === set) && (!low || c.zone === "good_low"));
    const f = {price: (a, b) => (b.price || 0) - (a.price || 0), name: (a, b) => a.name.localeCompare(b.name),
      d7: (a, b) => (d7(b) ?? -1e9) - (d7(a) ?? -1e9), d7down: (a, b) => (d7(a) ?? 1e9) - (d7(b) ?? 1e9),
      low: (a, b) => (a.low90 ? a.price / a.low90 : 9) - (b.low90 ? b.price / b.low90 : 9)};
    rows.sort(f[sort]);
    table($("#card-table"), rows, [
      {key: "name", label: "Card", html: c => `<div class="namecell">${thumb(c)}<div><div>${esc(c.name)}</div><div class="sub">${setLabel(c.set_name, c.set)} · ${esc(c.kind || "")}${c.number ? " · " + esc(c.number) : ""}${flags(c)}</div></div></div>`},
      {key: "price", label: "Price", num: 1, html: c => `<b>${money(c.price)}</b><div class="sub small muted">${esc(c.printing || "")}</div>`},
      {key: "d7", label: "7 days", num: 1, html: c => chg(d7(c))},
      {key: "zone", label: "Buy timing", cls: "hide-sm", html: c => quietChip(c.zone, c.zone_label) || '<span class="faint small">Normal</span>'},
      {key: "odds", label: "Pull odds", num: 1, cls: "hide-sm", html: c => c.boxes_per_hit ? oneIn(c.boxes_per_hit) : '<span class="faint">—</span>'},
    ], {onRow: c => openCard(sm.game, c.id, c.set), empty: "No cards match."});
  };
  ["#q", "#c-set", "#c-sort", "#c-low"].forEach(id => $(id).addEventListener("input", draw));
  draw();
}

/* ---------------- Movers ---------------- */
async function viewMovers(v, sm){
  const m = sm.movers;
  v.innerHTML = `<div style="margin-top:22px"><h1>Biggest price moves</h1><p class="lead" style="margin-top:6px">Cards and sealed products worth $2 or more.</p></div>
    <div class="grid g2"><div><h2>Up since yesterday</h2><div id="m1"></div></div><div><h2>Down since yesterday</h2><div id="m2"></div></div>
    <div><h2>Up this week</h2><div id="m3"></div></div><div><h2>Down this week</h2><div id="m4"></div></div></div>`;
  const cols = key => [
    {key: "n", label: "Name", html: r => `<div class="namecell">${r.sealed ? "" : thumb(r)}<div><a href="${href("set", r.set)}">${esc(r.name)}</a><div class="sub">${setLabel(r.set_name || r.set, r.set)} · ${esc(r.printing)}</div></div></div>`},
    {key: "p", label: "Price", num: 1, html: r => money(r.price)},
    {key: "c", label: "Change", num: 1, html: r => chg(r[key])},
  ];
  const empty = "Needs more price history. This fills in after a few daily updates.";
  table($("#m1"), m.up_1d.slice(0, 10), cols("d1"), {empty}); table($("#m2"), m.down_1d.slice(0, 10), cols("d1"), {empty});
  table($("#m3"), m.up_7d.slice(0, 10), cols("d7"), {empty}); table($("#m4"), m.down_7d.slice(0, 10), cols("d7"), {empty});
}

/* ---------------- How it works ---------------- */
async function viewHow(v, sm){
  const s = sm.selling, b = sm.buying, z = sm.zones, t = sm.benchmark_tax;
  v.innerHTML = `<div class="prose" style="margin-top:22px"><h1>How the numbers work</h1>
  <h2>Prices</h2><p>Every day this page pulls TCGplayer's prices through tcgcsv.com. "Market" is TCGplayer's market price, based on recent sales. When something has no recent sales, the cheapest listing is used instead. Cards marked <span class="chip warn plain">no recent sales</span> only have asking prices; in box values they're counted at the typical sale price for their rarity in that set, and asking prices of $9,999 or more are ignored. <span class="chip plain">price falling</span> means the cheapest listing is well under the last sale.</p>
  <h2>EV and return</h2><p><b>EV (expected value)</b> is what a pack, box or case holds on average at market prices. <b>EV after selling</b> takes off fees and shipping, and assumes you sell at the lower of the last sale and the cheapest listing, since you'd have to undercut current listings. <b>Return if you rip</b> is EV after selling compared with what you'd pay delivered.</p>
  <h2>Checks before a box value is shown</h2><p>Every day, each set's box value must pass checks: every counted card carries the set's own numbering, no counted card has a version label without known odds, and the box value hasn't jumped more than 30% overnight while the box price held steady. If a check fails, that set shows "being checked" instead of a number until it passes.</p>
  <h2>Buy timing</h2><p>Each product's price is compared with its own last 90 days:</p>
  <p>${zoneChip("good_msrp", "At or below MSRP")} costs no more than retail. ${zoneChip("good_low", "Near its 90-day low")} is within ${Math.round(z.near_low_pct * 100)}% of the lowest price in 90 days. ${zoneChip("high", "Above its usual price")} is at least ${Math.round(z.above_usual_pct * 100)}% over its 90-day average. ${zoneChip("normal", "In its normal range")} is everything else. A product needs ${z.min_points} saved prices in the last 90 days before it gets a label.</p>
  <p>"You'd pay" is the cheapest listing plus ${(b.sales_tax * 100).toFixed(2)}% sales tax and estimated shipping (about ${money(b.ship_sealed.box)} for a box, ${money(b.ship_single)} for a single card).</p>
  <h2>Is it worth opening?</h2><p><b>Average value inside</b> is what a box's cards are worth on average at market prices. Rare hits add a lot to the average even though most boxes never see one.</p>
  <p><b>You'd pocket</b> is what you'd get after selling: TCGplayer keeps about ${(s.fee_pct * 100).toFixed(2)}% of each sale, and each card shipped costs about ${money(s.per_card_cost)} in fees and supplies. Cards under ${money(s.sell_threshold)} count as bulk at ${money(s.bulk_value)} each.</p>
  <p><b>Out of 100 boxes</b> comes from opening 10,000 virtual boxes with the pack odds listed on each set's page. Each odds figure is labeled ${SOURCE.official}, ${SOURCE.community} or ${SOURCE.assumed}.</p>
  <h2>Buy it vs pull it</h2><p>For a chase card, "pull it" is the boxes you'd expect to open before hitting that exact card, times what each box loses after you sell the rest of its cards. When that's far above the card's price, buying the single is the better deal.</p>
  <h2>Compared with other investments</h2><p>For products out 90 days or more: what the MSRP would have earned in an S&amp;P 500 index fund or Treasury bills over the same time. After-tax figures use ${Math.round(t.collectibles_tax * 100)}% for collectibles, ${Math.round(t.stock_tax * 100)}% for stocks and ${Math.round(t.interest_tax * 100)}% for interest (federal long-term rates; state tax not included).</p>
  <h2>What this leaves out</h2><p>Your time listing cards, card condition (everything is priced as near mint), grading, and the fact that selling many copies at once pushes the price down. TCGplayer and eBay report sales to the IRS on a 1099-K.</p>
  <p class="muted small">Version ${esc(sm.version)} · built ${esc(sm.generated_at)} · ${sm.history_days} days of price history for ${esc(sm.name)}.</p></div>`;
}

/* ---------------- card detail modal ---------------- */
async function openCard(game, id, setCode, detail){
  id = +id;
  const modal = $("#modal"), body = $("#modal-body");
  modal.hidden = false; document.body.style.overflow = "hidden";
  body.innerHTML = '<p class="muted pad">Loading…</p>';
  let c = null, d = detail;
  if (!setCode){ const all = await cards(game); setCode = all.find(x => x.id === id)?.set; }
  if (setCode){ d = d || await setFile(game, setCode); c = d?.cards.find(x => x.id === id); }
  if (!c){ body.innerHTML = '<p class="pad muted">Card not found.</p>'; return; }
  const chase = d.chase.find(x => x.id === id) || c;
  const big = c.image ? c.image.replace(/_\d+w\.(jpg|png)$/i, "_in_1000x1000.$1") : null;
  body.innerHTML = `<div class="cardview"><div>${c.image ? `<img class="hero" src="${esc(big)}" onerror="this.onerror=null;this.src='${esc(c.image)}'" alt="${esc(c.name)}">` : '<div class="hero ph"></div>'}</div>
    <div><h2 style="margin-top:0">${esc(c.name)}</h2><div class="muted">${setLabel(d.name, d.code)} · ${esc(c.kind || "")}${c.number ? " · " + esc(c.number) : ""}${flags(c)}</div>
      <div style="display:flex;gap:10px;align-items:center;margin:12px 0"><span class="big">${money(c.price)}</span>${zoneChip(c.zone, c.zone_label)}</div>
      ${range(c.low90, c.high90, c.price)}
      <div class="table-scroll" style="margin-top:14px"><table class="data"><thead><tr><th>Printing</th><th class="num">Market</th><th class="num">Lowest listing</th><th class="num">7 days</th><th class="num">30 days</th></tr></thead><tbody>
        ${Object.entries(c.prices).map(([sub, p]) => `<tr><td>${esc(sub)}</td><td class="num">${money(p.market)}</td><td class="num">${money(p.low)}</td><td class="num">${chg(p.d7)}</td><td class="num">${chg(p.d30)}</td></tr>`).join("")}</tbody></table></div>
      <div class="kpis">${c.boxes_per_hit ? `<div class="kpi"><div class="k">Pull odds</div><div class="v">${oneIn(c.boxes_per_hit)}</div></div>` : ""}
        ${chase.buy_cost ? `<div class="kpi"><div class="k">Buy it</div><div class="v">${money(chase.buy_cost)}</div><div class="h">with tax and shipping</div></div>` : ""}
        ${chase.pull_cost != null && chase.pull_boxes >= 2 ? `<div class="kpi"><div class="k">Pull it</div><div class="v">${chase.pull_cost > 0 ? money(chase.pull_cost) : "$0"}</div><div class="h">expected net cost, over ~${Math.round(chase.pull_boxes).toLocaleString()} boxes</div></div>` : ""}</div>
      <a class="btn primary" href="${esc(c.url)}" target="_blank" rel="noopener">See it on TCGplayer</a></div></div>
    <div class="chart-box" style="padding:12px 0 0"><canvas id="c-card"></canvas></div>`;
  const ser = c.series || [];
  if (ser.length > 1){
    chart("c-card", {type: "line", data: {labels: ser.map(x => x[0]), datasets: [{label: `${c.printing} price`, data: ser.map(x => x[1]), borderColor: palette()[0], pointRadius: ser.length < 20 ? 3 : 0, borderWidth: 2, tension: .2}]},
      options: {scales: {x: {ticks: {maxTicksLimit: 6}}, y: moneyTicks}, plugins: {tooltip: tipMoney, legend: {display: false}}}});
  } else $("#c-card").parentElement.innerHTML = '<p class="note">Price history builds up with each daily update.</p>';
}
function closeModal(){
  $("#modal").hidden = true; document.body.style.overflow = "";
  if (S.charts["c-card"]) { S.charts["c-card"].destroy(); delete S.charts["c-card"]; }
  if (S.route.view === "card") history.replaceState(null, "", href("cards"));
}
$("#modal").addEventListener("click", e => { if (e.target.id === "modal" || e.target.closest(".close")) closeModal(); });

/* ---------------- big picture on hover (tap on phones) ---------------- */
(function(){
  const box = document.createElement("div"); box.id = "preview";
  const img = document.createElement("img"); img.alt = ""; box.appendChild(img); document.body.appendChild(box);
  const big = src => src.replace(/_\d+w\.(jpg|png)$/i, "_in_1000x1000.$1");
  let tapped = false;
  const show = (el, x, y, pinned) => {
    const small = el.getAttribute("src");
    img.onerror = () => { img.onerror = null; img.src = small; };
    img.src = big(small);
    box.classList.toggle("pinned", !!pinned); box.classList.add("on");
    if (!pinned) place(x, y);
  };
  const place = (x, y) => {
    const w = box.offsetWidth || 300, h = box.offsetHeight || 420, pad = 16;
    let left = x + 24, top = y - h / 2;
    if (left + w + pad > innerWidth) left = x - w - 24;
    top = Math.max(pad, Math.min(top, innerHeight - h - pad));
    box.style.left = Math.max(pad, left) + "px"; box.style.top = top + "px";
  };
  const hide = () => { box.classList.remove("on", "pinned"); tapped = false; };
  const canHover = matchMedia("(hover: hover)").matches;
  const isThumb = t => t.matches && t.matches("img.thumb");
  document.addEventListener("mouseover", e => { if (canHover && isThumb(e.target)) show(e.target, e.clientX, e.clientY); });
  document.addEventListener("mousemove", e => { if (canHover && isThumb(e.target) && !box.classList.contains("pinned")) place(e.clientX, e.clientY); });
  document.addEventListener("mouseout", e => { if (canHover && isThumb(e.target) && !box.classList.contains("pinned")) hide(); });
  document.addEventListener("click", e => {
    if (isThumb(e.target) && !canHover){ e.preventDefault(); e.stopPropagation(); if (tapped) return hide(); show(e.target, 0, 0, true); tapped = true; return; }
    if (box.classList.contains("pinned")) hide();
  }, true);
  addEventListener("scroll", () => { if (!box.classList.contains("pinned")) hide(); }, {passive: true});
  addEventListener("keydown", e => { if (e.key === "Escape"){ hide(); if (!$("#modal").hidden) closeModal(); } });
})();

/* ---------------- theme ---------------- */
(function(){
  const t = store.get("theme"); if (t) document.documentElement.dataset.theme = t;
  $("#theme").onclick = () => {
    const dark = matchMedia("(prefers-color-scheme: dark)").matches;
    const cur = document.documentElement.dataset.theme || (dark ? "dark" : "light");
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next; store.set("theme", next); render();
  };
})();

/* ---------------- start ---------------- */
getJSON("data/games.json").then(idx => {
  S.games = idx.games;
  S.build = idx.generated_at || idx.version;
  addEventListener("hashchange", render);
  render();
}).catch(e => { console.error(e); $("#view").innerHTML = '<p class="pad muted">Couldn\'t load the price data. Try refreshing.</p>'; });
