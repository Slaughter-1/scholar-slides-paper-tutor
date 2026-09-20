import { chromium } from "../runtime/node_modules/playwright/index.mjs";
import { createHash } from "node:crypto";
import { cp, mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const args = {};
for (let index = 2; index < process.argv.length; index += 1) {
  const value = process.argv[index];
  if (!value.startsWith("--")) continue;
  const key = value.slice(2);
  const next = process.argv[index + 1];
  args[key] = next && !next.startsWith("--") ? next : true;
}
const mapProject = path.resolve(String(args["map-project"]));
const reasoningMapProject = path.resolve(String(args["reasoning-map-project"] || mapProject));
const sweDeepHtml = path.resolve(String(args["swe-deep-html"]));
const reasoningDeepHtml = path.resolve(String(args["reasoning-deep-html"]));
const malformedFixture = path.resolve(String(args["malformed-fixture"]));
const outputDir = path.resolve(String(args.output || path.join(mapProject, "formula-experience-qa")));
await mkdir(outputDir, { recursive: true });

function sha256(file) {
  return readFile(file).then(buffer => createHash("sha256").update(buffer).digest("hex"));
}
function localUrl(file) { return pathToFileURL(file).href; }
function assertion(condition, message) { if (!condition) throw new Error(message); }

async function openPage(browser, file, viewport, label) {
  const page = await browser.newPage({ viewport: { width: viewport[0], height: viewport[1] } });
  const pageErrors = [], consoleErrors = [], externalRequests = [];
  page.on("pageerror", error => pageErrors.push(String(error)));
  page.on("console", message => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("request", request => { if (/^https?:/i.test(request.url())) externalRequests.push(request.url()); });
  const started = Date.now();
  await page.goto(localUrl(file), { waitUntil: "load" });
  await page.waitForTimeout(120);
  const initialRenderMs = Date.now() - started;
  return { page, pageErrors, consoleErrors, externalRequests, initialRenderMs, label };
}

async function makeStandaloneCopy(file, label) {
  const dir = await mkdtemp(path.join(os.tmpdir(), `rc2-standalone-${label}-`));
  const target = path.join(dir, path.basename(file));
  await cp(file, target);
  return target;
}

async function inspectDeep(browser, file, label, screenshotName, viewport = [1440, 900]) {
  const result = await openPage(browser, file, viewport, label);
  const { page } = result;
  const stats = await page.evaluate(() => ({
    title: document.title,
    formulaBlocks: document.querySelectorAll(".formula-block").length,
    rendered: document.querySelectorAll(".formula-render[data-rendered='true']").length,
    mathml: document.querySelectorAll(".katex-mathml").length,
    rawControls: document.querySelectorAll(".formula-source").length,
    formulaErrors: window.__formulaRenderErrors || [],
    sourceLayers: [...document.querySelectorAll(".formula-badge")].map(node => node.textContent),
    formulaRenderMs: Number(window.__formulaRenderMs || 0),
  }));
  const formulaRenderMs = await page.evaluate(() => {
    const nodes = [...document.querySelectorAll('.formula-render[data-tex]')];
    const started = performance.now();
    for (const node of nodes) {
      window.katex.render(node.dataset.tex, node, { displayMode: node.dataset.display !== 'false', throwOnError: true, trust: false, strict: 'warn', output: 'htmlAndMathml' });
    }
    return performance.now() - started;
  });
  stats.formulaRenderMs = formulaRenderMs;
  stats.htmlSize = (await readFile(file)).length;
  await page.screenshot({ path: path.join(outputDir, screenshotName), fullPage: true });
  assertion(!result.pageErrors.length && !result.consoleErrors.length, `${label}: page/console errors`);
  assertion(result.externalRequests.length === 0, `${label}: external requests ${result.externalRequests.join(",")}`);
  assertion(stats.formulaBlocks > 0 && stats.rendered > 0 && stats.mathml > 0 && stats.rawControls > 0, `${label}: formula rendering incomplete`);
  assertion(stats.formulaErrors.length === 0, `${label}: formula errors ${JSON.stringify(stats.formulaErrors)}`);
  await page.close();
  return { viewport: `${viewport[0]}x${viewport[1]}`, ...result, stats, page: undefined };
}

async function inspectMap(browser, file, label, anchor, query, screenshotName, darkScreenshotName, viewport = [1440, 900]) {
  const result = await openPage(browser, file, viewport, label);
  const { page } = result;
  const base = await page.evaluate(() => ({
    formulaData: (window.FORMULAS?.formulas || []).length,
    katex: typeof window.katex?.render === "function",
    externalText: document.documentElement.innerHTML.match(/(?:cdn\.jsdelivr|cdnjs|unpkg)/gi) || [],
    htmlSize: document.documentElement.outerHTML.length,
  }));
  const started = Date.now();
  await page.locator("#search").fill(query);
  await page.waitForTimeout(140);
  await page.locator(`svg g[data-id="${anchor}"]`).click();
  await page.waitForTimeout(80);
  const drawer = await page.evaluate(() => ({
    open: document.querySelector("#drawer")?.classList.contains("open") || false,
    blocks: document.querySelectorAll(".formula-drawer-block").length,
    rendered: document.querySelectorAll(".formula-drawer-block .formula-render[data-rendered='true']").length,
    mathml: document.querySelectorAll(".formula-drawer-block .katex-mathml").length,
    raw: document.querySelectorAll(".formula-drawer-block .formula-source").length,
    badges: [...document.querySelectorAll(".formula-drawer-block .formula-badge")].map(node => node.textContent),
    fields: ["Symbols", "Mathematical Meaning", "Intuition", "Necessity", "Example", "Misunderstanding", "Evidence"].filter(field => document.querySelector(`.formula-drawer-block h4:nth-of-type(${["Symbols", "Mathematical Meaning", "Intuition", "Necessity", "Example", "Misunderstanding", "Evidence"].indexOf(field) + 1})`)),
    formulaRenderMs: Number(window.__lastFormulaRenderMs || 0),
  }));
  const drawerOpenMs = Date.now() - started;
  assertion(drawer.open && drawer.blocks > 0 && drawer.rendered > 0 && drawer.mathml > 0 && drawer.raw > 0, `${label}: drawer formula incomplete`);
  assertion(drawer.badges.some(text => text.includes("Paper Formula")) && drawer.badges.some(text => text.includes("Tutor Explanation")) && drawer.badges.some(text => text.includes("Tutor Example")), `${label}: source boundary badges missing`);
  await page.screenshot({ path: path.join(outputDir, screenshotName), fullPage: true });
  await page.locator("#close").click();
  await page.locator("#search").fill(query);
  await page.waitForTimeout(120);
  const search = await page.evaluate(() => ({
    open: document.querySelector("#drawer")?.classList.contains("open") || false,
    formula: document.querySelectorAll(".formula-drawer-block").length,
    selected: document.querySelector("svg .node.selected")?.parentElement?.dataset.id || "",
  }));
  assertion(search.open && search.formula > 0, `${label}: formula search did not open drawer`);
  await page.locator("#theme").click();
  await page.waitForTimeout(80);
  const dark = await page.evaluate(() => ({
    enabled: document.body.classList.contains("dark"),
    visible: [...document.querySelectorAll(".formula-drawer-block .formula-render")].every(node => getComputedStyle(node).color !== "rgb(0, 0, 0)"),
  }));
  assertion(dark.enabled && dark.visible, `${label}: dark mode formula visibility failed`);
  await page.screenshot({ path: path.join(outputDir, darkScreenshotName), fullPage: true });
  assertion(!result.pageErrors.length && !result.consoleErrors.length, `${label}: page/console errors`);
  assertion(result.externalRequests.length === 0, `${label}: external requests ${result.externalRequests.join(",")}`);
  await page.close();
  return { viewport: `${viewport[0]}x${viewport[1]}`, ...result, base, html_size: (await readFile(file)).length, drawer, drawer_open_ms: drawerOpenMs, search, dark, page: undefined };
}

async function makeMalformedMap() {
  const dir = await mkdtemp(path.join(os.tmpdir(), "paper-map-malformed-"));
  for (const name of ["paper-map.json", "tutor-state.json", "study-state.json"]) await cp(path.join(mapProject, name), path.join(dir, name));
  const fixture = JSON.parse(await readFile(malformedFixture, "utf8"));
  const paperMap = JSON.parse(await readFile(path.join(mapProject, "paper-map.json"), "utf8"));
  // Bind the intentionally malformed expression to the copied map identity;
  // the renderer must test fallback behavior, not cross-paper rejection.
  fixture.paper_identity = paperMap.paper_identity;
  fixture.source = paperMap.source;
  await writeFile(path.join(dir, "formula-index.json"), JSON.stringify(fixture, null, 2) + "\n", "utf8");
  const renderer = path.join(path.dirname(fileURLToPath(import.meta.url)), "runtime", "render_paper_map.py");
  execFileSync("python", [renderer, "--project", dir], { stdio: "pipe" });
  return path.join(dir, "paper-learning-map.html");
}

const browser = await chromium.launch({ headless: true });
const receipt = { schema_version: "1.1", offline_bundle: true, standalone_copy_qa: true, viewports: ["1440x900", "1920x1080"], results: [], artifacts: {} };
try {
  const standaloneSweDeep = await makeStandaloneCopy(sweDeepHtml, "swe-deep");
  const standaloneReasonDeep = await makeStandaloneCopy(reasoningDeepHtml, "reason-deep");
  const standaloneSweMap = await makeStandaloneCopy(path.join(mapProject, "paper-learning-map.html"), "swe-map");
  const standaloneReasonMap = await makeStandaloneCopy(path.join(reasoningMapProject, "paper-learning-map.html"), "reason-map");
  for (const viewport of [[1440, 900], [1920, 1080]]) {
    const suffix = viewport[0] === 1440 ? "" : `-${viewport[0]}x${viewport[1]}`;
    receipt.results.push(await inspectDeep(browser, standaloneSweDeep, `swe-touch-deep-${viewport[0]}`, `swe-touch-deep-formula${suffix}.png`, viewport));
    receipt.results.push(await inspectDeep(browser, standaloneReasonDeep, `reasoning-table-deep-${viewport[0]}`, `reasoning-table-position-reward${suffix}.png`, viewport));
    receipt.results.push(await inspectMap(browser, standaloneSweMap, `swe-touch-map-${viewport[0]}`, "method.step_2", "Counter-Edit validation", `swe-touch-map-formula-drawer${suffix}.png`, `swe-touch-map-formula-dark${suffix}.png`, viewport));
    receipt.results.push(await inspectMap(browser, standaloneReasonMap, `reasoning-table-map-${viewport[0]}`, "method.step_3", "Position Reward", `reasoning-table-position-reward-map${suffix}.png`, `reasoning-table-dark-formula${suffix}.png`, viewport));
  }
  const malformedHtml = await makeMalformedMap();
  const malformed = await openPage(browser, malformedHtml, [1440, 900], "malformed-formula");
  await malformed.page.locator("#search").fill("Malformed Formula");
  await malformed.page.waitForTimeout(120);
  const malformedAnchor = malformed.page.locator('svg g[data-id="method.step_2"]');
  if (await malformedAnchor.count()) await malformedAnchor.click();
  await malformed.page.waitForTimeout(100);
  const fallback = await malformed.page.evaluate(() => ({
    errors: window.__formulaRenderErrors || [],
    fallback: document.querySelectorAll(".formula-fallback").length,
    unavailable: [...document.querySelectorAll(".formula-error")].map(node => node.textContent),
  }));
  await malformed.page.screenshot({ path: path.join(outputDir, "malformed-formula-fallback.png"), fullPage: true });
  assertion(fallback.errors.length > 0 && fallback.fallback > 0 && fallback.unavailable.some(text => text.includes("Formula rendering unavailable")), "malformed formula fallback failed");
  assertion(!malformed.pageErrors.length && !malformed.consoleErrors.length && malformed.externalRequests.length === 0, "malformed formula page errors or network requests");
  receipt.results.push({ viewport: "1440x900", ...malformed, fallback, page: undefined });
  for (const [name, file] of Object.entries({
    swe_deep_html: sweDeepHtml,
    reasoning_deep_html: reasoningDeepHtml,
    swe_map_html: path.join(mapProject, "paper-learning-map.html"),
    reasoning_map_html: path.join(reasoningMapProject, "paper-learning-map.html"),
    malformed_fixture: malformedFixture,
  })) receipt.artifacts[name] = { path: file, sha256: await sha256(file) };
  receipt.katex_version = "0.16.47";
  receipt.external_request_count = receipt.results.reduce((sum, item) => sum + (item.externalRequests || []).length, 0);
  const formulaErrors = receipt.results.flatMap(item => item.fallback?.errors || item.stats?.formulaErrors || []);
  receipt.formula_render_error_occurrences = formulaErrors.length;
  receipt.formula_render_errors = [...new Map(formulaErrors.map(error => [`${error.latex}\n${error.message}`, error])).values()];
  receipt.formula_render_error_count = receipt.formula_render_errors.length;
  receipt.screenshot_dir = outputDir;
  await writeFile(path.join(outputDir, "formula-experience-qa.json"), JSON.stringify(receipt, null, 2) + "\n", "utf8");
  console.log(JSON.stringify(receipt, null, 2));
} finally {
  await browser.close();
}
