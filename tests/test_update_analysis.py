"""Unit tests for the Update-Analysis computations (p6_update.analysis).

Builds small P6 update XMLs with an embedded BaselineProject (like a real export), parses
and computes them the way the app does, then checks Time Status, Planned-vs-Actual by code,
and the Critical Path Analyzer roll-ups.
"""
import json
import os
import tempfile

from p6_evm.parser import parse_file
from p6_evm.metrics import compute
from p6_evm.classify import auto_categories, build_wbs_classifier
from p6_update.analysis import (
    time_status, by_code, activity_counts, critical_path, build_report_from_data,
)
from utils import resource_path


def _cfg():
    with open(resource_path('config.json')) as f:
        return json.load(f)


def _parse_and_compute(xml):
    with tempfile.NamedTemporaryFile('w', suffix='.xml', delete=False, encoding='utf-8') as f:
        f.write(xml)
        path = f.name
    try:
        data = parse_file(path)
        cfg = dict(_cfg())
        cfg['categories'] = auto_categories(data)
        metrics = compute(data, cfg, classifier=build_wbs_classifier(data))
        return data, metrics
    finally:
        os.unlink(path)


def _xml(data_date, acts, rels=None, wbs=None, milestones=None, start_milestones=None):
    """acts: (oid, code, name, pct0to1, start, finish, dur_hr, wbs_oid, codes_dict).
    baseline planned dates == the given start/finish. rels: (pred_oid, succ_oid).
    wbs: list of (oid, name, parent). milestones: (oid, code, name, finish, wbs_oid).
    start_milestones: (oid, code, name, date, wbs_oid) — a Start Milestone that releases work."""
    wbs = wbs or [(100, 'Proj', '')]
    body = baseline = ras = wbs_xml = codes_defs = ''
    # activity-code type + value catalogue
    used_types = {}
    for a in acts:
        for t, v in (a[8] or {}).items():
            used_types.setdefault(t, set()).add(v)
    type_oid = {}
    val_oid = {}
    oid_seq = 900
    for t, vals in used_types.items():
        oid_seq += 1
        type_oid[t] = oid_seq
        codes_defs += (f'<ActivityCodeType><ObjectId>{oid_seq}</ObjectId><Name>{t}</Name></ActivityCodeType>')
        for v in vals:
            oid_seq += 1
            val_oid[(t, v)] = oid_seq
            codes_defs += (f'<ActivityCode><ObjectId>{oid_seq}</ObjectId><CodeValue>{v}</CodeValue>'
                           f'<CodeTypeObjectId>{type_oid[t]}</CodeTypeObjectId></ActivityCode>')

    for w in wbs:
        wbs_xml += f'<WBS><ObjectId>{w[0]}</ObjectId><Name>{w[1]}</Name><ParentObjectId>{w[2]}</ParentObjectId></WBS>\n'

    for oid, code, name, pct, start, finish, dur, wbs_oid, codes in acts:
        assigns = ''.join(
            f'<Code><TypeObjectId>{type_oid[t]}</TypeObjectId><ValueObjectId>{val_oid[(t, v)]}</ValueObjectId></Code>'
            for t, v in (codes or {}).items())
        body += (f'<Activity><ObjectId>{oid}</ObjectId><Id>{code}</Id><Name>{name}</Name>'
                 f'<Type>Task Dependent</Type><WBSObjectId>{wbs_oid}</WBSObjectId><CalendarObjectId></CalendarObjectId>'
                 f'<PercentComplete>{pct}</PercentComplete>'
                 f'<PlannedDuration>{dur}</PlannedDuration><RemainingDuration>{dur}</RemainingDuration>'
                 f'<RemainingEarlyStartDate>{start}T00:00:00</RemainingEarlyStartDate>'
                 f'<RemainingEarlyFinishDate>{finish}T00:00:00</RemainingEarlyFinishDate>'
                 f'{assigns}</Activity>\n')
        baseline += (f'<Activity><ObjectId>{oid + 1000}</ObjectId><Id>{code}</Id>'
                     f'<PlannedStartDate>{start}T00:00:00</PlannedStartDate>'
                     f'<PlannedFinishDate>{finish}T00:00:00</PlannedFinishDate></Activity>\n')
        ras += (f'<ResourceAssignment><ActivityObjectId>{oid}</ActivityObjectId>'
                f'<PlannedCost>{dur * 100}</PlannedCost></ResourceAssignment>\n')

    for oid, code, name, finish, wbs_oid in (milestones or []):
        body += (f'<Activity><ObjectId>{oid}</ObjectId><Id>{code}</Id><Name>{name}</Name>'
                 f'<Type>Finish Milestone</Type><WBSObjectId>{wbs_oid}</WBSObjectId><CalendarObjectId></CalendarObjectId>'
                 f'<PercentComplete>0</PercentComplete><PlannedDuration>0</PlannedDuration><RemainingDuration>0</RemainingDuration>'
                 f'<RemainingEarlyStartDate>{finish}T00:00:00</RemainingEarlyStartDate>'
                 f'<RemainingEarlyFinishDate>{finish}T00:00:00</RemainingEarlyFinishDate></Activity>\n')
        baseline += (f'<Activity><ObjectId>{oid + 1000}</ObjectId><Id>{code}</Id>'
                     f'<PlannedFinishDate>{finish}T00:00:00</PlannedFinishDate></Activity>\n')

    for oid, code, name, date, wbs_oid in (start_milestones or []):
        body += (f'<Activity><ObjectId>{oid}</ObjectId><Id>{code}</Id><Name>{name}</Name>'
                 f'<Type>Start Milestone</Type><WBSObjectId>{wbs_oid}</WBSObjectId><CalendarObjectId></CalendarObjectId>'
                 f'<PercentComplete>0</PercentComplete><PlannedDuration>0</PlannedDuration><RemainingDuration>0</RemainingDuration>'
                 f'<RemainingEarlyStartDate>{date}T00:00:00</RemainingEarlyStartDate>'
                 f'<RemainingEarlyFinishDate>{date}T00:00:00</RemainingEarlyFinishDate></Activity>\n')
        baseline += (f'<Activity><ObjectId>{oid + 1000}</ObjectId><Id>{code}</Id>'
                     f'<PlannedStartDate>{date}T00:00:00</PlannedStartDate>'
                     f'<PlannedFinishDate>{date}T00:00:00</PlannedFinishDate></Activity>\n')

    rel_xml = ''.join(
        f'<Relationship><PredecessorActivityObjectId>{p}</PredecessorActivityObjectId>'
        f'<SuccessorActivityObjectId>{s}</SuccessorActivityObjectId><Type>Finish to Start</Type><Lag>0</Lag></Relationship>\n'
        for p, s in (rels or []))

    return ('<?xml version="1.0"?>\n<APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">\n'
            f'{codes_defs}'
            f'  <Project><ObjectId>1</ObjectId><Id>P1</Id><Name>Proj</Name><DataDate>{data_date}T00:00:00</DataDate>\n'
            f'{wbs_xml}{body}{rel_xml}{ras}  </Project>\n'
            f'  <BaselineProject>\n{baseline}  </BaselineProject>\n</APIBusinessObjects>\n')


