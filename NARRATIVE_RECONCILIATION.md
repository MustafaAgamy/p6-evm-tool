# Narrative Report — Golden-Reference Reconciliation (binding spec)

**Golden Reference:** `Roots Narrative REV.03.docx` (RME/ROWAD, Grain-Bulk-Terminal-class
project). It is the CONTENT baseline and the FORMATTING/VISUAL reference. The feature must
preserve the reference's information value while adding editable, data-driven, P6-based
output. Improve presentation; never silently drop information. Project-agnostic — no client
names in code. Word and PDF must look like the same professional report.

## A. Content reconciliation (section-by-section)

Legend: v5 = present in current 5-section build · OLD = producer still exists (builder.py /
scope.py / costflow.py / codes.py) · NEW = Schedule-Intelligence (detect_fronts).

| # | Reference section | In v5? | Source to use | Action |
|---|---|---|---|---|
| 1 | Introduction | yes (overview) | NEW overview (executive) | keep; editable prose |
| 2 | Project Layout (image) | no | setup.layout | RESTORE (image section) |
| 3 | Project Brief (table) | no | OLD keyvals (parties/dates/budget) | RESTORE |
| 4 | Project Milestones | yes | milestones (finish + key dates) | keep + add key-dates timeline |
| 5 | Major Dates from Client | no | milestones w/ client constraint dates | RESTORE |
| 6 | Project Value | no | OLD cost_by_wbs / contract value | RESTORE |
| 7 | Scope of Work (per discipline) | no | OLD scope_blocks | RESTORE, editable |
| 8 | Calendars & Holidays | no | OLD _calendars_payload (Calendar feature) | RESTORE |
| 9 | WBS — per-branch org-charts | partial (one flat) | NEW per-branch adaptive org-chart | UPGRADE (see C) |
| 10 | Activity Codes | no | OLD _codes_payload + read_code_catalog | RESTORE |
| 11 | Activity IDs | no | OLD _id_anatomy | RESTORE |
| 12 | General Sequence (Design & Procurement) | partial | NEW cycle fronts | UPGRADE flow-charts |
| 13 | Sequence of Work (per area/front) | yes | NEW detect_fronts | keep + fix logic (D) |
| 14 | Interfaces & Dependencies | yes | NEW interactions | keep (macro flow + notes) |
| 15 | Major Quantities / Productivity & Resources | no | OLD prose (not in P6 -> honest note) | RESTORE (honest) |
| 16 | Cost Loading / Cash Flow | no | OLD cost_by_wbs / cash_flow | RESTORE |

**Target section order** (professional planning report): 1 Introduction · 2 Project Layout ·
3 Project Brief · 4 Milestones (+key dates) · 5 Major Dates from Client · 6 Project Value ·
7 Scope of Work · 8 Calendars & Holidays · 9 WBS · 10 Activity Codes · 11 Activity IDs ·
12 General Sequence (Design & Procurement) · 13 Sequence of Work · 14 Interfaces &
Dependencies · 15 Quantities & Resources · 16 Cost Loading & Cash Flow.

Renderers: the OLD kind-renderers (keyvals/scope/calendar/codes/idanatomy/costbars/cashflow/
image) were removed in the v5 rewrite — RECOVER them from git (`git show 8fc5c3f:p6_narrative/
html.py`, `…:p6_narrative/docx_writer.py`) and merge with the v5 kinds. Every section kind must
render in BOTH html.py and docx_writer.py.

## B. Shared formatting spec (Word == PDF, from the reference)

Both renderers MUST target the same spec so the outputs are visually consistent:
- **Page:** A4 portrait, margins ~2.0 cm all sides.
- **Page border/frame:** a true page-level frame on EVERY page, inside the margins, never
  overflowing to the next page, unbroken across section page-breaks. HTML/PDF: `@page { }` +
  a repeating border technique (not a border on one long div). Word: `w:pgBorders` in each
  section `sectPr`.
- **Header:** the three party logos (owner/consultant/contractor) when provided (meta.logos),
  else a title band. Same in preview, PDF, Word.
- **Footer:** automatic **Page X of Y** (Word fields PAGE/NUMPAGES; PDF via paged-media/Chrome
  footer). Present on every page in both.
- **Headings:** numbered hierarchy — H1 bold navy for the 16 sections, H2 for sub-sections.
- **Fonts:** one family (e.g. Segoe UI / Calibri), consistent sizes: H1 ~16pt, H2 ~13pt,
  body ~10.5pt, table ~9.5pt. Same in both.
- **Tables:** navy header row, thin borders, zebra rows — identical look in both.
- **Spacing / density:** professional, matching the reference; consistent section separation.

## C. WBS visualization (section 9)

- Data-driven from the ACTUAL P6 WBS hierarchy (children_of_wbs), never inferred from names.
- Preserve exact parent->child; a node's children sit under IT, never implying false siblings.
- **Full depth** (the reference file reaches depth 10 — remove/raise the depth-3 cap; only
  cap breadth with "+N more").
- Adaptive: small branch -> centered top-down org-chart; large/deep -> compact multi-column
  indented tree. Adaptive fallback, not the default.
- One chart PER major WBS branch (like the reference), not one giant chart.

## D. Sequence of Work (sections 12/13)

- Order strictly by the schedule's RELATIONSHIP logic (FS/SS/FF predecessors->successors) via
  topological order — NEVER by start/finish date or activity id. Where a front's internal
  logic is insufficient to order it, say so rather than presenting a date-order guess.
- Package/major-WBS altitude, consolidated (no per-discipline duplication, no activity dump).
- Editable + DYNAMIC arrows: adding/removing/reordering a step re-renders the flow with NO
  orphan arrows (none before the first box or after the last, none left by a removed middle
  step).

## E. The six tester bugs (must all close)

1. WBS hierarchy correctness (-> C).  2. Header logos missing across preview/Word/PDF (-> B).
3. Word/PDF inconsistency (-> B single spec).  4. Page border overflow (-> B page-level).
5. Page numbering missing (-> B Page X of Y).  6. Sequence ordered by dates not logic (-> D).

## F. Acceptance

"The new Narrative Report preserves the information value of the original Word report while
providing the new editable, data-driven, P6-based functionality." Validate content
completeness, structure, formatting, border, page numbering, WBS viz, sequence viz, charts,
tables, and Word/PDF visual consistency against the Golden Reference before calling it done.
