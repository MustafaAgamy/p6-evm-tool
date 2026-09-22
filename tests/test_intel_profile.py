"""Slice-1 Schedule Intelligence — the schedule profile / fingerprint.

Counts must reconcile EXACTLY with the raw parse; the profile must be JSON-serialisable
and its adaptive params must track the size class.
"""
import json
from pathlib import Path

from p6_evm.calendars import Calendar
from p6_evm.parser import ScheduleData, parse_file
from p6_narrative.intel import build_context, build_profile
from p6_narrative.intel.profile import _PARAMS, _size_class

from tests.test_intel_context import _act, _synthetic

FIXTURE = Path(__file__).parent / 'fixtures' / 'minimal.xml'


def _medium_schedule_with_shallow_repetition():
    """500+ activities (-> 'medium' size class) but the deepest measured repetition —
    WBS-sibling AND name — is only 2. Proves min_instances is capped by what the file
    actually repeats, never by size class alone (two real baselines of 896 and 2502
    activities both land in 'medium' yet repeat 14 deep and 6 deep respectively).
    """
    d = ScheduleData()
    d.calendars = {'C1': Calendar(object_id='C1', name='Cal', day_hours=8.0)}
    d.project = {'data_date': None}
    d.wbs = {
        'PRJ': {'name': 'Project', 'parent_object_id': None},
        'GRP': {'name': 'Twin Units', 'parent_object_id': 'PRJ'},
        'U1': {'name': 'Unit 1', 'parent_object_id': 'GRP'},
        'U2': {'name': 'Unit 2', 'parent_object_id': 'GRP'},
        'FILLER': {'name': 'Miscellaneous', 'parent_object_id': 'PRJ'},
    }
    d.activities = {}
    for wid in ('U1', 'U2'):
        for i in range(2):
            oid = '%s-%d' % (wid, i)
            d.activities[oid] = _act(oid, 'Step %d' % i, wid, dur_hours=8.0)
    for i in range(500):
        oid = 'filler-%d' % i
        d.activities[oid] = _act(oid, 'Unique Task %d' % i, 'FILLER', dur_hours=8.0)
    d.activity_code_types = []
    d.relationships = []
    d.bac_by_activity = {}
    d.ac_by_activity = {}
    return d


def test_counts_reconcile_exact_with_raw_parse():
    d = parse_file(str(FIXTURE))
    prof = build_profile(build_context(d))
    assert prof['activities'] == len(d.activities) == 2
    assert prof['relationships'] == len(d.relationships) == 0
    assert prof['milestones'] == 0
    assert prof['step_activities'] == 2


def test_counts_reconcile_on_synthetic_with_milestones():
    d = _synthetic()
    prof = build_profile(build_context(d))
    assert prof['activities'] == len(d.activities) == 7   # incl. milestones/LOE/summary
    assert prof['step_activities'] == 3
    assert prof['milestones'] == 2
    assert prof['relationships'] == len(d.relationships) == 2
    assert prof['critical_count'] == 1
    assert prof['disciplines'] == 2 and prof['packages'] == 2


def test_rel_type_mix_has_all_four_keys_and_correct_tally():
    prof = build_profile(build_context(_synthetic()))
    assert prof['rel_type_mix'] == {'FS': 1, 'SS': 1, 'FF': 0, 'SF': 0}
    # even an empty schedule reports all four keys
    empty = build_profile(build_context(parse_file(str(FIXTURE))))
    assert set(empty['rel_type_mix']) == {'FS', 'SS', 'FF', 'SF'}


def test_logic_density_and_pct_with_actuals():
    prof = build_profile(build_context(_synthetic()))
    assert prof['logic_density'] == round(2 / 7, 4)
    assert prof['pct_with_actuals'] == round(1 / 7, 4)  # only a1 has an actual start


def test_wbs_shape():
    prof = build_profile(build_context(_synthetic()))
    assert prof['wbs_depth'] == 3   # PRJ > CIV > PILE
    assert prof['wbs_width'] == 2   # CIV, MEC major branches


def test_coverage_flags():
    prof = build_profile(build_context(_synthetic()))
    assert prof['code_dimensions'] == ['Type of Works']
    assert prof['has_cost'] is True
    assert prof['has_resources'] is True
    # no codes / no cost variant
    d = _synthetic(with_codes=False)
    d.bac_by_activity = {}
    d.ac_by_activity = {}
    prof2 = build_profile(build_context(d))
    assert prof2['code_dimensions'] == []
    assert prof2['has_cost'] is False
    assert prof2['has_resources'] is False


def test_size_class_thresholds():
    assert _size_class(0) == 'small'
    assert _size_class(499) == 'small'
    assert _size_class(500) == 'medium'
    assert _size_class(4999) == 'medium'
    assert _size_class(5000) == 'large'
    # minimal fixture is small
    assert build_profile(build_context(parse_file(str(FIXTURE))))['size_class'] == 'small'


def test_params_scale_with_size_class():
    prof = build_profile(build_context(_synthetic()))
    assert prof['size_class'] == 'small'
    assert prof['params'] == _PARAMS['small']
    # params keys are stable and complete
    for sc in ('small', 'medium', 'large'):
        assert set(_PARAMS[sc]) == {'min_instances', 'sim_threshold',
                                    'max_chart_items', 'max_charts'}


def test_profile_is_json_serialisable():
    prof = build_profile(build_context(_synthetic()))
    assert json.loads(json.dumps(prof)) == prof


def test_repetition_key_is_present_and_reports_no_repetition_on_the_synthetic_fixture():
    prof = build_profile(build_context(_synthetic()))
    assert 'repetition' in prof
    # 3 activities, all 3 names distinct: the deepest anything occurs is once (no repeat)
    assert prof['repetition']['deepest_repeat'] == 1
    assert prof['repetition']['name_repeat_share'] == 0.0
    assert prof['repetition']['wbs_repeat_share'] == 0.0
    assert prof['params'] == _PARAMS['small']    # untouched: nothing measured to cap with


def test_min_instances_is_capped_by_measured_repetition_not_size_class_alone():
    d = _medium_schedule_with_shallow_repetition()
    ctx = build_context(d)
    prof = build_profile(ctx)
    assert prof['size_class'] == 'medium'
    assert _PARAMS['medium']['min_instances'] == 3          # the un-capped default
    assert prof['repetition']['deepest_repeat'] == 2         # this file repeats no deeper
    assert prof['params']['min_instances'] == 2               # capped DOWN, never up
    # every other param is untouched
    assert prof['params']['sim_threshold'] == _PARAMS['medium']['sim_threshold']
    assert prof['params']['max_chart_items'] == _PARAMS['medium']['max_chart_items']
    assert prof['params']['max_charts'] == _PARAMS['medium']['max_charts']
    assert json.loads(json.dumps(prof)) == prof
