import { chromium } from "../runtime/node_modules/playwright/index.mjs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { performance } from "node:perf_hooks";
import { pathToFileURL } from "node:url";

const root = process.cwd();
const project = path.resolve(root, "docs", "e2e-validation", "stress-100x200");
const htmlPath = path.join(project, "paper-learning-map.html");
const screenshotDir = path.join(project, "screenshots");
await mkdir(screenshotDir, { recursive: true });
const htmlSize = (await readFile(htmlPath)).byteLength;
const paperMap = JSON.parse(await readFile(path.join(project, "paper-map.json"), "utf-8"));
const tutorState = JSON.parse(await readFile(path.join(project, "tutor-state.json"), "utf-8"));
const sourceTutorItems = Object.values(tutorState.nodes || {}).reduce((total, state) => total + (state.map_items || []).length, 0);
const sourceCounts = { factual_nodes: (paperMap.nodes || []).length, tutor_items: sourceTutorItems };
const browser = await chromium.launch({ headless: true });
const results = { fixture: "stress-100x200", html_bytes: htmlSize, source_counts: sourceCounts, viewports: [], generated_at: new Date().toISOString() };

for (const [width, height] of [[1440, 900], [1920, 1080]]) {
  const page = await browser.newPage({ viewport: { width, height } });
  const errors = [];
  const consoleErrors = [];
  page.on("pageerror", error => errors.push(String(error)));
  page.on("console", message => { if (message.type() === "error") consoleErrors.push(message.text()); });
  const fileUrl = pathToFileURL(htmlPath).href;
  await page.goto(fileUrl, { waitUntil: "load" });
  await page.waitForTimeout(150);

  const initial = await page.evaluate(() => ({
    mode: document.querySelector("#tutor-layer")?.value || "",
    factual: document.querySelectorAll("svg .node.fact").length,
    total: document.querySelectorAll("svg g[data-id]").length,
    groups: document.querySelectorAll("svg .tutor-group").length,
    items: document.querySelectorAll("svg .tutor-item").length,
  }));
  await page.screenshot({ path: path.join(screenshotDir, `stress-${width}x${height}-key.png`), fullPage: true });

  const fitStart = performance.now();
  await page.locator("#fit").click();
  await page.waitForTimeout(20);
  const fitMs = performance.now() - fitStart;
  const finiteBounds = await page.locator("svg g[data-id]").evaluateAll(elements => elements.every(element => {
    const box = element.getBoundingClientRect();
    return Number.isFinite(box.x) && Number.isFinite(box.y) && Number.isFinite(box.width) && Number.isFinite(box.height);
  }));

  const offStart = performance.now();
  await page.locator("#tutor-layer").selectOption("off");
  await page.waitForTimeout(20);
  const offMs = performance.now() - offStart;
  const off = await page.evaluate(() => ({
    mode: document.querySelector("#tutor-layer")?.value || "",
    groups: document.querySelectorAll("svg .tutor-group").length,
    items: document.querySelectorAll("svg .tutor-item").length,
  }));

  const keyStart = performance.now();
  await page.locator("#tutor-layer").selectOption("key");
  await page.waitForTimeout(20);
  const keyMs = performance.now() - keyStart;
  const key = await page.evaluate(() => ({
    mode: document.querySelector("#tutor-layer")?.value || "",
    groups: document.querySelectorAll("svg .tutor-group").length,
    items: document.querySelectorAll("svg .tutor-item").length,
  }));

  const allStart = performance.now();
  await page.locator("#tutor-layer").selectOption("all");
  await page.waitForTimeout(40);
  const allMs = performance.now() - allStart;
  const allCollapsed = await page.evaluate(() => ({
    mode: document.querySelector("#tutor-layer")?.value || "",
    groups: document.querySelectorAll("svg .tutor-group").length,
    items: document.querySelectorAll("svg .tutor-item").length,
  }));
  await page.screenshot({ path: path.join(screenshotDir, `stress-${width}x${height}-all.png`), fullPage: true });

  // Open the hierarchy from the rendered DOM. This exercises the same user
  // path as double-clicking root, sections, and Tutor groups, without relying
  // on private JavaScript globals.
  const expandStart = performance.now();
  for (let pass = 0; pass < 30; pass += 1) {
    const ids = await page.locator("svg g[data-id]").evaluateAll(elements => elements
      .filter(element => element.querySelector(".node-badge"))
      .map(element => element.dataset.id)
      .filter(Boolean));
    if (!ids.length) break;
    for (const id of ids) {
      // Rendering after a double-click can detach the remaining hierarchy
      // nodes. Resolve each target from the current DOM to avoid a stale
      // locator race while keeping the same user-level event path.
      await page.evaluate((targetId) => {
        const node = [...document.querySelectorAll("svg g[data-id]")]
          .find(candidate => candidate.dataset.id === targetId);
        if (node) node.dispatchEvent(new MouseEvent("dblclick", { bubbles: true, cancelable: true }));
      }, id);
    }
  }
  await page.waitForTimeout(40);
  const expandMs = performance.now() - expandStart;
  const allExpanded = await page.evaluate(() => ({
    groups: document.querySelectorAll("svg .tutor-group").length,
    items: document.querySelectorAll("svg .tutor-item").length,
    factual: document.querySelectorAll("svg .node.fact").length,
    total: document.querySelectorAll("svg g[data-id]").length,
  }));

  const searchStart = performance.now();
  await page.locator("#search").fill("Tutor note 200");
  await page.waitForTimeout(40);
  const searchMs = performance.now() - searchStart;
  const search = await page.evaluate(() => ({
    selected: document.querySelector("svg .node.selected")?.parentElement?.dataset.id || "",
    visibleItems: document.querySelectorAll("svg .tutor-item").length,
    drawerOpen: document.querySelector("#drawer")?.classList.contains("open") || false,
  }));
  await page.screenshot({ path: path.join(screenshotDir, `stress-${width}x${height}-search.png`), fullPage: true });

  const firstItem = page.locator("svg g[data-id^='visual.tutor.item.']").first();
  let drawerText = "";
  if (await firstItem.count()) {
    await firstItem.dispatchEvent("click");
    drawerText = await page.locator("#detail").innerText();
  }
  const drawer = { open: await page.locator("#drawer.open").count() > 0, hasTutorBoundary: drawerText.includes("Tutor") || drawerText.includes("来源边界"), textLength: drawerText.length };

  const after = await page.evaluate(() => ({
    factual_visible_after_search: document.querySelectorAll("svg .node.fact").length,
    nonFinite: [...document.querySelectorAll("svg g[data-id]")].filter(element => {
      const box = element.getBoundingClientRect();
      return ![box.x, box.y, box.width, box.height].every(Number.isFinite);
    }).length,
  }));
  results.viewports.push({ width, height, initial, off, key, allCollapsed, allExpanded, fit_ms: Number(fitMs.toFixed(2)), off_ms: Number(offMs.toFixed(2)), key_ms: Number(keyMs.toFixed(2)), all_ms: Number(allMs.toFixed(2)), expand_ms: Number(expandMs.toFixed(2)), search_ms: Number(searchMs.toFixed(2)), finite_bounds: finiteBounds, search, drawer, after, page_errors: errors, console_errors: consoleErrors });
  await page.close();
}
await browser.close();
const resultPath = path.join(project, "stress-qa-results.json");
await writeFile(resultPath, JSON.stringify(results, null, 2) + "\n", "utf-8");
console.log(JSON.stringify({ resultPath, html_bytes: htmlSize, viewports: results.viewports }, null, 2));

if (sourceCounts.factual_nodes !== 100 || sourceCounts.tutor_items !== 200 || results.viewports.some(view => view.page_errors.length || view.console_errors.length || !view.finite_bounds || view.allExpanded.factual !== 100 || view.allExpanded.items !== 200 || view.allExpanded.groups !== 100 || view.after.nonFinite)) process.exitCode = 1;
