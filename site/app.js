"use strict";
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
const money = v => v == null || isNaN(v) ? "—" : (Math.abs(v) >= 100 ? "$" + Math.round(v).toLocaleString() : "$" + v.toFixed(2));
const pct = (v, plus = true) => v == null ? "—" : (plus && v > 0 ? "+" : "") + (v * 100).toFixed(Math.abs(v) < 0.1 ? 1 : 0) + "%";
const chg = v => v == null ? '<span class="muted">—</span>' : `<span class="${v > 0 ? "up" : v < 0 ? "down" : ""}">${v > 0 ? "+" : ""}${v.toFixed(1)}%</span>`;
const oneIn = n => n == null ? "—" : n < 1.05 ? "most boxes" : n < 10 ? `1 in ${n.toFixed(1)} boxes` : `1 in ${Math.round(n).toLocaleString()} boxes`;
const SOURCE_PILL = {official: '<span class="pill good">Riot</span>', community: '<span class="pill warn">Community estimate</span>', assumed: '<span class="pill bad">Our assumption</span>'};
const store = {get(k){try{return localStorage.getItem(k)}catch(e){return null}}, set(k,v){try{localStorage.setItem(k,v)}catch(e){}}};

let D, CARDS, charts = {}, currentSet = null;

function css(name){return getComputedStyle(document.documentElement).getPropertyValue(name).trim()}
function palette(){return ["--c1","--c2","--c3","--c4","--c5","--c6"].map(css)}
function chart(id, cfg){
  if (charts[id]) charts[id].destroy();
  const ink = css("--muted"), line = css("--line");
  Chart.defaults.color = ink; Chart.defaults.borderColor = line; Chart.defaults.font.family = "Inter, system-ui, sans-serif";
  cfg.options = Object.assign({responsive:true, maintainAspectRatio:false, interaction:{mode:"index", intersect:false},
    plugins:{legend:{labels:{boxWidth:12, boxHeight:12}}}}, cfg.options || {});
  charts[id] = new Chart(document.getElementById(id), cfg);
}

/* ---------------- theme + tabs ---------------- */
(function(){
  const t = store.get("theme"); if (t) document.documentElement.dataset.theme = t;
  $("#theme").onclick = () => {
    const dark = matchMedia("(prefers-color-scheme: dark)").matches;
    const cur = document.documentElement.dataset.theme || (dark ? "dark" : "light");
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next; store.set("theme", next); renderAll();
  };
  document.querySelectorAll("#tabs button").forEach(b => b.onclick = () => showTab(b.dataset.tab));
})();
function showTab(name){
  document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach(s => s.classList.toggle("on", s.id === name));
  store.set("tab", name);
  if (name === "set") renderSet(); if (name === "sealed") renderSealed();
}

/* ---------------- helpers ---------------- */
// Share of simulated boxes worth at least `x`, read off the stored percentiles.
function shareAtLeast(quantiles, x){
  const n = quantiles.length - 1;
  if (x <= quantiles[0]) return 1; if (x > quantiles[n]) return 0;
  for (let i = 1; i <= n; i++){
    if (quantiles[i] >= x){
      const lo = quantiles[i-1], hi = quantiles[i];
      const f = hi === lo ? 0 : (x - lo) / (hi - lo);
      return 1 - ((i - 1 + f) / n);
    }
  }
  return 0;
}
const released = s => s.released;

