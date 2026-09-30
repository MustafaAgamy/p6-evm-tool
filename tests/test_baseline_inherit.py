"""R4 / review F1 — an earlier update with no baseline of its own is measured against the
CURRENT update's baseline, and that baseline is the same whether it sits inside the current XML
or was attached to it as a separate file (p6_evm.baseline.inherit_baseline).

So Update vs Update (/api/period/compare), the Critical Path Analyzer's previous role
(/api/critpath/analyze two_updates) and Reporting Studio (SpecialContext.parsed_input('previous'))
give ONE answer for:
    previous  +  current XML with its baseline inside
    previous  +  current exported without it + the baseline attached
Before the fix only an ATTACHED baseline was passed on, so the first pair measured the previous
update against its own Planned dates (SG 07-Aug -> 22-Aug-2025: previous SPI 1.26 vs 0.23).
"""
import json
import urllib.request

import db
from tests.test_baseline_everywhere import NS

# Current update (data date 01-Apr-2025): S1, S2 and the completion milestone.
_ACT = '''    <Activity><ObjectId>{oid}</ObjectId><Id>{code}</Id><Name>{name}</Name><Type>{typ}</Type>
      <WBSObjectId>{wbs}</WBSObjectId><CalendarObjectId></CalendarObjectId><PercentComplete>{pct}</PercentComplete>
      <PlannedDuration>{pd}</PlannedDuration><RemainingDuration>{rd}</RemainingDuration>
      <PlannedStartDate>{ps}</PlannedStartDate><PlannedFinishDate>{pf}</PlannedFinishDate>
      <RemainingEarlyStartDate>{ps}</RemainingEarlyStartDate><RemainingEarlyFinishDate>{pf}</RemainingEarlyFinishDate></Activity>
'''


def _acts(rows):
    return ''.join(_ACT.format(oid=o, code=c, name=n, typ=t, wbs=w, pct=p, pd=pd, rd=rd, ps=ps, pf=pf)
                   for o, c, n, t, w, p, pd, rd, ps, pf in rows)


def _project(oid, pid, name, data_date, rows, costs, extra=''):
    ras = ''.join(f'    <ResourceAssignment><ActivityObjectId>{a}</ActivityObjectId>'
                  f'<PlannedCost>{c}</PlannedCost></ResourceAssignment>\n' for a, c in costs)
    rels = ''.join(f'    <Relationship><PredecessorActivityObjectId>{a}</PredecessorActivityObjectId>'
                   f'<SuccessorActivityObjectId>{b}</SuccessorActivityObjectId><Type>Finish to Start</Type>'
                   f'<Lag>0</Lag></Relationship>\n' for a, b in zip([r[0] for r in rows], [r[0] for r in rows][1:]))
    ptr = '' if oid == '7' else '<CurrentBaselineProjectObjectId>7</CurrentBaselineProjectObjectId>'
    return f'''<Project><ObjectId>{oid}</ObjectId><Id>{pid}</Id><Name>{name}</Name><DataDate>{data_date}</DataDate>{ptr}
    <WBS><ObjectId>100</ObjectId><Name>Proj</Name><ParentObjectId></ParentObjectId></WBS>
    <WBS><ObjectId>200</ObjectId><Name>Silo 1</Name><ParentObjectId>100</ParentObjectId></WBS>
    <WBS><ObjectId>301</ObjectId><Name>Soil Replacement</Name><ParentObjectId>200</ParentObjectId></WBS>
{_acts(rows)}{rels}{ras}{extra}  </Project>'''


def _doc(body):
    return f'<?xml version="1.0"?>\n<APIBusinessObjects xmlns="{NS}">\n  {body}\n</APIBusinessObjects>\n'


T = 'Task Dependent'
CURR_ROWS = [('20', 'S1', 'Soil a', T, '301', 0.6, 320, 128, '2025-03-10T00:00:00', '2025-05-20T00:00:00'),
             ('21', 'S2', 'Soil b', T, '301', 0.2, 320, 256, '2025-03-10T00:00:00', '2025-06-20T00:00:00'),
             ('999', 'MS', 'Project completion', 'Finish Milestone', '200', 0, 0, 0,
              '2025-06-20T00:00:00', '2025-06-20T00:00:00')]
# Previous update (15-Mar-2025) still carries S3, deleted from the current update since.
PREV_ROWS = [('20', 'S1', 'Soil a', T, '301', 0.2, 320, 256, '2025-03-05T00:00:00', '2025-05-10T00:00:00'),
             ('21', 'S2', 'Soil b', T, '301', 0.0, 320, 320, '2025-03-05T00:00:00', '2025-06-10T00:00:00'),
             ('22', 'S3', 'Soil c', T, '301', 0.1, 160, 144, '2025-03-05T00:00:00', '2025-04-10T00:00:00'),
             ('999', 'MS', 'Project completion', 'Finish Milestone', '200', 0, 0, 0,
              '2025-06-10T00:00:00', '2025-06-10T00:00:00')]
