"""Owner comment 36 (no wait after Run) — RUNUX-02: the Reporting Studio catalog must not do the
same heavy work twice. Two duplicates made it cost seconds on every open:

* ``p6_update.analysis.scope_all`` recomputed the construction filter (a WBS-ancestry walk over
  every activity) once PER activity-code dimension — 27x on Grain Bulk;
* ``p6_narrative.resload.read_resource_meta`` re-parsed the whole schedule file for §13 and
  again for §15.

Both are pure functions of the schedule, so doing them once must give identical results.
"""
import os

import pytest

from tests.test_update_analysis import _xml, _parse_and_compute


def _two_dim_schedule():
    return _parse_and_compute(_xml('2025-07-02', [
        (10, 'M1', 'Mech 1', 0.7, '2025-01-01', '2025-12-31', 80, 100,
         {'Discipline': 'Mechanical', 'Area': 'Zone A'}),
        (11, 'C1', 'Civil 1', 0.2, '2025-01-01', '2025-12-31', 800, 100,
         {'Discipline': 'Civil', 'Area': 'Zone B'}),
        (12, 'C2', 'Civil 2', 0.5, '2025-02-01', '2025-11-30', 400, 100,
         {'Discipline': 'Civil', 'Area': 'Zone A'}),
    ]))[0]


def test_scope_all_works_out_the_construction_filter_once(monkeypatch):
    import p6_compare.report as cr
    from p6_update.analysis import scope_all, scope_weights
    data = _two_dim_schedule()
    assert len(data.activity_code_types) >= 2

    # the per-dimension answer, exactly as before (each call works out its own filter)
    expected = {}
    for t in data.activity_code_types:
        s = scope_weights(data, t)
        if s['rows']:
            expected[t] = s
    assert expected, 'fixture is cost-loaded'

    real, calls = cr._construction_codes, []
    monkeypatch.setattr(cr, '_construction_codes', lambda d: (calls.append(1), real(d))[1])
    got = scope_all(data)
    assert len(calls) == 1, f'construction filter worked out {len(calls)} times'
    assert got == expected                          # identical numbers + recommendations


def test_scope_weights_alone_still_filters_to_construction():
    from p6_update.analysis import scope_weights
    data = _two_dim_schedule()
    with_filter = scope_weights(data, 'Discipline')
    no_filter = scope_weights(data, 'Discipline', construction_only=False)
    assert with_filter['rows'] and no_filter['rows']


_XER = ('ERMHDR\t8.0\n'
        '%T\tUMEASURE\n%F\tunit_id\tunit_abbrev\tunit_name\n%R\t1\tm3\tMETR CUBED\n'
        '%T\tRSRC\n%F\trsrc_id\trsrc_type\tunit_id\n'
        '%R\t100\tRT_Labor\t\n%R\t200\tRT_Mat\t1\n%E\n')


@pytest.fixture
def resload_fresh(monkeypatch):
    from p6_narrative import resload
    monkeypatch.setattr(resload, '_META_CACHE', {})
    calls = []
    real = resload._res_from_xer
    monkeypatch.setattr(resload, '_res_from_xer', lambda p: (calls.append(p), real(p))[1])
    return resload, calls


def test_resource_meta_is_read_once_per_file(tmp_path, resload_fresh):
    resload, calls = resload_fresh
    p = tmp_path / 'sched.xer'
    p.write_text(_XER, encoding='utf-8')
    a = resload.read_resource_meta(str(p))
    b = resload.read_resource_meta(str(p))
    assert a == b == {'100': {'type': 'RT_Labor', 'unit': None}, '200': {'type': 'RT_Mat', 'unit': 'm3'}}
    assert len(calls) == 1, 'second section re-read the whole file'
    a['100']['type'] = 'changed'                    # each caller gets its own copy
    assert resload.read_resource_meta(str(p))['100']['type'] == 'RT_Labor'


def test_resource_meta_rereads_a_changed_file(tmp_path, resload_fresh):
    resload, calls = resload_fresh
    p = tmp_path / 'sched.xer'
    p.write_text(_XER, encoding='utf-8')
    resload.read_resource_meta(str(p))
    p.write_text(_XER.replace('%R\t100\tRT_Labor\t\n', '%R\t100\tRT_Equip\t\n%R\t300\tRT_Labor\t\n'),
                 encoding='utf-8')
    st = os.stat(p)
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))
    again = resload.read_resource_meta(str(p))
    assert len(calls) == 2
    assert again['100']['type'] == 'RT_Equip' and '300' in again


def test_resource_meta_missing_file_is_empty(tmp_path, resload_fresh):
    resload, _ = resload_fresh
    assert resload.read_resource_meta(str(tmp_path / 'nope.xer')) == {}
    assert resload.read_resource_meta(None) == {}
