# AI Schedule Audit — Engine (Plan 1 of 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the offline, deterministic schedule-quality audit engine — read XER/XML into one model, build a relationship graph, run four rule-based checks (open ends, dangling, circular, float), and produce findings plus a transparent Schedule Health Score.

**Architecture:** Extend the existing `ScheduleData` model additively (relationships, float, activity type, constraints, WBS path); add an XER front-end that normalizes into it; add a new pure package `p6_audit/` that mirrors the isolation of `p6_evm/` — a `ScheduleGraph`, one module per check with an identical signature, a severity resolver, a deductive scorer, and a single `audit()` orchestrator. No I/O, no DB, no UI, no network in this plan.

**Tech Stack:** Python 3, standard library only (`xml.etree.ElementTree`, `dataclasses`), `pytest` for tests. Matches the existing `p6_evm/` style.

## Global Constraints

- Python standard library only — no new third-party runtime dependencies.
- `p6_evm/metrics.py` computation behavior MUST NOT change — the existing EVM test suite is the guardrail and must stay green.
- The `records` key convention is unchanged; the audit adds its own return keys, never touching EVM keys.
- Activity identity: primary key is **Activity ID** (`task_code` in XER, `Id` in XML). Every finding carries Activity ID + Activity Name + full WBS path. Never identify an activity by name alone.
- Durations/float from XER are in **hours** and MUST be converted to **working days** using the activity calendar's hours-per-day (default 8.0 when unknown). The float threshold default is **44 working days**.
- No fabricated confidence values — deterministic findings carry `confidence = None`.
- Relationship types are the four P6 types only: `FS`, `SS`, `FF`, `SF`.

---

## File structure

**Modified (additive only):**
- `p6_evm/parser.py` — extend `ScheduleData` (relationships list; new activity fields); add `parse_file` dispatch to XER; extend XML extraction (relationships, type, float, constraints).
- `p6_evm/calendars.py` — add `day_hours: float = 8.0` to `Calendar`.
- `config.json` — add an `audit` block (float threshold, severity penalties, category→severity, default severity).

**Created:**
- `p6_evm/xer.py` — low-level XER reader (`read_xer_tables`) + `parse_xer` builder → `ScheduleData`.
- `p6_audit/__init__.py` — exposes `audit`.
- `p6_audit/findings.py` — `Finding` dataclass + `resolve_severity` + severity ordering.
- `p6_audit/graph.py` — `ScheduleGraph`.
- `p6_audit/checks/__init__.py`
- `p6_audit/checks/open_ends.py`
- `p6_audit/checks/dangling.py`
- `p6_audit/checks/circular.py`
- `p6_audit/checks/float_snapshot.py`
- `p6_audit/scoring.py` — `score_categories`, `overall_score`.
- `p6_audit/engine.py` — `audit(data, config)` orchestrator.

**Tests created:**
- `tests/test_model_extension.py`, `tests/test_findings.py`, `tests/test_graph.py`,
  `tests/test_check_open_ends.py`, `tests/test_check_dangling.py`, `tests/test_check_circular.py`,
  `tests/test_check_float.py`, `tests/test_scoring.py`, `tests/test_engine.py`,
  `tests/test_xer.py`, `tests/test_xer_to_model.py`, `tests/test_xml_audit_fields.py`

---

## Task 1: Extend the schedule model + WBS path helper

**Files:**
- Modify: `p6_evm/parser.py` (the `ScheduleData` class, ~lines 22-30)
- Modify: `p6_evm/calendars.py` (the `Calendar` dataclass, ~lines 7-13)
- Create: `p6_audit/__init__.py` (empty for now)
- Test: `tests/test_model_extension.py`

**Interfaces:**
- Produces:
  - `ScheduleData.relationships: list[dict]` — each `{'pred_id': str, 'succ_id': str, 'type': str, 'lag_days': float}` where `pred_id`/`succ_id` are activity **object ids** (dict keys of `data.activities`).
  - New optional keys on each `data.activities[object_id]` dict: `'task_type'` (one of `'Task'`, `'StartMilestone'`, `'FinishMilestone'`, `'LOE'`, `'WBSSummary'`, `'ResourceDependent'`), `'total_float_days'` (float|None), `'free_float_days'` (float|None), `'is_critical'` (bool), `'constraint_type'` (str|None), `'constraint_date'` (datetime|None), `'activity_codes'` (dict). Existing keys unchanged.
  - `Calendar.day_hours: float` (default 8.0).
  - `full_wbs_path(wbs_id, wbs_map) -> str` in `p6_evm/parser.py` — returns e.g. `"Tower 33 > Foundation > Raft"` (root-first), or `""` if unknown.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_model_extension.py
from p6_evm.parser import ScheduleData, full_wbs_path
from p6_evm.calendars import Calendar


def test_scheduledata_has_relationships_list():
    data = ScheduleData()
    assert data.relationships == []


def test_calendar_has_default_day_hours():
    cal = Calendar(object_id='1', name='5-day')
    assert cal.day_hours == 8.0


def test_full_wbs_path_root_first():
    wbs_map = {
        'r': {'name': 'Tower 33', 'parent_object_id': None},
        'f': {'name': 'Foundation', 'parent_object_id': 'r'},
        'a': {'name': 'Raft', 'parent_object_id': 'f'},
    }
    assert full_wbs_path('a', wbs_map) == 'Tower 33 > Foundation > Raft'


def test_full_wbs_path_unknown_is_empty():
    assert full_wbs_path('nope', {}) == ''
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_model_extension.py -v`
Expected: FAIL — `ImportError: cannot import name 'full_wbs_path'` / `relationships` missing / `day_hours` missing.

- [ ] **Step 3: Add `day_hours` to `Calendar`**

In `p6_evm/calendars.py`, add the field to the dataclass (keep it last so positional construction elsewhere is unaffected):

```python
@dataclass
class Calendar:
    object_id: str
    name: str
    nonworking_days: set = field(default_factory=set)
    holidays: set = field(default_factory=set)
    added_work_days: set = field(default_factory=set)
    day_hours: float = 8.0
```

- [ ] **Step 4: Add `relationships` to `ScheduleData` and the `full_wbs_path` helper**

In `p6_evm/parser.py`, add to `ScheduleData.__init__`:

```python
        self.relationships = []    # list of {pred_id, succ_id, type, lag_days}
```

And add this module-level function (reuses the existing `wbs_ancestor_names` logic but root-first as a string; define locally to avoid a circular import with metrics):

```python
def full_wbs_path(wbs_id, wbs_map):
    """Root-first WBS path string, e.g. 'Tower 33 > Foundation > Raft'."""
    names = []
    seen = set()
    current = wbs_id
    while current and current not in seen:
        seen.add(current)
        node = wbs_map.get(current)
        if not node:
            break
        if node.get('name'):
            names.append(node['name'])
        current = node.get('parent_object_id')
    return ' > '.join(reversed(names))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_model_extension.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Run the existing suite to confirm no regression**

Run: `python -m pytest -q`
Expected: all existing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add p6_evm/parser.py p6_evm/calendars.py p6_audit/__init__.py tests/test_model_extension.py
git commit -m "feat(audit): extend ScheduleData with relationships, activity fields, WBS path helper"
```

---

## Task 2: Finding object + severity resolver + config block

**Files:**
- Create: `p6_audit/findings.py`
- Modify: `config.json` (add `audit` block)
- Test: `tests/test_findings.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `SEVERITY_ORDER = ['Low', 'Medium', 'High', 'Critical']`
  - `@dataclass Finding` with fields: `check_id, check_name, category, severity, activity_id, activity_name, wbs_path, related_activity_id=None, related_activity_name=None, summary='', basis='', recommendation='', confidence=None`. Method `as_dict(self) -> dict`.
  - `resolve_severity(check_base: str, category: str|None, is_critical: bool, config: dict) -> str` — returns the final severity level. Rule: take the higher (by `SEVERITY_ORDER`) of `check_base` and the category's configured base (`config['audit']['category_severity'].get(category, config['audit']['default_severity'])`); if `is_critical`, force `'Critical'`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_findings.py
