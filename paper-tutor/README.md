# Paper-Tutor

Paper-Tutor is the teaching and reading layer for evidence-grounded academic paper work. It turns a matching Scholar-Slides evidence bundle into a reusable explanation, reading card, verification question, and tutor state.

## What Paper-Tutor is for

Paper-Tutor answers a different question from Scholar-Slides:

- Scholar-Slides asks: **What does the source support, where is the evidence, and what is still unverified?**
- Paper-Tutor asks: **How can a reader understand the paper, follow its argument, and test their understanding?**

The first page of a full-paper explanation should begin with a plain-language mainline, then connect the problem, mechanism, decisive evidence, argument chain, terms, limitations, and a concrete research question. A compact card or map is an index; it is not a substitute for the full explanation.

## Modes

### Integrated Mode

Use Integrated Mode when a matching Scholar-Slides project contains a valid `reading-view.json` and source-bound evidence.

```text
paper.pdf
  -> Scholar-Slides digest / evidence / reading-view.json
  -> Paper-Tutor explanation and reading assets
  -> optional Paper Learning Map
```

The upstream project is read-only. Paper-Tutor may explain and simplify, but it must not edit `digest.json`, `reading-view.json`, checkpoints, or slide artifacts.

### Standalone Mode

Use Standalone Mode when a readable PDF exists but no matching validated Scholar-Slides view is available. State clearly that the explanation is not verified through Scholar-Slides CKPT-1. Do not silently present a raw-PDF explanation as an integrated result.

## Teaching depth

Use `quick` for a 10–20 minute overview, `deep` for the default full reading, and `research` for assumptions, missing controls, reproducibility, generalization, cost, and alternative designs.

At every depth, preserve the sequence:

```text
plain-language mainline
  -> accurate definition
  -> minimal example or intuition
  -> exact role in this paper
  -> confusion, limitation, or boundary
```

Do not compress a full-paper request into only a benchmark table. For a benchmark paper, keep the 16-field Benchmark Card, then explain why the benchmark measures its intended capability, how a task is completed and scored, what the experiments reveal, and how far the conclusion can go.

## Claim boundaries

Every substantive statement belongs to one visible role:

- **Paper Fact:** directly supported by the highest-priority matching evidence.
- **Tutor Explanation:** a simplification, intuition, analogy, or example that does not add a new author claim.
- **Tutor Analysis:** a clearly labeled inference, critique, alternative design, or research question.
- **Unsupported:** unavailable material that must not be presented as fact.

Keep page, figure, table, equation, or evidence references with important numbers and design claims. If the source does not establish a detail, write `Not reported by the authors.` or `Not verifiable from available evidence.` rather than filling the gap from plausibility.

## Full-paper deliverables

For a complete-paper request, create one `paper-tutor.md`. When the reading-completion workflow applies, also create:

- `reading-note.md`: a three-minute Reading Card, one-sentence takeaway, and one experimentally answerable verification question;
- `method.svg`: a standalone method flow derived from the Reading Card;
- optional structured Tutor records synchronized to a matching Learning Map.

The Reading Card uses the fixed fields `Problem`, `Setting`, `Baseline`, `Method`, `Objective`, `Evaluation`, `Result`, `Ablation`, `Failure`, and `Your idea`. Do not invent a trainable objective for a benchmark that only defines an evaluation protocol.

## Learning Map synchronization

Only enable map synchronization when `paper-map.json` and `tutor-state.json` exist and their source PDF hashes match. Send structured Tutor records to the shared writer; do not reconstruct state by parsing Markdown.

```powershell
$recordsJson | python paper-tutor/scripts/learning_map_sync.py `
  --map-root "C:\path\to\scholar-slides\paper-learning-map" `
  --project "C:\papers\paper-map" `
  --origin full_analysis
```

Tutor records use stable node IDs, `source_layer: "tutor"`, and an allowed Tutor `kind`. They can add explanations, intuitions, prerequisites, misconceptions, questions, checks, and reader analysis. They must not rewrite paper facts, evidence, availability, or source traces. Uncertain anchors remain in `unresolved_items`.

## Common failure states

- `pending_human_confirmation`: explanation is allowed, but the source has not crossed CKPT-1; presentation generation remains gated.
- `unverifiable`: the current evidence does not establish the claim. Preserve the gap.
- `READING INCOMPLETE`: one of the required reading fields or learning assets is missing or evidence-unsafe.
- `sync_skipped`: no matching Learning Map exists.
- `sync_failed`: identity, schema, or atomic-write validation failed; do not claim synchronization.

## References

Read the relevant reference before producing a full output:

- `references/integration-and-evidence.md` for mode, identity, source priority, and claim roles;
- `references/teaching-and-depth.md` for adaptive explanation depth;
- `references/output-contract.md` for full-document structure and evidence appendices;
- `references/benchmark-paper.md` for benchmark papers;
- `references/reading-completion.md` for Reading Card, method SVG, and completion gating;
- `references/learning-map-integration.md` for Tutor state synchronization.
