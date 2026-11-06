// Layout check: opens the built dashboard in a real browser at phone, tablet and desktop sizes
// and fails if anything spills out of its box, the page scrolls sideways, or the page throws an error.
//
//   node tests/layout/check.js http://localhost:8765/ [path-to-chart.umd.js]
//
// Runs in CI before every publish, against that day's real data.
const { chromium } = require("playwright");

const BASE = process.argv[2] || "http://localhost:8765/";
const LOCAL_CHART = process.argv[3];
const VIEWPORTS = [
  { name: "phone", width: 375, height: 812, isMobile: true, hasTouch: true },
  { name: "tablet", width: 768, height: 1024 },
  { name: "laptop", width: 1280, height: 800 },
  { name: "wide", width: 1920, height: 1080 },
];
// Boxes whose contents must stay inside them. Tables scroll on purpose, so they're only checked as a whole.
const BOXES = [".signal", ".settile", ".cardtile", ".kpi", ".panel", ".alert", ".verdict", ".sethead", ".paid", ".modal-card", ".buybox", ".range", ".era-head"];

async function routes(page) {
  const games = await page.evaluate(async (base) => (await (await fetch(base + "data/games.json")).json()).games, BASE);
  const out = [];
  for (const g of games) {
    for (const v of ["today", "sets", "sealed", "cards", "movers", "how"]) out.push(`${g.id}/${v}`);
    const sm = await page.evaluate(async ([base, id]) => (await (await fetch(`${base}data/${id}/summary.json`)).json()), [BASE, g.id]);
    // newest sets, sets with box values, and the sets whose products have the longest names
    const longest = [...sm.sets].sort((a, b) => ((b.hero || {}).name || "").length - ((a.hero || {}).name || "").length);
    const pick = [...sm.sets.slice(0, 4), ...sm.sets.filter(s => s.modeled).slice(0, 3), ...longest.slice(0, 4)];
    for (const s of [...new Map(pick.map(s => [s.code, s])).values()]) out.push(`${g.id}/set/${encodeURIComponent(s.code)}`);
  }
  return out;
}

async function check(page, label) {
  return page.evaluate(([boxes, label]) => {
    const bad = [];
    const vw = document.documentElement.clientWidth;
    if (document.documentElement.scrollWidth > vw + 1) bad.push(`${label}: page scrolls sideways (${document.documentElement.scrollWidth}px wide in a ${vw}px window)`);
    const visible = el => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none"; };
    for (const sel of boxes) {
      for (const box of document.querySelectorAll(sel)) {
        if (!visible(box)) continue;
        const b = box.getBoundingClientRect();
        for (const el of box.querySelectorAll("*")) {
          if (el.closest(".table-scroll") && el.closest(".table-scroll") !== box && box.contains(el.closest(".table-scroll"))) continue;
          if (el.closest("svg") && el.tagName.toLowerCase() !== "svg") continue;
          if (!visible(el)) continue;
          const r = el.getBoundingClientRect();
          if (r.right > b.right + 1.5 || r.left < b.left - 1.5) {
            const text = (el.textContent || el.getAttribute("src") || el.tagName).trim().slice(0, 60);
            bad.push(`${label}: "${text}" sticks out of ${sel} by ${Math.round(Math.max(r.right - b.right, b.left - r.left))}px`);
            break;
          }
        }
      }
    }
    // a table may never be wider than its column; on tablets and up it must also fit without sideways scrolling
    for (const t of document.querySelectorAll(".table-scroll")) {
      if (!visible(t)) continue;
      const p = t.parentElement.getBoundingClientRect(), r = t.getBoundingClientRect();
      if (r.right > p.right + 1.5) bad.push(`${label}: a table is wider than its column by ${Math.round(r.right - p.right)}px`);
      if (vw >= 700 && t.scrollWidth > t.clientWidth + 1) {
        const head = [...t.querySelectorAll("th")].map(th => th.textContent.trim()).filter(Boolean).slice(0, 3).join(", ");
        bad.push(`${label}: table (${head}) is cut off; ${t.scrollWidth - t.clientWidth}px hidden off the side`);
      }
    }
    return [...new Set(bad)];
  }, [BOXES, label]);
}

(async () => {
  const browser = await chromium.launch();
  const problems = [];
  let pages = 0;
  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, isMobile: !!vp.isMobile, hasTouch: !!vp.hasTouch });
    const page = await ctx.newPage();
    page.on("pageerror", e => problems.push(`${vp.name}: page error: ${e.message}`));
    if (LOCAL_CHART) await page.route("**/chart.umd.min.js", r => r.fulfill({ path: LOCAL_CHART, contentType: "application/javascript" }));
    await page.goto(BASE);
    const list = await routes(page);
    for (const rt of list) {
      await page.goto(`${BASE}#/${rt}`);
      await page.waitForFunction(() => !document.querySelector("#view .pad") || !/Loading/.test(document.querySelector("#view").textContent), null, { timeout: 15000 }).catch(() => {});
      await page.waitForTimeout(400);
      problems.push(...await check(page, `${vp.name} #/${rt}`));
      pages++;
      // stress pass: give every label and price the longest text it could ever show, so a rare label
      // (like a set going "Above its usual price" for the first time) can't break the page on a real day
      await page.evaluate(() => {
        const longest = ["Above its usual price", "Not enough history yet", "Near its 90-day low", "In its normal range"]
          .reduce((a, b) => (b.length > a.length ? b : a));
        document.querySelectorAll(".chip").forEach(c => { c.textContent = c.textContent.length < longest.length ? longest : c.textContent; });
        document.querySelectorAll(".settile .price, .signal .p, .big").forEach(p => { p.textContent = "$12,345.67"; });
      });
      problems.push(...(await check(page, `${vp.name} #/${rt} (longest labels)`)));
      // open the first chase card's pop-up on set pages
      if (rt.includes("/set/")) {
        const row = page.locator("#chase tbody tr[data-i]").first();
        if (await row.count()) {
          await row.click({ position: { x: 5, y: 5 } }).catch(() => {});
          await page.waitForTimeout(500);
          problems.push(...await check(page, `${vp.name} #/${rt} (card pop-up)`));
          await page.keyboard.press("Escape");
        }
      }
    }
    await ctx.close();
  }
  await browser.close();
  console.log(`Checked ${pages} pages at ${VIEWPORTS.length} screen sizes.`);
  if (problems.length) {
    // group repeats so one kind of problem can't hide another
    const groups = new Map();
    for (const p of new Set(problems)) {
      const i = p.indexOf(": ");
      const what = p.slice(i + 2).replace(/\d+px/g, "Npx"), where = p.slice(0, i);
      if (!groups.has(what)) groups.set(what, []);
      groups.get(what).push(where);
    }
    console.log(`\n${problems.length} layout problem(s), ${groups.size} kind(s):`);
    for (const [what, where] of groups) console.log(`- ${what}  [${where.length}x, e.g. ${where.slice(0, 3).join(" | ")}]`);
    process.exit(1);
  }
  console.log("No layout problems.");
})();
