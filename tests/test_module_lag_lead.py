import textwrap

from p6_evm.parser import ScheduleData, parse_file
from p6_audit.graph import ScheduleGraph
from p6_audit.engine import audit_modules
from p6_audit.modules.lag_lead import run_lag_lead

CONFIG = {'audit': {'near_critical_days': 10, 'long_lag_days': 14}}


def _g(acts, rels, cals=None):
    d = ScheduleData()
    d.activities = acts
    d.relationships = rels
    if cals:
        d.calendars = cals
    return ScheduleGraph(d)


def _act(oid, **kw):
    b = {'object_id': oid, 'id': oid, 'name': f'Act {oid}', 'task_type': 'Task',
         'is_critical': False, 'total_float_days': 50.0, 'wbs_path': 'Project > Area > Pkg',
         'category': None, 'calendar_id': None, 'percent_complete': 0.0,
         'actual_start': None, 'actual_finish': None}
    b.update(kw)
    return b


def _by_id(result):
    return {f['activity_id']: f for f in result['findings']}


# ── Detection ──────────────────────────────────────────────────────────────

def test_positive_lag_is_listed_anchored_on_successor():
    g = _g({'p': _act('p'), 's': _act('s')},
           [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 7}])
    r = run_lag_lead(g, CONFIG)
    f = _by_id(r)
    assert 's' in f                       # anchored on the successor (the waiting activity)
    row = f['s']
    assert row['pred_id'] == 'p'
    assert row['pred_rel'] == 'FS+7'
    assert row['lag_days'] == 7
    assert row['is_lead'] is False
    assert row['is_long'] is False
    assert row['rel_key'] == 'p|s|FS'
    assert row['justification'] == ''
    assert r['kpis']['lagged_count'] == 1
    assert r['kpis']['total_relationships'] == 1


def test_zero_lag_not_listed_but_counted():
    g = _g({'p': _act('p'), 's': _act('s')},
           [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 0}])
    r = run_lag_lead(g, CONFIG)
    assert r['findings'] == []
    assert r['kpis']['lagged_count'] == 0
    assert r['kpis']['total_relationships'] == 1
    assert r['kpis']['lagged_pct'] == 0.0


def test_sub_day_lag_rounds_to_zero_excluded():
    g = _g({'p': _act('p'), 's': _act('s')},
           [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 0.3}])
    assert run_lag_lead(g, CONFIG)['findings'] == []


