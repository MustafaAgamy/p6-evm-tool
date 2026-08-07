# AI Schedule Audit — Phase 1 Design (Single-Schedule Quality Core)

**Status:** Approved design — ready for implementation planning
**Date:** 2026-07-31
**Feature ID:** PC-001 (from `AI_Schedule_Audit_System_Specification_V1.docx`)
**Scope of this doc:** Phase 1 only. Later phases (comparison/evolution, calendar what-if, AI reasoning layer) are designed *around* but not built here.

---

## 1. Summary

Add a **Schedule Quality Audit** to the existing P6 EVM Tool. It parses a Primavera schedule
(XER or XML), builds a relationship graph, runs **deterministic rule-based checks** (open ends,
dangling logic, circular logic, float analysis), computes a transparent **Schedule Health Score**,
and displays findings in the existing single-page dashboard next to the EVM results — with a PDF
and Excel export.

The audit engine is **fully offline and AI-free** in Phase 1. A visually distinct, clearly-labeled
**"AI Engineering Observations"** area is reserved in the UI and data model but stays empty until a
later phase adds the optional AI layer. No fabricated confidence scores are shown for deterministic
findings.

### Guiding decisions (from brainstorming)

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Deployment:** internal tool first, productize later | Sets a moderate liability/polish bar; keep AI isolated and optional |
| 2 | **AI role:** deterministic engine is the product; AI is a later, optional, isolated enrichment layer | ~80% of audit value is deterministic; keeps the offline `.exe` intact; avoids sending schedules to a cloud LLM |
| 3 | **Two buckets:** rule-based findings (trustworthy) vs. AI observations (opinion), visually separated | Different kinds of truth must look different to the user |
| 4 | **Comparison is a core goal**, built in a later phase | Phase 1 persists per-activity/relationship detail so future update-to-update diffing is a pure DB read |
| 5 | **Phase 1 = single-schedule quality core** | Ships fast, one file in → real audit out; every later module reuses it |
| 6 | **XER required now**, normalized into the existing `ScheduleData`; XML kept working | XER natively carries relationships/float/critical/type; both formats feed one pipeline |
| — | **Calendar what-if (CPM recalc engine) deferred** | Highest effort/risk, separable, not needed to prove the pipeline |

---

## 2. Scope

### In scope (Phase 1)

- **XER parser front-end** normalizing into the existing `ScheduleData` model.
- **Parser/model extension**: relationships, total/free float, activity type, constraints, activity codes, full WBS path.
- **Deterministic checks:** LOGIC-001 Open Ends, LOGIC-002 Dangling, LOGIC-003 Circular, FLOAT-001 (snapshot only).
- **Schedule Health Score** (transparent, deductive, partial-normalized across computed categories).
- **Findings persistence** (Global Finding Output Standard) + per-snapshot activity/relationship detail.
- **Dashboard**: score gauge + category breakdown; two buckets (rule-based populated, AI placeholder); grouped findings list; Severity/Check/WBS filters.
- **Reports**: PDF (extends existing) + Excel findings export.

### Explicitly deferred (later phases — designed to require no rework)

- LOGIC-004 Relationship Realism (this is the AI-dependent check).
- Critical Path Evolution (CP-001), Float Evolution, Schedule Integrity diff (CON-001), Calendar comparison (CAL-001).
- Calendar **what-if** simulation (requires a CPM forward/backward-pass recalculation engine).
- AI Consultant Reasoning layer (AI-001) and AI-enriched narrative fields.
- PowerPoint export.
- Discipline/Activity-level filters (arrive with their modules).

---

## 3. Architecture

**Approach A — "Extend, don't fork."** One normalized model, a pure audit engine mirroring the
isolation of `p6_evm/`, findings persisted on import, dashboard reads from the DB.

```
XER / XML  ──►  parser (normalized ScheduleData)  ──►  p6_evm.compute()   ──►  EVM metrics
                                                   └─►  p6_audit.audit()   ──►  findings + scores
                                                                                   │
                                     server persists both to SQLite (per snapshot) │
                                                                                   ▼
                              dashboard reads metrics + audit from DB (no re-parse)
```

### 3.1 Parser & normalized model

- **`parse_file(path)`** dispatches on extension: `.xer` → new XER parser, `.xml` → existing XML parser. Both emit the same `ScheduleData`.
- **XER front-end** reads the tab-delimited format (`%T` table / `%F` field names / `%R` rows). Tables consumed: `PROJECT`, `PROJWBS`, `TASK`, `TASKPRED`, `CALENDAR`, `TASKRSRC`, `ACTVCODE`/`TASKACTV`. Unknown tables and missing optional fields are ignored.
- **`ScheduleData` extension (additive; EVM fields untouched):**
  - New `relationships: list[{pred_id, succ_id, type ∈ {FS,SS,FF,SF}, lag_days}]`.
  - Per activity: `task_type` (Task / Start-Milestone / Finish-Milestone / LOE / WBS-summary), `total_float_days`, `free_float_days`, `is_critical`, `constraint_type`, `constraint_date`, `activity_codes`.