/* ---------------- overview ---------------- */
function renderOverview(){
  const alerts = [];
  for (const n of D.new_sets || []) alerts.push(`New set spotted on TCGplayer: <b>${esc(n.name)}</b>. Pack odds need adding before it gets a box value.`);
  for (const s of D.sets) if (!s.released) alerts.push(`<b>${esc(s.name)}</b> releases ${new Date(s.release + "T12:00").toLocaleDateString(undefined,{month:"short",day:"numeric",year:"numeric"})}. Box pre-orders are ${money(s.box?.market ?? s.box?.low)}, against an MSRP of ${money(s.msrp_box)}.`);
  $("#alerts").innerHTML = alerts.map(a => `<div class="alert">${a}</div>`).join("");

  const rows = D.sets.filter(s => s.ev);
  $("#ov-table").innerHTML = `<thead><tr><th>Set</th><th class="num">Box price</th><th class="num hide-sm">vs MSRP</th>
    <th class="num">Average value inside</th><th class="num">You'd pocket (average)</th><th class="num">Typical box (pocket)</th>
    <th class="num">Chance it pays for itself</th><th>Open or hold?</th></tr></thead><tbody>` +
    rows.map(s => {
      const b = s.box || {}, e = s.ev, sim = s.sim.net;
      const beat = sim.beat_market;
      const openWins = s.open_vs_hold.sell_sealed_net != null && e.box_net >= s.open_vs_hold.sell_sealed_net;
      return `<tr><td><a href="#" data-set="${s.code}"><b>${esc(s.name)}</b></a><div class="muted small">${s.code} · ${s.release}</div></td>
      <td class="num">${money(b.market)}</td><td class="num hide-sm">${pct(b.vs_msrp)}</td>
      <td class="num">${money(e.box_sticker)}</td><td class="num"><b>${money(e.box_net)}</b></td><td class="num">${money(sim.median)}</td>
      <td class="num">${beat == null ? "—" : Math.round(beat * 100) + "%"}</td>
      <td>${openWins ? '<span class="pill good">Open</span>' : '<span class="pill info">Hold sealed</span>'}</td></tr>`;
    }).join("") + "</tbody>";
  document.querySelectorAll("#ov-table [data-set]").forEach(a => a.onclick = ev => {ev.preventDefault(); currentSet = a.dataset.set; showTab("set");});

  const p = palette();
  chart("ov-chart", {type:"bar", data:{labels: rows.map(s => s.name), datasets:[
    {label:"Box price today", data: rows.map(s => s.box?.market), backgroundColor:p[0]},
    {label:"Average value inside", data: rows.map(s => s.ev.box_sticker), backgroundColor:p[1]},
    {label:"You'd pocket (average)", data: rows.map(s => s.ev.box_net), backgroundColor:p[2]},
    {label:"Typical box (pocket)", data: rows.map(s => s.sim.net.median), backgroundColor:p[3]},
  ]}, options:{scales:{y:{ticks:{callback:v => "$" + v}}}, plugins:{tooltip:{callbacks:{label:c => `${c.dataset.label}: ${money(c.raw)}`}}}}});
}

