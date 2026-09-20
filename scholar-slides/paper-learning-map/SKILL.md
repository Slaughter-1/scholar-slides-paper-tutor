# Paper Learning Map

Paper Learning Map is a downstream, source-grounded learning view. It consumes a
validated Scholar-Slides `reading-view.json`, projects facts into `paper-map.json`,
and keeps tutor explanations and user progress in separate state files.

It never writes to `reading-view.json`, `digest.json`, checkpoints, or Mode B.

## Build

```powershell
python runtime/build_paper_map.py --project <scholar-slides-project> --out <output-dir>
python runtime/render_paper_map.py --project <output-dir>
```

The generated `paper-learning-map.html` is standalone and can be opened directly.
Validated projects may also emit the derived `formula-index.json`. The renderer
vendors KaTeX locally (including fonts) and inlines the bundle, so formula blocks
render offline in the detail drawer while retaining raw LaTeX and a local fallback
when parsing fails. The formula index is presentation-only: it never writes back to
`paper-map.json`, `reading-view.json`, or `digest.json` and is rejected when its paper
identity or validation level does not match the loaded map.

## State updates

```powershell
python runtime/update_learning_state.py --project <output-dir> mark-understood <node-id>
python runtime/update_learning_state.py --project <output-dir> add-question <node-id> "Question text"
```

Only `tutor-state.json` and `study-state.json` are writable downstream state.

## Paper-Tutor structured hook

Paper-Tutor should send its in-memory Full Analysis records to the shared writer
before it renders Markdown. The preferred bridge does not create a hand-edited
records file:

```powershell
$recordsJson | python "$env:PAPER_LEARNING_MAP_ROOT/runtime/update_tutor_state.py" `
  --project <output-dir> sync --stdin --origin full_analysis
```

Set `PAPER_LEARNING_MAP_ROOT` to this runtime root or pass an explicitly
selected project-local root; the installed Skill must not depend on a fixed
machine path.

Follow-up questions use the same writer through `ask`; exact stable `node_id`
comes first, and uncertain anchors stay in `unresolved_items`. The fallback
`sync --from-paper-map` command is a validation helper only; it produces
conservative teaching scaffolding from map semantics and must not be described
as a model-generated Tutor analysis.

Each `sync --stdin` transaction appends a schema-validated receipt under the
project's `sync-receipts/` directory. Receipts expose event type, status,
counts, node resolutions, unresolved deltas, study-state transition, and before /
after state hashes without copying answer text. Missing maps are observable as
`sync_skipped`; identity, schema, and atomic-write failures are `sync_failed` and
must be surfaced to the Tutor caller rather than reported as successful sync.
