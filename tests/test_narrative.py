"""Tests for p6_evm.narrative.build_narrative — the deterministic Baseline Narrative.

Pure function over an already-computed result: always the same five sections, tone
derived from SPI/CPI, category ranking surfaces the area furthest behind, and every
metric is guarded so a sparse result still yields correct (shorter) prose.
"""
from p6_evm.narrative import build_narrative, spi_phrase, cpi_phrase


def _result(**kw):
    base = {
        'project_name': 'Harbor Expansion', 'data_date': '2026-08-24',
        'spi': 0.82, 'cpi': 1.01, 'delay_days': 34,
        'overall_planned_pct': 0.56, 'overall_actual_pct': 0.38,
        'pv': 1_000_000, 'ev': 820_000, 'ac': 810_000,
        'categories': {
            'Engineering':  {'planned_pct': 0.60, 'actual_pct': 0.62},
            'Construction': {'planned_pct': 0.55, 'actual_pct': 0.30},
        },
    }
    base.update(kw)
    return base


def test_sections_are_stable_and_keyed():
    n = build_narrative(_result())
    assert [s['key'] for s in n['sections']] == ['summary', 'schedule', 'cost', 'areas', 'outlook']
    for s in n['sections']:
        assert s['paragraphs'] and all(isinstance(p, str) and p for p in s['paragraphs'])


def test_behind_schedule_tone_and_delay_language():
    n = build_narrative(_result(spi=0.82, delay_days=34))
    assert n['tone'] == 'bad'
    sched = ' '.join(dict((s['key'], ' '.join(s['paragraphs'])) for s in n['sections'])['schedule'].split())
    assert 'behind schedule' in sched
    assert '34 day' in sched and 'later than the baseline' in sched


def test_ahead_of_schedule_is_good():
    n = build_narrative(_result(spi=1.05, cpi=1.05, delay_days=-5))
    assert n['tone'] == 'good'
    summary = ' '.join(n['sections'][0]['paragraphs'])
    assert 'ahead of schedule' in summary


def test_worst_area_is_surfaced():
    areas = ' '.join(build_narrative(_result())['sections'][3]['paragraphs'])
    # Construction (30% actual vs 55% planned) is furthest behind
    assert 'Construction' in areas and 'furthest behind' in areas


def test_missing_metrics_degrade_without_crashing():
    n = build_narrative({'project_name': 'Sparse', 'spi': None, 'cpi': None,
                         'delay_days': None, 'overall_planned_pct': None,
                         'overall_actual_pct': None, 'categories': {}})
    assert [s['key'] for s in n['sections']] == ['summary', 'schedule', 'cost', 'areas', 'outlook']
    # no numbers → the guarded fallbacks, not a traceback
    assert 'not available' in ' '.join(n['sections'][1]['paragraphs'] + n['sections'][2]['paragraphs'])


def test_empty_result_is_safe():
    n = build_narrative({})
    assert n['headline'] and len(n['sections']) == 5


def test_phrase_helpers_boundaries():
    assert spi_phrase(1.05)[1] == 'good' and spi_phrase(0.85)[1] == 'bad'
    assert cpi_phrase(None)[1] == 'neutral'