from p6_audit.findings import Finding, resolve_severity, SEVERITY_ORDER

CONFIG = {'audit': {
    'default_severity': 'Medium',
    'category_severity': {'Construction': 'High', 'Design Phase I': 'Low'},
}}


def test_finding_as_dict_has_standard_keys():
    f = Finding(check_id='LOGIC-001', check_name='Open Ends', category='Construction',
                severity='High', activity_id='A230', activity_name='Roof Steel',
                wbs_path='T33 > Structure', summary='Missing successor', basis='succ=0')
    d = f.as_dict()
    assert d['activity_id'] == 'A230'
    assert d['confidence'] is None
    assert d['check_id'] == 'LOGIC-001'


def test_resolve_takes_higher_of_check_and_category():
    # check base Medium, category Construction (High) -> High
    assert resolve_severity('Medium', 'Construction', False, CONFIG) == 'High'
    # check base High, category Design Phase I (Low) -> High
    assert resolve_severity('High', 'Design Phase I', False, CONFIG) == 'High'


def test_resolve_unknown_category_uses_default():
    assert resolve_severity('Low', 'Procurement', False, CONFIG) == 'Medium'


def test_resolve_critical_path_forces_critical():
    assert resolve_severity('Low', 'Design Phase I', True, CONFIG) == 'Critical'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_findings.py -v`
Expected: FAIL — module `p6_audit.findings` not found.

- [ ] **Step 3: Implement `p6_audit/findings.py`**

```python
from dataclasses import dataclass, asdict

SEVERITY_ORDER = ['Low', 'Medium', 'High', 'Critical']


@dataclass
class Finding:
    check_id: str
    check_name: str
    category: str | None
    severity: str
    activity_id: str
    activity_name: str
    wbs_path: str
    related_activity_id: str | None = None
    related_activity_name: str | None = None
    summary: str = ''
    basis: str = ''
    recommendation: str = ''
    confidence: float | None = None

    def as_dict(self):
        return asdict(self)


def _rank(sev):
    return SEVERITY_ORDER.index(sev) if sev in SEVERITY_ORDER else 0


def resolve_severity(check_base, category, is_critical, config):
    audit_cfg = config.get('audit', {})
    default = audit_cfg.get('default_severity', 'Medium')
    cat_base = audit_cfg.get('category_severity', {}).get(category, default)
    base = check_base if _rank(check_base) >= _rank(cat_base) else cat_base
    if is_critical:
        return 'Critical'
    return base
```

- [ ] **Step 4: Add the `audit` block to `config.json`**

Add a sibling key to `categories`:

```json
    "audit": {
        "float_threshold_days": 44,
        "default_severity": "Medium",
        "category_severity": {
            "Construction": "High"
        },
        "severity_penalties": {
            "Critical": 25,
            "High": 12,
            "Medium": 5,
            "Low": 2
        },
        "category_weights": {
            "Schedule Logic": 0.5,
            "Float Analysis": 0.5
        }
    }
```

(Only Logic and Float exist in Phase 1, so their weights sum to 1.0 for the partial score. Later phases add their own keys.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_findings.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add p6_audit/findings.py config.json tests/test_findings.py
git commit -m "feat(audit): add Finding object, severity resolver, and audit config block"
```

---

## Task 3: ScheduleGraph

**Files:**
- Create: `p6_audit/graph.py`
- Test: `tests/test_graph.py`

**Interfaces:**
- Consumes: a `ScheduleData` (Task 1 shape). Reads `data.activities` (dict object_id -> activity dict) and `data.relationships` (list of `{pred_id, succ_id, type, lag_days}`).
- Produces `ScheduleGraph(data)` with:
  - `.activities` -> dict object_id -> activity dict (as given)
  - `.predecessors(oid) -> list[dict]` and `.successors(oid) -> list[dict]`, each edge dict `{'other': object_id, 'type': str, 'lag_days': float}`
  - `.preds_of(oid) -> list[edge]` where `oid` is the successor; `.succs_of(oid) -> list[edge]` where `oid` is the predecessor
  - `.wbs_path(oid) -> str` (from the activity dict, precomputed at parse time; fall back to `''`)
  - `.is_real_activity(oid) -> bool` — True only when `task_type == 'Task'` (excludes milestones, LOE, WBS summary, resource-dependent)
  - `.critical_ids() -> set[str]` — object ids where `activity['is_critical']` is True

- [ ] **Step 1: Write the failing test**

```python
# tests/test_graph.py
from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph


def _data():
    data = ScheduleData()
    data.activities = {
        'a': {'object_id': 'a', 'id': 'A1', 'name': 'Mob', 'task_type': 'Task',
              'is_critical': True, 'wbs_path': 'P > Enable'},
        'b': {'object_id': 'b', 'id': 'A2', 'name': 'Survey', 'task_type': 'Task',
              'is_critical': False, 'wbs_path': 'P > Enable'},
        'm': {'object_id': 'm', 'id': 'A0', 'name': 'Start', 'task_type': 'StartMilestone',
              'is_critical': True, 'wbs_path': 'P'},
    }
    data.relationships = [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0.0}]
    return data


def test_successors_and_predecessors():
    g = ScheduleGraph(_data())
    assert g.succs_of('a')[0]['other'] == 'b'
    assert g.succs_of('a')[0]['type'] == 'FS'
    assert g.preds_of('b')[0]['other'] == 'a'
    assert g.succs_of('b') == []


def test_is_real_activity_excludes_milestones():
    g = ScheduleGraph(_data())
    assert g.is_real_activity('a') is True
    assert g.is_real_activity('m') is False


def test_critical_ids():
    g = ScheduleGraph(_data())
    assert g.critical_ids() == {'a', 'm'}


def test_wbs_path_reads_from_activity():
    g = ScheduleGraph(_data())
    assert g.wbs_path('b') == 'P > Enable'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_graph.py -v`
Expected: FAIL — module `p6_audit.graph` not found.

- [ ] **Step 3: Implement `p6_audit/graph.py`**

```python
class ScheduleGraph:
    def __init__(self, data):
        self.activities = data.activities
        self._succ = {oid: [] for oid in self.activities}
        self._pred = {oid: [] for oid in self.activities}
        for rel in data.relationships:
            p, s = rel['pred_id'], rel['succ_id']
            if p not in self.activities or s not in self.activities:
                continue  # ignore dangling relationship records
            edge_type = rel.get('type', 'FS')
            lag = rel.get('lag_days', 0.0)
            self._succ[p].append({'other': s, 'type': edge_type, 'lag_days': lag})
            self._pred[s].append({'other': p, 'type': edge_type, 'lag_days': lag})

    def succs_of(self, oid):
        return self._succ.get(oid, [])

    def preds_of(self, oid):
        return self._pred.get(oid, [])

    def is_real_activity(self, oid):
        act = self.activities.get(oid)
        return bool(act) and act.get('task_type') == 'Task'

    def wbs_path(self, oid):
        act = self.activities.get(oid, {})
        return act.get('wbs_path', '') or ''

    def critical_ids(self):
        return {oid for oid, a in self.activities.items() if a.get('is_critical')}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_graph.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add p6_audit/graph.py tests/test_graph.py
git commit -m "feat(audit): add ScheduleGraph (typed adjacency, critical set, real-activity filter)"
```

---

## Task 4: Open Ends check (LOGIC-001)

**Files:**
- Create: `p6_audit/checks/__init__.py` (empty), `p6_audit/checks/open_ends.py`
- Test: `tests/test_check_open_ends.py`