# ── Section 1 ────────────────────────────────────────────────────────────────

def test_time_status_elapsed_and_earned():
    # Baseline: 01 Jan → 31 Dec (365 d). Data date 02 Jul ≈ half the year. Two equal-cost
    # activities, one 100% one 0% → 50% earned.
    xml = _xml('2025-07-02', [
        (10, 'A1', 'Act 1', 1.0, '2025-01-01', '2025-06-30', 80, 100, {}),
        (11, 'A2', 'Act 2', 0.0, '2025-07-01', '2025-12-31', 80, 100, {}),
    ])
    data, metrics = _parse_and_compute(xml)
    ts = time_status(data, metrics)
    assert 48 <= ts['elapsed_pct'] <= 52, ts['elapsed_pct']
    assert ts['actual_pct'] == 50.0, ts['actual_pct']
    assert ts['exceeded_days'] == 0
    assert ts['behind_clock'] is not None


def test_time_status_exceeds_baseline():
    # Data date well past the baseline finish → caps at 100% and reports days exceeded.
    xml = _xml('2026-03-01', [
        (10, 'A1', 'Act 1', 0.5, '2025-01-01', '2025-12-31', 80, 100, {}),
    ])
    data, metrics = _parse_and_compute(xml)
    ts = time_status(data, metrics)
    assert ts['elapsed_pct'] == 100.0
    assert ts['exceeded_days'] == (2026 - 2025) * 0 + 60  # 01 Jan→01 Mar 2026 = 60 days
    # 31 Dec 2025 → 01 Mar 2026 = 60 days
    assert ts['exceeded_days'] == 60


