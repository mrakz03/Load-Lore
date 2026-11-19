// Web check (check.yml, and release.yml before a release): opens the built page web/www/index.html in
// headless Chromium on a PC-sized and a phone-sized screen, walks through the main pages and fails on
// any JavaScript error. Run after `python3 web/build_web.py`:  node scripts/check_web.mjs
// (needs Playwright: npm install playwright && npx playwright install chromium)
import { chromium } from "playwright";
import { pathToFileURL } from "node:url";
import path from "node:path";

const page_url = pathToFileURL(path.resolve("web/www/index.html")).href;
const pages = ["", "#loads", "#h2h", "#bench", "#hand", "#ladder", "#range", "#favs", "#settings"];
const browser = await chromium.launch();
let bad = 0;
for (const [name, opts] of [["PC", { viewport: { width: 1400, height: 900 } }],
                             ["phone", { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true }]]) {
  const ctx = await browser.newContext(opts);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", e => errors.push(String(e)));
  page.on("console", m => { if (m.type() === "error" && !/net::|Failed to load resource|sync\./.test(m.text())) errors.push(m.text()); });
  await page.route(/^https?:/, r => r.abort());   // no network: sync and fonts stay off
  let n = 0;
  const open = async h => { await page.goto(`${page_url}?${n++}${h}`); await page.waitForTimeout(300); };
  for (const h of pages) {
    await open(h);
    const txt = (await page.textContent("body")) || "";
    if (txt.trim().length < 50) errors.push(`${h || "Home"}: page is empty`);
  }
  // every category, then a load from each opened through a share link (cartridge picked, load opened)
  const cats = await page.evaluate(() => CATEGORIES.map(c => c.title));
  if (!cats.length) errors.push("no categories");
  for (const c of cats) await open("#loads/" + encodeURIComponent(c));
  const links = await page.evaluate(() => CATEGORIES.filter(hasDetail).map(c => {
    const ls = state.detail[c.title], it = ls[Math.floor(ls.length / 2)];
    return shareURL({ t: "l", c: c.title, k: it.cartridge, n: it.label }).replace(/^[^#]*/, "");
  }));
  for (const h of links) await open(h);
  if (links.length) await open("#share/" + links[0].slice(7).replace(/./, "x"));   // a broken link shows a notice, no error
  if (errors.length) { bad++; console.log(`${name}: ${errors.length} error(s)`); errors.forEach(e => console.log("  " + e)); }
  else console.log(`${name}: OK (${pages.length} pages, ${cats.length} categories, ${links.length} opened loads)`);
  await ctx.close();
}
await browser.close();
process.exit(bad ? 1 : 0);