**Interfaces:**
- Consumes: `ScheduleGraph` (Task 3), `config` (Task 2), `resolve_severity` + `Finding` (Task 2).
- Produces: `check_open_ends(graph, config) -> list[Finding]`. Emits a finding for each **real** activity (`is_real_activity`) with zero predecessors ("missing predecessor", check base `Medium`) or zero successors ("missing successor", check base `High`). Milestones/LOE/summary are skipped. `check_id='LOGIC-001'`, `check_name='Open Ends'`, `category` from `activity.get('category')`, severity via `resolve_severity(base, category, is_critical, config)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_check_open_ends.py
from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.checks.open_ends import check_open_ends

CONFIG = {'audit': {'default_severity': 'Medium', 'category_severity': {}}}


def _graph(acts, rels):
    d = ScheduleData(); d.activities = acts; d.relationships = rels
    return ScheduleGraph(d)


def _act(oid, **kw):
    base = {'object_id': oid, 'id': oid, 'name': oid, 'task_type': 'Task',
            'is_critical': False, 'wbs_path': '', 'category': None}
    base.update(kw); return base


def test_missing_successor_is_high():
    g = _graph({'a': _act('a'), 'b': _act('b')},
               [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0}])
    findings = check_open_ends(g, CONFIG)
    # 'a' has no predecessor (Medium), 'b' has no successor (High)
    by_act = {f.activity_id: f for f in findings}
    assert by_act['b'].severity == 'High'
    assert 'successor' in by_act['b'].summary.lower()
    assert by_act['a'].severity == 'Medium'
    assert 'predecessor' in by_act['a'].summary.lower()


def test_start_and_finish_milestones_ignored():
    g = _graph({'m': _act('m', task_type='StartMilestone'),
                'f': _act('f', task_type='FinishMilestone')}, [])
    assert check_open_ends(g, CONFIG) == []


def test_critical_open_end_escalates():
    g = _graph({'a': _act('a', is_critical=True), 'b': _act('b')},
               [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0}])
    a = {f.activity_id: f for f in check_open_ends(g, CONFIG)}['a']
    assert a.severity == 'Critical'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_check_open_ends.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `p6_audit/checks/open_ends.py`**

```python
from p6_audit.findings import Finding, resolve_severity


def check_open_ends(graph, config):
    findings = []
    for oid, act in graph.activities.items():
        if not graph.is_real_activity(oid):
            continue
        is_crit = bool(act.get('is_critical'))
        cat = act.get('category')
        if not graph.preds_of(oid):
            findings.append(Finding(
                check_id='LOGIC-001', check_name='Open Ends', category=cat,
                severity=resolve_severity('Medium', cat, is_crit, config),
                activity_id=act['id'], activity_name=act['name'],
                wbs_path=graph.wbs_path(oid),
                summary='Missing predecessor — start date is not logically driven',
                basis='predecessor_count = 0',
                recommendation='Connect this activity to its true preceding work with a Finish-to-Start relationship.',
            ))
        if not graph.succs_of(oid):
            findings.append(Finding(
                check_id='LOGIC-001', check_name='Open Ends', category=cat,
                severity=resolve_severity('High', cat, is_crit, config),
                activity_id=act['id'], activity_name=act['name'],
                wbs_path=graph.wbs_path(oid),
                summary='Missing successor — nothing depends on this activity finishing',
                basis='successor_count = 0',
                recommendation='Connect this activity to its true downstream work with a Finish-to-Start relationship.',
            ))
    return findings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_check_open_ends.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add p6_audit/checks/__init__.py p6_audit/checks/open_ends.py tests/test_check_open_ends.py
git commit -m "feat(audit): add Open Ends check (LOGIC-001)"
```

---

## Task 5: Dangling Logic check (LOGIC-002)

**Files:**
- Create: `p6_audit/checks/dangling.py`
- Test: `tests/test_check_dangling.py`

**Interfaces:**
- Consumes: `ScheduleGraph`, `config`, `Finding`/`resolve_severity`.
- Produces: `check_dangling(graph, config) -> list[Finding]`. For each **real** activity with at least one relationship on each side considered:
  - **Start not controlled**: the activity has predecessors, but none tie its *start* — i.e. no incoming edge of type `FS` or `SS` (where this activity is the successor). Only flag when the activity HAS at least one predecessor edge (a total open end is Task 4's job, not this one).
  - **Finish not controlled**: the activity has successors, but none tie its *finish* — i.e. no outgoing edge of type `FS` or `FF` (where this activity is the predecessor). Only flag when the activity HAS at least one successor edge.
  - Check base severity `High`. `check_id='LOGIC-002'`, `check_name='Dangling Logic'`. `basis` names which end dangles.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_check_dangling.py
from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.checks.dangling import check_dangling

CONFIG = {'audit': {'default_severity': 'Medium', 'category_severity': {}}}


def _g(acts, rels):
    d = ScheduleData(); d.activities = acts; d.relationships = rels
    return ScheduleGraph(d)


def _act(oid, **kw):
    b = {'object_id': oid, 'id': oid, 'name': oid, 'task_type': 'Task',
         'is_critical': False, 'wbs_path': '', 'category': None}; b.update(kw); return b


def test_ss_only_predecessor_flags_dangling_start():
    # b is driven only by SS from a on its start; a also FS-> nothing? give a a successor via SS to keep it out of scope for finish
    g = _g({'a': _act('a'), 'b': _act('b'), 'c': _act('c')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'SS', 'lag_days': 0},
            {'pred_id': 'b', 'succ_id': 'c', 'type': 'FS', 'lag_days': 0}])
    # b: has predecessor edges (SS only) -> start not controlled -> flag
    b = [f for f in check_dangling(g, CONFIG) if f.activity_id == 'b']
    assert len(b) == 1
    assert 'start' in b[0].basis.lower()
    assert b[0].check_id == 'LOGIC-002'


def test_fs_predecessor_start_is_controlled():
    g = _g({'a': _act('a'), 'b': _act('b'), 'c': _act('c')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0},
            {'pred_id': 'b', 'succ_id': 'c', 'type': 'FS', 'lag_days': 0}])
    b = [f for f in check_dangling(g, CONFIG) if f.activity_id == 'b']
    assert b == []


def test_ss_only_successor_flags_dangling_finish():
    # b's finish is not controlled: it only has an SS successor
    g = _g({'a': _act('a'), 'b': _act('b'), 'c': _act('c')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0},
            {'pred_id': 'b', 'succ_id': 'c', 'type': 'SS', 'lag_days': 0}])
    b = [f for f in check_dangling(g, CONFIG) if f.activity_id == 'b']
    assert len(b) == 1
    assert 'finish' in b[0].basis.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_check_dangling.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `p6_audit/checks/dangling.py`**

```python
from p6_audit.findings import Finding, resolve_severity


def check_dangling(graph, config):
    findings = []
    for oid, act in graph.activities.items():
        if not graph.is_real_activity(oid):
            continue
        preds = graph.preds_of(oid)
        succs = graph.succs_of(oid)
        is_crit = bool(act.get('is_critical'))
        cat = act.get('category')

        start_controlled = any(e['type'] in ('FS', 'SS') for e in preds)
        finish_controlled = any(e['type'] in ('FS', 'FF') for e in succs)

        if preds and not start_controlled:
            findings.append(Finding(
                check_id='LOGIC-002', check_name='Dangling Logic', category=cat,
                severity=resolve_severity('High', cat, is_crit, config),
                activity_id=act['id'], activity_name=act['name'],
                wbs_path=graph.wbs_path(oid),
                summary='Start not logically controlled — no Finish-to-Start or Start-to-Start driver',
                basis='activity start has no FS/SS predecessor tie',
                recommendation='Review whether a Finish-to-Start predecessor is needed so the start is driven by real logic.',
            ))
        if succs and not finish_controlled:
            findings.append(Finding(
                check_id='LOGIC-002', check_name='Dangling Logic', category=cat,
                severity=resolve_severity('High', cat, is_crit, config),
                activity_id=act['id'], activity_name=act['name'],
                wbs_path=graph.wbs_path(oid),
                summary='Finish not logically controlled — remaining work floats free after updates',
                basis='activity finish has no FS/FF successor tie',
                recommendation='Review whether a Finish-to-Start successor is needed so completion is controlled.',
            ))
    return findings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_check_dangling.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add p6_audit/checks/dangling.py tests/test_check_dangling.py