def test_lead_is_flagged_and_signs_verdict():
    g = _g({'p': _act('p'), 's': _act('s')},
           [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': -3}])
    r = run_lag_lead(g, CONFIG)
    row = _by_id(r)['s']
    assert row['is_lead'] is True
    assert row['pred_rel'] == 'FS-3'
    assert row['lag_days'] == -3
    assert r['kpis']['leads_count'] == 1
    assert r['kpis']['verdict'] == 'Needs attention'


def test_long_lag_threshold_is_strict_over_14():
    g = _g({'p': _act('p'), 's14': _act('s14'), 's15': _act('s15')},
           [{'pred_id': 'p', 'succ_id': 's14', 'type': 'FS', 'lag_days': 14},
            {'pred_id': 'p', 'succ_id': 's15', 'type': 'FS', 'lag_days': 15}])
    f = _by_id(run_lag_lead(g, CONFIG))
    assert f['s14']['is_long'] is False       # 14 is not "over 14"
    assert f['s15']['is_long'] is True
    assert run_lag_lead(g, CONFIG)['kpis']['long_count'] == 1


def test_long_lead_also_flagged_long():
    g = _g({'p': _act('p'), 's': _act('s')},
           [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': -17}])
    row = _by_id(run_lag_lead(g, CONFIG))['s']
    assert row['is_lead'] is True and row['is_long'] is True


# ── Criticality ─────────────────────────────────────────────────────────────

def test_criticality_from_endpoints():
    g = _g({
        'p':  _act('p'),
        'sc': _act('sc', is_critical=True, total_float_days=-2.0),
        'sn': _act('sn', total_float_days=5.0),
        'sf': _act('sf', total_float_days=50.0),
    }, [
        {'pred_id': 'p', 'succ_id': 'sc', 'type': 'FS', 'lag_days': 5},
        {'pred_id': 'p', 'succ_id': 'sn', 'type': 'FS', 'lag_days': 5},
        {'pred_id': 'p', 'succ_id': 'sf', 'type': 'FS', 'lag_days': 5},
    ])
    r = run_lag_lead(g, CONFIG)
    f = _by_id(r)
    assert f['sc']['criticality'] == 'Critical'
    assert f['sn']['criticality'] == 'Near-Critical'
    assert f['sf']['criticality'] == ''
    assert r['kpis']['critical_count'] == 1
    assert r['kpis']['near_critical_count'] == 1


# ── KPIs, distribution, verdict ─────────────────────────────────────────────

def test_lagged_pct_and_pass_verdict():
    # 20 clean links + 1 lag = 1/21 ~ 4.8% (under 5%, no leads) → Pass
    acts = {'p': _act('p')}
    rels = []
    for i in range(20):
        acts[f's{i}'] = _act(f's{i}')
        rels.append({'pred_id': 'p', 'succ_id': f's{i}', 'type': 'FS', 'lag_days': 0})
    acts['L'] = _act('L')
    rels.append({'pred_id': 'p', 'succ_id': 'L', 'type': 'FS', 'lag_days': 6})
    r = run_lag_lead(_g(acts, rels), CONFIG)
    assert r['kpis']['total_relationships'] == 21
    assert r['kpis']['lagged_count'] == 1
    assert r['kpis']['lagged_pct'] == 4.8
    assert r['kpis']['verdict'] == 'Pass'


def test_over_5pct_needs_attention():
    # 10 links, 1 lagged = 10% > 5% → Needs attention (no leads)
    acts = {'p': _act('p')}
    rels = []
    for i in range(9):
        acts[f's{i}'] = _act(f's{i}')
        rels.append({'pred_id': 'p', 'succ_id': f's{i}', 'type': 'FS', 'lag_days': 0})
    acts['L'] = _act('L')
    rels.append({'pred_id': 'p', 'succ_id': 'L', 'type': 'FS', 'lag_days': 6})
    assert run_lag_lead(_g(acts, rels), CONFIG)['kpis']['verdict'] == 'Needs attention'


def test_by_type_distribution():
    g = _g({'p': _act('p'), 'a': _act('a'), 'b': _act('b'), 'c': _act('c')},
           [{'pred_id': 'p', 'succ_id': 'a', 'type': 'FS', 'lag_days': 3},
            {'pred_id': 'p', 'succ_id': 'b', 'type': 'SS', 'lag_days': 3},
            {'pred_id': 'p', 'succ_id': 'c', 'type': 'FS', 'lag_days': 3}])
    by_type = {t['type']: t for t in run_lag_lead(g, CONFIG)['kpis']['by_type']}
    assert by_type['FS']['count'] == 2
    assert by_type['SS']['count'] == 1


def test_wbs_summary_by_area():
    g = _g({
        'p1': _act('p1', wbs_path='Project > Marine Works > Quay'),
        's1': _act('s1', wbs_path='Project > Marine Works > Quay'),
        'p2': _act('p2', wbs_path='Project > Buildings > Admin'),
        's2': _act('s2', wbs_path='Project > Buildings > Admin'),
    }, [{'pred_id': 'p1', 'succ_id': 's1', 'type': 'FS', 'lag_days': 4},
        {'pred_id': 'p2', 'succ_id': 's2', 'type': 'FS', 'lag_days': 4}])
    dist = {r['wbs']: r for r in run_lag_lead(g, CONFIG)['wbs_summary']}
    assert dist['Marine Works']['lagged'] == 1
    assert dist['Buildings']['lagged'] == 1


def test_worst_first_ordering_lead_before_plain():
    g = _g({'p': _act('p'), 'plain': _act('plain'), 'lead': _act('lead')},
           [{'pred_id': 'p', 'succ_id': 'plain', 'type': 'FS', 'lag_days': 3},
            {'pred_id': 'p', 'succ_id': 'lead', 'type': 'FS', 'lag_days': -3}])
    order = [f['activity_id'] for f in run_lag_lead(g, CONFIG)['findings']]
    assert order.index('lead') < order.index('plain')


def test_context_successor_link_shown():
    # s waits FS+5 after p; s then drives t with FS+2 → the onward link is context
    g = _g({'p': _act('p'), 's': _act('s'), 't': _act('t')},
           [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 5},
            {'pred_id': 's', 'succ_id': 't', 'type': 'FS', 'lag_days': 2}])
    row = _by_id(run_lag_lead(g, CONFIG))['s']
    assert row['succ_id'] == 't'
    assert row['succ_rel'] == 'FS+2'


def test_empty_conclusion():
    g = _g({'p': _act('p'), 's': _act('s')},
           [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 0}])
    assert 'No lag' in run_lag_lead(g, CONFIG)['kpis']['executive_conclusion']


# ── Justifications (merged in by the server from project settings) ──────────

def test_apply_justifications_merges_by_rel_key():
    from p6_audit.modules.lag_lead import apply_justifications
    g = _g({'p': _act('p'), 's': _act('s')},
           [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 7}])
    mod = run_lag_lead(g, CONFIG)
    apply_justifications(mod, {'p|s|FS': 'Curing 7 wd per method statement'})
    assert _by_id(mod)['s']['justification'] == 'Curing 7 wd per method statement'


def test_apply_justifications_blank_key_and_none_safe():
    from p6_audit.modules.lag_lead import apply_justifications
    g = _g({'p': _act('p'), 's': _act('s')},
           [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 7}])
    mod = run_lag_lead(g, CONFIG)
    apply_justifications(mod, {'x|y|FS': 'irrelevant'})
    assert _by_id(mod)['s']['justification'] == ''
    apply_justifications(mod, None)          # no saved settings → no crash
    assert _by_id(mod)['s']['justification'] == ''
    assert apply_justifications(None, {}) is None


