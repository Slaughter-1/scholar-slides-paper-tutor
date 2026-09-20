import { chromium } from "../runtime/node_modules/playwright/index.mjs";
import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

const root = process.argv[2];
if (!root) throw new Error("usage: node qa_final_artifact.mjs <handoff-root>");
const papers = ["swe-touch", "reasoning-table"];
const browser = await chromium.launch({ headless: true });
const results = [];
for (const paper of papers) {
  for (const [kind, name] of [["learning_map", "paper-learning-map.html"], ["deep_reading", "paper-tutor-deep-v2.html"]]) {
    const file = `${root}/${paper}/${name}`;
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const pageErrors = [], consoleErrors = [], externalRequests = [];
    page.on("pageerror", e => pageErrors.push(String(e)));
    page.on("console", m => { if (m.type() === "error") consoleErrors.push(m.text()); });
    page.on("request", r => { if (/^https?:/i.test(r.url())) externalRequests.push(r.url()); });
    await page.goto(pathToFileURL(file).href, { waitUntil: "load" });
    const state = await page.evaluate(kind === "learning_map" ? () => ({
      title: document.title, mapType: typeof MAP, tutorType: typeof TUTOR, studyType: typeof STUDY,
      formulasType: typeof FORMULAS, nodes: Array.isArray(MAP?.nodes) ? MAP.nodes.length : 0,
      svgNodes: document.querySelectorAll("#map .node").length,
      bodyText: document.body.innerText.length,
    }) : () => ({ title: document.title, bodyText: document.body.innerText.length, formulaBlocks: document.querySelectorAll(".formula-block").length }));
    const text = await readFile(file, "utf8");
    const passed = !pageErrors.length && !consoleErrors.length && !externalRequests.length && state.bodyText > 20 && !/__\w+__/.test(text) && (kind !== "learning_map" || (state.mapType === "object" && state.nodes > 0 && state.svgNodes > 0));
    results.push({ paper, kind, path: file, passed, pageErrors, consoleErrors, externalRequests, state });
    await page.close();
    const pageWide = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
    const wideErrors = [], wideConsole = [], wideExternal = [];
    pageWide.on("pageerror", e => wideErrors.push(String(e)));
    pageWide.on("console", m => { if (m.type() === "error") wideConsole.push(m.text()); });
    pageWide.on("request", r => { if (/^https?:/i.test(r.url())) wideExternal.push(r.url()); });
    await pageWide.goto(pathToFileURL(file).href, { waitUntil: "load" });
    const wideText = await pageWide.evaluate(() => document.body.innerText.length);
    const widePassed = !wideErrors.length && !wideConsole.length && !wideExternal.length && wideText > 20;
    results.push({ paper, kind, viewport: "1920x1080", path: file, passed: widePassed, pageErrors: wideErrors, consoleErrors: wideConsole, externalRequests: wideExternal, state: { bodyText: wideText } });
    await pageWide.close();
  }
}
await browser.close();
const output = { schema_version: "1.0", final_artifact_qa: true, exact_handoff_root: root, viewports: ["1440x900", "1920x1080"], external_request_count: results.reduce((n, r) => n + r.externalRequests.length, 0), results, passed: results.every(r => r.passed) };
console.log(JSON.stringify(output, null, 2));
if (!output.passed) process.exitCode = 1;
