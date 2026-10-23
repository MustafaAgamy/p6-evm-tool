"""Owner comment 17 — the Baseline Narrative said 'no critical path' on the Saint Gobain baseline.

Cause: that XER was exported with every activity's Total Float column (total_float_hr_cnt)
BLANK, so the reader had no float for any activity and the Appendix (Critical Path) reported
"The schedule carries no total-float values". The XER reader now rebuilds a blank float from
the activity's own early / late dates, exactly as P6 computes it (and as the XML reader does),
so the Narrative finds the critical path. Checked on the real file: 223 critical activities,
19-Dec.2024 → Project Completion 30-Aug.2025.

This locks the whole chain: blank float in the XER → float rebuilt → Narrative critical path.
"""
from p6_evm.parser import parse_file
from p6_narrative import critpath
from p6_narrative.report import build_report

HEAD = ("%F\ttask_id\tproj_id\twbs_id\tclndr_id\ttask_type\tstatus_code\ttask_code\ttask_name\t"
        "target_drtn_hr_cnt\tremain_drtn_hr_cnt\ttotal_float_hr_cnt\ttarget_start_date\ttarget_end_date\t"
        "restart_date\treend_date\trem_late_start_date\trem_late_end_date\n")


def _row(tid, code, name, wbs, es, ef, ls, lf, tf=''):
    return (f"%R\t{tid}\t1\t{wbs}\t10\tTT_Task\tTK_NotStart\t{code}\t{name}\t40\t40\t{tf}\t"
            f"{es}\t{ef}\t{es}\t{ef}\t{ls}\t{lf}\n")


def _xer(tmp_path, float_col=''):
    rows = (
        # the driving chain: late dates = early dates → zero float
        _row(1001, 'EX-1000', 'Excavation works', 110, '2025-03-03 08:00', '2025-03-07 17:00',
             '2025-03-03 08:00', '2025-03-07 17:00', float_col)
        + _row(1002, 'RC-1000', 'RC columns pouring', 110, '2025-03-10 08:00', '2025-03-14 17:00',
               '2025-03-10 08:00', '2025-03-14 17:00', float_col)
        + _row(1003, 'ST-1000', 'Steel structure erection', 120, '2025-03-17 08:00', '2025-03-21 17:00',
               '2025-03-17 08:00', '2025-03-21 17:00', float_col)
        # a side activity that can slip two weeks → positive float, not critical
        + _row(1004, 'FN-1000', 'Painting works', 120, '2025-03-03 08:00', '2025-03-07 17:00',
               '2025-03-17 08:00', '2025-03-21 17:00', float_col)
    )
    text = (
        "ERMHDR\t19.12\n"
        "%T\tPROJECT\n%F\tproj_id\tproj_short_name\tlast_recalc_date\n%R\t1\tSG\t2025-03-01 00:00\n"
        "%T\tCALENDAR\n%F\tclndr_id\tclndr_name\tday_hr_cnt\n%R\t10\t5-Day\t8\n"
        "%T\tPROJWBS\n%F\twbs_id\twbs_name\tparent_wbs_id\tproj_node_flag\n"
        "%R\t100\tSaint Gobain Baseline\t\tY\n%R\t110\tBatch House\t100\tN\n%R\t120\tMixer Building\t100\tN\n"
        "%T\tTASK\n" + HEAD + rows + "%E\n")
    p = tmp_path / 'blank_float.xer'
    p.write_text(text, encoding='cp1252')
    return str(p)


def test_blank_total_float_in_the_xer_is_rebuilt_from_the_dates(tmp_path):
    data = parse_file(_xer(tmp_path))
    tf = {a['id']: a.get('total_float_days') for a in data.activities.values()}
    assert all(v is not None for v in tf.values()), tf          # was: every one None → "no critical path"
    assert tf['EX-1000'] == 0 and tf['RC-1000'] == 0 and tf['ST-1000'] == 0
    assert tf['FN-1000'] > 0


def test_narrative_finds_the_critical_path_when_the_float_column_is_blank(tmp_path):
    path = _xer(tmp_path)
    data = parse_file(path)
    cp = critpath.critical_path(data)
    assert cp['available'] is True and cp['crit_basis'] == 'tf<=0'
    kpis = {label: value for value, label in cp['kpis']}
    assert kpis['Critical activities'] == '3'
    assert kpis['Critical path start'] == '03-Mar.2025' and kpis['Critical path finish'] == '21-Mar.2025'
    # … and the report section carries it (never the 'no total-float values' note)
    sec = next(s for s in build_report(data, path=path, setup=None).to_dict()['sections'] if s.get('kind') == 'critpath')
    assert sec['payload']['available'] is True
    assert 'no total-float' not in (sec['payload'].get('note') or '')