git commit -m "feat(audit): add Dangling Logic check (LOGIC-002)"
```

---

## Task 6: Circular Logic check (LOGIC-003)

**Files:**
- Create: `p6_audit/checks/circular.py`
- Test: `tests/test_check_circular.py`

**Interfaces:**
- Consumes: `ScheduleGraph`, `config`, `Finding`/`resolve_severity`.
- Produces: `check_circular(graph, config) -> list[Finding]`. Finds every cycle using strongly-connected components (iterative Tarjan) over the predecessor→successor edges. Each SCC of size > 1 (or a self-loop) yields ONE finding whose `related_activity_id`/loop chain is described in `basis`. Check base severity `Critical` (always Critical regardless of category). `check_id='LOGIC-003'`, `check_name='Circular Logic'`. The finding's `activity_id` is the loop's lowest activity id (stable ordering); `basis` lists the loop as `A → B → C → A` using activity **ids**.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_check_circular.py
from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.checks.circular import check_circular

CONFIG = {'audit': {'default_severity': 'Medium', 'category_severity': {}}}


def _g(rels, ids):
    d = ScheduleData()
    d.activities = {i: {'object_id': i, 'id': i, 'name': i, 'task_type': 'Task',
                        'is_critical': False, 'wbs_path': '', 'category': None} for i in ids}
    d.relationships = [{'pred_id': p, 'succ_id': s, 'type': 'FS', 'lag_days': 0} for p, s in rels]
    return ScheduleGraph(d)


def test_no_cycle_no_findings():
    g = _g([('a', 'b'), ('b', 'c')], ['a', 'b', 'c'])
    assert check_circular(g, CONFIG) == []


def test_three_node_loop_is_one_critical_finding():
    g = _g([('a', 'b'), ('b', 'c'), ('c', 'a')], ['a', 'b', 'c'])
    findings = check_circular(g, CONFIG)
    assert len(findings) == 1
    assert findings[0].severity == 'Critical'
    assert findings[0].check_id == 'LOGIC-003'
    # all three ids appear in the basis chain
    for i in ('a', 'b', 'c'):
        assert i in findings[0].basis


def test_two_independent_loops_two_findings():
    g = _g([('a', 'b'), ('b', 'a'), ('c', 'd'), ('d', 'c')], ['a', 'b', 'c', 'd'])
    assert len(check_circular(g, CONFIG)) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_check_circular.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `p6_audit/checks/circular.py`**

```python
from p6_audit.findings import Finding, resolve_severity


def _sccs(graph):
    """Iterative Tarjan over pred->succ edges. Returns list of SCC id-lists (size>1 or self-loop)."""
    index = {}
    low = {}
    on_stack = set()
    stack = []
    counter = [0]
    result = []
    nodes = list(graph.activities.keys())

    def succ_ids(oid):
        return [e['other'] for e in graph.succs_of(oid)]

    for root in nodes:
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            node, pi = work[-1]
            if pi == 0:
                index[node] = low[node] = counter[0]
                counter[0] += 1
                stack.append(node)
                on_stack.add(node)
            recursed = False
            neighbors = succ_ids(node)
            if pi < len(neighbors):
                work[-1] = (node, pi + 1)
                nxt = neighbors[pi]
                if nxt not in index:
                    work.append((nxt, 0))
                    recursed = True
                elif nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
            if recursed:
                continue
            if pi >= len(neighbors):
                if low[node] == index[node]:
                    comp = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        comp.append(w)
                        if w == node:
                            break
                    self_loop = node in succ_ids(node)
                    if len(comp) > 1 or self_loop:
                        result.append(comp)
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
    return result


def check_circular(graph, config):
    findings = []
    for comp in _sccs(graph):
        ids = sorted(graph.activities[o]['id'] for o in comp)
        anchor_oid = min(comp, key=lambda o: graph.activities[o]['id'])
        anchor = graph.activities[anchor_oid]
        chain = ' → '.join(ids + [ids[0]])
        findings.append(Finding(
            check_id='LOGIC-003', check_name='Circular Logic', category=anchor.get('category'),
            severity=resolve_severity('Critical', anchor.get('category'), True, config),
            activity_id=anchor['id'], activity_name=anchor['name'],
            wbs_path=graph.wbs_path(anchor_oid),
            summary=f'Logic loop of {len(comp)} activities — P6 cannot compute a valid schedule',
            basis=f'cycle: {chain}',
            recommendation='Break the loop by removing or re-typing one relationship in the chain.',
        ))
    return findings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_check_circular.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add p6_audit/checks/circular.py tests/test_check_circular.py
git commit -m "feat(audit): add Circular Logic check (LOGIC-003, iterative Tarjan)"
```

---

## Task 7: Float Snapshot check (FLOAT-001, single-schedule)

**Files:**
- Create: `p6_audit/checks/float_snapshot.py`
- Test: `tests/test_check_float.py`

**Interfaces:**
- Consumes: `ScheduleGraph`, `config`, `Finding`/`resolve_severity`. Reads `activity['total_float_days']` (float|None) and `activity['free_float_days']`.
- Produces: `check_float(graph, config) -> list[Finding]`. Threshold from `config['audit']['float_threshold_days']` (default 44). Emits:
  - Per **real** activity with `total_float_days < 0`: a **negative float** finding, check base `High`, `basis` gives the value.
  - ONE **excessive float** summary finding when any activities exceed the threshold: base `Medium`, `basis` = `"N of M activities (P%) with total float > T working days"`, `related`/summary names the worst WBS (highest count above threshold). Activities with `total_float_days is None` are ignored in counts.
  - `check_id='FLOAT-001'`, `check_name='Float Analysis'`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_check_float.py
from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.checks.float_snapshot import check_float

CONFIG = {'audit': {'default_severity': 'Medium', 'category_severity': {}, 'float_threshold_days': 44}}


def _g(acts):
    d = ScheduleData(); d.activities = acts; d.relationships = []
    return ScheduleGraph(d)


def _act(oid, tf, wbs='WBS-X', **kw):
    b = {'object_id': oid, 'id': oid, 'name': oid, 'task_type': 'Task',
         'is_critical': False, 'wbs_path': wbs, 'category': None,
         'total_float_days': tf, 'free_float_days': tf}
    b.update(kw); return b


def test_negative_float_flagged_high():
    g = _g({'a': _act('a', -3.0)})
    findings = check_float(g, CONFIG)
    neg = [f for f in findings if 'negative' in f.summary.lower()]
    assert len(neg) == 1
    assert neg[0].severity == 'High'


def test_excessive_float_single_summary_with_percentage():
    acts = {f'x{i}': _act(f'x{i}', 60.0) for i in range(3)}
    acts['ok'] = _act('ok', 10.0)
    g = _g(acts)
    summary = [f for f in check_float(g, CONFIG) if 'excessive' in f.summary.lower()]
    assert len(summary) == 1
    assert '3' in summary[0].basis and '4' in summary[0].basis  # 3 of 4


def test_none_float_ignored():
    g = _g({'a': _act('a', None)})
    assert check_float(g, CONFIG) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_check_float.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `p6_audit/checks/float_snapshot.py`**

```python
from collections import Counter
from p6_audit.findings import Finding, resolve_severity


