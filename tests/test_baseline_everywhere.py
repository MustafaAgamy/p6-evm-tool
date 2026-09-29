"""R4 — ONE baseline resolution for every feature (p6_evm/baseline.py + server._schedule_for):
the baseline inside the file, else the baseline attached for the update (XER or XML), else the
file's own Planned dates (flagged 'self').

End-to-end against a real server + temp DB:
  * XML exported WITHOUT its baseline + the baseline attached == the XML exported WITH it
    (the whole /api/parse result, not only PV);
  * the attachment is used by Update Analysis (and its counts / scope), the PV-EV gap and the
    project re-open — by snapshot id or by the file's path — and survives a re-import;
  * removing it, or attaching the wrong project's baseline, falls back honestly.
"""
import json
import urllib.request

import db

NS = 'http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects'

_UPDATE_XML = f'''<?xml version="1.0"?>
<APIBusinessObjects xmlns="{NS}">
  <ActivityCodeType><ObjectId>901</ObjectId><Name>Discipline</Name></ActivityCodeType>
  <ActivityCode><ObjectId>902</ObjectId><CodeValue>Civil</CodeValue><CodeTypeObjectId>901</CodeTypeObjectId></ActivityCode>
  <Project><ObjectId>1</ObjectId><Id>P1</Id><Name>Proj</Name><DataDate>2025-04-01T00:00:00</DataDate>
    <WBS><ObjectId>100</ObjectId><Name>Proj</Name><ParentObjectId></ParentObjectId></WBS>
    <WBS><ObjectId>200</ObjectId><Name>Silo 1</Name><ParentObjectId>100</ParentObjectId></WBS>
    <WBS><ObjectId>301</ObjectId><Name>Soil Replacement</Name><ParentObjectId>200</ParentObjectId></WBS>
    <Activity><ObjectId>20</ObjectId><Id>S1</Id><Name>Soil a</Name><Type>Task Dependent</Type>
      <WBSObjectId>301</WBSObjectId><CalendarObjectId></CalendarObjectId><PercentComplete>0.5</PercentComplete>
      <PlannedDuration>320</PlannedDuration><RemainingDuration>160</RemainingDuration>
      <PlannedStartDate>2025-03-20T00:00:00</PlannedStartDate><PlannedFinishDate>2025-07-01T00:00:00</PlannedFinishDate>
      <RemainingEarlyStartDate>2025-03-02T00:00:00</RemainingEarlyStartDate>
      <RemainingEarlyFinishDate>2025-06-01T00:00:00</RemainingEarlyFinishDate>
      <Code><TypeObjectId>901</TypeObjectId><ValueObjectId>902</ValueObjectId></Code></Activity>
    <Activity><ObjectId>21</ObjectId><Id>S2</Id><Name>Soil b</Name><Type>Task Dependent</Type>
      <WBSObjectId>301</WBSObjectId><CalendarObjectId></CalendarObjectId><PercentComplete>0.3</PercentComplete>
      <PlannedDuration>320</PlannedDuration><RemainingDuration>224</RemainingDuration>
      <PlannedStartDate>2025-03-20T00:00:00</PlannedStartDate><PlannedFinishDate>2025-07-01T00:00:00</PlannedFinishDate>
      <RemainingEarlyStartDate>2025-03-02T00:00:00</RemainingEarlyStartDate>
      <RemainingEarlyFinishDate>2025-06-01T00:00:00</RemainingEarlyFinishDate>
      <Code><TypeObjectId>901</TypeObjectId><ValueObjectId>902</ValueObjectId></Code></Activity>
    <Activity><ObjectId>999</ObjectId><Id>MS</Id><Name>Project completion</Name><Type>Finish Milestone</Type>
      <WBSObjectId>200</WBSObjectId><CalendarObjectId></CalendarObjectId><PercentComplete>0</PercentComplete>
      <PlannedDuration>0</PlannedDuration><RemainingDuration>0</RemainingDuration>
      <PlannedFinishDate>2025-07-01T00:00:00</PlannedFinishDate>
      <RemainingEarlyStartDate>2025-06-01T00:00:00</RemainingEarlyStartDate>
      <RemainingEarlyFinishDate>2025-06-01T00:00:00</RemainingEarlyFinishDate></Activity>
    <Relationship><PredecessorActivityObjectId>20</PredecessorActivityObjectId><SuccessorActivityObjectId>999</SuccessorActivityObjectId><Type>Finish to Start</Type><Lag>0</Lag></Relationship>
    <ResourceAssignment><ActivityObjectId>20</ActivityObjectId><PlannedCost>32000</PlannedCost></ResourceAssignment>
    <ResourceAssignment><ActivityObjectId>21</ActivityObjectId><PlannedCost>32000</PlannedCost></ResourceAssignment>
  </Project>
  <!--BASELINE-->
</APIBusinessObjects>
'''

