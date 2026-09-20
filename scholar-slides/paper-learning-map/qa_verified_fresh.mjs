import { chromium } from "../runtime/node_modules/playwright/index.mjs";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const project = path.resolve(process.env.PAPER_MAP_QA_PROJECT || "docs/e2e-validation/verified-fresh/swe-touch/learning-map-rc1-final");
const screenshotDir = path.join(project, "screenshots");
await mkdir(screenshotDir, { recursive: true });
const html = path.join(project, "paper-learning-map.html");
const browser = await chromium.launch({ headless: true });
const viewports = [[1440, 900], [1920, 1080]];
const results = [];

for (const [width, height] of viewports) {
  const page = await browser.newPage({ viewport: { width, height } });
  const pageErrors = [];
  const consoleErrors = [];
  page.on("pageerror", error => pageErrors.push(String(error)));
  page.on("console", message => { if (message.type() === "error") consoleErrors.push(message.text()); });
  await page.goto(pathToFileURL(html).href, { waitUntil: "load" });
  await page.waitForTimeout(180);

  const base = await page.evaluate(() => ({
    subtitle: document.querySelector("#subtitle")?.textContent || "",
    title: document.querySelector("#title")?.textContent || "",
    tutorMode: document.querySelector("#tutor-layer")?.value || "",
    factualNodes: document.querySelectorAll("svg .node.fact").length,
    totalNodes: document.querySelectorAll("svg g[data-id]").length,
    blackFactNodes: [...document.querySelectorAll("svg .node.fact")].filter(node => getComputedStyle(node).fill === "rgb(0, 0, 0)").length,
  }));
  await page.screenshot({ path: path.join(screenshotDir, width === 1440 ? "fresh-verified-1440-overview.png" : "fresh-verified-1920-overview.png"), fullPage: true });

  const finite = async () => page.evaluate(() => [...document.querySelectorAll("svg g[data-id]")].filter(node => {
    const box = node.getBoundingClientRect();
    return ![box.x, box.y, box.width, box.height].every(Number.isFinite);
  }).length);
  const mode = async () => page.evaluate(() => ({
    value: document.querySelector("#tutor-layer")?.value || "",
    groups: document.querySelectorAll("svg .tutor-group").length,
    items: document.querySelectorAll("svg .tutor-item").length,
  }));

  await page.locator("#tutor-layer").selectOption("off");
  await page.waitForTimeout(50);
  const off = await mode();
  await page.locator("#tutor-layer").selectOption("key");
  await page.waitForTimeout(50);
  const key = await mode();
  await page.locator("#tutor-layer").selectOption("all");
  await page.waitForTimeout(50);
  const allCollapsed = await mode();

  const group = page.locator("svg g[data-id^='visual.tutor.group.']").first();
  const groupCount = await group.count();
  if (groupCount) await group.dispatchEvent("dblclick");
  await page.waitForTimeout(80);
  const afterGroupExpand = await mode();

  const firstFactual = page.locator("svg g[data-id]").filter({ has: page.locator(".node.fact") }).first();
  await page.locator("svg g[data-id]").first().click();
  const drawerOpen = await page.locator("#drawer.open").count() > 0;
  await page.locator("#close").click();
  const drawerClosed = await page.locator("#drawer.open").count() === 0;

  await page.locator("#search").fill("Counter-Edit");
  await page.waitForTimeout(100);
  const search = await page.evaluate(() => ({
    drawerOpen: document.querySelector("#drawer")?.classList.contains("open") || false,
    selected: Boolean(document.querySelector("svg .node.selected")),
    selectedId: document.querySelector("svg .node.selected")?.parentElement?.dataset.id || "",
  }));
  await page.screenshot({ path: path.join(screenshotDir, width === 1920 ? "fresh-verified-1920-search.png" : "fresh-verified-1440-tutor.png"), fullPage: true });

  await page.locator("#fit").click();
  await page.waitForTimeout(60);
  // Expand the factual hierarchy so at least one cross-relation has two
  // visible endpoints before the relation toggle is checked.
  for (let pass = 0; pass < 12; pass += 1) {
    const ids = await page.locator("svg g[data-id]").evaluateAll(nodes => nodes
      .filter(node => node.querySelector(".node-badge"))
      .map(node => node.dataset.id)
      .filter(Boolean));
    if (!ids.length) break;
    for (const id of ids) {
      // Each double-click schedules a render and may detach the remaining
      // nodes from the DOM. Resolve the target against the current document
      // for every click instead of dispatching through a stale Locator.
      await page.evaluate((targetId) => {
        const node = [...document.querySelectorAll("svg g[data-id]")]
          .find(candidate => candidate.dataset.id === targetId);
        if (node) node.dispatchEvent(new MouseEvent("dblclick", { bubbles: true, cancelable: true }));
      }, id);
    }
    await page.waitForTimeout(20);
  }
  const fitFinite = await finite();
  await page.locator("#relations").click();
  const relations = await page.evaluate(() => document.querySelectorAll("svg .edge.cross.active").length);

  // Collapse/expand a factual node and assert that the visible graph changes
  // reversibly; its initial direction depends on the current hierarchy state.
  await page.locator("#search").fill("");
  await page.waitForTimeout(60);
  const beforeCollapse = await page.locator("svg g[data-id]").count();
  const collapsibleId = await page.locator("svg g[data-id]").filter({ has: page.locator(".node-badge") }).first().getAttribute("data-id");
  const collapsible = collapsibleId ? page.locator(`svg g[data-id="${collapsibleId.replaceAll('"', '\\"')}"]`) : page.locator("svg g[data-id='__missing__']");
  if (await collapsible.count()) await collapsible.dispatchEvent("dblclick");
  await page.waitForTimeout(60);
  const afterCollapse = await page.locator("svg g[data-id]").count();
  if (await collapsible.count()) await collapsible.dispatchEvent("dblclick");
  await page.waitForTimeout(60);
  const afterExpand = await page.locator("svg g[data-id]").count();

  await page.locator("#theme").click();
  await page.waitForTimeout(50);
  const dark = await page.evaluate(() => ({
    enabled: document.body.classList.contains("dark"),
    blackFactNodes: [...document.querySelectorAll("svg .node.fact")].filter(node => getComputedStyle(node).fill === "rgb(0, 0, 0)").length,
  }));
  await page.screenshot({ path: path.join(screenshotDir, "fresh-verified-1920-dark.png"), fullPage: true });

  results.push({
    viewport: `${width}x${height}`,
    page_errors: pageErrors,
    console_errors: consoleErrors,
    base,
    off,
    key,
    all_collapsed: allCollapsed,
    after_group_expand: afterGroupExpand,
    drawer: { open: drawerOpen, closed: drawerClosed },
    search,
    fit_finite_nonfinite: fitFinite,
    relations_active: relations,
    collapse: { before: beforeCollapse, after: afterCollapse, expanded: afterExpand },
    dark,
  });
  await page.close();
}
await browser.close();

const report = { project, screenshots: [
  "fresh-verified-1440-overview.png", "fresh-verified-1440-tutor.png",
  "fresh-verified-1920-overview.png", "fresh-verified-1920-search.png", "fresh-verified-1920-dark.png",
], results };
await writeFile(path.join(project, "fresh-verified-chromium-qa.json"), JSON.stringify(report, null, 2) + "\n", "utf-8");
console.log(JSON.stringify(report, null, 2));

const failed = results.some(item => item.page_errors.length || item.console_errors.length ||
  !item.base.subtitle.includes("integrated") || !item.base.subtitle.includes("scholar_slides_validated") ||
  item.base.factualNodes < 1 || item.base.blackFactNodes !== 0 || item.drawer.open !== true ||
  item.drawer.closed !== true || !item.search.drawerOpen || !item.search.selected ||
  item.fit_finite_nonfinite !== 0 || item.dark.enabled !== true || item.dark.blackFactNodes !== 0 ||
  item.off.groups !== 0 || item.off.items !== 0 || item.all_collapsed.groups < 1 ||
  item.after_group_expand.items < 1 || item.collapse.after === item.collapse.before || item.collapse.expanded !== item.collapse.before);
if (failed) process.exitCode = 1;
