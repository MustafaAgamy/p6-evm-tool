# Special Report — provider contract

A provider exposes one feature's detailed results to Special Report. It is a module
`p6_special/providers/<feature>.py` with:

```python
def provide(ctx) -> list[registry.Item]
```

Keep `provide` cheap (no parsing). Do heavy recompute inside each item's
`produce(ctx)` closure, memoized via `ctx.memo(key, fn)`.

## Item

```python
from p6_special.registry import Item
Item(id, feature, feature_title, title, ctype, produce, availability=None, requires=None)
```
- `id` — globally unique, `"<feature>:<key>"` (e.g. `"audit:float_score"`).
- `feature` / `feature_title` — group key + display name (e.g. `"audit"` / `"Schedule Audit"`).
- `title` — the result's name as the user sees it (granular: one metric per item where sensible).
- `ctype` — `kpi|table|chart|findings|text|score|summary` (UI badge only).
- `produce(ctx)` — returns ONE payload (see below). Return `payloads.NO_DATA` if absent.
- `availability(ctx)` — returns `'ready' | 'needs_input' | 'no_data'`.
- `requires` — list of `{'role','label','accept','hint'}` for extra files needed
  (only for two-/three-file features). The UI highlights these and lets the user
  attach; attached paths arrive on `ctx.inputs[role]`.

## Payload vocabulary (`from p6_special import payloads as P`)

- `P.kpi_group([P.kpi(label, value, sub=None, tone=...)])` — row of KPI tiles.
- `P.table(columns, rows, aligns=None)` — rows are lists of cells; a cell may be
  `(text, tone)` to colour it. `aligns` each `'l'|'r'|'c'`.
- `P.bars(rows, series, note=None)` — `series=[{'label','tone'}]`;
  `rows=[{'label','values':[0..100],'display':[str]}]` (values on a 0..100 scale).
- `P.segbar([{'label','value','tone'}], note=None)` — one 100%-stacked bar.
- `P.findings([{'severity':'high|medium|low|info','title','detail'}], empty=...)`.
- `P.keyvals([(label, value)])`, `P.text(str|list[str])`, `P.note(msg, tone=...)`.
- `P.group([block, block, ...])` — several payloads shown as one section.
- `tone` = `'neutral'|'accent'|'good'|'warn'|'bad'`.

## Formatting (`from p6_special import fmt`)

EVM percentages are **0..1 fractions** → `fmt.pct01(x)` / `fmt.signed_pct01(x)`.
Values already on 0..100 → `fmt.pct100(x)`. Ratios (SPI/CPI) → `fmt.ratio(x)`.
Money (PV/EV/AC) → `fmt.money(x)`. Working days → `fmt.days(x)`. Counts → `fmt.num(x)`.
**Verify each feature's own scale by reading its code — do not guess.**

## Context API (`ctx`)

Parse-free DB reads (memoized): `ctx.evm`, `ctx.audit`, `ctx.calendar`,
`ctx.settings`, `ctx.weather`, `ctx.extras`, `ctx.snapshots`, `ctx.meta`,
`ctx.snapshot_id`, `ctx.project_name`, `ctx.data_date`.
Recompute (memoized): `ctx.has_xml()`, `ctx.parsed()` (ScheduleData or None),
`ctx.computed()` (full EVM result incl. `records`), `ctx.config`.
Attached inputs: `ctx.has_input(role)`, `ctx.input_path(role)`,
`ctx.parsed_input(role)` (ScheduleData of the attached file).

## Availability rules

- Result derivable from the imported file alone → `'ready'` (DB-backed or a
  single-file recompute via `ctx.parsed()`/`ctx.computed()`). Guard with
  `ctx.has_xml()` / presence of the DB slice; else `'no_data'`.
- Result needs an extra file → `'needs_input'` until `ctx.has_input(role)` for
  every required role, then `'ready'`. Declare each in `requires`.

## Rules

- Never recompute a metric a feature already stores if the DB has it — read `ctx`.
- Reuse each feature's own compute entry point for recompute (don't reimplement maths).
- One test file `tests/test_special_<feature>_provider.py`: seed via `temp_db` +
  the `xml_path` fixture (`tests/fixtures/minimal.xml`), assert each item's
  `produce(ctx)` returns a payload dict without raising, and assert availability.
- Match the shape/scale by READING the feature's code (see the data-source map in
  each task). Copy `providers/evm.py` for the pattern.