def check_float(graph, config):
    threshold = config.get('audit', {}).get('float_threshold_days', 44)
    findings = []
    real = [(oid, a) for oid, a in graph.activities.items() if graph.is_real_activity(oid)]

    # Negative float — per activity
    for oid, act in real:
        tf = act.get('total_float_days')
        if tf is None:
            continue
        if tf < 0:
            cat = act.get('category')
            findings.append(Finding(
                check_id='FLOAT-001', check_name='Float Analysis', category=cat,
                severity=resolve_severity('High', cat, True, config),  # negative float => behind => critical-ish
                activity_id=act['id'], activity_name=act['name'], wbs_path=graph.wbs_path(oid),
                summary='Negative float — activity is behind the schedule need date',
                basis=f'total_float = {tf:g} working days',
                recommendation='Investigate the driving logic or delay; negative float means the finish milestone is threatened.',
            ))

    # Excessive float — one summary finding
    counted = [(oid, a) for oid, a in real if a.get('total_float_days') is not None]
    total = len(counted)
    over = [(oid, a) for oid, a in counted if a['total_float_days'] > threshold]
    if over and total:
        pct = 100.0 * len(over) / total
        wbs_counts = Counter(graph.wbs_path(oid) or '(no WBS)' for oid, _ in over)
        worst_wbs, worst_n = wbs_counts.most_common(1)[0]
        findings.append(Finding(
            check_id='FLOAT-001', check_name='Float Analysis', category=None,
            severity=resolve_severity('Medium', None, False, config),
            activity_id='—', activity_name='(project-wide)', wbs_path=worst_wbs,
            summary='Excessive float — a large share of activities exceed the float threshold',
            basis=f'{len(over)} of {total} activities ({pct:.1f}%) with total float > {threshold} working days',
            recommendation=f'Review logic in "{worst_wbs}" ({worst_n} activities over threshold) — high float usually means missing successors.',
        ))
    return findings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_check_float.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add p6_audit/checks/float_snapshot.py tests/test_check_float.py
git commit -m "feat(audit): add Float snapshot check (FLOAT-001)"
```

---

## Task 8: Scoring

**Files:**
- Create: `p6_audit/scoring.py`
- Test: `tests/test_scoring.py`

**Interfaces:**
- Consumes: a list of `Finding` (Task 2), `config` (`audit.severity_penalties`, `audit.category_weights`). A mapping of `check_id`→category name: `CATEGORY_OF_CHECK = {'LOGIC-001':'Schedule Logic','LOGIC-002':'Schedule Logic','LOGIC-003':'Schedule Logic','FLOAT-001':'Float Analysis'}`.
- Produces:
  - `score_categories(findings, config) -> dict[str, dict]` — for each category present in `category_weights`, `{'score': float 0-100, 'finding_count': int, 'weight': float}`. Score = `max(0, 100 - sum(penalty[sev] for findings in category))`.
  - `overall_score(category_scores) -> dict` — `{'score': float, 'categories_evaluated': int, 'categories_total': int, 'grade': str}` where overall = weighted average over categories that HAVE findings-or-are-present, renormalizing weights across the evaluated categories. Grade bands: ≥95 Excellent, ≥85 Very Good, ≥70 Good, ≥50 Fair, else Poor.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scoring.py
from p6_audit.findings import Finding
from p6_audit.scoring import score_categories, overall_score, CATEGORY_OF_CHECK

CONFIG = {'audit': {
    'severity_penalties': {'Critical': 25, 'High': 12, 'Medium': 5, 'Low': 2},
    'category_weights': {'Schedule Logic': 0.5, 'Float Analysis': 0.5},
}}


def _f(check_id, sev):
    return Finding(check_id=check_id, check_name='x', category=None, severity=sev,
                   activity_id='a', activity_name='a', wbs_path='')


def test_category_score_deducts_penalties():
    findings = [_f('LOGIC-001', 'High'), _f('LOGIC-002', 'Medium')]  # 12 + 5 = 17
    cats = score_categories(findings, CONFIG)
    assert cats['Schedule Logic']['score'] == 83
    assert cats['Float Analysis']['score'] == 100


def test_score_floors_at_zero():
    findings = [_f('LOGIC-003', 'Critical')] * 10  # 250 penalty
    cats = score_categories(findings, CONFIG)
    assert cats['Schedule Logic']['score'] == 0


def test_overall_is_weighted_and_reports_coverage():
    cats = score_categories([_f('LOGIC-001', 'High')], CONFIG)  # Logic 88, Float 100
    ov = overall_score(cats)
    assert ov['score'] == 94  # 0.5*88 + 0.5*100
    assert ov['categories_total'] == 2
    assert ov['grade'] == 'Very Good'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scoring.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `p6_audit/scoring.py`**

```python
CATEGORY_OF_CHECK = {
    'LOGIC-001': 'Schedule Logic',
    'LOGIC-002': 'Schedule Logic',
    'LOGIC-003': 'Schedule Logic',
    'FLOAT-001': 'Float Analysis',
}

_GRADES = [(95, 'Excellent'), (85, 'Very Good'), (70, 'Good'), (50, 'Fair'), (0, 'Poor')]


def _grade(score):
    for cutoff, label in _GRADES:
        if score >= cutoff:
            return label
    return 'Poor'


def score_categories(findings, config):
    audit_cfg = config.get('audit', {})
    penalties = audit_cfg.get('severity_penalties', {})
    weights = audit_cfg.get('category_weights', {})
    result = {}
    for cat, weight in weights.items():
        cat_findings = [f for f in findings if CATEGORY_OF_CHECK.get(f.check_id) == cat]
        penalty = sum(penalties.get(f.severity, 0) for f in cat_findings)
        result[cat] = {
            'score': max(0, 100 - penalty),
            'finding_count': len(cat_findings),
            'weight': weight,
        }
    return result