# The baseline project (Rev.00): earlier dates than the update's own Planned dates, so a
# self-baseline and the true baseline give visibly different Planned % / PV.
_BASELINE_ACTS = '''
    <Activity><ObjectId>1020</ObjectId><Id>S1</Id><Name>Soil a</Name><Type>Task Dependent</Type><WBSObjectId>301</WBSObjectId><PlannedStartDate>2025-03-02T00:00:00</PlannedStartDate><PlannedFinishDate>2025-04-01T00:00:00</PlannedFinishDate></Activity>
    <Activity><ObjectId>1021</ObjectId><Id>S2</Id><Name>Soil b</Name><Type>Task Dependent</Type><WBSObjectId>301</WBSObjectId><PlannedStartDate>2025-03-02T00:00:00</PlannedStartDate><PlannedFinishDate>2025-04-01T00:00:00</PlannedFinishDate></Activity>
    <Activity><ObjectId>1999</ObjectId><Id>MS</Id><Name>Project completion</Name><Type>Finish Milestone</Type><WBSObjectId>200</WBSObjectId><PlannedFinishDate>2025-04-01T00:00:00</PlannedFinishDate></Activity>'''

WITH_BL = _UPDATE_XML.replace('<!--BASELINE-->', f'<BaselineProject>{_BASELINE_ACTS}\n  </BaselineProject>')
NO_BL = _UPDATE_XML.replace('<!--BASELINE-->', '')
# The same baseline exported on its own (a separate baseline XML the planner attaches).
BASELINE_ALONE = f'''<?xml version="1.0"?>
<APIBusinessObjects xmlns="{NS}">
  <Project><ObjectId>7</ObjectId><Id>P1-BL</Id><Name>Proj baseline</Name><DataDate>2025-03-01T00:00:00</DataDate>
    <WBS><ObjectId>100</ObjectId><Name>Proj</Name><ParentObjectId></ParentObjectId></WBS>
    <WBS><ObjectId>200</ObjectId><Name>Silo 1</Name><ParentObjectId>100</ParentObjectId></WBS>
    <WBS><ObjectId>301</ObjectId><Name>Soil Replacement</Name><ParentObjectId>200</ParentObjectId></WBS>{_BASELINE_ACTS}
  </Project>
</APIBusinessObjects>
'''
OTHER_PROJECT = BASELINE_ALONE.replace('<Id>S1</Id>', '<Id>X1</Id>').replace(
    '<Id>S2</Id>', '<Id>X2</Id>').replace('<Id>MS</Id>', '<Id>XM</Id>')

# Keys that SAY where the baseline came from — the only ones allowed to differ.
_BL_KEYS = {'baseline_source', 'baseline_name', 'baseline_path', 'baseline_matched',
            'baseline_total', 'baseline_missing'}


