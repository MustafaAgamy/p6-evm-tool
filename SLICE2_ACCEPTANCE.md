# Narrative Intelligence — Grouping / Front-Detection Acceptance (governing spec)

This is the acceptance gate for the repeated-work-front engine (`p6_narrative/intel/`).
It is the single source of truth for "is the grouping correct". Locked with Ibrahim
(planning engineer, authority on the planning truth). **Do not hardcode any client name
or structure below — Saint-Gobain and Alstom are real-world acceptance tests for a
project-agnostic rule, never targets to fit.**

## The ten criteria

1. Meaningful repeated work fronts
2. Meaningful schedule coverage
3. No over-lumping
4. No artificial fragmentation
5. No duplicate fronts
6. WBS / parent / scope context preserved
7. Complete traceability to the original P6 activities
8. Deterministic output
9. Reasonable runtime
10. No project-specific hardcoding

## The governing priority (most important rule)

**Meaningful structure is more important than maximizing coverage or group count.**
The selector optimizes in this strict order:

> meaningful fronts → meaningful coverage → no over-lumping → no artificial
> fragmentation → no duplicate fronts → preserved WBS/parent/scope → full traceability

- If increasing coverage requires creating artificial or duplicate groups, **do not
  increase coverage**.
- If avoiding fragmentation makes 70–80% of a real schedule disappear from the analysis,
  that is **also not acceptable**.
- The engine must be able to say: *"I can confidently identify these repeated fronts,
  while these other activities/scopes lack sufficient structural evidence to be grouped."*
  Honest ungrouping beats forcing every activity into a front.

## Permanent fixture gate (automated, `tests/test_intel_fronts.py`)

road=12 fronts · tower=25 floors + podium separate · opaque=honest (8 fronts or nothing)
· phase_vs_trade=3 worlds (14 construction + 8 engineering + 10 procurement) ·
no_repetition=0 groups · scale≈13k within runtime budget · engine source carries zero
client names. **Any future selector change must keep these green automatically.**

## Real-world acceptance examples (planning ground truth — NOT to hardcode)

### Saint-Gobain
- `Conveyors`, `Steel` are valid meaningful construction fronts.
- `Mixer Building`, `Batch Building` are valid construction fronts **when they contain a
  coherent repeated sequence**; do not merge them just because both are "construction".
- `SDA` / `SDS` families must **not** fragment into artificial slivers because labels or
  branches differ. Where SDA/SDS are the same repeated front pattern, recognize the common
  front while **preserving the real parent/WBS context**.
- 21.3% coverage is clearly insufficient — a few correct groups is not success if most of
  the schedule is unexplained.
- Engineering / Procurement / Construction must not silently disappear. Represent a world
  as its own scope **when meaningful repeated/package structure exists there** — but do not
  force Engineering/Procurement activities into a front just to raise coverage.

### Alstom
- `Approval` and `Submittal` should generally be **one document-control/package front when
  they refer to the same underlying scope/package** — not duplicated fronts because names
  differ by "Approval" vs "Submittal". This must be based on the underlying scope/package
  relationship, **not a global name rule**.
- Seven separate `Procurement` groups (shape selector) are suspicious — group Procurement by
  meaningful package structure where it exists, not to inflate the count.
- Dropping Procurement entirely (judge selector) is also a failure — preserve a genuine world.
- `Works for Building` (245 activities / 41 steps, multiple branches) is an over-lump unless
  the activities genuinely form one coherent repeated construction front → reject it.
- Engineering / Procurement / Construction must stay distinguishable where the structure
  supports it.

## Process (locked)

1. Re-derive the selector from the priority order above (not from a case).
2. **Before implementing**, show Ibrahim the proposed grouping output on Saint-Gobain and
   Alstom **including the actual activities/fronts behind each group** — the structure
   itself, not just a scorecard. Do **not** ask him to approve a scoring formula in the
   abstract.
3. Iterate on the real structure until correct **and** the permanent fixtures still pass.
4. Only then: final selector implementation + full validation (fixtures + determinism +
   runtime + blind holdout on the two progressed updates).

## Narrative Report — visual & editability acceptance (added; build AFTER the selector)

The report is **not complete just because the narrative text is correct.** The planning
visuals must be professionally structured, auto-generated, and **meaningfully editable.**

1. **WBS** — a real visual hierarchy/tree (Project → Phase → Discipline/Trade →
   Building/Area → Work Package), like a professional org-chart; never a flat list/table.