def overall_score(category_scores):
    total_weight = sum(c['weight'] for c in category_scores.values())
    if not total_weight:
        return {'score': 100, 'categories_evaluated': 0, 'categories_total': 0, 'grade': 'Excellent'}
    weighted = sum(c['score'] * c['weight'] for c in category_scores.values()) / total_weight
    score = round(weighted)
    return {
        'score': score,
        'categories_evaluated': len(category_scores),
        'categories_total': len(category_scores),
        'grade': _grade(score),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_scoring.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add p6_audit/scoring.py tests/test_scoring.py
git commit -m "feat(audit): add transparent deductive scoring with partial-coverage overall"
```

---

## Task 9: audit() orchestrator

**Files:**
- Create: `p6_audit/engine.py`
- Modify: `p6_audit/__init__.py` (export `audit`)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: everything above. Also needs each activity to carry `'category'` and `'wbs_path'`; the orchestrator fills these from `config['categories']` + `full_wbs_path` if not already present (so it works on any `ScheduleData` regardless of which parser produced it).
- Produces: `audit(data, config) -> dict`:
  ```
  {
    'findings': [finding.as_dict(), ...],          # all checks, severity-sorted (Critical first)
    'scores': {'categories': {...}, 'overall': {...}},
    'counts': {'total': int, 'by_severity': {...}},
  }
  ```

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine.py
from p6_evm.parser import ScheduleData
from p6_audit import audit

CONFIG = {
    'categories': [{'name': 'Construction', 'weight': 0.95, 'wbs_match': 'Construction'}],
    'audit': {
        'default_severity': 'Medium', 'category_severity': {'Construction': 'High'},
        'float_threshold_days': 44,
        'severity_penalties': {'Critical': 25, 'High': 12, 'Medium': 5, 'Low': 2},
        'category_weights': {'Schedule Logic': 0.5, 'Float Analysis': 0.5},
    },
}


def _data():
    d = ScheduleData()
    d.wbs = {'w': {'name': 'Construction', 'parent_object_id': None}}
    d.activities = {
        'a': {'object_id': 'a', 'id': 'A1', 'name': 'Mob', 'task_type': 'Task',
              'wbs_id': 'w', 'is_critical': False, 'total_float_days': 5.0, 'free_float_days': 5.0},
        'b': {'object_id': 'b', 'id': 'A2', 'name': 'Excavate', 'task_type': 'Task',
              'wbs_id': 'w', 'is_critical': False, 'total_float_days': 5.0, 'free_float_days': 5.0},
    }
    d.relationships = [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0}]
    return d


def test_audit_returns_findings_scores_counts():
    out = audit(_data(), CONFIG)
    assert 'findings' in out and 'scores' in out and 'counts' in out
    # a has no predecessor, b has no successor -> 2 open-end findings
    assert out['counts']['total'] >= 2
    assert out['scores']['overall']['categories_total'] == 2
    # findings are dicts carrying the standard keys
    assert out['findings'][0]['activity_id']
    assert out['findings'][0]['wbs_path'] == 'Construction'


def test_findings_sorted_critical_first():
    out = audit(_data(), CONFIG)
    order = ['Critical', 'High', 'Medium', 'Low']
    ranks = [order.index(f['severity']) for f in out['findings']]
    assert ranks == sorted(ranks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine.py -v`
Expected: FAIL — cannot import `audit`.

- [ ] **Step 3: Implement `p6_audit/engine.py` and export it**

```python
# p6_audit/engine.py
from p6_evm.parser import full_wbs_path
from p6_evm.metrics import classify_activity
from p6_audit.graph import ScheduleGraph
from p6_audit.findings import SEVERITY_ORDER
from p6_audit.checks.open_ends import check_open_ends
from p6_audit.checks.dangling import check_dangling
from p6_audit.checks.circular import check_circular
from p6_audit.checks.float_snapshot import check_float
from p6_audit.scoring import score_categories, overall_score

CHECKS = [check_open_ends, check_dangling, check_circular, check_float]


def _enrich(data, config):
    """Ensure each activity has 'category' and 'wbs_path' for the checks."""
    categories = config.get('categories', [])
    wbs_map = getattr(data, 'wbs', {}) or {}
    for act in data.activities.values():
        if 'wbs_path' not in act:
            act['wbs_path'] = full_wbs_path(act.get('wbs_id'), wbs_map)
        if 'category' not in act:
            act['category'] = classify_activity(act, wbs_map, categories)


def audit(data, config):
    _enrich(data, config)
    graph = ScheduleGraph(data)
    findings = []
    for check in CHECKS:
        findings.extend(check(graph, config))

    cats = score_categories(findings, config)
    overall = overall_score(cats)

    rank = {s: i for i, s in enumerate(reversed(SEVERITY_ORDER))}  # Critical -> 0
    findings.sort(key=lambda f: rank.get(f.severity, 99))

    by_sev = {}
    for f in findings:
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1

    return {
        'findings': [f.as_dict() for f in findings],
        'scores': {'categories': cats, 'overall': overall},
        'counts': {'total': len(findings), 'by_severity': by_sev},
    }
```

```python
# p6_audit/__init__.py
from p6_audit.engine import audit

__all__ = ['audit']
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_engine.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add p6_audit/engine.py p6_audit/__init__.py tests/test_engine.py
git commit -m "feat(audit): add audit() orchestrator (enrich, run checks, score, sort)"
```

---

## Task 10: XER low-level reader

**Files:**
- Create: `p6_evm/xer.py` (add `read_xer_tables` only in this task)
- Test: `tests/test_xer.py`

**Interfaces:**
- Consumes: a file path.
- Produces: `read_xer_tables(path) -> dict[str, list[dict]]` — table name → list of row dicts keyed by the `%F` field names. Handles the XER line types: `ERMHDR` (skip), `%T <table>`, `%F <field>...`, `%R <value>...`, `%E` (end). Tab-delimited. Tolerates trailing empty cells and unknown tables. Reads with `encoding='cp1252'` fallback to `utf-8` (XER is commonly Windows-1252).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_xer.py
from p6_evm.xer import read_xer_tables

SAMPLE = (
    "ERMHDR\t19.12\t2026-07-24\tProject\tadmin\n"
    "%T\tPROJECT\n"
    "%F\tproj_id\tproj_short_name\n"
    "%R\t123\tTOWER33\n"
    "%T\tTASK\n"
    "%F\ttask_id\ttask_code\ttask_name\ttotal_float_hr_cnt\n"
    "%R\t1001\tA230\tRoof Steel\t0\n"
    "%R\t1002\tA240\tRoof Cladding\t40\n"
    "%E\n"
)


def test_reads_tables_and_rows(tmp_path):
    p = tmp_path / "s.xer"
    p.write_text(SAMPLE, encoding='cp1252')
    tables = read_xer_tables(str(p))
    assert set(tables) == {'PROJECT', 'TASK'}
    assert tables['PROJECT'][0]['proj_short_name'] == 'TOWER33'
    assert tables['TASK'][1]['task_code'] == 'A240'
    assert tables['TASK'][0]['total_float_hr_cnt'] == '0'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_xer.py -v`
Expected: FAIL — module `p6_evm.xer` not found.

- [ ] **Step 3: Implement `read_xer_tables` in `p6_evm/xer.py`**

```python
def _read_text(path):
    for enc in ('cp1252', 'utf-8'):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, encoding='latin-1') as f:
        return f.read()


def read_xer_tables(path):
    """Parse an XER file into {table_name: [row_dict, ...]}."""
    tables = {}
    current = None
    fields = []
    for line in _read_text(path).splitlines():
        if not line:
            continue
        parts = line.split('\t')
        tag = parts[0]
        if tag == '%T':
            current = parts[1]
            fields = []
            tables[current] = []
        elif tag == '%F':
            fields = parts[1:]
        elif tag == '%R' and current is not None:
            values = parts[1:]
            row = {}
            for i, name in enumerate(fields):
                row[name] = values[i] if i < len(values) else ''
            tables[current].append(row)
        # ERMHDR, %E, and anything else are ignored
    return tables
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_xer.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add p6_evm/xer.py tests/test_xer.py
git commit -m "feat(audit): add low-level XER table reader"
```

---

## Task 11: XER → ScheduleData builder + parse_file dispatch

**Files:**
- Modify: `p6_evm/xer.py` (add `parse_xer`)
- Modify: `p6_evm/parser.py` (make `parse_file` dispatch by extension)
- Test: `tests/test_xer_to_model.py`

**Interfaces:**
- Consumes: `read_xer_tables` (Task 10), `ScheduleData`/`full_wbs_path` (Task 1), `Calendar` (Task 1).
- Produces:
  - `parse_xer(path) -> ScheduleData` — populates `project`, `wbs`, `calendars` (with `day_hours` from `day_hr_cnt`), `activities` (keyed by `task_id`; `id`=`task_code`, `task_type` mapped, `total_float_days`/`free_float_days` = hours ÷ calendar day_hours, `is_critical` = total_float_days ≤ 0, `constraint_type`/`constraint_date`, `wbs_path` precomputed), `relationships` (from `TASKPRED`, `pred_id`/`succ_id` = task_ids, `type` mapped, `lag_days` = lag_hr_cnt ÷ day_hours), and cost dicts from `TASKRSRC` (`target_cost`→bac, `act_reg_cost`+`act_ot_cost`→ac) keyed by task_id.
  - `parse_file(path)` now returns `parse_xer(path)` when the path ends in `.xer` (case-insensitive), else the existing XML parse.
- Mapping tables (module constants in `xer.py`):
  ```
  TASK_TYPE = {'TT_Task':'Task','TT_Mile':'StartMilestone','TT_FinMile':'FinishMilestone',
               'TT_LOE':'LOE','TT_WBS':'WBSSummary','TT_Rsrc':'ResourceDependent'}
  PRED_TYPE = {'PR_FS':'FS','PR_SS':'SS','PR_FF':'FF','PR_SF':'SF'}
  ```

- [ ] **Step 1: Write the failing test**

```python
# tests/test_xer_to_model.py
from p6_evm.xer import parse_xer
from p6_evm.parser import parse_file

