# Scholar-Slides + Paper-Tutor

Evidence-grounded academic paper analysis, teaching, presentations, and source-bound learning maps for Codex. The current release is Scholar-Slides **0.4.0**.

## Packages

- `scholar-slides/`: PDF/source ingestion, evidence resolver, reading view, CKPT-1 and CKPT-2 gates, slide planning, speaker notes, export, and offline QA.
- `paper-tutor/`: integrated or standalone paper teaching at quick, deep, and research depth, with explicit Paper Fact, Tutor Explanation, and Tutor Analysis layers.
- `scholar-slides/paper-learning-map/`: source-bound map projection, formula index and offline KaTeX rendering, tutor-state synchronization, study state, unresolved-question tracking, and hash-bound receipts.

The data flow is one way:

```text
paper source -> Scholar-Slides evidence and reading view
             -> Paper-Tutor and Learning Map projections
             -> slides, notes, and study state
```

Downstream outputs do not write back into the source reading view, digest, or checkpoint records.

## Install on Windows

From a checkout of this repository, run:

```powershell
.\scripts\install.ps1
```

The installer backs up existing installations, installs the packages to `%USERPROFILE%\.agents\skills\scholar-slides` and `%USERPROFILE%\.codex\skills\paper-tutor`, creates the Scholar-Slides Python environment, installs Node dependencies, and installs Playwright Chromium. Use `-SkipPlaywright` only when browser QA is not required.

Projects belong in user-selected output directories, never inside an installed skill. The bundle resolves resources relative to its own installation and does not depend on a fixed machine path.

## Scholar-Slides

Check the installation:

```powershell
scholar-slides --version
scholar-slides doctor --json
```

For Chinese PDF/PPTX export, require a verified CJK font explicitly:

```powershell
scholar-slides doctor --json --require-cjk
```

Build a source-bound project:

```powershell
scholar-slides build --input "C:\papers\paper.pdf" --project "C:\papers\paper-project"
```

Prepare CKPT-1 without recording approval:

```powershell
scholar-slides prepare-checkpoint --project "C:\papers\paper-project" `
  --checkpoint CKPT-1 --review-input "C:\papers\review-input.json" --prepared-by Codex
```

Only an explicit human or user-authorized decision can approve CKPT-1. A source hash change makes the review stale. After CKPT-1 is confirmed:

```powershell
scholar-slides build --project "C:\papers\paper-project" --resume
scholar-slides review --project "C:\papers\paper-project"
scholar-slides export --project "C:\papers\paper-project" --formats html,pdf,pptx,notes
```

Export remains gated by CKPT-2. Blocking evidence, stale bindings, missing quantitative facts, and failed QA fail closed.

## Evidence resolver

The resolver supports page, page range, section, figure, table, equation, appendix, and mixed locators. It distinguishes PDF page index, printed page label, and source page reference. Every locator ends in an explicit status: `exact`, `normalized`, `fuzzy`, `partial`, `ambiguous`, or `unresolved`.

`ambiguous` and `unresolved` evidence is never guessed automatically. Locator parsing is followed by evidence-span validation. Producer bugs and resolver gaps are recorded separately, and paper-specific locator exceptions are prohibited.

## Paper-Tutor

In Integrated Mode, Paper-Tutor consumes a matching Scholar-Slides reading view and evidence set while keeping the upstream project read-only. In Standalone Mode it states that Scholar-Slides CKPT-1 verification was unavailable. Paper Facts, Tutor Explanation, and Tutor Analysis remain visibly distinct; unsupported claims stay unavailable, unverifiable, or analytical.

The structured Learning Map bridge is available as:

```powershell
$recordsJson | python paper-tutor/scripts/learning_map_sync.py `
  --project "C:\papers\paper-map" `
  --map-root "C:\path\to\scholar-slides\paper-learning-map" `
  --origin full_analysis
```

## Learning Map and formulas

```powershell
python scholar-slides/paper-learning-map/runtime/build_paper_map.py `
  --project "C:\papers\paper-project" --out "C:\papers\paper-map"
python scholar-slides/paper-learning-map/runtime/render_paper_map.py `
  --project "C:\papers\paper-map"
```

The map renders formulas offline and retains raw LaTeX plus a fallback when parsing fails. Formula indexes are rejected when identity or validation level does not match. Only downstream tutor and study state is writable.

## Validation

The repository contains runnable unit tests:

```powershell
python scripts/validate_skills.py scholar-slides paper-tutor
python scripts/audit_public_release.py --repo . --json
python -m unittest discover -s scholar-slides/tests -q
python -m unittest discover -s scholar-slides/paper-learning-map/tests -q
```

Six deep-output tests require generated SWE-Touch, Reasoning-Table, or CKPT-1 closeout artifacts and are skipped with an explicit reason when those optional artifacts are absent. CI installs dependencies and Chromium, runs all available tests, validates metadata, runs the public-release audit, and executes the CLI doctor.

The current CKPT-1 baseline is immutable. Evidence status, review decisions, promotion provenance, and `partial` states belong to a new checkpoint rather than a rewrite of CKPT-1.

## Public-release audit

Run `scripts/audit_public_release.py` before publishing. It checks tracked files for credentials, private keys, and oversized artifacts. Sample fixtures are included for regression coverage; review their licensing and distribution suitability before adding new source material.
