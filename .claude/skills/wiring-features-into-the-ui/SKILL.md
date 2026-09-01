---
name: wiring-features-into-the-ui
description: Use when planning, implementing, or marking done any user-facing feature in Controlyx (new import source, button, panel, KPI, view) — before writing the plan and before claiming the feature works. Symptoms you are about to violate this: "coming soon" placeholder, "the UI is a later phase", "the backend/parser is done", a feature that only a test or CLI can reach.
---

# Wiring Features Into the UI

## Overview

**A feature is not done until a user can reach it in the app and it looks like it belongs there.**

Parsing, metrics, an API route, a passing test — none of that is a *feature* until it is wired into `ui/` and matches the existing pattern. Backend work that a user cannot click is invisible work. This skill exists because that exact mistake shipped once: an XER import + audit engine were built, tested, and released with the UI card still reading "Coming soon" and not clickable. The user had to discover it was unreachable.

**Violating the letter of this rule is violating the spirit of it.** "The parser works" is not "the feature works."

## The Rule

Every user-facing feature plan MUST include a UI task, and that task is not complete until:

1. **Reachable** — a real user can trigger it from the interface (button, card, drag-drop, menu), not only from a test or `cli.py`.
2. **Consistent** — it reuses the existing component pattern (same classes, same wiring path), not a one-off.
3. **Stateful** — loading, success, and error states are handled the same way siblings handle them.
4. **Verified** — you confirmed it renders and works, not just that the backend returns data.

No shipping a feature behind a disabled/"Coming soon" element that you are actually delivering this cycle. Placeholders are for work that genuinely is not being built yet — never for the thing you just built.

## When To Use

- Writing a spec or plan for anything a user will see or click → add the UI task now, in the plan.
- Implementing a feature whose backend/parser/route is finished → the job is half done.
- About to mark a feature complete, commit "done", or trigger a release build.
- Adding a new import source, KPI tile, report section, settings control, or dashboard panel.

**When NOT to use:** pure internal refactors, DB migrations, or CLI-only tooling with no user-facing surface. (If unsure whether it has a surface, assume it does.)

## Reference: the 5 touch-points to add a file-import path

To wire a new import source (this is the map the XER feature should have followed from the start):

| # | File | What to add |
|---|------|-------------|
| 1 | `app.py` — `Api.choose_file()` | Add the extension to `file_types=(...)` so the native picker shows it |
| 2 | `ui/index.html` | An `.import-card` with `card-icon` / `card-name` / `card-sub` / `card-btn` (unique id) / `spinner` (unique id) — copy the XML card verbatim, change ids + labels |
| 3 | `ui/app.js` | `getElementById('<id>-btn').addEventListener('click', ...)` → `await window.pywebview.api.choose_file()` → `importFile(path)` |
| 4 | `ui/app.js` drag-drop handler | Add the extension to the accepted-extension check |
| 5 | `ui/modules/render.js` — `setLoading()` | Toggle the new button + spinner so the loading state is consistent |

The parse flow itself (`importFile` → `POST /api/parse` → `renderResults`) is shared — you do NOT re-implement it. New formats are handled in `parse_file()` dispatch, not in the UI.

### The card pattern (copy, don't invent)

```html
<div class="import-card">
  <div class="card-icon" style="background:#0ea5e9"> <!-- svg icon --> </div>
  <div class="card-name">Import XER</div>
  <div class="card-sub">P6 XER Export</div>
  <button class="card-btn" id="xer-btn">Browse File</button>
  <div class="spinner hidden" id="xer-spinner"></div>
</div>
```

Every import card has a **Browse File button** — not a clickable card div. Match siblings exactly; a missing button or spinner is a broken pattern even if it "works".

## Rationalizations — STOP if you catch yourself here

| Excuse | Reality |
|--------|---------|
| "The plan says this phase is backend-only" | Then the plan was wrong. A phase that ships something a user touches includes its UI. Split phases by feature, not by layer. |
| "The parser/route/test works" | That is plumbing, not a feature. Users click buttons, not functions. |
| "I'll wire the UI in the next plan" | The next plan is not guaranteed to happen before a release. Unreachable code ships as a dead placeholder. |
| "I made the whole card clickable, close enough" | Siblings use a Browse File button + spinner. "Close enough" is a broken pattern. Match it. |
| "It's obvious how to trigger it" | If it is not wired, it is not triggerable. Obvious-to-you ≠ reachable. |
| "Leaving 'Coming soon' is harmless" | It shipped a released .exe advertising a feature as absent that was actually present. That is worse than nothing. |

## Red Flags — the feature is NOT done

- A `.import-card`, button, or menu item marked `disabled` or "Coming soon" for something you built this cycle
- The only way to exercise the feature is a pytest or `cli.py` invocation
- A new card/panel that doesn't reuse the existing classes and wiring path
- New button with no matching entry in `setLoading()` (loading state will be wrong)
- You are about to commit "feat: X" or trigger a build without having seen X work in the app

**Any of these means: go back to the 5 touch-points and finish the wiring before claiming done.**

## Definition of Done (verification)

Before marking a user-facing feature complete:

1. The trigger exists in `ui/` and is enabled.
2. It follows the sibling pattern (classes, ids, button+spinner).
3. Loading / success / error states are wired.
4. You launched the app (or the build) and **watched the feature work end-to-end** — picked the file, saw it parse, saw the result render.

Evidence before assertion: "it works" requires having seen it work in the UI, not in a test.