SAMPLE = (
    "ERMHDR\t19.12\n"
    "%T\tPROJECT\n%F\tproj_id\tproj_short_name\tlast_recalc_date\n%R\t1\tTOWER33\t2026-07-24 00:00\n"
    "%T\tCALENDAR\n%F\tclndr_id\tclndr_name\tday_hr_cnt\n%R\t10\t5-Day\t8\n"
    "%T\tPROJWBS\n%F\twbs_id\twbs_name\tparent_wbs_id\tproj_node_flag\n"
    "%R\t100\tTower 33\t\tY\n%R\t101\tStructure\t100\tN\n"
    "%T\tTASK\n"
    "%F\ttask_id\tproj_id\twbs_id\tclndr_id\ttask_type\ttask_code\ttask_name\ttotal_float_hr_cnt\tfree_float_hr_cnt\tcstr_type\tcstr_date\n"
    "%R\t1001\t1\t101\t10\tTT_Task\tA230\tRoof Steel\t0\t0\t\t\n"
    "%R\t1002\t1\t101\t10\tTT_Task\tA240\tRoof Cladding\t320\t80\tCS_MSO\t2026-08-01 00:00\n"
    "%T\tTASKPRED\n%F\ttask_id\tpred_task_id\tpred_type\tlag_hr_cnt\n%R\t1002\t1001\tPR_FS\t0\n"
    "%E\n"
)


def test_parse_xer_builds_model(tmp_path):
    p = tmp_path / "s.xer"; p.write_text(SAMPLE, encoding='cp1252')
    data = parse_xer(str(p))
    assert data.project['name'] == 'TOWER33'
    a = data.activities['1002']
    assert a['id'] == 'A240'
    assert a['task_type'] == 'Task'
    assert a['total_float_days'] == 40.0      # 320 / 8
    assert a['free_float_days'] == 10.0
    assert a['is_critical'] is False
    assert a['constraint_type'] == 'CS_MSO'
    assert a['wbs_path'] == 'Tower 33 > Structure'
    crit = data.activities['1001']
    assert crit['is_critical'] is True         # 0 float
    rel = data.relationships[0]
    assert rel['pred_id'] == '1001' and rel['succ_id'] == '1002' and rel['type'] == 'FS'


def test_parse_file_dispatches_on_extension(tmp_path):
    p = tmp_path / "s.xer"; p.write_text(SAMPLE, encoding='cp1252')
    data = parse_file(str(p))
    assert '1001' in data.activities
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_xer_to_model.py -v`
Expected: FAIL — `parse_xer` not defined.

- [ ] **Step 3: Implement `parse_xer` in `p6_evm/xer.py`**

```python
from datetime import datetime
from p6_evm.parser import ScheduleData, full_wbs_path
from p6_evm.calendars import Calendar

TASK_TYPE = {'TT_Task': 'Task', 'TT_Mile': 'StartMilestone', 'TT_FinMile': 'FinishMilestone',
             'TT_LOE': 'LOE', 'TT_WBS': 'WBSSummary', 'TT_Rsrc': 'ResourceDependent'}
PRED_TYPE = {'PR_FS': 'FS', 'PR_SS': 'SS', 'PR_FF': 'FF', 'PR_SF': 'SF'}


def _num(s, default=None):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def _dt(s):
    if not s:
        return None
    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


def parse_xer(path):
    tables = read_xer_tables(path)
    data = ScheduleData()

    proj = (tables.get('PROJECT') or [{}])[0]
    data.project = {
        'object_id': proj.get('proj_id'),
        'id': proj.get('proj_short_name'),
        'name': proj.get('proj_short_name'),
        'data_date': _dt(proj.get('last_recalc_date')),
        'baseline_object_id': None,
    }

    for c in tables.get('CALENDAR', []):
        oid = c.get('clndr_id')
        data.calendars[oid] = Calendar(
            object_id=oid, name=c.get('clndr_name'),
            day_hours=_num(c.get('day_hr_cnt'), 8.0) or 8.0,
        )

    for w in tables.get('PROJWBS', []):
        data.wbs[w.get('wbs_id')] = {
            'name': w.get('wbs_name'),
            'parent_object_id': w.get('parent_wbs_id') or None,
        }

    for t in tables.get('TASK', []):
        oid = t.get('task_id')
        cal = data.calendars.get(t.get('clndr_id'))
        day_hours = cal.day_hours if cal else 8.0
        tf = _num(t.get('total_float_hr_cnt'))
        ff = _num(t.get('free_float_hr_cnt'))
        tf_days = (tf / day_hours) if tf is not None else None
        ff_days = (ff / day_hours) if ff is not None else None
        data.activities[oid] = {
            'object_id': oid,
            'id': t.get('task_code'),
            'name': t.get('task_name'),
            'status': t.get('status_code'),
            'calendar_id': t.get('clndr_id'),
            'wbs_id': t.get('wbs_id'),
            'task_type': TASK_TYPE.get(t.get('task_type'), 'Task'),
            'percent_complete': _num(t.get('phys_complete_pct'), 0.0) or 0.0,
            'planned_duration': _num(t.get('target_drtn_hr_cnt'), 0.0),
            'total_float_days': tf_days,
            'free_float_days': ff_days,
            'is_critical': (tf_days is not None and tf_days <= 0),
            'constraint_type': t.get('cstr_type') or None,
            'constraint_date': _dt(t.get('cstr_date')),
            'activity_codes': {},
            'wbs_path': full_wbs_path(t.get('wbs_id'), data.wbs),
            # EVM-facing date fields absent in this minimal XER mapping:
            'planned_start': None, 'planned_finish': None,
            'remaining_early_start': None, 'remaining_early_finish': None,
            'remaining_late_start': None, 'remaining_late_finish': None,
        }

    for r in tables.get('TASKPRED', []):
        succ = r.get('task_id')
        pred = r.get('pred_task_id')
        day_hours = 8.0
        cal = data.calendars.get((data.activities.get(succ) or {}).get('calendar_id'))
        if cal:
            day_hours = cal.day_hours
        lag_hr = _num(r.get('lag_hr_cnt'), 0.0) or 0.0
        data.relationships.append({
            'pred_id': pred, 'succ_id': succ,
            'type': PRED_TYPE.get(r.get('pred_type'), 'FS'),
            'lag_days': lag_hr / day_hours,
        })

    for ra in tables.get('TASKRSRC', []):
        tid = ra.get('task_id')
        if not tid:
            continue
        bac = _num(ra.get('target_cost'), 0.0) or 0.0
        ac = (_num(ra.get('act_reg_cost'), 0.0) or 0.0) + (_num(ra.get('act_ot_cost'), 0.0) or 0.0)
        data.bac_by_activity[tid] = data.bac_by_activity.get(tid, 0.0) + bac
        data.ac_by_activity[tid] = data.ac_by_activity.get(tid, 0.0) + ac

    return data
```

- [ ] **Step 4: Add the dispatch in `p6_evm/parser.py`**

At the top of the existing `parse_file(path)` function body (before `_detect_namespace`), add:

```python
def parse_file(path) -> ScheduleData:
    if path.lower().endswith('.xer'):
        from p6_evm.xer import parse_xer
        return parse_xer(path)
    # ---- existing XML parsing continues unchanged below ----
    ns_uri = _detect_namespace(path)
    ...
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_xer_to_model.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Run full suite + a real-file smoke check**

Run: `python -m pytest -q`
Then smoke-test the real sample from the vault:
```bash
python -c "from p6_evm.xer import parse_xer; d=parse_xer(r'D:\Vault\Projects\P6 EVM Tool\08 Sample Files\..\..\..\..\Vault\_attachments'); print(len(d.activities))" || echo "adjust path to the real .xer"
```
(Use the real sample: `D:\Vault\Projects\P6 EVM Tool` references `Grain Bulk Terminal ... REV.03.xer` — point the smoke test at that file; expect a non-zero activity count and non-empty `relationships`.)

- [ ] **Step 7: Commit**

```bash
git add p6_evm/xer.py p6_evm/parser.py tests/test_xer_to_model.py
git commit -m "feat(audit): map XER into ScheduleData and dispatch parse_file by extension"
```

---

## Task 12: Extend the XML parser with audit fields (best-effort)

**Files:**
- Modify: `p6_evm/parser.py` (the XML activity loop ~lines 112-129; add a Relationship loop; add activity type/float/constraint extraction)
- Test: `tests/test_xml_audit_fields.py`

