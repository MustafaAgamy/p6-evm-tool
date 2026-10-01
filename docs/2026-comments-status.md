# Controlyx 2026 — remaining comments

Tick a row when its work is on master. A new session reads this file first and starts at the
first unticked row of the current phase.

Effort points (rough, for planning): very small 0.5 · small 1 · small–medium 2 · medium 3 ·
medium–large 5 · large 8.

## Phase A — quick wins (≈ 6.5 points)

| Done | Comment | Work left | Points |
|------|---------|-----------|--------|
| [ ] | #28 Dark-mode PDF margins | Fix already on master; check it on a few reports | 0.5 |
| [ ] | #35 Studio: remove Overview/WBS | Small | 1 |
| [ ] | #16 Page layout in reports (Studio and Narrative) | 2 defects, the Word check, tests | 1 |
| [ ] | #26 Gantt fixes | Small–medium | 2 |
| [ ] | #37 Productivity settings change the rates | Small–medium | 2 |

## Phase B — Narrative (≈ 6 points, one session)

| Done | Comment | Work left | Points |
|------|---------|-----------|--------|
| [ ] | #23 The 31 failing Narrative/Word tests | Do first: a green suite makes every later check cheaper | 3 |
| [ ] | #17 Saint Gobain critical path in Narrative | Medium | 3 |

## Phase C — AI Chat (≈ 14 points, one session if possible)

| Done | Comment | Work left | Points |
|------|---------|-----------|--------|
| [ ] | #14 AI Chat clear answers | Medium | 3 |
| [ ] | #15 AI Chat behaves like Claude | Medium; shares the answer-building code with #14 | 3 |
| [ ] | #39 AI Chat dashboard as PDF | Medium; uses the one PDF helper (`p6_export/pdf.py`) | 3 |
| [ ] | #33 AI Chat more charts | Medium–large; charts must also print in #39 | 5 |

**Checkpoint release** after Phase C: add a `## [vX.Y.Z]` heading to `CHANGELOG.md` and merge,
so a working exe exists whatever happens to Phase D.

## Phase D — large, per-feature work (≈ 40 points)

| Done | Comment | Work left | Points |
|------|---------|-----------|--------|
| [ ] | #1 + #2 + #29 Pickers, same output in all 5 formats, full Excel — every feature | One pass per feature using `docs/report-picker-adoption.md`; Excel is one of the 5 formats, so #29 rides along. Done separately ≈ 24 points | ≈ 14 |
| [ ] | #38 Knowledge Base: more projects | Large; mostly content | 8 |
| [ ] | #9 Course videos | Large; agree the scope (what the videos show, who records them) before starting | 8 |

Per-feature progress for #1/#2/#29 (Earned Value and P6 Calendar Audit already have the picker):

| Done | Feature |
|------|---------|
| [x] | Earned Value (picker) |
| [x] | P6 Calendar Audit (picker) |

## Phase E — finish

| Done | Comment | Work left | Points |
|------|---------|-----------|--------|
| [ ] | #3, #5, #18 Final whole-tool check | After everything else | 3 |
| [ ] | #20, #21 (and #19) Final merge and final exe | Last | 2 |

## How to save usage (staying on Pro)

- **Acceptance first:** before a comment starts, the owner writes 2–3 lines of "done means …"
  next to its row. Redoing a misunderstood comment is the biggest waste.
- **Sonnet builds, Opus reviews:** Sonnet writes the code and tests; one Opus pass reviews the
  whole phase's diff before its merge (not one reviewer per comment). Opus builds only #23,
  #17 and #15.
- **Tests are the quality gate:** every comment gets a test that fails before the fix and
  passes after. Related tests while working (`pytest -q -x tests/test_<area>*.py`); the full
  suite once per phase, before the merge.
- **No subagents or worktrees** for small and medium comments; the per-phase review replaces
  them.
- **The owner checks the exe by hand** at the checkpoint release and at the end; Claude's live
  headless checks only for the first feature of Phase D.
- One fresh session per phase (or per few features in Phase D). Commit and push after each
  comment and tick its row here.
- #9 Course videos: Claude writes the scripts and shot list; the owner records.