/* ---------------- set detail ---------------- */
function renderSet(){
  const sets = D.sets;
  if (!currentSet) currentSet = store.get("set") || (sets.filter(s => s.ev).slice(-1)[0] || sets[0]).code;
  store.set("set", currentSet);
  $("#set-picker").innerHTML = sets.map(s => `<button data-code="${s.code}" class="${s.code === currentSet ? "on" : ""}">${esc(s.name)}</button>`).join("");
  document.querySelectorAll("#set-picker button").forEach(b => b.onclick = () => {currentSet = b.dataset.code; renderSet();});
  const s = sets.find(x => x.code === currentSet) || sets[0];
  const body = $("#set-body");
  const b = s.box || {};
  if (!s.ev){
    body.innerHTML = `<h2>${esc(s.name)}</h2><p class="lead">${esc(s.note || "")}</p>${sealedMini(s)}`;
    return;
  }
  const savedPaid = parseFloat(store.get("paid-" + s.code));
  const paid0 = !isNaN(savedPaid) ? savedPaid : (b.market || s.msrp_box);
  body.innerHTML = `
    <h2>${esc(s.name)} <span class="muted small">${s.code} · released ${s.release}</span></h2>
    <div class="paid"><label for="paid"><b>What I paid for a box</b></label> <input id="paid" type="number" min="1" step="1" value="${paid0.toFixed(2)}">
      <button class="ghost" id="paid-mkt">Market ${money(b.market)}</button><button class="ghost" id="paid-msrp">MSRP ${money(s.msrp_box)}</button></div>
    <div class="cards" id="set-cards"></div>
    <div class="verdict" id="set-verdict"></div>
    <h3>What a box is worth, out of 10,000 simulated boxes</h3>
    <p class="lead">Each point is one simulated box, sorted from worst to best. The flat line is what you paid. Boxes above the line paid for themselves.</p>
    <div class="chart-box"><canvas id="dist-chart"></canvas></div>
    <div class="grid2">
      <div><h3>Where the value comes from (per box)</h3><div class="table-scroll"><table class="data">${contribTable(s)}</table></div></div>
      <div><h3>How often you hit (per box)</h3><div class="table-scroll"><table class="data">${hitTable(s)}</table></div></div>
    </div>
    <h3>Chase cards</h3>
    <div class="table-scroll"><table class="data">${chaseTable(s)}</table></div>
    ${s.ev_series && s.ev_series.length > 1 ? `<h3>Box value over time</h3><div class="chart-box"><canvas id="evh-chart"></canvas></div>` : `<p class="muted small">Value history starts building from the first daily update.</p>`}
    <h3>Sealed ${esc(s.name)} products</h3>${sealedMini(s)}
    <h3>Pack odds used</h3>
    <div class="table-scroll"><table class="data"><thead><tr><th>What</th><th>Rate</th><th>Source</th></tr></thead><tbody>
      ${s.odds.map(o => `<tr><td>${esc(o.what)}${o.in_set === false ? ' <span class="muted small">(none in this set)</span>' : ""}</td><td>${esc(o.rate || "")}</td><td>${SOURCE_PILL[o.source] || esc(o.source)}</td></tr>`).join("")}
    </tbody></table></div>
    <p class="muted small">Cards in this set's pack math: ${Object.entries(s.card_counts).map(([k,v]) => `${v} ${esc(k.toLowerCase())}`).join(", ")}.</p>`;
  const update = () => {
    const paid = parseFloat($("#paid").value) || b.market || s.msrp_box;
    store.set("paid-" + s.code, String(paid));
    const e = s.ev, n = s.sim.net, st = s.sim.sticker;
    const beatNet = shareAtLeast(n.quantiles, paid), beatSt = shareAtLeast(st.quantiles, paid);
    const sellNet = s.open_vs_hold.sell_sealed_net;
    $("#set-cards").innerHTML = [
      ["Average value inside", money(e.box_sticker), `At market prices. Return ${pct(e.box_sticker / paid - 1)}`],
      ["You'd pocket (average)", money(e.box_net), `After fees, shipping and bulk. Return ${pct(e.box_net / paid - 1)}`],
      ["Typical box (pocket)", money(n.median), `Half of boxes do better, half worse`],
      ["Chance it pays for itself", Math.round(beatNet * 100) + "%", `${Math.round(beatSt * 100)}% before selling costs`],
      ["Bad box / great box", `${money(n.p10)} / ${money(n.p90)}`, "1 in 10 boxes is worse than the first, 1 in 10 better than the second"],
      ["Sell it sealed instead", money(sellNet), `Today's market, after fees and shipping. ${pct(sellNet / paid - 1)} on what you paid`],
    ].map(([k, v, h]) => `<div class="card"><div class="k">${k}</div><div class="v">${v}</div><div class="h">${h}</div></div>`).join("");
    const gap = e.box_net - paid;
    $("#set-verdict").innerHTML = `<b>${esc(s.open_vs_hold.verdict)}</b> At ${money(paid)}, an average box ${gap >= 0 ? "makes" : "loses"} about ${money(Math.abs(gap))} once you sell the cards, and ${Math.round(beatNet * 100)} in 100 boxes come out ahead.`;
    const p = palette();
    const xs = n.quantiles.map((_, i) => i / 2);
    chart("dist-chart", {type:"line", data:{labels: xs, datasets:[
      {label:"You'd pocket", data:n.quantiles, borderColor:p[0], backgroundColor:p[0], pointRadius:0, borderWidth:2, tension:.2},
      {label:"Market value", data:st.quantiles, borderColor:p[1], backgroundColor:p[1], pointRadius:0, borderWidth:1.5, borderDash:[4,3], tension:.2},
      {label:"What you paid", data:xs.map(() => paid), borderColor:p[3], backgroundColor:p[3], pointRadius:0, borderWidth:1.5},
    ]}, options:{scales:{x:{title:{display:true, text:"Boxes, worst to best (percent)"}, ticks:{callback:(v,i) => i % 20 === 0 ? xs[i] + "%" : ""}},
      y:{type:"logarithmic", ticks:{callback:v => [10,20,50,100,200,500,1000,2000,5000].includes(v) ? "$" + v : ""}}},
      plugins:{tooltip:{callbacks:{title:c => `${c[0].label}% of boxes are worse`, label:c => `${c.dataset.label}: ${money(c.raw)}`}}}}});
  };
  $("#paid").oninput = update;
  $("#paid-mkt").onclick = () => {$("#paid").value = (b.market || 0).toFixed(2); update();};
  $("#paid-msrp").onclick = () => {$("#paid").value = s.msrp_box.toFixed(2); update();};
  update();
  if (s.ev_series && s.ev_series.length > 1){
    const p = palette();
    chart("evh-chart", {type:"line", data:{labels:s.ev_series.map(r => r[0]), datasets:[
      {label:"Box price", data:s.ev_series.map(r => r[3]), borderColor:p[0], pointRadius:0, borderWidth:2, spanGaps:true},
      {label:"Average value inside", data:s.ev_series.map(r => r[1]), borderColor:p[1], pointRadius:0, borderWidth:2},
      {label:"You'd pocket", data:s.ev_series.map(r => r[2]), borderColor:p[2], pointRadius:0, borderWidth:2},
    ]}, options:{scales:{x:{ticks:{maxTicksLimit:8}}, y:{ticks:{callback:v => "$" + v}}}, plugins:{tooltip:{callbacks:{label:c => `${c.dataset.label}: ${money(c.raw)}`}}}}});
  }
}
function contribTable(s){
  const max = Math.max(...s.contrib.map(c => c.box_sticker));
  return `<thead><tr><th>Cards</th><th class="num">Market</th><th class="num">Pocket</th><th></th></tr></thead><tbody>` +
    s.contrib.map(c => `<tr><td>${esc(c.label)}</td><td class="num">${money(c.box_sticker)}</td><td class="num">${money(c.box_net)}</td>
      <td style="width:30%"><div class="bar" style="width:${(c.box_sticker / max * 100).toFixed(1)}%"></div></td></tr>`).join("") + "</tbody>";
}
function hitTable(s){
  return `<thead><tr><th>Hit</th><th class="num">Per box</th><th class="num">Chance in a box</th><th class="num">About</th></tr></thead><tbody>` +
    s.hit_odds.map(h => `<tr><td>${esc(h.label)}</td><td class="num">${h.per_box.toFixed(h.per_box < 1 ? 2 : 1)}</td>
      <td class="num">${Math.round(h.chance_in_box * 100)}%</td><td class="num">${h.boxes_per_hit < 1 ? `${(1/h.boxes_per_hit).toFixed(1)} per box` : oneIn(h.boxes_per_hit)}</td></tr>`).join("") + "</tbody>";
}
function chaseTable(s){
  return `<thead><tr><th></th><th>Card</th><th>Kind</th><th class="num">Price</th><th class="num">Odds for this exact card</th></tr></thead><tbody>` +
    s.chase.map(c => `<tr><td><img class="thumb" loading="lazy" src="${esc(c.image)}" alt=""></td>
      <td><a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.name)}</a> <span class="muted small">${esc(c.number || "")}</span>
      ${c.thin ? ' <span class="pill warn" title="Few recent sales or a wide gap between listings and sales">thin market</span>' : ""}</td>
      <td>${esc(c.label)}</td><td class="num">${money(c.price)}</td><td class="num">${oneIn(c.boxes_per_hit)}</td></tr>`).join("") + "</tbody>";
}
function sealedMini(s){
  const rows = [["Booster box", s.box], ["Case (6 boxes)", s.case], ["Booster pack", s.pack]].filter(r => r[1]);
  if (!rows.length) return '<p class="muted">No sealed prices yet.</p>';
  return `<div class="table-scroll"><table class="data"><thead><tr><th>Product</th><th class="num">Market</th><th class="num">MSRP</th><th class="num">vs MSRP</th><th class="num hide-sm">Per year</th><th class="num">30 days</th></tr></thead><tbody>` +
    rows.map(([k, p]) => `<tr><td><a href="${esc(p.url)}" target="_blank" rel="noopener">${k}</a>${p.presale ? ' <span class="pill info">pre-order</span>' : ""}</td>
      <td class="num">${money(p.market ?? p.low)}</td><td class="num">${money(p.msrp)}</td><td class="num">${pct(p.vs_msrp)}</td>
      <td class="num hide-sm">${p.annualized == null ? '<span class="muted">too new</span>' : pct(p.annualized)}</td><td class="num">${chg(p.change_30d)}</td></tr>`).join("") + "</tbody></table></div>";
}