**Interfaces:**
- Consumes: existing XML parse.
- Produces: after XML parse, each activity dict ALSO carries `task_type`, `total_float_days` (derived from late−early via `signed_working_days` when present, else the P6 `TotalFloat`/`TotalFloatHours` element ÷ calendar day_hours), `free_float_days`, `is_critical`, `constraint_type`, `constraint_date`, `activity_codes` (empty dict acceptable), and `wbs_path`. `data.relationships` is populated from `<Relationship>` elements (`PredecessorActivityObjectId`, `SuccessorActivityObjectId`, `Type`, `Lag`). Missing fields degrade to `None` — never raise.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_xml_audit_fields.py
import textwrap
from p6_evm.parser import parse_file


def _xml(tmp_path):
    content = textwrap.dedent('''\
    <?xml version="1.0"?>
    <APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">
      <Project>
        <ObjectId>1</ObjectId><Id>T33</Id><Name>Tower 33</Name>
        <DataDate>2026-07-24T00:00:00</DataDate>
        <WBS><ObjectId>10</ObjectId><Name>Structure</Name><ParentObjectId></ParentObjectId></WBS>
        <Activity>
          <ObjectId>1001</ObjectId><Id>A230</Id><Name>Roof Steel</Name>
          <Type>Task Dependent</Type><Status>Not Started</Status>
          <WBSObjectId>10</WBSObjectId><CalendarObjectId></CalendarObjectId>
          <PercentComplete>0</PercentComplete>
        </Activity>
        <Activity>
          <ObjectId>1002</ObjectId><Id>A240</Id><Name>Roof Cladding</Name>
          <Type>Task Dependent</Type><Status>Not Started</Status>
          <WBSObjectId>10</WBSObjectId><CalendarObjectId></CalendarObjectId>
          <PercentComplete>0</PercentComplete>
        </Activity>
        <Relationship>
          <PredecessorActivityObjectId>1001</PredecessorActivityObjectId>
          <SuccessorActivityObjectId>1002</SuccessorActivityObjectId>
          <Type>Finish to Start</Type><Lag>0</Lag>
        </Relationship>
      </Project>
    </APIBusinessObjects>
    ''')
    p = tmp_path / "s.xml"; p.write_text(content, encoding='utf-8')
    return str(p)


def test_xml_relationships_and_type(tmp_path):
    data = parse_file(_xml(tmp_path))
    assert data.relationships == [
        {'pred_id': '1001', 'succ_id': '1002', 'type': 'FS', 'lag_days': 0.0}
    ]
    assert data.activities['1001']['task_type'] == 'Task'
    assert data.activities['1002']['wbs_path'] == 'Structure'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_xml_audit_fields.py -v`
Expected: FAIL — `relationships` empty / `task_type` KeyError.

- [ ] **Step 3: Implement the additions in `p6_evm/parser.py`**

Add mapping constants near the top:

```python
XML_TASK_TYPE = {
    'Task Dependent': 'Task', 'Resource Dependent': 'ResourceDependent',
    'Level of Effort': 'LOE', 'Start Milestone': 'StartMilestone',
    'Finish Milestone': 'FinishMilestone', 'WBS Summary': 'WBSSummary',
}
XML_REL_TYPE = {
    'Finish to Start': 'FS', 'Start to Start': 'SS',
    'Finish to Finish': 'FF', 'Start to Finish': 'SF',
}
```

In the activity loop, after building each `data.activities[object_id]` dict, add the audit fields (append to the dict literal or set afterward):

```python
        act = data.activities[object_id]
        act['task_type'] = XML_TASK_TYPE.get(text(act_el, 'Type'), 'Task')
        cal = data.calendars.get(act['calendar_id'])
        day_hours = cal.day_hours if cal else 8.0
        tf_hours = parse_float(text(act_el, 'TotalFloatHours'), None) if text(act_el, 'TotalFloatHours') else None
        ff_hours = parse_float(text(act_el, 'FreeFloatHours'), None) if text(act_el, 'FreeFloatHours') else None
        # Prefer explicit float element; else derive from late-early dates
        if tf_hours is not None:
            act['total_float_days'] = tf_hours / day_hours
        else:
            from p6_evm.calendars import signed_working_days
            act['total_float_days'] = (
                signed_working_days(cal, act['remaining_early_start'], act['remaining_late_start'])
                if (cal and act['remaining_early_start'] and act['remaining_late_start']) else None
            )
        act['free_float_days'] = (ff_hours / day_hours) if ff_hours is not None else None
        act['is_critical'] = (act['total_float_days'] is not None and act['total_float_days'] <= 0)
        act['constraint_type'] = text(act_el, 'PrimaryConstraintType')
        act['constraint_date'] = parse_datetime(text(act_el, 'PrimaryConstraintDate'))
        act['activity_codes'] = {}
        act['wbs_path'] = full_wbs_path(act['wbs_id'], data.wbs)
```

After the activity loop (still inside `parse_file`, before `return data`), add the Relationship loop:

```python
    for rel_el in project_el.findall(tag('Relationship')):
        pred = text(rel_el, 'PredecessorActivityObjectId')
        succ = text(rel_el, 'SuccessorActivityObjectId')
        if not pred or not succ:
            continue
        cal = data.calendars.get(data.activities.get(succ, {}).get('calendar_id'))
        day_hours = cal.day_hours if cal else 8.0
        lag_hours = parse_float(text(rel_el, 'Lag'), 0.0)
        data.relationships.append({
            'pred_id': pred, 'succ_id': succ,
            'type': XML_REL_TYPE.get(text(rel_el, 'Type'), 'FS'),
            'lag_days': (lag_hours or 0.0) / day_hours,
        })
```

> Note: P6 XML `Lag` is sometimes in hours, sometimes in minutes depending on export settings. For Phase 1 the lag value is informational only (no check uses lag magnitude), so an approximate conversion is acceptable; do not block on it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_xml_audit_fields.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Run the FULL suite — EVM regression gate**

Run: `python -m pytest -q`
Expected: ALL tests pass, including the pre-existing EVM suite (proves the XML additions are additive and did not disturb `compute()`).

- [ ] **Step 6: Commit**

```bash
git add p6_evm/parser.py tests/test_xml_audit_fields.py
git commit -m "feat(audit): extract relationships, type, float, constraints from XML (best-effort)"
```

---

## Self-review

**Spec coverage (against the design doc §3-4 engine scope):**
- XER parsing → Tasks 10-11. ✓
- Normalized model + relationships/float/type/constraints/WBS path → Tasks 1, 11, 12. ✓
- ScheduleGraph → Task 3. ✓
- LOGIC-001/002/003 + FLOAT-001 → Tasks 4-7. ✓
- Severity (category reuse + critical escalation) → Task 2, applied in every check. ✓
- Transparent partial score → Task 8. ✓
- `audit()` entry point → Task 9. ✓
- Units hours→working days → Tasks 11, 12. ✓
- No fabricated confidence → `Finding.confidence=None` (Task 2), never set. ✓
- EVM unchanged → regression gate in Tasks 1, 11, 12. ✓
- **Deferred (correctly NOT in this plan):** persistence, API, UI, PDF/Excel (Plan 2); LOGIC-004, comparison, calendar what-if, AI layer (later phases).

**Type consistency:** `Finding` fields, `resolve_severity(check_base, category, is_critical, config)`, graph methods `preds_of/succs_of/is_real_activity/wbs_path/critical_ids`, `score_categories`/`overall_score`, `CATEGORY_OF_CHECK`, and `audit()` return shape are used identically across Tasks 2-12. Relationship dicts use `pred_id`/`succ_id`/`type`/`lag_days` everywhere. Activity `task_type` values are the same 6 strings in graph, XER map, and XML map.

**Placeholder scan:** none — every step has runnable code and an exact command.

---

## Not doing in this plan (Plan 2 covers it)

- DB tables (`audit_findings`, `audit_scores`, `activity_detail`, `relationship_detail`) and the import-transaction wiring.
- `/api/audit/{snapshot_id}`, `/api/export/excel`, and calling `audit()` inside `_handle_parse`.
- Dashboard rendering, the two buckets, filters.
- PDF audit pages and Excel export.
