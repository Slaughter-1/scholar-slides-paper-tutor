import { chromium } from "../runtime/node_modules/playwright/index.mjs";
import { pathToFileURL } from "node:url";

const inputs = process.argv.slice(2);
if (!inputs.length) throw new Error("usage: node qa_phase7_2_chromium.mjs label=path [label=path ...]");
const browser = await chromium.launch({ headless: true });
const results = [];
for (const input of inputs) {
  const separator = input.indexOf("=");
  const label = separator >= 0 ? input.slice(0, separator) : input;
  const file = separator >= 0 ? input.slice(separator + 1) : input;
  for (const viewport of [{ width: 1440, height: 900 }, { width: 1920, height: 1080 }]) {
    const page = await browser.newPage({ viewport });
    const pageErrors = [], consoleErrors = [], externalRequests = [];
    page.on("pageerror", error => pageErrors.push(String(error)));
    page.on("console", message => { if (message.type() === "error") consoleErrors.push(message.text()); });
    page.on("request", request => { if (/^https?:/i.test(request.url())) externalRequests.push(request.url()); });
    await page.goto(pathToFileURL(file).href, { waitUntil: "load" });
    const state = await page.evaluate(() => ({
      title: document.title,
      mapType: typeof MAP,
      tutorType: typeof TUTOR,
      studyType: typeof STUDY,
      formulasType: typeof FORMULAS,
      nodes: Array.isArray(MAP?.nodes) ? MAP.nodes.length : 0,
      svgNodes: document.querySelectorAll("#map .node").length,
      bodyText: document.body.innerText.length,
      verificationLevel: MAP?.source?.verification_level || null,
    }));
    const passed = !pageErrors.length && !consoleErrors.length && !externalRequests.length && state.bodyText > 20 && state.mapType === "object" && state.nodes > 0 && state.svgNodes > 0;
    results.push({ label, file, viewport: `${viewport.width}x${viewport.height}`, passed, pageErrors, consoleErrors, externalRequests, state });
    await page.close();
  }
}
await browser.close();
const output = {
  schema_version: "phase7.2.chromium-qa.v1",
  external_requests: results.reduce((total, item) => total + item.externalRequests.length, 0),
  results,
  passed: results.every(item => item.passed),
};
console.log(JSON.stringify(output, null, 2));
if (!output.passed) process.exitCode = 1;