def test_a_float_p6_did_export_is_used_as_is(tmp_path):
    # 16 working hours on an 8 h calendar = 2 days for every activity, whatever the dates say
    data = parse_file(_xer(tmp_path, float_col='16'))
    assert {a.get('total_float_days') for a in data.activities.values()} == {2.0}
    cp = critpath.critical_path(data)                         # no activity at zero → the least-float band
    assert cp['available'] is True and cp['crit_basis'] == 'min-float'


def test_no_dates_and_no_float_still_says_so_honestly(tmp_path):
    text = (
        "ERMHDR\t19.12\n"
        "%T\tPROJECT\n%F\tproj_id\tproj_short_name\tlast_recalc_date\n%R\t1\tSG\t2025-03-01 00:00\n"
        "%T\tCALENDAR\n%F\tclndr_id\tclndr_name\tday_hr_cnt\n%R\t10\t5-Day\t8\n"
        "%T\tPROJWBS\n%F\twbs_id\twbs_name\tparent_wbs_id\tproj_node_flag\n%R\t100\tP\t\tY\n"
        "%T\tTASK\n"
        "%F\ttask_id\tproj_id\twbs_id\tclndr_id\ttask_type\ttask_code\ttask_name\ttarget_start_date\ttarget_end_date\n"
        "%R\t1001\t1\t100\t10\tTT_Task\tA1\tTask A\t2025-03-03 08:00\t2025-03-07 17:00\n%E\n")
    p = tmp_path / 'nofloat.xer'
    p.write_text(text, encoding='cp1252')
    cp = critpath.critical_path(parse_file(str(p)))
    assert cp['available'] is False and 'no total-float values' in cp['note']


def test_activity_ids_work_for_any_separator():
    """Comment 103: §12 Activity IDs was empty for dash-separated IDs (Saint Gobain, Alstom, MAFI).
    The separator and the serial position are read from the schedule itself."""
    from p6_narrative import actids
    dash = [{'id': 'EX-%d-GC-CON-BAT' % (1000 + 10 * i), 'name': 'Excavation works', 'activity_codes': {}} for i in range(6)]
    pl = actids.activity_id_analysis(dash, [])
    assert pl['blocks'] and pl['anatomy']
    roles = [c['role'] for c in pl['anatomy']['cols']]
    assert roles[0] == 'stage' and roles[1] == 'serial' and 'dash ("-")' in pl['intro']
    dot = [{'id': 'CONS.PL.S1.%d' % (1000 + 10 * i), 'name': 'Pile works', 'activity_codes': {}} for i in range(6)]
    pl = actids.activity_id_analysis(dot, [])
    assert pl['anatomy']['cols'][-1]['role'] == 'serial' and 'dot (".")' in pl['intro']


def test_activity_ids_any_coding_style():
    """Comment 103: must work for ANY project - every common P6 ID style yields a filled section
    with the serial read where it really sits."""
    from p6_narrative import actids
    mk = lambda ids: [{'id': i, 'name': 'Concrete works', 'activity_codes': {}} for i in ids]
    cases = {
        'p6 default': (['A%d' % (1000 + 10 * k) for k in range(20)], 1),
        'numbers only': ([str(1000 + 10 * k) for k in range(20)], 0),
        'underscore': (['CIV_%s_%d' % (z, 1000 + k) for z in ('FDN', 'COL') for k in range(6)], -1),
        'slash': (['B%d/CIV/%d' % (b, 1000 + k) for b in (1, 2) for k in range(6)], -1),
        'mixed': (['B%d-CIV.%d' % (b, 1000 + k) for b in (1, 2) for k in range(6)], -1),
        'serial first': (['%d-CIV-B%d' % (1000 + k, b) for b in (1, 2) for k in range(6)], 0),
        'spaces': (['B%d CIV %d' % (b, 1000 + k) for b in (1, 2) for k in range(6)], -1),
    }
    for name, (ids, serial_at) in cases.items():
        pl = actids.activity_id_analysis(mk(ids), [])
        assert pl['blocks'] and pl['anatomy'], name
        roles = [c['role'] for c in pl['anatomy']['cols']]
        assert roles[serial_at] == 'serial', (name, roles)
    pl = actids.activity_id_analysis(mk(['Start', 'Mobilisation', 'Handover']), [])
    assert pl['blocks'] and 'serial' not in [c['role'] for c in pl['anatomy']['cols']]


