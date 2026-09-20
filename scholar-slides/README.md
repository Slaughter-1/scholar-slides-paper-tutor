# Scholar-Slides + Paper-Tutor

Evidence-grounded academic paper analysis, teaching, presentation generation, and source-bound learning maps for Codex.

## What is included

- **Scholar-Slides** (`scholar-slides/`): source ingestion, metadata and evidence extraction, reading-view generation, CKPT-1/CKPT-2 gates, slide planning, speaker notes, export, and offline QA.
- **Paper-Tutor** (`paper-tutor/`): integrated or standalone paper teaching at quick, deep, and research depth, with explicit separation of Paper Facts, Tutor Explanation, and Tutor Analysis.
- **Paper Learning Map** (bundled under `scholar-slides/paper-learning-map/`): source-bound map projection, formula index and KaTeX rendering, tutor-state synchronization, study state, unresolved-question tracking, and hash-bound sync receipts.

The flow is one way:

```text
paper PDF / source
        |
        v
Scholar-Slides reading-view + evidence
        |
        v
Paper-Tutor / Learning Map projections
        |
        v
slides, notes, maps, and study state
```

Downstream outputs never write back into the source reading view, digest, or checkpoint records.

## Install locally

Copy `scholar-slides/` into the local Codex skill directory and `paper-tutor/` into the Paper-Tutor skill directory. Keep each paper project in its own user-selected output directory; never write project artifacts into the installed skill.

Typical Windows locations are:

```text
%USERPROFILE%\\.agents\\skills\\scholar-slides
%USERPROFILE%\\.codex\\skills\\paper-tutor
```

The installed bundle is self-contained. Runtime commands resolve resources relative to the installed skill and do not depend on a fixed machine path.

## Scholar-Slides workflow

Check the runtime before a long run:

```powershell
scholar-slides --version
scholar-slides doctor --json
```

Build a source-bound Mode A project:

```powershell
scholar-slides build --input "C:\\path\\paper.pdf" --project "C:\\path\\paper-project"
```

Prepare a CKPT-1 review input without recording approval:

```powershell
scholar-slides prepare-checkpoint --project "C:\\path\\paper-project" `
  --checkpoint CKPT-1 --review-input "C:\\path\\review-input.json" --prepared-by Codex
```

Only an explicit user instruction can approve a checkpoint. Never infer approval from silence, an automated result, or a model-written receipt. CKPT-1 approval freezes the source-bound reviewed semantic view. A source hash change makes the review stale and requires a new checkpoint.

After a confirmed CKPT-1, resume the presentation pipeline:

```powershell
scholar-slides build --project "C:\\path\\paper-project" --resume
scholar-slides review --project "C:\\path\\paper-project"
scholar-slides export --project "C:\\path\\paper-project" --formats html,pdf,pptx,notes
```

Presentation export remains gated by CKPT-2. Blocking evidence, stale source bindings, missing quantitative facts, and failed QA must fail closed.

## Evidence and locator policy

Evidence is source-bound. Locator parsing supports page, page range, section, figure, table, equation, appendix, and mixed locators while distinguishing PDF page index, printed page label, and source page reference. Resolver status is explicit: `exact`, `normalized`, `fuzzy`, `partial`, `ambiguous`, or `unresolved`.

`ambiguous` and `unresolved` evidence must never be guessed automatically. Parsing a locator is insufficient: the referenced evidence span must be validated against the source. Producer defects and resolver gaps are recorded separately. Do not add paper-specific locator exceptions.

## Paper-Tutor workflow

Read the matching Scholar-Slides reading view when available, keep the upstream project read-only, and disclose the verification mode in the output. Use the references in `paper-tutor/references/` for integration, depth, output contracts, benchmark papers, reading completion, and learning-map synchronization.

Integrated output must preserve the paper identity and source hashes. Standalone output must say that Scholar-Slides CKPT-1 verification was not available. Unsupported claims remain unavailable, not verifiable, or Tutor Analysis; they are never silently promoted to Paper Facts.

## Learning Map and formula projection

Build and render a map from a validated Scholar-Slides project:

```powershell
python scholar-slides/paper-learning-map/runtime/build_paper_map.py `
  --project C:\\path\\paper-project --out C:\\path\\map
python scholar-slides/paper-learning-map/runtime/render_paper_map.py `
  --project C:\\path\\map
```

Tutor records should use the structured sync hook. It writes only downstream tutor/study state and a receipt containing event status, node resolutions, unresolved deltas, and before/after hashes:

```powershell
$recordsJson | python scholar-slides/paper-learning-map/runtime/update_tutor_state.py `
  --project C:\\path\\map sync --stdin --origin full_analysis
```

Formula rendering is offline and retains raw LaTeX plus a local fallback when parsing fails. Formula indexes are rejected when their paper identity or validation level does not match the loaded map.

## Quality gates

Run the relevant tests from the repository root:

```powershell
python -m unittest discover -s scholar-slides/tests -q
python -m unittest discover -s scholar-slides/paper-learning-map/tests -q
```

Chromium and integrity QA must report zero unexpected external requests, zero page errors, source/hash consistency, and successful formula/detail rendering. Keep CKPT-1 records immutable; any evidence, decision, promotion, or provenance change belongs to a new checkpoint.

## Provenance

Automated checks and Codex-authorized review are not natural-person signatures. Human review receipts must identify the reviewer and remain bound to the PDF, digest, reading-view, resolver report, and relevant output hashes. Promotion never changes the underlying evidence status.