def test_time_status_explicit_span():
    # Baseline spans 01 Jan → 31 Dec 2025, data date 02 Jul. The no-span call clocks the whole
    # baseline (≈50% elapsed). Passing an explicit narrower span (01 Apr → 31 Dec) must re-measure
    # "time elapsed" over THAT window only — (02 Jul − 01 Apr)=92 d over (31 Dec − 01 Apr)=274 d ≈ 33.6%.
    from datetime import datetime
    xml = _xml('2025-07-02', [
        (10, 'A1', 'Act 1', 1.0, '2025-01-01', '2025-06-30', 80, 100, {}),
        (11, 'A2', 'Act 2', 0.0, '2025-07-01', '2025-12-31', 80, 100, {}),
    ])
    data, metrics = _parse_and_compute(xml)
    full = time_status(data, metrics)
    assert 48 <= full['elapsed_pct'] <= 52, full['elapsed_pct']   # whole-baseline clock ≈ 50%

    span = time_status(data, metrics,
                       span_start=datetime(2025, 4, 1), span_finish=datetime(2025, 12, 31))
    # hand-computed 92/274 → 33.6%; must differ from the whole-baseline reading
    assert abs(span['elapsed_pct'] - 33.6) < 0.2, span['elapsed_pct']
    assert span['elapsed_pct'] != full['elapsed_pct']
    # the span dates are echoed back, proving the given window (not the baseline extremes) was used
    assert span['baseline_start'] == '2025-04-01'
    assert span['baseline_finish'] == '2025-12-31'
    # earned side is cost/EV-based and unaffected by the clock window
    assert span['actual_pct'] == full['actual_pct'] == 50.0


# ── Section 2 ────────────────────────────────────────────────────────────────

def test_by_code_planned_vs_actual():
    xml = _xml('2025-07-02', [
        (10, 'M1', 'Mech 1', 0.30, '2025-01-01', '2025-12-31', 80, 100, {'Discipline': 'Mechanical'}),
        (11, 'M2', 'Mech 2', 0.30, '2025-01-01', '2025-12-31', 80, 100, {'Discipline': 'Mechanical'}),
        (12, 'C1', 'Civil 1', 0.80, '2025-01-01', '2025-12-31', 80, 100, {'Discipline': 'Civil'}),
    ])
    data, metrics = _parse_and_compute(xml)
    bc = by_code(data)
    assert 'Discipline' in bc
    rows = {r['value']: r for r in bc['Discipline']}
    assert set(rows) == {'Mechanical', 'Civil'}
    # Both disciplines planned ~50% by mid-year; Mechanical at 30% actual is behind, Civil ahead.
    assert rows['Mechanical']['actual'] == 30.0
    assert rows['Civil']['actual'] == 80.0
    assert rows['Mechanical']['variance'] < 0
    assert rows['Civil']['variance'] > 0
    # Worst gap first
    assert bc['Discipline'][0]['value'] == 'Mechanical'


def test_activity_counts_planned_vs_actual():
    # Data date 2025-07-02. A1 baseline done (Jan–Jun) and 100% actual → both completed.
    # A2 baseline mid-flight (Mar–Sep) and 40% actual → both in progress.
    # A3 baseline future (Aug–Dec) and 0% actual → both not started.
    xml = _xml('2025-07-02', [
        (10, 'A1', 'Done', 1.0, '2025-01-01', '2025-06-30', 80, 100, {'Discipline': 'Civil'}),
        (11, 'A2', 'Mid', 0.4, '2025-03-01', '2025-09-30', 80, 100, {'Discipline': 'Civil'}),
        (12, 'A3', 'Future', 0.0, '2025-08-01', '2025-12-31', 80, 100, {'Discipline': 'Mechanical'}),
    ])
    data, metrics = _parse_and_compute(xml)
    c = activity_counts(data)
    assert c['total'] == 3
    assert c['actual_completed'] == 1 and c['actual_in_progress'] == 1 and c['actual_not_started'] == 1
    assert c['planned_completed'] == 1 and c['planned_in_progress'] == 1 and c['planned_not_started'] == 1
    # actual buckets reconcile to the total
    assert c['actual_completed'] + c['actual_in_progress'] + c['actual_not_started'] == c['total']
    # filter by activity code narrows the set
    civ = activity_counts(data, code_filter={'type': 'Discipline', 'value': 'Civil'})
    assert civ['total'] == 2