- **Units:** XER stores durations/float in **hours**; convert to **working days** using each activity's calendar hours-per-day. XER is the tested primary path. For XML, float is **derived** from late−early dates where present; XML audit support is best-effort (XML EVM behavior is unchanged).
- **Activity identity (Global Rule):** primary key = **Activity ID** (`task_code` in XER, `Id` in XML). A **full WBS path** string ("Tower 33 > Foundation > Raft") is built by walking the WBS parent chain. Name is display-only. Every finding carries ID + Name + WBS path.

### 3.2 Audit engine — `p6_audit/` (pure, offline, no I/O)

- **`graph.py` — `ScheduleGraph`**: built once from activities + relationships. Provides predecessor/successor adjacency, typed edges (with lag), lookups by ID and by WBS, and the critical set. Every check reads this single structure. Complexity O(activities + relationships).
- **Checks — one module per check, identical signature** `check(graph, config) -> list[Finding]`:
  - `logic_open_ends.py` — real activities (task_type = Task; Start/Finish milestones, LOE, WBS-summary excluded) with predecessor_count = 0 (missing predecessor) or successor_count = 0 (missing successor).
  - `logic_dangling.py` — **start not controlled**: no predecessor tie into the activity via FS or SS. **finish not controlled**: no successor tie out via FS (this activity as predecessor) or FF. Report which end(s) dangle.
  - `logic_circular.py` — Tarjan strongly-connected components; any SCC of size > 1 (or a self-loop) reported as a complete loop chain.
  - `float_snapshot.py` — per activity total/free float; flag **negative** (TF < 0), **zero/critical** (TF ≤ 0), **excessive** (TF > threshold, default **44 working days**, configurable); compute % of activities excessive and the WBS with the highest excessive concentration.
- **`scoring.py`**: per category start at 100, subtract a per-finding penalty by severity (Critical/High/Medium/Low weights from `config.json`), floor at 0. Overall = weighted average across **only the categories computed**, re-normalized. No black-box math.
- **`audit(data, config) -> dict`**: build graph → run each check → collect findings → score → return `{findings, scores, categories_evaluated}`. Single entry point `server.py` calls, analogous to `compute()`.

### 3.3 Severity model

- Base severity by **WBS category**, reusing the existing `config.json` category mapping (the same one EVM uses for weighting) — no second classification system.
- **Critical-path escalation:** any finding on an activity with TF ≤ 0 escalates to **Critical** regardless of category.
- Severity weights and the float threshold are configurable in `config.json`.

### 3.4 Confidence

Deterministic findings do **not** show a fabricated confidence percentage. They carry a **severity**
and a plain **basis** string (e.g. `successor_count = 0 · total_float = 0`). The `confidence` field
exists in the finding schema (nullable) for the future AI layer, and renders as "—" for rule-based
findings.

---

## 4. Data model & flow

### 4.1 Finding object (Global Finding Output Standard)

```
finding_id, check_id, check_name, category, severity,
activity_id, activity_name, wbs_path,
related_activity_id, related_activity_name,   # e.g. other end of a bad relationship / loop
summary, basis,                                # basis = deterministic reason string
recommendation,                                # templated for rule-based checks
confidence                                     # null in Phase 1; AI layer fills later
```

Narrative-heavy spec fields (Engineering Explanation, Root Cause, Business Impact, Risk if Ignored)
exist in the schema but are **templated** in Phase 1 and become AI-enriched later — no schema change
when that happens.

### 4.2 New DB tables (additive; follow the existing snapshot model)

```
audit_findings       — one row per finding, FK snapshot_id  (implements the standard above)
audit_scores         — per-category + overall score + categories_evaluated, FK snapshot_id
activity_detail      — per-activity rows per snapshot (id, name, wbs_path, type, TF, FF, critical, constraint...)
relationship_detail  — per-relationship rows per snapshot (pred_id, succ_id, type, lag_days)
```

`activity_detail` and `relationship_detail` are the per-snapshot detail that makes future
update-to-update comparison a **pure DB diff** — honoring "parse once, read from DB forever."

### 4.3 Flow — audit runs once, on import, persisted

```
POST /api/parse
  → parse_file() (XER or XML) → ScheduleData
  → compute()  [existing EVM]              → metrics
  → audit(data, config)  [NEW]             → findings + scores
  → cache file + insert snapshot
  → insert metrics + category_metrics      [existing]
  → insert audit_findings + audit_scores + activity_detail + relationship_detail  [NEW, one transaction]
  → return {result, audit}   (records stripped, as today)
```