/* ---------------- sealed ---------------- */
function renderSealed(){
  const all = $("#sealed-all").checked;
  const rows = D.sealed.filter(r => all || ["box", "case", "pack"].includes(r.kind));
  $("#sealed-table").innerHTML = `<thead><tr><th>Product</th><th class="num">Market</th><th class="num">Lowest listing</th><th class="num">MSRP</th>
    <th class="num">vs MSRP</th><th class="num">Per year</th><th class="num">If sold</th><th class="num">7 days</th><th class="num">30 days</th></tr></thead><tbody>` +
    rows.map(r => `<tr><td><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.name)}</a>${r.presale ? ' <span class="pill info">pre-order</span>' : ""}</td>
      <td class="num">${money(r.market)}</td><td class="num">${money(r.low)}</td><td class="num">${money(r.msrp)}</td><td class="num">${pct(r.vs_msrp)}</td>
      <td class="num">${r.annualized == null ? (r.msrp ? '<span class="muted">too new</span>' : "—") : pct(r.annualized)}</td>
      <td class="num">${r.net_if_sold == null ? "—" : money(r.net_if_sold)}</td><td class="num">${chg(r.change_7d)}</td><td class="num">${chg(r.change_30d)}</td></tr>`).join("") + "</tbody>";
  const boxes = D.sets.filter(s => s.box && s.box.series && s.box.series.length);
  const dates = [...new Set(boxes.flatMap(s => s.box.series.map(r => r[0])))].sort();
  const p = palette();
  chart("sealed-chart", {type:"line", data:{labels:dates, datasets: boxes.map((s, i) => {
    const m = Object.fromEntries(s.box.series);
    return {label:`${s.name} box`, data:dates.map(d => m[d] ?? null), borderColor:p[i % p.length], backgroundColor:p[i % p.length], pointRadius:dates.length < 3 ? 4 : 0, borderWidth:2, spanGaps:true};
  })}, options:{scales:{x:{ticks:{maxTicksLimit:8}}, y:{ticks:{callback:v => "$" + v}}}, plugins:{tooltip:{callbacks:{label:c => `${c.dataset.label}: ${money(c.raw)}`}}}}});
}
$("#sealed-all").onchange = renderSealed;