def test_equipment_same_content_any_loading():
    """Comment 103: §13.2 Equipment is the same content for any project - machines on site per
    month and 'Total plant loaded' - whether P6 loads the equipment as a count or in hours."""
    from p6_narrative import resload as R
    count = R._equipment_group({'window': 'w', 'span': [], 'values': [], 'peak_val': 0, 'peak_label': '',
                                'total': 3, 'rows': [('Excavator', 3, 2)]}, 'count')
    hours = R._equipment_group({'window': 'w', 'span': [], 'values': [], 'peak_val': 0, 'peak_label': '',
                                'total': 2, 'rows': [('Water Truck', 2, 2)]}, 'hours')
    for g in (count, hours):
        assert g['row_headers'] == ['Resource', 'Total plant loaded', 'Peak no. on site']
        assert g['total_unit'] == 'plant units'
    assert 'loaded in hours' in hours['basis_note'] and 'number of machines' in count['basis_note']


def test_no_unit_material_note_names_the_resources():
    from types import SimpleNamespace as NS
    from p6_narrative import resload as R
    data = NS(assignments_by_activity={1: [{'resource_id': 'R1', 'budget_units': 100}, {'resource_id': 'R1', 'budget_units': 50}]},
              resources={'R1': {'name': 'EX-resource'}})
    rows = R._no_unit_materials(data, {'R1': {'type': 'RT_Mat', 'unit': None}})
    assert rows == [('EX-resource', 2, 150.0)]


def test_word_code_box_survives_special_characters():
    """Alstom's Word export failed: a code name with '&' went unescaped into the text-box XML."""
    from p6_narrative.docx_writer import _xml_attr
    assert _xml_attr('Doors & Windows "A" <B>') == 'Doors &amp; Windows &quot;A&quot; &lt;B&gt;'


def test_activity_id_parts_read_from_the_activity_codes():
    """Comment 103: each part of the ID is explained by the activity code it stands for -
    the code whose values differ between the sibling parts (ARC/CON/SS = Trade), checked
    against the activities; a part that is the same on every activity is called a fixed code."""
    from p6_narrative import actids
    acts, k = [], 0
    for tr, trv, nm in (('CON', 'Civil Works', 'RC Footing'), ('SS', 'Steel Structure Works', 'Erect Steel'), ('ARC', 'Arc. Works', 'Plastering')):
        for b, bv in (('BAT', 'Batch Area'), ('MIX', 'Mixer Building')):
            for i in range(3):
                k += 1
                acts.append({'id': 'EX-%d-GC-%s-%s' % (1000 + 10 * k, tr, b), 'name': '%s %s' % (nm, bv),
                             'activity_codes': {'Type of Work': 'Construction', 'Trade': trv, 'Building': bv},
                             'wbs_path': 'Construction > %s > %s' % (bv, trv)})
    pl = actids.activity_id_analysis(acts, ['Type of Work', 'Trade', 'Building'])
    cols = {c['code']: c['meaning'] for c in pl['blocks'][0]['cols']}
    trade = next(v for c, v in cols.items() if 'CON' in c)
    assert 'CON = Civil Works' in trade and 'SS = Steel Structure Works' in trade and 'ARC = Arc. Works' in trade
    area = next(v for c, v in cols.items() if 'BAT' in c)
    assert 'BAT = Batch Area' in area and 'MIX = Mixer Building' in area
    assert 'fixed code' in cols['GC']
    assert pl['blocks'][0]['title'] == 'Construction'


def test_scope_says_what_each_code_consists_of():
    """Comment 103: §7 says what each picked code consists of (cost-loaded values only), then
    combines them - and the AI Assistant example shows the same."""
    from p6_narrative import scope
    acts = []
    for i, (tw, b, c) in enumerate([('Construction', 'Batch Area', 100), ('Construction', 'Mixer Building', 60),
                                    ('Procurement', 'Batch Area', 40), ('Design', 'Batch Area', 0)]):
        acts.append({'id': 'A%d' % i, 'object_id': i, 'task_type': 'TaskDependent', 'name': 'x',
                     'activity_codes': {'Type of Work': tw, 'Building': b}, 'wbs_id': None})
    bac = {0: 100, 1: 60, 2: 40, 3: 0}
    sc = scope.scope_sections(acts, {}, bac, ['Type of Work', 'Building'], {'scope_codes': ['Type of Work', 'Building']}, '')
    lists = {cl['code']: [v['name'] for v in cl['values']] for cl in sc['code_lists']}
    assert lists['Type of Work'] == ['Construction', 'Procurement']          # Design has no cost
    assert lists['Building'] == ['Batch Area', 'Mixer Building']
    assert 'Design' not in [d['name'] for d in sc['disciplines']]