- **Reload** an existing project: `GET /api/audit/{snapshot_id}` reads findings + scores from the DB — **no re-parse**.
- **PDF**: existing exception — re-parses via `resolve_xml_path()` for full `ScheduleData`, then renders.

### 4.4 API routes (additions)

| Method | Path | Returns |
|--------|------|---------|
| POST | `/api/parse` | *(extended)* `{ok, result, audit, cached_path}` |
| GET | `/api/audit/{snapshot_id}` | `{findings, scores}` for the dashboard (no XML touched) |
| POST | `/api/report` | *(extended)* PDF now includes audit pages |
| POST | `/api/export/excel` | Excel findings-table file |

---

## 5. UI / dashboard

Built into the existing single-page app, reusing the module pattern, theme system, HTML-escaping,
and JS tooltip.

- **Schedule Audit section** below the EVM tiles (same page, same import).
- **Health Score**: gauge with the honest label *"78/100 · based on 2 of 5 modules (Logic, Float)"*; per-category mini-bars, with not-yet-built categories shown greyed ("— soon").
- **Two buckets:**
  - **Rule-Based Findings** — authoritative styling; populated.
  - **AI Engineering Observations** — visually distinct (accent color + "opinion" pill); a clearly-labeled empty placeholder in Phase 1 ("Coming in a later phase"). The slot exists now so the AI layer drops in later with zero UI restructuring.
- **Findings list**: grouped by check; each row = severity chip + Activity ID + Name + WBS path; expander reveals Basis / Why it matters / Recommendation. Confidence shown as "—" for rule-based.
- **Filters** (client-side over loaded findings): Severity, Check/Category, WBS. Discipline/Activity deferred.
- **Actions**: Export Excel, Generate PDF Report.

---

## 6. Error handling

- **Corrupt / invalid file** → show error banner, keep the previously loaded project intact. Audit rows are written in a **single transaction**; if the audit throws, its rows roll back together (no orphaned findings).
- **Missing audit inputs** (e.g. XML without relationships/float) → checks that cannot run are marked *"not evaluated — data unavailable"* rather than throwing or scoring 0. The "N of M modules" score label reflects what actually ran.
- **XER quirks** (unknown tables, extra columns, missing optional fields) → tolerated; only genuinely unparseable structure errors out.
- **Large schedules** → single graph build, linear checks. Realistic tested limits will be documented; the spec's 500k-activity figure is a stretch target, **not** a Phase 1 guarantee.

---

## 7. Testing

Matching the existing 134-Python / 44-JS discipline.

- **XER parser** — unit tests on a small hand-written XER fixture: table parsing, hours→working-days conversion, WBS-path building, relationship extraction.
- **Each check** — tiny hand-built graphs with known answers: a deliberate open end (missing pred / missing succ), an SS-only dangler, a planted 3-node loop, floats above/below threshold. Exact assertions (deterministic).
- **Scoring** — fixed finding sets → known scores, including partial-normalization across computed categories.
- **Integration** — one realistic sample schedule end-to-end: parse → audit → persist → load-from-DB; assert no re-parse on reload.
- **EVM regression** — existing suite stays green, proving the additive parser/model changes don't disturb EVM.

---

## 8. Files touched / added

**Added**
- `p6_evm/xer_parser.py` — XER front-end → `ScheduleData` (or `p6_evm/parser_xer.py` per repo convention)
- `p6_audit/__init__.py`, `graph.py`, `logic_open_ends.py`, `logic_dangling.py`, `logic_circular.py`, `float_snapshot.py`, `scoring.py`, `findings.py`
- `ui/modules/audit.js` — audit render + filters
- Excel export helper (module TBD in plan)
- Tests under existing test dirs

**Modified (additive)**
- `p6_evm/parser.py` — extended `ScheduleData` (relationships, float, type, constraints, codes, WBS path); dispatch to XER
- `db.py` — new tables + insert/read functions; extend the import transaction
- `server.py` — call `audit()` in `_handle_parse`; new `/api/audit/{id}` and `/api/export/excel`; extend `/api/report`
- `report.py` — audit pages in the PDF
- `ui/index.html`, `ui/style.css`, `ui/app.js` — audit section, buckets, wiring
- `config.json` — severity weights + float threshold

**Not modified in behavior**
- Core EVM computation in `p6_evm/metrics.py` (guarded by regression tests)

---

## 9. Out-of-scope guardrails (do not build in Phase 1)

- No CPM recalculation engine.
- No LLM/network calls.
- No multi-schedule comparison logic (storage is prepared, diffing is not built).
- No PPT export.
- No fabricated confidence percentages anywhere.
