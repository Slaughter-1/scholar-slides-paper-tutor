import { chromium } from "../runtime/node_modules/playwright/index.mjs";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const qa = path.join(root, "paper-learning-map", "qa-screenshots");
await mkdir(qa, { recursive: true });
const browser = await chromium.launch({ headless: true });
const cases = [
  ["Reasoning-Table", 1440, 900],
  ["Reasoning-Table", 1920, 1080],
  ["StartupBench", 1440, 900],
  ["StartupBench", 1920, 1080],
];
for (const [name, width, height] of cases) {
  const page = await browser.newPage({ viewport: { width, height } });
  const errors = [];
  page.on("pageerror", e => errors.push(String(e)));
  await page.goto(`file://${path.join(root, "paper-learning-map", "fixtures", name, "output", "paper-learning-map.html")}`);
  await page.waitForTimeout(150);
  const overview = await page.locator("svg g[data-id]").count();
  const blackFacts = await page.locator("svg .node.fact").evaluateAll(es => es.filter(e => getComputedStyle(e).fill === "rgb(0, 0, 0)").length);
  await page.screenshot({ path: path.join(qa, `${name}-${width}x${height}-overview.png`), fullPage: true });
  await page.locator("svg g[data-id]").first().click();
  const drawerOpen = await page.locator("#drawer.open").count();
  await page.screenshot({ path: path.join(qa, `${name}-${width}x${height}-detail.png`), fullPage: true });
  await page.keyboard.press("Escape");
  const drawerClosed = await page.locator("#drawer.open").count() === 0;
  await page.locator("#search").fill("Method");
  const searchDrawer = await page.locator("#drawer.open").count();
  const searchSelected = await page.locator("svg .node.selected").count();
  await page.locator("#theme").click();
  const dark = await page.locator("body.dark").count();
  await page.screenshot({ path: path.join(qa, `${name}-${width}x${height}-dark.png`), fullPage: true });
  await page.close();
  console.log(JSON.stringify({ name, width, height, overview, blackFacts, drawerOpen, drawerClosed, searchDrawer, searchSelected, dark, errors }));
}
await browser.close();