/* ---------------- cards ---------------- */
function renderCardsFilters(){
  const sets = [...new Set(CARDS.map(c => c.set))];
  const names = Object.fromEntries(D.sets.map(s => [s.code, s.name]));
  $("#card-set").innerHTML = `<option value="">All sets</option>` + sets.map(s => `<option value="${s}">${esc(names[s] || s)}</option>`).join("");
  const kinds = [...new Set(CARDS.map(c => c.kind))].filter(Boolean);
  $("#card-kind").innerHTML = `<option value="">All kinds</option>` + kinds.map(k => `<option>${esc(k)}</option>`).join("");
  ["#q", "#card-set", "#card-kind", "#card-sort"].forEach(id => $(id).oninput = renderCards);
}
const best = c => Math.max(c.normal?.market || 0, c.foil?.market || 0, (!c.normal?.market && !c.foil?.market) ? (c.normal?.low || c.foil?.low || 0) : 0);
const bestD7 = c => (c.foil?.market || 0) > (c.normal?.market || 0) ? c.foil?.d7 : c.normal?.d7;
function renderCards(){
  const q = $("#q").value.trim().toLowerCase(), set = $("#card-set").value, kind = $("#card-kind").value, sort = $("#card-sort").value;
  let rows = CARDS.filter(c => (!q || c.name.toLowerCase().includes(q)) && (!set || c.set === set) && (!kind || c.kind === kind));
  const sorters = {price:(a, b) => best(b) - best(a), name:(a, b) => a.name.localeCompare(b.name),
    d7:(a, b) => (bestD7(b) ?? -1e9) - (bestD7(a) ?? -1e9), d7down:(a, b) => (bestD7(a) ?? 1e9) - (bestD7(b) ?? 1e9)};
  rows.sort(sorters[sort]);
  const total = rows.length; rows = rows.slice(0, 200);
  $("#card-table").innerHTML = `<thead><tr><th></th><th>Card</th><th class="hide-sm">Set</th><th class="num">Normal</th><th class="num">Foil</th><th class="num">7 days</th><th class="num hide-sm">30 days</th><th class="num">Pull odds</th></tr></thead><tbody>` +
    rows.map(c => `<tr><td><img class="thumb" loading="lazy" src="${esc(c.image)}" alt=""></td>
      <td><a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.name)}</a><div class="muted small">${esc(c.kind)} · ${esc(c.number || "")}${c.thin ? ' · <span class="pill warn">thin market</span>' : ""}</div></td>
      <td class="hide-sm">${esc(c.set)}</td><td class="num">${money(c.normal?.market ?? c.normal?.low)}</td><td class="num">${money(c.foil?.market ?? c.foil?.low)}</td>
      <td class="num">${chg(bestD7(c))}</td><td class="num hide-sm">${chg((c.foil?.market || 0) > (c.normal?.market || 0) ? c.foil?.d30 : c.normal?.d30)}</td>
      <td class="num">${c.boxes_per_hit ? oneIn(c.boxes_per_hit) : '<span class="muted">not in packs</span>'}</td></tr>`).join("") + "</tbody>";
  $("#card-count").textContent = total > 200 ? `Showing 200 of ${total}. Narrow the search to see more.` : `${total} cards`;
}

