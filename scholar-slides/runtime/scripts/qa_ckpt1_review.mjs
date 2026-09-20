import { chromium } from "../node_modules/playwright/index.mjs";
import { pathToFileURL } from "node:url";
import { writeFile } from "node:fs/promises";

const inputs = process.argv.slice(2);
if (!inputs.length) throw new Error("usage: node qa_ckpt1_review.mjs label=path [label=path ...]");
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
    const state = await page.evaluate(() => {
      const pack = JSON.parse(document.querySelector("#review-pack")?.textContent || "{}");
      const text = document.body.innerText || "";
      const headings = [...document.querySelectorAll("h2")].map(node => node.textContent || "");
      const groups = ["partial", "fuzzy", "ambiguous", "unresolved"].filter(status => headings.some(heading => heading.startsWith(status + " evidence")));
      return {
        title: document.title,
        packType: pack.kind || null,
        state: pack.promotion_status || null,
        items: Array.isArray(pack.review_items) ? pack.review_items.length : 0,
        cards: document.querySelectorAll(".claim-card").length,
        controls: document.querySelectorAll("[data-decision]").length,
        nonExactGroups: groups,
        bodyText: text.length,
      };
    });
    const passed = !pageErrors.length && !consoleErrors.length && !externalRequests.length
      && state.packType === "ckpt-1-review-pack" && state.state === "WAITING_FOR_HUMAN_CKPT1"
      && state.items > 0 && state.cards === state.items && state.controls === state.items
      && state.bodyText > 500;
    results.push({ label, file, viewport: viewport.width + "x" + viewport.height, passed, pageErrors, consoleErrors, externalRequests, state });
    await page.close();
  }
}
await browser.close();
const output = {
  schema_version: "phase7.3.ckpt1-review-chromium-qa.v1",
  external_requests: results.reduce((total, item) => total + item.externalRequests.length, 0),
  results,
  passed: results.every(item => item.passed),
};
const out = process.env.CKPT1_QA_OUT;
if (out) await writeFile(out, JSON.stringify(output, null, 2) + "\n", "utf8");
console.log(JSON.stringify(output, null, 2));
if (!output.passed) process.exitCode = 1;