def _post(port, route, body):
    req = urllib.request.Request(
        f'http://127.0.0.1:{port}/{route}', data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _files(tmp_path):
    out = {}
    for name, txt in (('with_bl.xml', WITH_BL), ('no_bl.xml', NO_BL),
                      ('baseline.xml', BASELINE_ALONE), ('other.xml', OTHER_PROJECT)):
        p = tmp_path / name
        p.write_text(txt, encoding='utf-8')
        out[name.split('.')[0]] = str(p)
    return out


def _core(result):
    return {k: v for k, v in result.items() if k not in _BL_KEYS}


def test_xml_without_baseline_plus_attached_equals_xml_with_baseline(test_server, tmp_path):
    f = _files(tmp_path)
    a = _post(test_server, 'api/parse', {'path': f['with_bl']})
    b = _post(test_server, 'api/parse', {'path': f['no_bl']})
    assert a['ok'] and b['ok'], (a.get('error'), b.get('error'))
    assert a['result']['baseline_source'] == 'embedded'
    assert b['result']['baseline_source'] == 'self'          # said plainly, not PV 0
    assert b['result']['pv'] > 0
    assert round(b['result']['overall_planned_pct'], 6) != round(a['result']['overall_planned_pct'], 6)

    up = _post(test_server, 'api/baseline/upload', {
        'path': f['baseline'], 'xml_path': f['no_bl'], 'cached_path': b['cached_path'],
        'snapshot_id': b['snapshot_id']})
    assert up['ok'], up.get('error')
    assert up['matched'] == 3 and up['total'] == 3
    c = up['result']                                          # the snapshot, recomputed in place
    assert c['baseline_source'] == 'attached' and c['baseline_name'] == 'baseline.xml'
    # EVERYTHING the import produces is identical to the XML exported with its baseline.
    assert json.dumps(_core(c), sort_keys=True) == json.dumps(_core(a['result']), sort_keys=True)
    assert up['pv'] == a['result']['pv'] and up['spi'] == a['result']['spi']

    # The snapshot was recomputed IN PLACE (no extra import in the history) …
    assert db.get_attached_baseline(snapshot_id=b['snapshot_id'])
    pid = db.get_project_id_for_snapshot(b['snapshot_id'])
    # (both files are project P1: one snapshot per import, none added by the attach)
    assert sorted(r['id'] for r in db.get_project_snapshots(pid)) == sorted([a['snapshot_id'], b['snapshot_id']])
    # … and re-opening the project reads the stored, baselined numbers.
    load = _post(test_server, 'api/project/load', {'project_id': pid})
    assert load['ok'] and load['result']['baseline_source'] == 'attached'
    assert load['result']['pv'] == a['result']['pv']
    assert load['result']['overall_planned_pct'] == a['result']['overall_planned_pct']


def test_attached_baseline_is_used_by_update_analysis_and_gap(test_server, tmp_path):
    f = _files(tmp_path)
    a = _post(test_server, 'api/parse', {'path': f['with_bl']})
    b = _post(test_server, 'api/parse', {'path': f['no_bl']})
    before = _post(test_server, 'api/update/analyze', {'xml_path': f['no_bl'], 'cached_path': b['cached_path'],
                                                       'snapshot_id': b['snapshot_id']})
    assert before['ok'] is False and before['code'] == 'no_baseline'

    _post(test_server, 'api/baseline/upload', {'path': f['baseline'], 'xml_path': f['no_bl'],
                                               'cached_path': b['cached_path'], 'snapshot_id': b['snapshot_id']})
    want = _post(test_server, 'api/update/analyze', {'xml_path': f['with_bl'], 'cached_path': a['cached_path']})
    assert want['ok'], want
    # by snapshot id (the screen sends it) and by path alone (routes that don't) — same report
    for body in ({'xml_path': f['no_bl'], 'cached_path': b['cached_path'], 'snapshot_id': b['snapshot_id']},
                 {'xml_path': f['no_bl'], 'cached_path': b['cached_path']},
                 {'xml_path': f['no_bl']}):
        got = _post(test_server, 'api/update/analyze', body)
        assert got['ok'], got
        assert got['report']['baseline_source'] == 'attached'
        assert got['report']['time_status'] == want['report']['time_status']
        assert got['report']['by_code'] == want['report']['by_code']
        assert got['report']['counts'] == want['report']['counts']
    for route, extra in (('api/update/counts', {}), ('api/update/scope', {'types': ['Discipline']}),
                         ('api/gap', {'dimension': 'Discipline'})):
        g = _post(test_server, route, {'xml_path': f['no_bl'], 'cached_path': b['cached_path'], **extra})
        w = _post(test_server, route, {'xml_path': f['with_bl'], 'cached_path': a['cached_path'], **extra})
        assert g['ok'] and w['ok'], (route, g, w)
        g.pop('code_types', None), w.pop('code_types', None)
        assert g == w, route

    # Remove → back to the file's own dates, honestly flagged; Update Analysis refuses again.
    cl = _post(test_server, 'api/baseline/clear', {'xml_path': f['no_bl'], 'cached_path': b['cached_path'],
                                                   'snapshot_id': b['snapshot_id']})
    assert cl['ok'] and cl['result']['baseline_source'] == 'self'
    assert cl['pv'] == b['result']['pv']
    again = _post(test_server, 'api/update/analyze', {'xml_path': f['no_bl'], 'cached_path': b['cached_path']})
    assert again['ok'] is False and again['code'] == 'no_baseline'


def test_reimport_keeps_the_attached_baseline(test_server, tmp_path):
    f = _files(tmp_path)
    a = _post(test_server, 'api/parse', {'path': f['with_bl']})
    b = _post(test_server, 'api/parse', {'path': f['no_bl']})
    _post(test_server, 'api/baseline/upload', {'path': f['baseline'], 'xml_path': f['no_bl'],
                                               'cached_path': b['cached_path'], 'snapshot_id': b['snapshot_id']})
    r = _post(test_server, 'api/parse', {'path': f['no_bl']})    # same file imported again
    assert r['ok'] and r['snapshot_id'] != b['snapshot_id']
    assert r['result']['baseline_source'] == 'attached'
    assert r['result']['pv'] == a['result']['pv']


def test_wrong_project_baseline_is_not_attached(test_server, tmp_path):
    f = _files(tmp_path)
    b = _post(test_server, 'api/parse', {'path': f['no_bl']})
    up = _post(test_server, 'api/baseline/upload', {'path': f['other'], 'xml_path': f['no_bl'],
                                                    'cached_path': b['cached_path'], 'snapshot_id': b['snapshot_id']})
    assert up['ok'] and up['matched'] == 0 and 'result' not in up
    assert db.get_attached_baseline(snapshot_id=b['snapshot_id']) is None   # never remembered
    ua = _post(test_server, 'api/update/analyze', {'xml_path': f['no_bl'], 'cached_path': b['cached_path']})
    assert ua['code'] == 'no_baseline'


def test_xml_with_embedded_baseline_keeps_it(test_server, tmp_path):
    f = _files(tmp_path)
    a = _post(test_server, 'api/parse', {'path': f['with_bl']})
    up = _post(test_server, 'api/baseline/upload', {'path': f['other'], 'xml_path': f['with_bl'],
                                                    'cached_path': a['cached_path'], 'snapshot_id': a['snapshot_id']})
    assert up['ok'] is False and up['code'] == 'embedded'
    assert db.get_attached_baseline(snapshot_id=a['snapshot_id']) is None
