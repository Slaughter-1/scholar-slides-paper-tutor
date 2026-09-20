import { chromium } from "../runtime/node_modules/playwright/index.mjs";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = process.cwd();
const project = process.env.PAPER_MAP_QA_PROJECT
  ? path.resolve(process.env.PAPER_MAP_QA_PROJECT)
  : path.resolve(root, "docs", "e2e-validation", "agent-harness", "map-output");
const screenshotDir = path.join(project, "screenshots");
await mkdir(screenshotDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const results = [];
for (const [width, height] of [[1440, 900], [1920, 1080]]) {
  const page = await browser.newPage({ viewport: { width, height } });
  const errors = [];
  page.on("pageerror", error => errors.push(String(error)));
  await page.goto(pathToFileURL(path.join(project, "paper-learning-map.html")).href, { waitUntil: "load" });
  await page.waitForTimeout(120);
  const initial = await page.evaluate(() => ({
    mode: document.querySelector("#tutor-layer")?.value,
    factualNodes: document.querySelectorAll("svg .node.fact").length,
    tutorGroups: document.querySelectorAll("svg .tutor-group").length,
    tutorItems: document.querySelectorAll("svg .tutor-item").length,
  }));
  await page.screenshot({ path: path.join(screenshotDir, `fresh-${width}x${height}-key.png`), fullPage: true });
  await page.locator("#tutor-layer").selectOption("all");
  await page.waitForTimeout(50);
  const allCollapsed = await page.evaluate(() => ({ groups: document.querySelectorAll("svg .tutor-group").length, items: document.querySelectorAll("svg .tutor-item").length }));
  const firstGroup = page.locator("svg g[data-id^='visual.tutor.group.']").first();
  if (await firstGroup.count()) await firstGroup.dispatchEvent("dblclick");
  await page.waitForTimeout(50);
  const all = await page.evaluate(() => ({ groups: document.querySelectorAll("svg .tutor-group").length, items: document.querySelectorAll("svg .tutor-item").length }));
  await page.locator("svg g[data-id]").first().click();
  const drawer = await page.locator("#drawer.open").count() > 0;
  await page.locator("#search").fill("Agent Harness");
  await page.waitForTimeout(50);
  const search = await page.evaluate(() => ({ open: document.querySelector("#drawer")?.classList.contains("open"), selected: Boolean(document.querySelector("svg .node.selected")) }));
  await page.screenshot({ path: path.join(screenshotDir, `fresh-${width}x${height}-all-search.png`), fullPage: true });
  results.push({ width, height, initial, allCollapsed, all, drawer, search, errors });
  await page.close();
}
await browser.close();
const output = { project, results };
await writeFile(path.join(project, "fresh-chromium-qa.json"), JSON.stringify(output, null, 2) + "\n", "utf-8");
console.log(JSON.stringify(output));
if (results.some(item => item.errors.length || item.initial.factualNodes < 1 || item.all.groups < 1 || item.all.items < 1 || !item.drawer || !item.search.open || !item.search.selected)) process.exitCode = 1;
