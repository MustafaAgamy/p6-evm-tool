"""Slice-1 Schedule Intelligence — the schedule profile / fingerprint.

Counts must reconcile EXACTLY with the raw parse; the profile must be JSON-serialisable
and its adaptive params must track the size class.
"""
import json
from pathlib import Path

from p6_evm.parser import parse_file
from p6_narrative.intel import build_context, build_profile
from p6_narrative.intel.profile import _PARAMS, _size_class

from tests.test_intel_context import _synthetic

FIXTURE = Path(__file__).parent / 'fixtures' / 'minimal.xml'


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
