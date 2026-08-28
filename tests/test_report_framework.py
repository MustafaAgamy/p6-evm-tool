"""Global Print-Preview framework — the reusable report component registry and the
single assembler that Preview, PDF and Print all consume.

The whole point of the framework is one source of truth: whatever the user ticks in
Report Contents, in whatever order, produces exactly one HTML document, and that same
document is what the preview iframe shows and what Chrome turns into the PDF. These
tests pin that contract down at the framework level, independent of any one feature.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from p6_report.registry import ReportComponent, ReportSpec, get_spec, register
from p6_report.render import build_document, manifest


def _spec():
    return ReportSpec(
        feature='demo',
        title='Demo Report',
        subtitle='for tests',
        css='.demo { color: teal; }',
        components=[
            ReportComponent('summary', 'Summary', 'summary',
                            render=lambda r: f"<p class='demo'>Score {r['score']}</p>"),
            ReportComponent('chart', 'Trend Chart', 'chart',
                            render=lambda r: "<svg><rect/></svg>"),
            ReportComponent('table', 'Detail Table', 'table',
                            render=lambda r: "<table><tr><td>row</td></tr></table>",
                            has_data=lambda r: bool(r.get('rows'))),
            ReportComponent('notes', 'Notes', 'text', default=False,
                            render=lambda r: "<p>notes</p>"),
        ],
    )


# ── the manifest the selector is built from ──────────────────────────────────

def test_manifest_lists_components_in_order_with_type_and_default():
    m = manifest(_spec(), {'score': 90, 'rows': [1]})
    assert [c['id'] for c in m] == ['summary', 'chart', 'table', 'notes']
    assert [c['type'] for c in m] == ['summary', 'chart', 'table', 'text']
    # default selection excludes the opt-out component
    assert [c['id'] for c in m if c['default']] == ['summary', 'chart', 'table']
    # a component whose data is absent is still listed, but flagged
    assert next(c for c in m if c['id'] == 'table')['has_data'] is True


def test_manifest_flags_components_with_no_data():
    m = manifest(_spec(), {'score': 1, 'rows': []})
    assert next(c for c in m if c['id'] == 'table')['has_data'] is False


# ── the assembler: the single source of truth ────────────────────────────────

def test_document_contains_only_selected_components_in_selected_order():
    doc = build_document(_spec(), {'score': 90, 'rows': [1]},
                         selected_ids=['table', 'summary'], order=['table', 'summary'])
    assert 'Detail Table' in doc and 'Summary' in doc
    assert 'Trend Chart' not in doc and 'Notes' not in doc
    # order honoured: table's section appears before summary's
    assert doc.index('Detail Table') < doc.index('Summary')


def test_unselected_component_is_absent_not_hidden():
    doc = build_document(_spec(), {'score': 90, 'rows': [1]}, selected_ids=['summary'])
    # the chart's actual content must not be in the document at all
    assert '<svg>' not in doc
    assert 'display:none' not in doc.replace(' ', '')


def test_selected_component_with_no_data_shows_placeholder_not_dropped():
    doc = build_document(_spec(), {'score': 1, 'rows': []},
                         selected_ids=['summary', 'table'])
    assert 'Detail Table' in doc                      # heading still present
    assert 'No data' in doc                           # explicit placeholder
    assert '<td>row</td>' not in doc                  # the empty render is not used


def test_sections_are_auto_numbered_in_selected_order():
    doc = build_document(_spec(), {'score': 90, 'rows': [1]},
                         selected_ids=['chart', 'summary', 'table'],
                         order=['chart', 'summary', 'table'])
    # numbering follows selection order, starting at 1
    assert doc.index('1.') < doc.index('Trend Chart')
    assert doc.index('2.') < doc.index('Summary')
    assert doc.index('3.') < doc.index('Detail Table')


def test_document_is_self_contained_and_carries_feature_css():
    doc = build_document(_spec(), {'score': 90, 'rows': [1]}, selected_ids=['summary'])
    assert doc.lstrip().lower().startswith('<!doctype html')
    assert '.demo { color: teal; }' in doc            # feature CSS embedded
    assert '@page' in doc                             # print page setup present
    assert 'Demo Report' in doc                       # title in the header


def test_empty_selection_still_valid_document_with_header():
    doc = build_document(_spec(), {'score': 90}, selected_ids=[])
    assert doc.lstrip().lower().startswith('<!doctype html')
    assert 'Demo Report' in doc


def test_unknown_selected_id_is_ignored_safely():
    doc = build_document(_spec(), {'score': 90, 'rows': [1]},
                         selected_ids=['summary', 'does_not_exist'])
    assert 'Summary' in doc


def test_none_selection_defaults_to_the_default_set():
    # selected_ids=None means "use each component's default" — the common first open
    doc = build_document(_spec(), {'score': 90, 'rows': [1]}, selected_ids=None)
    assert 'Summary' in doc and 'Trend Chart' in doc and 'Detail Table' in doc
    assert 'notes' not in doc.lower().replace('teal', '')   # opt-out excluded


# ── registry ─────────────────────────────────────────────────────────────────

def test_register_and_get_spec_roundtrip():
    register('demo_reg', lambda report: _spec())
    spec = get_spec('demo_reg', {'score': 1})
    assert spec.feature == 'demo'
    assert get_spec('no_such_feature', {}) is None


def test_component_render_receives_the_report_dict():
    doc = build_document(_spec(), {'score': 77, 'rows': [1]}, selected_ids=['summary'])
    assert 'Score 77' in doc


# ── appearance modes: the assembler themes every print-preview report ─────────

def test_document_injects_the_selected_appearance_theme():
    # a non-default mode must stamp its palette + data-rpt-theme, and the frame CSS
    # must read from tokens (so the whole report follows the six appearance modes).
    doc = build_document(_spec(), {'score': 90, 'rows': [1]}, selected_ids=['summary'],
                         theme='dark')
    assert 'data-rpt-theme="dark"' in doc          # the palette block for dark is present
    assert '--rpt-bg:' in doc                       # tokens defined on :root
    assert 'var(--rpt-ink)' in doc                  # frame CSS reads a token, not a fixed hex


def test_document_defaults_to_light_and_unknown_mode_falls_back():
    light = build_document(_spec(), {'score': 90}, selected_ids=['summary'])           # theme unset
    assert 'data-rpt-theme="light"' in light
    bogus = build_document(_spec(), {'score': 90}, selected_ids=['summary'], theme='nope')
    assert 'data-rpt-theme="light"' in bogus        # unknown mode is normalized to light