# ── Section 3 ────────────────────────────────────────────────────────────────

def test_critical_path_rolls_up_to_wbs_boxes():
    # WBS: 100 Proj → 200 Silo 1 → 300 Pile Works, 301 Soil Replacement.
    # Chain: pile (100%) → soil (100%) → finish milestone. Both under Silo 1.
    wbs = [(100, 'Proj', ''), (200, 'Silo 1', 100), (300, 'Pile Works', 200), (301, 'Soil Replacement', 200)]
    acts = [
        (10, 'P1', 'Pile a', 1.0, '2025-01-01', '2025-03-01', 320, 300, {}),
        (11, 'P2', 'Pile b', 1.0, '2025-01-01', '2025-03-01', 320, 300, {}),
        (20, 'S1', 'Soil a', 0.5, '2025-03-02', '2025-06-01', 320, 301, {}),
    ]
    rels = [(10, 20), (11, 20), (20, 999)]
    ms = [(999, 'MS', 'Project completion', '2025-06-01', 200)]
    data, metrics = _parse_and_compute(_xml('2025-04-01', acts, rels, wbs, ms))
    cp = critical_path(data)
    assert cp['milestone'] is not None
    assert cp['milestone']['name'] == 'Project completion'
    assert cp['charts'], 'expected one driving-path chart'
    boxes = cp['charts'][0]['boxes']
    names = [b['name'] for b in boxes]
    # Pile Works (100% both) then Soil Replacement (50%) as the two work fronts.
    assert 'Pile Works' in names
    assert 'Soil Replacement' in names
    soil = next(b for b in boxes if b['name'] == 'Soil Replacement')
    assert soil['pct'] == 50.0
    assert soil['crumb'] == 'Silo 1'
    # New box fields: planned %, source, and the milestone big-box path start
    assert 'planned' in soil and 'source' in soil
    assert soil['source'] == 'wbs'           # these activities are cost-loaded → WBS rollup
    assert cp['milestone'].get('path_start')  # earliest baseline start on the path


def test_critical_path_no_cost_shows_the_activity():
    # The file IS cost-loaded (a Columns activity carries cost), but the Soil Replacement work
    # front on the path has NO cost → its box must show the specific driving activity by name,
    # not a budget-weighted WBS rollup.
    wbs = [(100, 'Proj', ''), (200, 'Silo 1', 100), (301, 'Soil Replacement', 200), (302, 'Columns', 200)]
    acts = [
        (20, 'S1', 'Soil layer 1 in Silo 1', 0.5, '2025-03-02', '2025-06-01', 320, 301, {}),
        (21, 'S2', 'Soil layer 2 in Silo 1', 0.0, '2025-03-02', '2025-06-01', 320, 301, {}),
        (30, 'C1', 'Columns in Silo 1', 0.0, '2025-03-02', '2025-06-01', 320, 302, {}),
    ]
    rels = [(20, 999)]
    ms = [(999, 'MS', 'Project completion', '2025-06-01', 200)]
    # Keep the Columns cost (C1 = oid 30) but strip the two Soil ResourceAssignments (20, 21).
    xml = _xml('2025-04-01', acts, rels, wbs, ms)
    import re
    for oid in (20, 21):
        xml = re.sub(rf'<ResourceAssignment><ActivityObjectId>{oid}</ActivityObjectId>.*?</ResourceAssignment>', '', xml, flags=re.S)
    data, metrics = _parse_and_compute(xml)
    boxes = critical_path(data)['charts'][0]['boxes']
    soil = next(b for b in boxes if 'Soil' in b['name'])
    assert soil['source'] == 'activity'          # file costed, work front not → the activity itself
    assert soil['name'] == 'Soil layer 1 in Silo 1'   # exact activity name, not the WBS name


