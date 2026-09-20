import { chromium } from "../node_modules/playwright/index.mjs";
import { pathToFileURL } from "node:url";
import { writeFile } from "node:fs/promises";
import path from "node:path";

const root = path.resolve(process.argv[2]);
const output = process.env.CHECKPOINT_A_QA_OUT || path.join(root, "reading-usability-chromium-qa.json");
const results = [];
const errors = [];
const browser = await chromium.launch({ headless: true });
try {
  for (const paper of ["skillpyramid", "startupbench"]) {
    const mapFile = path.join(root, "handoff", paper, "paper-learning-map.html");
    const deepFile = path.join(root, "handoff", paper, "paper-tutor-deep-v2.html");
    for (const viewport of [{ width: 1440, height: 900 }, { width: 1920, height: 1080 }]) {
      const page = await browser.newPage({ viewport });
      const pageErrors = [], consoleErrors = [], externalRequests = [];
      page.on("pageerror", error => pageErrors.push(String(error)));
      page.on("console", message => { if (message.type() === "error") consoleErrors.push(message.text()); });
      page.on("request", request => { if (/^https?:/i.test(request.url())) externalRequests.push(request.url()); });
      await page.goto(pathToFileURL(mapFile).href, { waitUntil: "load" });
      await page.waitForTimeout(80);
      const mapState = await page.evaluate(() => ({
        formulas: window.FORMULAS?.formulas || [],
        mapErrors: window.__formulaRenderErrors || [],
        relationCount: (typeof MAP === "object" ? MAP.edges : []).filter(edge => edge.relation !== "parent_of").length,
        nodes: document.querySelectorAll("svg g[data-id]").length,
      }));
      // Cross-paper relations are attached to child nodes that start collapsed.
      // Expand the relevant factual groups through the same UI handler before
      // asserting that the relation toggle makes them visible.
      for (const id of ["method", "evidence", "terms", "takeaways"]) {
        await page.evaluate(nodeId => document.querySelector(`g[data-id="${nodeId}"]`)?.ondblclick?.(), id);
        await page.waitForTimeout(25);
      }
      const relationButton = page.locator("#relations");
      await relationButton.click();
      const relationState = await page.evaluate(() => document.querySelectorAll(".edge.cross.active").length);
      const formulaChecks = [];
      for (const formula of mapState.formulas) {
        const id = formula.id;
        await page.goto(`${pathToFileURL(mapFile).href}#formula=${encodeURIComponent(id)}`, { waitUntil: "load" });
        await page.waitForTimeout(50);
        const drawer = await page.evaluate(formulaId => ({
          open: document.querySelector("#drawer")?.classList.contains("open"),
          blocks: [...document.querySelectorAll(".formula-drawer-block")].filter(node => node.dataset.formulaId === formulaId).length,
          deep: [...document.querySelectorAll("#detail a[href*='paper-tutor-deep-v2.html']")].map(link => link.getAttribute("href")),
        }), id);
        await page.goto(`${pathToFileURL(deepFile).href}#formula=${encodeURIComponent(id)}`, { waitUntil: "load" });
        await page.waitForTimeout(80);
        const deep = await page.evaluate(formulaId => {
          const node = document.querySelector(`[data-formula-id="${CSS.escape(formulaId)}"]`);
          return {
            present: Boolean(node),
            rendered: node ? node.querySelectorAll("[data-rendered='true']").length : 0,
            mapLinks: node ? [...node.querySelectorAll("a[href*='paper-learning-map.html']")].map(link => link.getAttribute("href")) : [],
            errors: window.__formulaRenderErrors || [],
          };
        }, id);
        formulaChecks.push({ id, drawer, deep, passed: drawer.open && drawer.blocks === 1 && drawer.deep.includes(`paper-tutor-deep-v2.html#formula=${id}`) && deep.present && deep.rendered > 0 && deep.mapLinks.includes(`paper-learning-map.html#formula=${id}`) && deep.errors.length === 0 });
      }
      const passed = !pageErrors.length && !consoleErrors.length && !externalRequests.length && mapState.formulas.length > 0 && mapState.mapErrors.length === 0 && mapState.relationCount > 0 && relationState > 0 && formulaChecks.every(check => check.passed);
      results.push({ paper, viewport: `${viewport.width}x${viewport.height}`, map_nodes: mapState.nodes, formula_count: mapState.formulas.length, relation_count: mapState.relationCount, relation_active_edges: relationState, formula_checks: formulaChecks, page_errors: pageErrors, console_errors: consoleErrors, external_requests: externalRequests, passed });
      await page.close();
    }
  }
} finally {
  await browser.close();
}
const receipt = { schema_version: "checkpoint-a.reading-usability-chromium-qa.v1", viewports: ["1440x900", "1920x1080"], results, external_request_count: results.reduce((total, result) => total + result.external_requests.length, 0), page_error_count: results.reduce((total, result) => total + result.page_errors.length + result.console_errors.length, 0), passed: results.every(result => result.passed) };
await writeFile(output, JSON.stringify(receipt, null, 2) + "\n", "utf8");
console.log(JSON.stringify(receipt, null, 2));
if (!receipt.passed) process.exitCode = 1;