2. **Sequence of work** — actual sequence/workflow charts (e.g. Piles → PC Foundation →
   Insulation → RC Footing → RC Walls → …), generated at the appropriate levels: per
   Building / per Trade / per Discipline / per major Work Front. Multiple meaningful
   sequences → multiple clear diagrams, not one generic text description.
3. **Editability is a core acceptance criterion** — edits are structural, not cosmetic. The
   user can rename a work package, change a sequence, add/remove/move a step, change a
   relationship between steps, change the grouping/front, or modify the WBS hierarchy, and
   the visual updates accordingly. **No flattened images** the user must recreate in
   PowerPoint/Word — the report carries editable, structured components.
4. **Smart visuals encouraged** — WBS tree, swimlane sequence, process-flow, discipline/
   building matrix, etc. The bar is that the visual communicates the planning logic clearly
   and stays meaningfully editable.
5. Must use the **Global Print-Preview framework** so the user chooses exactly which
   sections/tables/charts appear in Preview, PDF and Print.

## Instance-primary consolidation — locked prototype principles (2026-08-20)

**Correction (important):** `SDA`/`SDS` are **Shop Drawing Approval / Shop Drawing
Submittal**, not area codes. This must be read from the **Activity Codes**, which are a
first-class source of truth alongside WBS + activity names + relationships. Both baselines
encode the structure explicitly in codes: a **World** dim (SNG `Type of Work`, Alstom
`RME-WBS`: Construction/Engineering/Procurement/Design), an **Instance** dim (SNG/Alstom
`Building`), a **discipline** dim (`Trade`), a **document-control phase** dim (SNG
`Engineering` = `… S.D Submittal`/`… S.D Approval`; Alstom `RME-Engineering Category`,
`RME-Procurement Category` = `… Submittals`/`… Approvals`), and **work-type** dims
(BOQ/PKG/Civil-Works-Category). Evidence confirmed: one Building spans worlds; Submittal→
Approval activities are ≈1:1 cross-linked; construction breaks into work-type steps.

**The governing distinction (project-agnostic, structural — no name lists):**
> An **identity** dimension partitions into *parallel repeats* (buildings/conveyors do not
> hand off to each other). A **step** dimension partitions into a *sequential chain*
> (Submittal→Approval; Formwork→Rebar→Concrete). The Narrative **front boundary** is the
> identity dimensions (instance × discipline); the phase & work-type dimensions **collapse
> into the front's internal sequence.** Classify a dimension by whether its values hand off
> to each other in the schedule's own relationships, never by the words in them.

Consequences: Submittal + Approval become **one** document-control front (two internal
steps), not two duplicate fronts; a conveyor smeared across structural/steel/RC work-types
becomes **one** front with an internal work-type sequence, not five fragments.

**Eight principles Ibrahim locked for the prototype:**
1. The physical/logical **instance is the Narrative identity — not the WBS node**. WBS is
   evidence/context, not necessarily the definition of the front.
2. **Never lose P6 traceability.** If activities from multiple WBS lenses are consolidated
   into one front, retain the original WBS parent/path for *every* activity. Consolidation
   is a reporting abstraction; it must not rewrite or hide the source structure.
3. **Do not blindly merge similar names.** A merge requires meaningful evidence: same
   physical/logical instance; compatible scope; sequence/coupling evidence; common
   building/area/package identity; and/or cross-links such as Submittal→Approval.
4. **Submittal + Approval = one document-control front** when they represent the same
   package — but the report still **preserves the two underlying phases** inside the front.
5. **For construction, distinguish physical instance from work type** — one conveyor front
   with its internal work-type sequence, not five fragmented fronts.
6. **Do not force grouping.** Insufficient evidence for an instance identity → leave
   ungrouped rather than inventing a front.
7. **Project-agnostic.** No rules for Saint-Gobain / Alstom / SDA / SDS / CB3M / etc. They
   are validation cases, not hardcoded logic.
8. **Do not assume every EPC schedule is matrix-WBS.** Treat the matrix/multi-lens
   structure as a **detected** characteristic of a schedule, not a universal assumption.

**Required prototype output — per consolidated Narrative front, show all seven facets:**
> Narrative Front → Instance Identity → World/Scope → Original WBS Parents → Activities →
> Internal Work Sequence → Evidence used for consolidation

Show the actual activities/fronts behind each group (not a scorecard) on both baselines,
with no project-specific rules, before any further scoring formula.
