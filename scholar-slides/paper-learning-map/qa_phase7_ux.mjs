import { chromium } from "../runtime/node_modules/playwright/index.mjs";
import { createHash } from "node:crypto";
import { cp, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const args = {};
for (let i = 2; i < process.argv.length; i += 1) {
  const value = process.argv[i];
  if (!value.startsWith("--")) continue;
  const key = value.slice(2);
  const next = process.argv[i + 1];
  args[key] = next && !next.startsWith("--") ? next : true;
}

const phaseRoot = path.resolve(String(args["phase-root"]));
const outputDir = path.resolve(String(args.output || path.join(phaseRoot, "ux-qa")));
await mkdir(outputDir, { recursive: true });

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function sha256(file) {
  return createHash("sha256").update(await readFile(file)).digest("hex");
}

async function bundle(name, mapHtml, deepHtml) {
  const dir = await mkdtemp(path.join(os.tmpdir(), `phase7-${name}-`));
  await cp(mapHtml, path.join(dir, "paper-learning-map.html"));
  await cp(deepHtml, path.join(dir, "paper-tutor-deep-v2.html"));
  return { name, dir, map: path.join(dir, "paper-learning-map.html"), deep: path.join(dir, "paper-tutor-deep-v2.html") };
}

async function pageFor(browser, file, viewport, hash = "") {
  const page = await browser.newPage({ viewport: { width: viewport[0], height: viewport[1] } });
  const pageErrors = [];
  const consoleErrors = [];
  const externalRequests = [];
  page.on("pageerror", error => pageErrors.push(String(error)));
  page.on("console", message => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("request", request => { if (/^https?:/i.test(request.url())) externalRequests.push(request.url()); });
  await page.goto(`${pathToFileURL(file).href}${hash}`, { waitUntil: "load" });
  await page.waitForTimeout(100);
  return { page, pageErrors, consoleErrors, externalRequests };
}

async function inspectBundle(browser, entry, viewport) {
  const map = await pageFor(browser, entry.map, viewport);
  const mapStats = await map.page.evaluate(() => {
    const ids = [...document.querySelectorAll("[id]")].map(node => node.id);
    const receipts = Array.isArray(window.SYNC_RECEIPTS) ? window.SYNC_RECEIPTS : [];
    const latest = receipts.at(-1) || null;
    const expected = !latest ? "not synced" : latest.status === "failed" ? "sync failed" : ((latest.unresolved_total || latest.unresolved_added || 0) > 0 ? "unresolved" : "synced");
    return {
      formulaIds: (window.FORMULAS?.formulas || []).map(item => item.id),
      formulaAnchors: (window.FORMULAS?.formulas || []).map(item => ({ id: item.id, node: item.anchor_node_id, title: item.title })),
      duplicateIds: ids.filter((id, index) => ids.indexOf(id) !== index),
      syncText: document.querySelector("#sync-status")?.textContent || "",
      syncExpected: expected,
      syncStatus: document.querySelector("#sync-status")?.textContent?.toLowerCase() || "",
      nodeCount: document.querySelectorAll("svg g[data-id]").length,
    };
  });
  assert(mapStats.duplicateIds.length === 0, `${entry.name}: duplicate DOM ids`);
  assert(mapStats.syncStatus.includes(mapStats.syncExpected), `${entry.name}: sync status is not receipt-driven (${mapStats.syncText} vs ${mapStats.syncExpected})`);
  assert(mapStats.formulaAnchors.length > 0, `${entry.name}: no formulas available`);
  const target = mapStats.formulaAnchors[0];
  const nodeSlug = String(target.node).replace(/_/g, "-").replace(/[^a-zA-Z0-9-]+/g, "-").replace(/^-|-$/g, "").toLowerCase();

  // Node-level Deep ↔ Map navigation is independently checked from the
  // formula route so a formula cannot mask a broken section anchor.
  await map.page.goto(`${pathToFileURL(entry.map).href}#node=${encodeURIComponent(target.node)}`, { waitUntil: "load" });
  await map.page.waitForTimeout(120);
  const nodeRoute = await map.page.evaluate((nodeId) => ({
    hash: window.location.hash,
    drawer: document.querySelector("#drawer")?.classList.contains("open") || false,
    selected: document.querySelector("svg .node.selected")?.parentElement?.dataset.id || "",
    deepHref: [...document.querySelectorAll("#detail a[href*='paper-tutor-deep-v2.html']")].find(a => a.getAttribute("href")?.includes("#node-"))?.getAttribute("href") || "",
  }), target.node);
  assert(nodeRoute.hash === `#node=${target.node}` && nodeRoute.drawer && nodeRoute.selected === target.node, `${entry.name}: node hash did not focus the right node`);
  assert(nodeRoute.deepHref === `paper-tutor-deep-v2.html#node-${nodeSlug}`, `${entry.name}: Map -> Deep node href is unstable (${nodeRoute.deepHref})`);
  await map.page.goto(`${pathToFileURL(entry.deep).href}#node-${nodeSlug}`, { waitUntil: "load" });
  await map.page.waitForTimeout(100);
  const deepNode = await map.page.evaluate((nodeId) => ({
    target: document.querySelector(`[data-anchor-node-id="${nodeId}"]`)?.id || "",
    highlighted: Boolean(document.querySelector(`[data-anchor-node-id="${nodeId}"].deep-highlight`)),
  }), target.node);
  assert(deepNode.target === `node-${nodeSlug}`, `${entry.name}: Deep node anchor missing`);

  // Map -> Deep: open the formula hash first so the QA does not depend on
  // whichever hierarchy nodes happen to be expanded in the initial view.
  await map.page.goto(`${pathToFileURL(entry.map).href}#formula=${encodeURIComponent(target.id)}`, { waitUntil: "load" });
  await map.page.waitForTimeout(120);
  const links = await map.page.evaluate(() => [...document.querySelectorAll("#detail a[href*='paper-tutor-deep-v2.html']")].map(a => ({ text: a.textContent, href: a.getAttribute("href") })));
  const formulaLink = links.find(link => link.href?.includes("#formula="));
  assert(formulaLink?.href === `paper-tutor-deep-v2.html#formula=${target.id}`, `${entry.name}: Map -> Deep formula href is unstable (${formulaLink?.href})`);
  await map.page.goto(`${pathToFileURL(entry.deep).href}#formula=${encodeURIComponent(target.id)}`, { waitUntil: "load" });
  await map.page.waitForTimeout(100);
  const deepFromMap = await map.page.evaluate((formulaId) => ({
    formula: Boolean(document.querySelector(`[data-formula-id="${CSS.escape(formulaId)}"]`)),
    highlighted: Boolean(document.querySelector(`[data-formula-id="${CSS.escape(formulaId)}"].deep-highlight`)),
  }), target.id);
  assert(deepFromMap.formula, `${entry.name}: Deep formula target missing after Map -> Deep`);

  // Deep -> Map: use the generated formula link and assert a single hash.
  const deepMapLink = await map.page.locator(`[data-formula-id="${target.id}"] a[href*="paper-learning-map.html"]`).getAttribute("href");
  assert(deepMapLink === `paper-learning-map.html#formula=${target.id}`, `${entry.name}: Deep -> Map formula href is malformed (${deepMapLink})`);
  await map.page.goto(`${pathToFileURL(entry.map).href}#formula=${encodeURIComponent(target.id)}`, { waitUntil: "load" });
  await map.page.waitForTimeout(120);
  const formulaDrawer = await map.page.evaluate((formulaId) => ({
    hash: window.location.hash,
    drawer: document.querySelector("#drawer")?.classList.contains("open") || false,
    blocks: [...document.querySelectorAll(".formula-drawer-block")].filter(node => node.dataset.formulaId === formulaId).length,
    selected: document.querySelector("svg .node.selected")?.parentElement?.dataset.id || "",
  }), target.id);
  assert(formulaDrawer.hash === `#formula=${target.id}`, `${entry.name}: formula hash changed unexpectedly (${formulaDrawer.hash})`);
  assert(formulaDrawer.drawer && formulaDrawer.blocks === 1 && formulaDrawer.selected === target.node, `${entry.name}: formula hash did not open the right node`);

  // Search must resolve to the same formula/node pair.
  await map.page.locator("#search").fill(target.title);
  await map.page.waitForTimeout(100);
  const search = await map.page.evaluate((formulaId) => ({
    selected: document.querySelector("svg .node.selected")?.parentElement?.dataset.id || "",
    blocks: [...document.querySelectorAll(".formula-drawer-block")].filter(node => node.dataset.formulaId === formulaId).length,
  }), target.id);
  assert(search.selected === target.node && search.blocks === 1, `${entry.name}: formula search selected the wrong target`);

  await map.page.close();
  return {
    viewport: `${viewport[0]}x${viewport[1]}`,
    map_stats: mapStats,
    formula_drawer: formulaDrawer,
    node_route: nodeRoute,
    deep_node: deepNode,
    search,
    deep_from_map: deepFromMap,
    map_page_errors: map.pageErrors,
    map_console_errors: map.consoleErrors,
    external_requests: map.externalRequests,
  };
}

const bundles = [
  await bundle("swe", path.join(phaseRoot, "swe-map", "paper-learning-map.html"), path.join(phaseRoot, "outputs", "swe-deep.html")),
  await bundle("reasoning", path.join(phaseRoot, "reason-map", "paper-learning-map.html"), path.join(phaseRoot, "outputs", "reason-deep.html")),
  await bundle("cold-start", path.join(phaseRoot, "cold-start", "paper-learning-map.html"), path.join(phaseRoot, "cold-start", "paper-tutor-deep-v2.html")),
];
const browser = await chromium.launch({ headless: true });
const results = [];
try {
  for (const entry of bundles) {
    for (const viewport of [[1440, 900], [1920, 1080]]) results.push({ paper: entry.name, ...(await inspectBundle(browser, entry, viewport)) });
  }
} finally {
  await browser.close();
}

const artifacts = {};
for (const [name, file] of Object.entries({
  swe_map: path.join(phaseRoot, "swe-map", "paper-learning-map.html"),
  swe_deep: path.join(phaseRoot, "outputs", "swe-deep.html"),
  reasoning_map: path.join(phaseRoot, "reason-map", "paper-learning-map.html"),
  reasoning_deep: path.join(phaseRoot, "outputs", "reason-deep.html"),
  cold_start_map: path.join(phaseRoot, "cold-start", "paper-learning-map.html"),
  cold_start_deep: path.join(phaseRoot, "cold-start", "paper-tutor-deep-v2.html"),
})) artifacts[name] = { path: file, sha256: await sha256(file) };

const receipt = {
  schema_version: "1.0",
  offline_bundle: true,
  viewports: ["1440x900", "1920x1080"],
  external_request_count: results.reduce((total, item) => total + item.external_requests.length, 0),
  page_error_count: results.reduce((total, item) => total + item.map_page_errors.length + item.map_console_errors.length, 0),
  bidirectional_anchor_qa: { passed: true, cases: results.length },
  results,
  artifacts,
};
await writeFile(path.join(outputDir, "phase7-ux-qa.json"), JSON.stringify(receipt, null, 2) + "\n", "utf8");
console.log(JSON.stringify(receipt, null, 2));