def test_build_report_flags_missing_baseline():
    # A bare update with no BaselineProject → has_baseline False.
    xml = ('<?xml version="1.0"?>\n<APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">\n'
           '  <Project><ObjectId>1</ObjectId><Id>P1</Id><Name>Proj</Name><DataDate>2025-07-02T00:00:00</DataDate>\n'
           '    <WBS><ObjectId>100</ObjectId><Name>Proj</Name><ParentObjectId></ParentObjectId></WBS>\n'
           '    <Activity><ObjectId>10</ObjectId><Id>A1</Id><Name>A</Name><Type>Task Dependent</Type>'
           '<WBSObjectId>100</WBSObjectId><CalendarObjectId></CalendarObjectId><PercentComplete>0.5</PercentComplete>'
           '<PlannedDuration>80</PlannedDuration><RemainingDuration>40</RemainingDuration></Activity>\n'
           '  </Project>\n</APIBusinessObjects>\n')
    data, metrics = _parse_and_compute(xml)
    report = build_report_from_data(data, metrics)
    assert report['has_baseline'] is False
    assert 'time_status' in report and 'critical_path' in report


def test_build_report_time_status_uses_driving_path_span():
    # Driving path: Start Milestone (01 Mar) → Pile a (Mar–Jun) → Completion milestone (BL 01 Jun).
    # An off-path Mobilisation activity carries an EARLIER baseline start (01 Jan) so the whole-
    # baseline clock would read from Jan. build_report must instead clock the DRIVING-PATH span —
    # from the start milestone (01 Mar) to the milestone baseline finish (01 Jun) — not Jan→Jun.
    wbs = [(100, 'Proj', ''), (200, 'Silo 1', 100), (300, 'Pile Works', 200)]
    acts = [
        # off-path early works — earlier baseline start, must NOT anchor the clock
        (5, 'MOB', 'Mobilisation', 1.0, '2025-01-01', '2025-03-01', 320, 300, {}),
        # the single driving construction work front
        (10, 'P1', 'Pile a', 0.4, '2025-03-01', '2025-06-01', 320, 300, {}),
    ]
    rels = [(700, 10), (10, 999)]                       # Start MS → Pile a → Completion MS
    ms = [(999, 'MS', 'Project completion', '2025-06-01', 200)]
    sms = [(700, 'NTP', 'Notice to Proceed', '2025-03-01', 200)]
    data, metrics = _parse_and_compute(_xml('2025-04-01', acts, rels, wbs, ms, sms))
    report = build_report_from_data(data, metrics)

    # the driving-path chart carries the releasing start milestone
    chart = report['critical_path']['charts'][0]
    assert chart['start_milestone'] and chart['start_milestone']['date'] == '2025-03-01'

    ts = report['time_status']
    assert isinstance(ts.get('elapsed_pct'), (int, float))
    # span echoed back = start-milestone date → milestone baseline finish (NOT the Jan mobilisation)
    assert ts['baseline_start'] == '2025-03-01'
    assert ts['baseline_finish'] == '2025-06-01'
    # (01 Apr − 01 Mar)=31 d over (01 Jun − 01 Mar)=92 d → 33.7% — the driving-path clock,
    # far from the whole-baseline reading of ~59% that Jan→Jun would give
    assert abs(ts['elapsed_pct'] - 33.7) < 0.4, ts['elapsed_pct']
    assert ts['elapsed_pct'] < 45


# ── Exporters ────────────────────────────────────────────────────────────────

