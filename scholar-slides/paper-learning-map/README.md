# Paper Learning Map

Paper Learning Map is the downstream, source-grounded map generated from a validated Scholar-Slides `reading-view.json`. It turns the paper's argument, mechanism steps, evidence blocks, terms, and takeaways into a navigable HTML map while keeping teaching notes and learner state separate.

## What the map represents

The map has two layers:

- `paper-map.json`: source-grounded nodes and relations. These preserve claim type, availability, evidence references, source traces, and the paper identity hash.
- `tutor-state.json`: downstream Tutor Layer items such as explanations, intuition, prerequisites, misconceptions, questions, comprehension checks, and reader analysis.

`study-state.json` records learner progress. It is separate from factual evidence and must not be used to rewrite the paper map.

The map is a navigation and study surface, not a replacement for the full Paper-Tutor explanation. A good `reading-view.json` gives it a narrative spine: problem → gap → approach → mechanism → decisive evidence → boundary.

## Build and render

The project must contain a valid, identity-matched `reading-view.json`, `digest.json`, and source PDF:

```powershell
python runtime/build_paper_map.py `
  --project "C:\papers\paper-project" `
  --out "C:\papers\paper-map"

python runtime/render_paper_map.py `
  --project "C:\papers\paper-map"
```

The output includes:

```text
paper-map.json       source-grounded graph
tutor-state.json     Tutor Layer state
study-state.json     learner progress
paper-learning-map.html  standalone rendered map
```

When CKPT-1 is not confirmed, the map remains valid but is marked `verification_level: "tutor_only"`. A confirmed, hash-matched CKPT-1 may promote the map to `scholar_slides_validated`.

## Reading-view requirements

The map quality depends on the reading view. For a complete paper, include:

- six overview items: `problem`, `gap`, `approach`, `insight`, `findings`, `boundary`;
- mechanism steps with purpose, input, output, and necessity;
- an argument chain whose relations explain why the evidence supports the conclusion;
- decisive evidence blocks with question, comparison, metric, result, support, and limit;
- terms with plain meaning, paper role, and likely confusion;
- takeaways that keep Reader Analysis separate from Paper Facts.

Do not seed the map from a generic abstract or from `paper-tutor.md`. The runtime consumes the validated reading view and digest directly so stale prose cannot silently become source evidence.

## Tutor synchronization

Use the shared writer for Tutor records:

```powershell
$recordsJson | python runtime/update_tutor_state.py `
  --project "C:\papers\paper-map" `
  sync --stdin --origin full_analysis
```

The writer requires exact stable node IDs. Each item has `source_layer: "tutor"` and an allowed Tutor `kind`. Unknown or ambiguous anchors are recorded in `unresolved_items`; they are never attached to a nearby node by guesswork.

Paper Facts, evidence references, availability, and source traces are owned by `paper-map.json`. Tutor synchronization may add or update teaching records, but it cannot change those source-grounded fields.

## Learner state

```powershell
python runtime/update_learning_state.py `
  --project "C:\papers\paper-map" `
  mark-understood overview.problem

python runtime/update_learning_state.py `
  --project "C:\papers\paper-map" `
  add-question method.step_2 "为什么三条件验证能排除可叠加 patch？"
```

Answering a question does not automatically mark a node understood or mastered. Those transitions require an explicit learner action or comprehension check.

## Validation and QA

Run the map tests from the repository root:

```powershell
python -m unittest discover -s scholar-slides/paper-learning-map/tests -q
```

For renderer changes, also run the relevant final-artifact and Chromium QA scripts. Check that the HTML loads offline, formulas have a fallback, node IDs resolve, the Tutor overlay does not overwrite Paper Facts, and the source identity hash remains stable.