# The baseline (Rev.00): earlier dates, its own budget, and S3.
BL_ROWS = [('1020', 'S1', 'Soil a', T, '301', 0, 320, 320, '2025-03-01T00:00:00', '2025-04-01T00:00:00'),
           ('1021', 'S2', 'Soil b', T, '301', 0, 320, 320, '2025-03-01T00:00:00', '2025-04-20T00:00:00'),
           ('1022', 'S3', 'Soil c', T, '301', 0, 160, 160, '2025-03-01T00:00:00', '2025-03-20T00:00:00'),
           ('1999', 'MS', 'Project completion', 'Finish Milestone', '200', 0, 0, 0,
            '2025-04-20T00:00:00', '2025-04-20T00:00:00')]
CURR_COST = [('20', 30000), ('21', 34000)]
PREV_COST = [('20', 30000), ('21', 34000), ('22', 9000)]
BL_COST = [('1020', 40000), ('1021', 36000), ('1022', 12000)]


def _bl_embedded():
    ras = ''.join(f'    <ResourceAssignment><ActivityObjectId>{a}</ActivityObjectId>'
                  f'<PlannedCost>{c}</PlannedCost></ResourceAssignment>\n' for a, c in BL_COST)
    return f'<BaselineProject><Name>Proj Rev.00</Name>\n{_acts(BL_ROWS)}{ras}  </BaselineProject>'


CURR_WITH_BL = _doc(_project('1', 'P1', 'Proj', '2025-04-01T00:00:00', CURR_ROWS, CURR_COST)
                    + '\n  ' + _bl_embedded())
CURR_NO_BL = _doc(_project('1', 'P1', 'Proj', '2025-04-01T00:00:00', CURR_ROWS, CURR_COST))
PREV = _doc(_project('1', 'P1', 'Proj', '2025-03-15T00:00:00', PREV_ROWS, PREV_COST))
BASELINE_ALONE = _doc(_project('7', 'P1-BL', 'Proj Rev.00', '2025-03-01T00:00:00', BL_ROWS, BL_COST))


def _files(tmp_path):
    out = {}
    for name, txt in (('curr_with_bl.xml', CURR_WITH_BL), ('curr_no_bl.xml', CURR_NO_BL),
                      ('prev.xml', PREV), ('baseline.xml', BASELINE_ALONE)):
        p = tmp_path / name
        p.write_text(txt, encoding='utf-8')
        out[name.rsplit('.', 1)[0]] = str(p)
    return out


