# Paper Learning Map Integration

Paper Learning Map integration is an optional downstream projection. Paper-Tutor remains usable when no matching `paper-map.json` exists.

## When to enable

Enable the integration only when `paper-map.json` and `tutor-state.json` exist and their `paper_identity.source_pdf_sha256` values match. Read `paper-map.json` as the source-grounded navigation graph; never write to it, `reading-view.json`, or `digest.json`.

## Structured output point

Build one logical model that keeps Paper Fact, Tutor Explanation, and Tutor Analysis separate. Write the structured Tutor records to `tutor-state.json` before producing `paper-tutor.md`, `reading-note.md`, or `method.svg`. Markdown and SVG are projections; they are never parsed back as the long-term source of Tutor state.

Full analysis uses the batch `sync` operation. Follow-up Q&A uses the same `TutorStateStore` writer through `ask` or `item`. Both paths preserve existing state, validate the schema, use stable item IDs, deduplicate by node/kind/title, and write atomically.

### Structured hook (before Markdown)

When the logical Tutor model is complete, call the workspace Paper Learning Map
writer before rendering `paper-tutor.md` or any other projection. The payload is
the JSON array of structured records already classified as `tutor_explanation`,
`intuition`, `reader_analysis`, `user_question`, or another allowed Tutor kind.
It is streamed directly to the writer, so no hand-maintained `records.json` and
no Markdown round-trip are required:

```powershell
$mapRoot = $env:PAPER_LEARNING_MAP_ROOT  # or an explicitly selected project-local runtime
$recordsJson | <runtime-python> <paper-tutor-skill>/scripts/learning_map_sync.py `
  --map-root "$mapRoot" --project <matching-project> --origin full_analysis
```

Resolve `PAPER_LEARNING_MAP_ROOT` or an explicitly supplied project-local root
at runtime; never bake a machine-specific `E:\`/`C:\` path into the Skill.

The installed bridge delegates to the shared `update_tutor_state.py sync
--stdin` writer and owns no duplicate state logic. The same command is the
Full Analysis hook used by the Skill path: the model creates the structured
payload in memory, then sends it through stdin. A
follow-up answer uses `ask` with the exact stable `node_id` when available. If
the bridge is unavailable, emit a visible integration warning and continue the
Tutor response without claiming that synchronization occurred. Never parse
`paper-tutor.md` to reconstruct state.

Every bridge invocation also appends one schema-validated JSON receipt under the
matching project's `sync-receipts/` directory. Receipts are an append-only audit
trail: they record the event (`full_analysis_sync`, `incremental_qa_sync`,
`sync_skipped`, or `sync_failed`), paper identity, counts, resolved node IDs,
unresolved deltas, state hashes, and a short error summary. They never contain
the full Tutor answer and never become a source of map state. A missing map is
reported as `sync_skipped` with `reason=no_learning_map`; an identity, schema,
or atomic-write failure is reported as `sync_failed` and surfaced as a warning.

## Anchoring

Resolve a record by exact stable `node_id` first. Title or tag lookup is allowed only when it yields one candidate. Do not guess from a partial term or nearby prose. If there is no anchor, a stale ID, or more than one candidate, keep the record in `unresolved_items` with its reason and candidates.

## Record boundary

Every map item uses `source_layer: "tutor"` and a Tutor `kind`. Explanations, intuition, examples, misconceptions, reader analysis, questions, and checks must never be copied into Paper Fact fields. `reader_analysis` is an inference or critique and must remain visibly distinct. Do not update factual evidence, claim types, availability, or source traces through the Tutor writer.

## Renderer behavior

The renderer reads `tutor-state.json` alongside `paper-map.json` and synthesizes presentation-only Tutor Group and Tutor Item nodes in memory. These nodes are never appended to `paper-map.json`. The `Tutor Layer` control has three states: `Off`, `Key Notes` (default, map-visible items only), and `All`. Groups remain compact and collapsed by default; opening a Paper Fact still shows its complete Tutor data in the drawer.

## Learning state

Answering a question may record the question and its answer, but must not automatically mark a concept understood or mastered. Those states require explicit learner action or an explicit comprehension check.
