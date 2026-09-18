---
name: scholar-slides
description: Use when a user asks to read, explain, digest, review, summarize, or create a presentation from an academic paper, local PDF, Zotero-exported PDF, arXiv paper, or existing scholar-slides project.
---

# scholar-slides

Version: 0.3.0 Final Stable

Use this Skill for source-grounded paper analysis and academic presentations. Never fill a
scientific gap from memory. Keep every project in the user's chosen output directory, never
inside the installed Skill.

## Mode A — 论文分析

Mode A reads the paper, extracts metadata and evidence, prepares the source-bound
candidate, and produces a concise Chinese reading view before the CKPT-1 gate. The
reading view must explain the paper's mainline, concrete mechanism steps, decisive
evidence, argument chain, and genuinely necessary terms. It is a derived teaching
projection, never a new factual source. Read `references/mode-a-reading.md` before
writing or reviewing this document.

```powershell
scholar-slides build --input "C:\path\paper.pdf" --project "C:\path\paper-project"
```

The pending project may include `reading-view.json` and `paper-analysis.md`. Codex writes
`reading-view.json` after checking the matching source evidence; the runtime validates its
schema, resolvable evidence references, and source bindings, then renders `paper-analysis.md`
in the view's declared `language` (`zh-CN` or `en-US`). A missing view keeps legacy
projects readable through the compatibility renderer. An invalid or stale view must fail
closed rather than silently falling back.

When a user also requests Paper-Tutor teaching, continue from the matching Mode A evidence
and reading view while preserving the real CKPT-1 status. CKPT-1 approval remains required
for presentation generation, but pending approval does not block already-authorized
explanation. Paper-Tutor output is read-only with respect to this project.

When a formal review input is required, prepare it without recording approval:

```powershell
scholar-slides prepare-checkpoint --project "C:\path\paper-project" `
  --checkpoint CKPT-1 --review-input "C:\path\review-input.json" --prepared-by Codex
```

Only an explicit user instruction may approve CKPT-1:

```powershell
scholar-slides approve 1 --project "C:\path\paper-project" --confirmed-by "Reviewer Name"
```

Approval freezes the source-bound reviewed semantic view. Never edit checkpoint JSON, infer
approval from silence, or regenerate a confirmed CKPT-1.

## Mode B — 汇报生成

Mode B starts from a confirmed CKPT-1 and generates the narrative plan, visible quantitative
coverage, deck, speaker notes, user preparation documents, and QA evidence:

```powershell
scholar-slides build --project "C:\path\paper-project" --resume
```

It stops at pending CKPT-2. The project contains:

- `deck.json` and `deck-outline.md`;
- `speaker_notes.md` or the project notes artifact;
- `presentation-script.md`, a complete per-slide preparation script;
- `presentation-summary.md`, a five-minute pre-talk summary;
- the review montage and semantic, quantitative, audience, visual, figure-legibility, and
  aesthetics reports.

Generate or refresh only the pending review preview with:

```powershell
scholar-slides review --project "C:\path\paper-project"
```

Only an explicit user instruction may approve the unchanged reviewed deck:

```powershell
scholar-slides approve 2 --project "C:\path\paper-project" --confirmed-by "Reviewer Name"
```

Do not export before CKPT-2 is confirmed. If an approved deck must change, use the documented
reopen lifecycle; never overwrite its approval record.

## Export

After CKPT-2 approval, run the single formal delivery command:

Canonical project placeholder: `scholar-slides export --project <project> --formats html,pdf,pptx,notes`.

```powershell
scholar-slides export --project "C:\path\paper-project" --formats html,pdf,pptx,notes
```

Delivery contains `slides.html`, `slides.pdf`, editable `slides.pptx`, `speaker_notes.md`,
`presentation-script.md`, `presentation-summary.md`, and machine-verifiable manifest,
validation, consistency, and parity evidence.

## Environment check

```powershell
scholar-slides --version
scholar-slides doctor --json
```

Require version `0.3.0` and `doctor.ok = true` before starting a long run. A missing or stale
source, checkpoint binding, required quantitative fact, or blocking QA finding must fail
closed. Do not invent content, bypass a gate, or add a paper-specific exception.

Read only the reference needed for the current stage:

- `references/workflow.md`: sources, Mode A, Mode B, and planning.
- `references/mode-a-reading.md`: Mode A reading view, first-stage structure, and Paper-Tutor handoff.
- `references/checkpoints.md`: approvals, reopen, and immutable history.
- `references/cli.md`: supported commands and output paths.
- `references/troubleshooting.md`: environment, stale evidence, and resume.
- `references/USAGE_ZH.md`: Chinese guide and copyable commands.
