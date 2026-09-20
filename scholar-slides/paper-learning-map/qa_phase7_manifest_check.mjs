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
const manifest = path.resolve(String(args.manifest || path.join(root, "docs", "release-manifest-paper-learning-system-rc1.json")));
const priorCheck = path.resolve(String(args.prior || path.join(root, "docs", "release-manifest-self-check.json")));
const output = path.resolve(String(args.output || path.join(root, "docs", "phase7-ux-hardening", "manifest-check", "manifest-self-check.json")));

async function json(file) { return JSON.parse(await readFile(file, "utf8")); }
async function sha256(file) { return createHash("sha256").update(await readFile(file)).digest("hex"); }

const payload = await json(manifest);
const prior = await json(priorCheck);
const mismatches = [];
for (const [name, entry] of Object.entries(payload.artifacts || {})) {
  if (name === "paper_tutor_backup" || !entry?.path) continue;
  try {
    const actual = await sha256(entry.path);
    if (actual !== entry.sha256) mismatches.push({ name, expected: entry.sha256, actual });
  } catch {
    mismatches.push({ name, expected: entry.sha256, missing: true });
  }
}
const currentHash = await sha256(manifest);
const receipt = {
  schema_version: "1.0",
  kind: "phase7_frozen_manifest_check",
  manifest_path: manifest,
  manifest_sha256_before: prior.manifest_sha256 || null,
  manifest_sha256_after: currentHash,
  frozen_manifest_unchanged: Boolean(prior.manifest_sha256) && prior.manifest_sha256 === currentHash,
  recorded_release_status: payload.release_status || null,
  artifact_mismatches: mismatches,
  self_consistency_passed: mismatches.length === 0,
  decision: mismatches.length === 0 ? "candidate" : "conditional-candidate",
  note: "Read-only check; the frozen RC1 manifest is intentionally not rewritten.",
};
await mkdir(path.dirname(output), { recursive: true });
await writeFile(output, JSON.stringify(receipt, null, 2) + "\n", "utf8");
console.log(JSON.stringify(receipt, null, 2));