# ── Exporters (Excel + PDF) ─────────────────────────────────────────────────

def test_excel_columns_lag_lead():
    from p6_audit.exporters import excel_columns
    g = _g({'p': _act('p'), 's': _act('s')},
           [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 21}])
    mod = run_lag_lead(g, CONFIG)
    headers, rows = excel_columns(mod)
    assert headers[1] == 'Activity ID'
    assert 'Justification' in headers
    assert rows[0][1] == 's'          # activity id = the successor (the waiting activity)
    assert rows[0][7] == 21           # lag (wd)
    assert 'Long' in rows[0][8]       # flags


def test_render_module_report_lag_lead_smoke():
    from p6_audit.report import render_module_report
    g = _g({'p': _act('p'), 's': _act('s', is_critical=True, total_float_days=-1.0)},
           [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': -20}])
    mod = run_lag_lead(g, CONFIG)
    html = render_module_report(mod, {'project_name': 'Demo'})
    assert 'Lag &amp; Lead Register' in html
    assert 'Needs attention' in html
    assert 'DCMA' in html


# ── End-to-end via the parser + audit_modules ───────────────────────────────

def test_end_to_end_xml_lag_detected(tmp_path):
    xml = textwrap.dedent('''\
    <?xml version="1.0"?>
    <APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">
      <Project>
        <ObjectId>1</ObjectId><Id>PJ</Id><Name>P</Name>
        <DataDate>2026-02-01T00:00:00</DataDate>
        <WBS><ObjectId>10</ObjectId><Name>Construction Works</Name><ParentObjectId></ParentObjectId></WBS>
        <Activity>
          <ObjectId>1001</ObjectId><Id>A100</Id><Name>Cure slab</Name>
          <Type>Task Dependent</Type><Status>Not Started</Status>
          <WBSObjectId>10</WBSObjectId><CalendarObjectId></CalendarObjectId>
        </Activity>
        <Activity>
          <ObjectId>1002</ObjectId><Id>A200</Id><Name>Strike formwork</Name>
          <Type>Task Dependent</Type><Status>Not Started</Status>
          <WBSObjectId>10</WBSObjectId><CalendarObjectId></CalendarObjectId>
        </Activity>
        <Relationship>
          <PredecessorActivityObjectId>1001</PredecessorActivityObjectId>
          <SuccessorActivityObjectId>1002</SuccessorActivityObjectId>
          <Type>Finish to Start</Type><Lag>56</Lag>
        </Relationship>
      </Project>
    </APIBusinessObjects>
    ''')
    p = tmp_path / 's.xml'
    p.write_text(xml, encoding='utf-8')
    data = parse_file(str(p))
    out = audit_modules(data, {'categories': [], 'audit': {'near_critical_days': 10, 'long_lag_days': 14}})
    assert 'lag_lead' in out['modules']
    lag = out['modules']['lag_lead']
    assert lag['kpis']['lagged_count'] == 1
    f = {x['activity_id']: x for x in lag['findings']}
    assert 'A200' in f
    assert f['A200']['pred_id'] == 'A100'
    assert f['A200']['lag_days'] == 7           # 56 hours / 8 = 7 working days