/* ---------------- movers ---------------- */
function renderMovers(){
  const m = D.movers;
  const list = (title, rows, key) => `<div><h3>${title}</h3><div class="table-scroll"><table class="data"><tbody>` +
    (rows.length ? rows.slice(0, 10).map(r => `<tr><td><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.name)}</a><div class="muted small">${esc(r.set)} · ${esc(r.printing)}</div></td>
      <td class="num">${money(r.price)}</td><td class="num">${chg(r[key])}</td></tr>`).join("") : `<tr><td class="muted">Needs more price history. This fills in after a few daily updates.</td></tr>`) + "</tbody></table></div></div>";
  $("#movers-body").innerHTML = list("Up since yesterday", m.up_1d, "d1") + list("Down since yesterday", m.down_1d, "d1") +
    list("Up this week", m.up_7d, "d7") + list("Down this week", m.down_7d, "d7");
}

/* ---------------- how ---------------- */
function renderHow(){
  const s = D.selling;
  $("#how-body").innerHTML = `
  <p><b>Prices.</b> Every day this page pulls TCGplayer's prices through tcgcsv.com. "Market" is TCGplayer's market price, based on recent sales. When a card has no recent sales, the cheapest listing is used instead. Cards marked <span class="pill warn">thin market</span> have no recent sale price, or listings far from the sale price, so treat their price as rough.</p>
  <p><b>What's in a pack.</b> 14 cards: 7 commons, 3 uncommons, 2 rare-or-better, 1 foil of any rarity, and 1 rune or token. About 1 pack in 4 has an Epic. Alternate arts, Overnumbered, Signature and Ultimate cards take the foil card's place when they show up. Each set's detail page lists every rate used and where it came from: <span class="pill good">Riot</span> means Riot published it, <span class="pill warn">Community estimate</span> means it comes from fans counting their box openings, and <span class="pill bad">Our assumption</span> means nobody has good data yet. Within a rarity, every card is treated as equally likely.</p>
  <p><b>Average value inside.</b> The cards you'd get per box, on average, at market prices. Rare hits like Signatures add a lot to the average even though most boxes never see one.</p>
  <p><b>You'd pocket.</b> What you'd get after actually selling: TCGplayer keeps about ${(s.fee_pct * 100).toFixed(2)}% of each sale, and each card shipped costs about ${money(s.per_card_cost)} in order fee, envelope, stamp and toploader. Cards under ${money(s.sell_threshold)} aren't worth listing on their own, so they count as bulk at ${money(s.bulk_value)} each.</p>
  <p><b>Typical box and chance it pays for itself.</b> The page opens 10,000 virtual boxes using the odds above. The typical box is the middle one: half of boxes do better and half do worse. The chance it pays for itself is the share of those boxes worth at least what you paid, after selling costs.</p>
  <p><b>Sealed.</b> "vs MSRP" compares today's price with the $${D.sets[0]?.msrp_box ?? 120} retail price. "Per year" turns that into a yearly growth rate, like an interest rate, once a set has been out 90 days. "If sold" takes off ${(s.sealed_fee_pct * 100).toFixed(2)}% fees and ${money(s.sealed_ship_cost)} shipping.</p>
  <p><b>What this leaves out.</b> Sales tax on what you buy, your time listing cards, card condition (everything is priced as near mint), and the fact that selling a lot of one card at once pushes its price down. Collectibles profits are taxed at up to 28% when held over a year, and TCGplayer and eBay report sales to the IRS on a 1099-K.</p>
  <p class="muted small">Built ${esc(D.generated_at)}. Version ${esc(D.version)}. ${D.history_days} days of price history.</p>`;
}

function renderAll(){
  renderOverview(); renderMovers(); renderHow(); renderCards();
  if ($("#set").classList.contains("on")) renderSet();
  if ($("#sealed").classList.contains("on")) renderSealed();
}

Promise.all([fetch("data/latest.json").then(r => r.json()), fetch("data/cards.json").then(r => r.json())]).then(([d, c]) => {
  D = d; CARDS = c;
  const date = new Date(D.price_date + "T12:00").toLocaleDateString(undefined, {weekday:"short", month:"short", day:"numeric", year:"numeric"});
  $("#stamp").textContent = `TCGplayer prices from ${date} · updates daily`;
  renderCardsFilters(); renderAll();
  showTab(store.get("tab") || "overview");
}).catch(e => { $("#stamp").textContent = "Couldn't load price data. Try refreshing."; console.error(e); });
