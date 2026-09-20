import { chromium } from "../../runtime/node_modules/playwright/index.mjs";
import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import path from "node:path";
const root=path.resolve(process.argv[2]);
const results=[];
const sha=async f=>createHash("sha256").update(await readFile(f)).digest("hex");
function check(x,msg){if(!x)throw new Error(msg)}
const browser=await chromium.launch({headless:true});
try {
 for (const paper of ["skillpyramid","startupbench"]) for (const viewport of [[1440,900],[1920,1080]]) {
  const map=path.join(root,"handoff",paper,"paper-learning-map.html");
  const deep=path.join(root,"handoff",paper,"paper-tutor-deep-v2.html");
  const page=await browser.newPage({viewport:{width:viewport[0],height:viewport[1]}});
  const pageErrors=[],consoleErrors=[],external=[];
  page.on("pageerror",e=>pageErrors.push(String(e))); page.on("console",m=>{if(m.type()==="error")consoleErrors.push(m.text())}); page.on("request",r=>{if(/^https?:/i.test(r.url()))external.push(r.url())});
  await page.goto(pathToFileURL(map).href,{waitUntil:"load"}); await page.waitForTimeout(150);
  const stats=await page.evaluate(()=>({title:document.title,formulas:(window.FORMULAS?.formulas||[]),nodes:document.querySelectorAll("svg g[data-id]").length,mapErrors:window.__formulaRenderErrors||[]}));
  check(stats.formulas.length>0,`${paper}: no formula in final map`); check(stats.mapErrors.length===0,`${paper}: map formula render errors`);
  const f=stats.formulas[0];
  await page.goto(`${pathToFileURL(map).href}#formula=${encodeURIComponent(f.id)}`,{waitUntil:"load"}); await page.waitForTimeout(150);
  const drawer=await page.evaluate(id=>({open:document.querySelector("#drawer")?.classList.contains("open"),selected:document.querySelector("svg .node.selected")?.parentElement?.dataset.id||"",blocks:[...document.querySelectorAll(".formula-drawer-block")].filter(n=>n.dataset.formulaId===id).length,deep:[...document.querySelectorAll("#detail a[href*='paper-tutor-deep-v2.html']")].map(a=>a.getAttribute("href"))}),f.id);
  check(drawer.open&&drawer.blocks===1,`${paper}: formula drawer failed`); const deepHref=drawer.deep.find(h=>h?.includes("#formula=")); check(deepHref===`paper-tutor-deep-v2.html#formula=${f.id}`,`${paper}: map->deep link mismatch`);
  await page.goto(`${pathToFileURL(deep).href}#formula=${encodeURIComponent(f.id)}`,{waitUntil:"load"}); await page.waitForTimeout(150);
  const deepStats=await page.evaluate(id=>({formula:!!document.querySelector(`[data-formula-id="${CSS.escape(id)}"]`),rendered:document.querySelectorAll(`[data-formula-id="${CSS.escape(id)}"] [data-rendered='true']`).length,mapLinks:[...document.querySelectorAll(`[data-formula-id="${CSS.escape(id)}"] a[href*='paper-learning-map.html']`)].map(a=>a.getAttribute("href")),errors:window.__formulaRenderErrors||[]}),f.id);
  check(deepStats.formula&&deepStats.errors.length===0,`${paper}: deep formula failed`); check(deepStats.mapLinks.includes(`paper-learning-map.html#formula=${f.id}`),`${paper}: deep->map link mismatch`);
  results.push({paper,viewport:`${viewport[0]}x${viewport[1]}`,title:stats.title,formula_id:f.id,map_nodes:stats.nodes,formula_count:stats.formulas.length,drawer,deep:deepStats,page_errors:pageErrors,console_errors:consoleErrors,external_requests:external}); await page.close();
 }
} finally {await browser.close()}
const receipt={schema_version:"phase7.1.ckpt1-chromium-qa.v1",viewports:["1440x900","1920x1080"],results,external_request_count:results.reduce((n,r)=>n+r.external_requests.length,0),page_error_count:results.reduce((n,r)=>n+r.page_errors.length+r.console_errors.length,0),passed:results.every(r=>!r.page_errors.length&&!r.console_errors.length&&!r.external_requests.length)};
await writeFile(path.join(root,"ckpt1-final-chromium-qa.json"),JSON.stringify(receipt,null,2)+"\n"); console.log(JSON.stringify(receipt,null,2));
if(!receipt.passed)process.exitCode=1;
