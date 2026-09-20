import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const args = {};
for (let index = 2; index < process.argv.length; index += 1) {
  const value = process.argv[index];
  if (!value.startsWith("--")) continue;
  const key = value.slice(2);
  const next = process.argv[index + 1];
  args[key] = next && !next.startsWith("--") ? next : true;
}

const root = path.resolve(String(args.root || path.join(import.meta.dirname, "..")));
const beforeReceipt = path.resolve(String(args.before || path.join(
  root,
  "docs",
  "e2e-validation",
  "verified-fresh",
  "swe-touch",
  "deep-v2-rc1",
  "receipts",
  "fresh-verified-e2e-receipt.json",
)));
const afterReport = path.resolve(String(args.after || path.join(
  root,
  "docs",
  "e2e-validation",
  "stress-100x200",
  "stress-qa-results.json",
)));
const renderer = path.resolve(String(args.renderer || path.join(root, "paper-learning-map", "assets", "paper-learning-map.js")));
const output = path.resolve(String(args.output || path.join(root, "docs", "phase7-ux-hardening", "performance", "performance-before-after.json")));

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function readJson(file) {
  return JSON.parse(await readFile(file, "utf8"));
}

async function sha256(file) {
  return createHash("sha256").update(await readFile(file)).digest("hex");
}

function viewKey(view) {
  return `${view.width}x${view.height}`;
}

function sourceViewports(receipt) {
  const viewports = receipt?.stress?.viewports;
  assert(Array.isArray(viewports) && viewports.length > 0, "before receipt has no embedded stress viewports");
  return viewports;
}

function validateAfter(viewports) {
  assert(Array.isArray(viewports) && viewports.length > 0, "after report has no viewports");
  for (const view of viewports) {
    assert(view.allExpanded?.factual === 100, `${viewKey(view)}: factual count changed`);
    assert(view.allExpanded?.items === 200, `${viewKey(view)}: Tutor item count changed`);
    assert(view.allExpanded?.groups === 100, `${viewKey(view)}: Tutor group count changed`);
    assert(view.finite_bounds === true, `${viewKey(view)}: non-finite bounds`);
    assert((view.page_errors || []).length === 0, `${viewKey(view)}: page errors`);
    assert((view.console_errors || []).length === 0, `${viewKey(view)}: console errors`);
  }
}

const before = await readJson(beforeReceipt);
const after = await readJson(afterReport);
const beforeViews = sourceViewports(before);
const afterViews = after.viewports;
validateAfter(afterViews);

const beforeByKey = new Map(beforeViews.map(view => [viewKey(view), view]));
const afterByKey = new Map(afterViews.map(view => [viewKey(view), view]));
assert(beforeByKey.size === afterByKey.size, "viewport sets differ");

const metrics = ["expand_ms", "all_ms", "search_ms", "fit_ms", "off_ms", "key_ms"];
const comparisons = [];
for (const [key, afterView] of afterByKey) {
  const beforeView = beforeByKey.get(key);
  assert(beforeView, `missing before viewport ${key}`);
  const values = {};
  for (const metric of metrics) {
    const beforeMs = Number(beforeView[metric]);
    const afterMs = Number(afterView[metric]);
    assert(Number.isFinite(beforeMs) && Number.isFinite(afterMs), `${key}: invalid ${metric}`);
    values[metric] = {
      before_ms: beforeMs,
      after_ms: afterMs,
      delta_ms: Number((afterMs - beforeMs).toFixed(2)),
      improvement_percent: Number((((beforeMs - afterMs) / beforeMs) * 100).toFixed(2)),
    };
  }
  comparisons.push({ viewport: key, metrics: values });
}

const receipt = {
  schema_version: "1.0",
  kind: "phase7_performance_before_after",
  fixture: "stress-100x200",
  workload: { factual_nodes: 100, tutor_items: 200, viewports: comparisons.map(item => item.viewport) },
  before: {
    phase: "pre-phase7-baseline",
    source_kind: "embedded stress snapshot",
    receipt_path: beforeReceipt,
    report_sha256_at_baseline: before?.stress?.report_sha256 || null,
    source_note: "Values are the stress snapshot embedded in the Deep V2 Fresh E2E receipt; the original report is historical.",
  },
  after: {
    phase: "phase7-current",
    source_kind: "qa_stress_100x200.mjs",
    report_path: afterReport,
    report_sha256: await sha256(afterReport),
    renderer_sha256: await sha256(renderer),
  },
  comparisons,
  gates: {
    after_stress_passed: true,
    factual_and_tutor_counts_unchanged: true,
    page_and_console_errors_zero: true,
    expand_time_improved_all_viewports: comparisons.every(item => item.metrics.expand_ms.improvement_percent > 0),
  },
  limitations: [
    "Wall-clock timings are single-run Chromium measurements and can vary with host load.",
    "The before values are an embedded historical receipt snapshot, not a rerun with the pre-Phase7 renderer.",
  ],
};
receipt.passed = Object.values(receipt.gates).every(Boolean);

await mkdir(path.dirname(output), { recursive: true });
await writeFile(output, JSON.stringify(receipt, null, 2) + "\n", "utf8");
console.log(JSON.stringify(receipt, null, 2));
if (!receipt.passed) process.exitCode = 1;
