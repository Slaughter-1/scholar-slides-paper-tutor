---
name: paper-tutor
description: Use when a user wants to understand, study, or question an academic paper, especially a complete-paper reading or review that should leave reusable study assets; also use for quick, deep, or research-level explanations of a formula, figure, table, method, experiment, contribution, or limitation from Scholar-Slides results or a paper PDF.
---

# Paper Tutor

## Core principle

Treat Scholar-Slides as the accurate reader and Paper-Tutor as the clear teacher. Exercise teaching freedom only in explanations and explicitly labeled analysis; never let it create, strengthen, or reclassify a factual claim beyond its evidence.

For a complete-paper reading session, treat the existing deep analysis as the source of truth. The Reading Completion Contract is a final compression, gap-check, and learning-asset gate; it is not a second paper-analysis workflow.

When a matching Scholar-Slides project contains `reading-view.json` or the new seven-part
Mode A analysis, use it as the reading navigation layer. Reuse its mainline, mechanism
steps, decisive evidence, argument chain, and term choices; add teaching detail only where
it removes a real comprehension barrier. The view is not a higher-priority factual source.

## Non-negotiable boundaries

Use Scholar-Slides only as a read-only upstream source. Maintain a one-way flow from matching paper inputs and Scholar-Slides artifacts into Paper-Tutor; never write to, modify, or feed Paper-Tutor prose back into Scholar-Slides or a presentation workflow. Accept no presentation as an input requirement. Constrain every Paper Fact to matching evidence, preserve uncertainty and conflicts, and disclose Standalone Mode transparently as not verified through Scholar-Slides CKPT-1.

## Workflow

1. Establish the paper identity and requested scope.
2. Read `references/integration-and-evidence.md` and select Integrated or Standalone Mode.
3. Select quick, deep, or research depth using `references/teaching-and-depth.md`.
4. If Integrated, read the matching Scholar-Slides Mode A reading guide and use its navigation view; keep the upstream project read-only.
5. Classify the paper by its primary contribution. If the benchmark, evaluation suite, task collection, or test environment is itself a primary contribution, treat it as a Benchmark paper; a method paper that merely reports benchmark scores remains a general paper. When a paper co-contributes a method and a new benchmark, let the main argument choose the primary structure; if both are equally central, retain the 16-field Benchmark Card as an index and add a compact method module with its inputs, objective, mechanism, and evidence.
6. Build a logical model separating Paper Facts, Tutor Explanation, and Tutor Analysis.
7. For a full-paper request, follow `references/output-contract.md` and create one `paper-tutor.md`. For a Benchmark paper, also read and apply `references/benchmark-paper.md` as the full-document schema.
8. If the request is a complete-paper reading/review or asks for a reading card, learning assets, or reading completion, read `references/reading-completion.md` after the deep analysis. Project the existing analysis into the fixed Reading Card, fill only evidence-backed gaps, create the required assets, and run the completion gate.
9. For a focused or follow-up request, answer only the requested part while reusing current paper context; do not trigger the completion gate or create the three assets unless the user also explicitly requests a complete-paper workflow.
10. Check claims and uncertainty before delivery.

## Reference routing

Always read `references/integration-and-evidence.md` before selecting a mode, combining sources, assigning claim types, or disclosing verification. In Integrated Mode, also read the matching Scholar-Slides `references/mode-a-reading.md` when available. Always read `references/teaching-and-depth.md` before choosing or changing depth, teaching a focused concept, or continuing a follow-up. Read `references/output-contract.md` for every full-paper output and whenever explaining a formula, figure, table, experiment, or ablation, or providing an evidence appendix. Read `references/validation-scenarios.md` when forward-testing this skill, diagnosing a behavior gap, or verifying a change against reusable scenarios.
Read `references/benchmark-paper.md` whenever a benchmark, evaluation suite, task collection, or test environment is a primary paper contribution, including focused questions about its tasks, data, metrics, agents, scaling, failures, or validity.
Read `references/reading-completion.md` only for a complete-paper reading/review workflow or when the user explicitly asks for the Reading Card, reading note, reconstructed method SVG, verification question, or completion status.

## Delivery check

- In the first full-paper response, put one compact Chinese status line near the title (`来源：...；CKPT-1 ...；讲解深度：...`), then place the complete mode, paper identity, analysis source, evidence source, verification status, and depth block at the end. For focused follow-ups, repeat the status only when the source, identity, or verification state changes. Use the mode-specific status block from `references/integration-and-evidence.md`; when paper identity is unavailable, write `Paper identity: Not verifiable from available evidence`. Render depth in plain text as `Depth: quick`, `Depth: deep`, or `Depth: research`, never with a placeholder or backticked value.
- Use `Analysis source: Scholar-Slides-backed Paper-Tutor analysis` in Integrated Mode and `Analysis source: Standalone Paper-Tutor analysis` in Standalone Mode. In `Evidence source`, state only the highest-priority matching factual evidence class from `references/integration-and-evidence.md`; never use an input-discovery channel. Apply source priority without silently merging conflicts.
- Keep Paper Facts, Tutor Explanation, and Tutor Analysis visibly distinct; treat a role inferred from a caption such as "overview" as Tutor Analysis, not a Paper Fact.
- Apply the required formula, figure/table, experiment, or ablation contract whenever that content is requested.
- For a full Benchmark-paper output, include all 16 required Benchmark fields in their fixed order, a task-level Input/Output map, and the completed one-sentence Benchmark formula from `references/benchmark-paper.md`.
- Include the required claim-to-evidence appendix for every full-paper output and preserve available evidence identifiers and locations.
- Mark unsupported material as unavailable, not verifiable, or Tutor Analysis rather than presenting it as fact.
- Confirm that no Scholar-Slides artifact, presentation input, or reverse-contaminating output was written or instructed.
- In a complete-paper workflow, emit `READING COMPLETE` only when the Reading Completion Contract's ten fields, `reading-note.md`, `method.svg`, and one experiment-verifiable `Verification Question` are all present and evidence-safe; otherwise use `READING INCOMPLETE` and expose only the missing items.
- Keep the completion checklist internal or compact; it must not turn local tutoring into a workflow report.

## First-reading handoff

The first page should begin with a Chinese 30-second mainline, then explain the problem/gap,
the concrete input-to-output mechanism, 2–4 decisive evidence blocks, the paper's argument
chain, and only the terms that can block understanding. A term entry must define the term,
state its role in this paper, and warn about a relevant confusion; never emit a generic
“retain the original term and interpret it in context” placeholder. For Benchmark papers,
keep all 16 Benchmark Card fields, but use the table as an index and move long explanations
into grouped prose. A pending CKPT-1 status is disclosed truthfully and does not block an
already-authorized explanation; it still blocks presentation generation.