def _post(port, route, body):
    req = urllib.request.Request(
        f'http://127.0.0.1:{port}/{route}', data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _dump(obj, drop=()):
    return json.dumps({k: v for k, v in obj.items() if k not in drop}, sort_keys=True, default=str)


# ── unit: the inherited baseline equals the attached one, field by field ──────────────────
def test_inherit_from_embedded_equals_inherit_from_attached(tmp_path):
    from p6_evm.parser import parse_file
    from p6_evm.baseline import load_schedule, inherit_baseline
    f = _files(tmp_path)
    cur_emb = load_schedule(f['curr_with_bl'])
    cur_att = load_schedule(f['curr_no_bl'], f['baseline'])
    assert cur_emb.baseline_source == 'embedded' and cur_att.baseline_source == 'attached'
    # the current update's baseline reads the same both ways (incl. S3, not in the current file)
    assert cur_emb.baseline_by_id == cur_att.baseline_by_id
    assert cur_emb.baseline_bac_by_code == cur_att.baseline_bac_by_code == {
        'S1': 40000.0, 'S2': 36000.0, 'S3': 12000.0}

    p1, p2 = load_schedule(f['prev']), load_schedule(f['prev'])
    assert p1.baseline_source == 'self'
    i1, i2 = inherit_baseline(p1, cur_emb), inherit_baseline(p2, cur_att)
    for p in (p1, p2):
        assert p.baseline_source == 'attached'
        assert p.baseline_by_id['S3']['planned_finish'].isoformat() == '2025-03-20T00:00:00'
        assert p.baseline_bac_by_activity == {'20': 40000.0, '21': 36000.0, '22': 12000.0}
    assert p1.baseline_by_id == p2.baseline_by_id
    assert i1['matched'] == i2['matched'] == 4 and i1['total'] == 4
    assert i1['from_current'] and i2['from_current']
    assert i2['name'] == 'baseline.xml' and 'inside the current update' in i1['name']

    # An update that has its own baseline keeps it; a self-only current passes nothing on.
    own = parse_file(f['curr_with_bl'])
    keep = dict(own.baseline_by_id)
    inherit_baseline(own, cur_att)
    assert own.baseline_source == 'embedded' and own.baseline_by_id == keep
    p3 = load_schedule(f['prev'])
    inherit_baseline(p3, load_schedule(f['curr_no_bl']))
    assert p3.baseline_source == 'self'


def _two_currents(port, f):
    """(snapshot of the XML with its baseline inside, snapshot of the XML without it + attached)."""
    a = _post(port, 'api/parse', {'path': f['curr_with_bl']})
    b = _post(port, 'api/parse', {'path': f['curr_no_bl']})
    assert a['ok'] and b['ok'], (a.get('error'), b.get('error'))
    up = _post(port, 'api/baseline/upload', {'path': f['baseline'], 'xml_path': f['curr_no_bl'],
                                             'cached_path': b['cached_path'], 'snapshot_id': b['snapshot_id']})
    assert up['ok'] and up['matched'] == 3, up
    assert a['result']['pv'] == up['result']['pv']          # the two currents are the same update
    return a, b


# ── end to end: Update vs Update ────────────────────────────────────────────────────────────
def test_period_compare_same_for_embedded_and_attached_current(test_server, tmp_path):
    f = _files(tmp_path)
    a, b = _two_currents(test_server, f)
    ra = _post(test_server, 'api/period/compare', {'prev_path': f['prev'], 'update_path': f['curr_with_bl'],
                                                   'cached_path': a['cached_path'], 'snapshot_id': a['snapshot_id']})
    rb = _post(test_server, 'api/period/compare', {'prev_path': f['prev'], 'update_path': f['curr_no_bl'],
                                                   'cached_path': b['cached_path'], 'snapshot_id': b['snapshot_id']})
    assert ra['ok'] and rb['ok'], (ra.get('error'), rb.get('error'))
    drop = ('prev_file', 'update_file')
    assert _dump(ra['report'], drop) == _dump(rb['report'], drop)

    # …and the previous update really was measured against the baseline, not its own dates:
    # without any baseline on the current, the previous update's numbers differ.
    c = _post(test_server, 'api/parse', {'path': str(tmp_path / 'curr_no_bl.xml')})
    db.save_baseline(c['snapshot_id'], None)
    rc = _post(test_server, 'api/period/compare', {'prev_path': f['prev'], 'update_path': f['curr_no_bl'],
                                                   'snapshot_id': c['snapshot_id']})
    assert rc['ok'], rc.get('error')
    assert _dump(rc['report'], drop) != _dump(ra['report'], drop)


# ── end to end: Critical Path Analyzer, previous role ──────────────────────────────────────
def test_critpath_previous_same_for_embedded_and_attached_current(test_server, tmp_path):
    f = _files(tmp_path)
    a, b = _two_currents(test_server, f)

    def run(path, snap):
        r = _post(test_server, 'api/critpath/analyze', {
            'mode': 'two_updates', 'current_path': path, 'cached_path': snap['cached_path'],
            'snapshot_id': snap['snapshot_id'], 'previous_path': f['prev']})
        assert r['ok'], r.get('error')
        return r
    ra, rb = run(f['curr_with_bl'], a), run(f['curr_no_bl'], b)
    assert _dump(ra['report'], ('files',)) == _dump(rb['report'], ('files',))


# ── Reporting Studio: parsed_input('previous') ─────────────────────────────────────────────
def test_reporting_studio_previous_same_for_embedded_and_attached_current(test_server, tmp_path):
    from p6_special.context import SpecialContext
    f = _files(tmp_path)

    def previous_of(snap):          # the context reads the project's LATEST snapshot = this one
        pid = db.get_project_id_for_snapshot(snap['snapshot_id'])
        ctx = SpecialContext(pid, snapshot_id=snap['snapshot_id'], inputs={'previous': f['prev']})
        assert ctx.parsed().baseline_source in ('embedded', 'attached')
        prev = ctx.parsed_input('previous')
        assert prev.baseline_source == 'attached' and prev.baseline_info['from_current']
        return prev.baseline_by_id, prev.baseline_bac_by_activity

    a = _post(test_server, 'api/parse', {'path': f['curr_with_bl']})
    from_embedded = previous_of(a)
    b = _post(test_server, 'api/parse', {'path': f['curr_no_bl']})
    up = _post(test_server, 'api/baseline/upload', {'path': f['baseline'], 'xml_path': f['curr_no_bl'],
                                                    'cached_path': b['cached_path'], 'snapshot_id': b['snapshot_id']})
    assert up['ok'] and up['matched'] == 3, up
    assert from_embedded == previous_of(b)
