# Scholar-Slides

Scholar-Slides is the source and evidence layer for academic paper analysis, teaching, presentations, and downstream learning maps. It is designed to make a paper understandable without losing track of what the source actually supports.

## End-to-end flow

```text
PDF / arXiv source
  -> source bundle and digest
  -> validated Mode A reading-view.json
  -> paper-analysis.md and Paper-Tutor explanation
  -> optional Paper Learning Map
  -> CKPT-1-confirmed presentation workflow
```

The data flow is one-way. Downstream Markdown, maps, tutor state, and slides must not write back into `digest.json`, `reading-view.json`, or checkpoint records.

## Install and health check

From a repository checkout:

```powershell
.\scripts\install.ps1
scholar-slides --version
scholar-slides doctor --json
```

The current release is `0.4.0`. `doctor.ok` must be true before a long build. For Chinese documents and slides, confirm that the CJK font check passes.

## Mode A: source-grounded reading

Build a project from a PDF or arXiv identifier:

```powershell
scholar-slides build `
  --input "C:\papers\paper.pdf" `
  --project "C:\papers\paper-project"
```

Mode A produces a source bundle, extractive digest, figures/tables, and a pending CKPT-1 review state. A validated `reading-view.json` is the navigation layer for the first reading. It should contain:

- a 30-second overview with problem, gap, approach, insight, findings, and boundary;
- concrete input → processing → output mechanism steps;
- a separate argument chain from background to conclusion;
- 2–4 decisive evidence blocks with comparisons, metrics, results, and limits;
- only the terms that block understanding;
- claim type, availability, and evidence references for every substantive item.

The reading view is not a second abstract. Its job is to preserve the paper's causal and argumentative spine so Paper-Tutor and Learning Map can expand it without inventing a new story.

## Evidence and checkpoints

Evidence locators may refer to pages, sections, figures, tables, equations, or appendices. Each locator is resolved as `exact`, `normalized`, `fuzzy`, `partial`, `ambiguous`, or `unresolved`. Ambiguous and unresolved evidence remains visible and blocks any claim that depends on it.

Prepare, but do not approve, a CKPT-1 review package with:

```powershell
scholar-slides prepare-checkpoint `
  --project "C:\papers\paper-project" `
  --checkpoint CKPT-1 `
  --review-input "C:\papers\review-input.json" `
  --prepared-by "Codex"
```

Only an explicit human decision may approve CKPT-1. A pending CKPT-1 does not block an already authorized explanation, but it blocks workflows that require a confirmed reviewed view.

## Mode B: presentations

After CKPT-1 is confirmed:

```powershell
scholar-slides build --project "C:\papers\paper-project" --resume
scholar-slides review --project "C:\papers\paper-project"
scholar-slides export --project "C:\papers\paper-project" --formats html,pdf,pptx,notes
```

Presentation generation has its own CKPT-2 review. Do not export an unconfirmed deck, and do not overwrite an approved deck without using the documented reopen lifecycle.

## Paper Learning Map

Build the source-grounded map only after a valid `reading-view.json` exists:

```powershell
python scholar-slides/paper-learning-map/runtime/build_paper_map.py `
  --project "C:\papers\paper-project" `
  --out "C:\papers\paper-map"

python scholar-slides/paper-learning-map/runtime/render_paper_map.py `
  --project "C:\papers\paper-map"
```

The generated map contains `paper-map.json`, `tutor-state.json`, `study-state.json`, and `paper-learning-map.html`. `paper-map.json` is source-grounded and immutable downstream; `tutor-state.json` and `study-state.json` are the writable learning layers. Formula rendering is offline and identity-bound.

## Validation

Run the repository checks after documentation or runtime changes:

```powershell
python scripts/validate_skills.py scholar-slides paper-tutor
python scripts/audit_public_release.py --repo . --json
python -m unittest discover -s scholar-slides/tests -q
python -m unittest discover -s scholar-slides/paper-learning-map/tests -q
```

If a check is skipped because an optional artifact is absent, report the skip explicitly. Never turn a pending, partial, or unresolved source state into a confirmed claim.