def test_render_html_and_excel_smoke():
    from p6_update.exporters import render_html, report_excel
    wbs = [(100, 'Proj', ''), (200, 'Silo 1', 100), (301, 'Soil Replacement', 200)]
    acts = [
        (20, 'S1', 'Soil a', 0.5, '2025-03-02', '2025-06-01', 320, 301, {'Discipline': 'Civil'}),
        (21, 'S2', 'Soil b', 0.3, '2025-03-02', '2025-06-01', 320, 301, {'Discipline': 'Civil'}),
    ]
    rels = [(20, 999)]
    ms = [(999, 'MS', 'Project completion', '2025-06-01', 200)]
    import re
    data, metrics = _parse_and_compute(_xml('2025-04-01', acts, rels, wbs, ms))
    report = build_report_from_data(data, metrics)
    report['file'] = 'test.xml'
    # cost-loaded fixture → Section 5 scope is populated with a default code
    assert isinstance(report.get('scope'), dict) and report['scope']
    assert isinstance(report.get('scope_default'), str) and report['scope_default']
    html = render_html(report)
    assert '<h1>Update Analysis</h1>' in html
    assert 'Time Status' in html and 'Planned vs Actual' in html and 'Driving Path Analyzer' in html
    assert 'by activity count' in html   # Section 4 present
    # dates render in the house '09-Feb.2027' format (two-digit day · 3-letter month · year)
    assert re.search(r'\d\d-[A-Z][a-z][a-z]\.\d{4}', html), html[:400]
    # section filter drops the others
    only = render_html(report, sections=['time'])
    assert 'Time Status' in only and 'Driving Path Analyzer' not in only
    headers, rows = report_excel(report)
    assert headers[0] == 'Section'
    assert any(r[0] == 'Time Status' for r in rows)
    assert any(r[0].startswith('Driving Path') for r in rows)
    assert any(r[0] == 'Activity count' for r in rows)


def test_scope_weights_and_recommendation():
    from p6_update.analysis import scope_weights
    # Civil is the heavy scope (dur 800 → BAC 80000) AND behind plan (20% actual by mid-year);
    # Mechanical is light (dur 80 → BAC 8000) and ahead (70% actual).
    xml = _xml('2025-07-02', [
        (10, 'M1', 'Mech 1', 0.7, '2025-01-01', '2025-12-31', 80, 100, {'Discipline': 'Mechanical'}),
        (11, 'C1', 'Civil 1', 0.2, '2025-01-01', '2025-12-31', 800, 100, {'Discipline': 'Civil'}),
    ])
    data, _ = _parse_and_compute(xml)
    s = scope_weights(data, 'Discipline')
    rows = s['rows']

    # (ii) heaviest first — rows sorted by weight descending
    assert [r['weight_pct'] for r in rows] == sorted((r['weight_pct'] for r in rows), reverse=True)
    assert rows[0]['value'] == 'Civil'
    assert rows[0]['weight_pct'] > 80

    # (i) every row carries budget-weighted planned + actual %
    civ = next(r for r in rows if r['value'] == 'Civil')
    mech = next(r for r in rows if r['value'] == 'Mechanical')
    for r in (civ, mech):
        assert 'planned' in r and 'actual' in r
        assert isinstance(r['planned'], (int, float)) and isinstance(r['actual'], (int, float))
    assert civ['actual'] == 20.0 and mech['actual'] == 70.0
    assert civ['planned'] > civ['actual']       # heavy scope is behind plan
    assert mech['planned'] < mech['actual']      # light scope is ahead

    # (iv) recommendation prioritises the largest-weight scope that is ALSO behind plan
    assert s['recommendation'][0].startswith('Prioritise')
    assert 'Civil' in s['recommendation'][0]

    # (iii) a LIST of two code dimensions buckets by the combination — value keys joined by ' · '
    xml2 = _xml('2025-07-02', [
        (10, 'M1', 'Mech 1', 0.7, '2025-01-01', '2025-12-31', 80, 100,
         {'Discipline': 'Mechanical', 'Area': 'Zone A'}),
        (11, 'C1', 'Civil 1', 0.2, '2025-01-01', '2025-12-31', 800, 100,
         {'Discipline': 'Civil', 'Area': 'Zone A'}),
    ])
    data2, _ = _parse_and_compute(xml2)
    combo = scope_weights(data2, ['Discipline', 'Area'])
    assert combo['code_type'] == 'Discipline · Area'
    assert combo['rows'], combo
    assert all(' · ' in r['value'] for r in combo['rows'])
    vals = {r['value'] for r in combo['rows']}
    assert 'Civil · Zone A' in vals and 'Mechanical · Zone A' in vals
