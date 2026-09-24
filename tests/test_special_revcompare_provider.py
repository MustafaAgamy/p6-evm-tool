"""Tests for the Baseline Revision Comparison Special Report provider.

revcompare is a TWO-file feature: the open schedule is Rev.01, the user attaches the
Rev.00 original. The provider reuses p6_revcompare.exporters.render_html and slices
each data-sec section. These tests seed a project + snapshot (so the open file is the
minimal fixture) and attach the SAME fixture as the 'original' input, so the report
compares the fixture against itself — enough to exercise every section and the
availability gating.
"""
import db
from p6_special.providers import revcompare
from p6_special.context import SpecialContext

# The 6-tab redesign's section keys (p6_revcompare.exporters._SECTIONS). Comparing the
# minimal fixture against itself, every section renders (each shows its "no change" state
# rather than being omitted), so nothing is skipped for this fixture.
RENDERED = ['summary', 'findings', 'critical', 'register', 'ms', 'cal', 'cost',
            'resource', 'manpower', 'scope']
SKIPPED = []


def _seed(fixture):
    pid = db.upsert_project('P1', 'Grain')
    # original_path == cached_path == the fixture, so ctx.has_xml()/ctx.parsed() work.
    db.insert_snapshot(pid, '2026-01-01', str(fixture), str(fixture), 'h', 10, 2)
    return pid


def _ctx_both(fixture):
    """Context with the open file seeded AND the Rev.00 original attached."""
    return SpecialContext(_seed(fixture), inputs={'original': str(fixture)})


def _items(ctx):
    return {i.id: i for i in revcompare.provide(ctx)}


def test_all_sections_offered(temp_db, xml_path):
    ids = set(_items(SpecialContext(_seed(xml_path))))
    for key, _ in revcompare.SECS:
        assert f'revcompare:{key}' in ids


def test_items_declare_original_requirement(temp_db, xml_path):
    it = _items(SpecialContext(_seed(xml_path)))['revcompare:summary']
    assert it.requires and it.requires[0]['role'] == 'original'


def test_needs_input_until_original_attached(temp_db, xml_path):
    """With the open file only (no attached Rev.00) every item is 'needs_input' and
    produces no_data — never a false 'ready'."""
    ctx = SpecialContext(_seed(xml_path))          # no inputs
    for it in _items(ctx).values():
        assert it.availability(ctx) == 'needs_input'
        assert it.produce(ctx)['kind'] == 'no_data'


def test_needs_input_when_no_open_file(temp_db):
    ctx = SpecialContext(9999)                      # no project, no inputs
    assert revcompare.provide(ctx)[0].availability(ctx) == 'needs_input'


def test_rendered_sections_ready_and_html(temp_db, xml_path):
    ctx = _ctx_both(xml_path)
    items = _items(ctx)
    for key in RENDERED:
        it = items[f'revcompare:{key}']
        assert it.availability(ctx) == 'ready', key
        pl = it.produce(ctx)
        assert pl['kind'] == 'html', key
        assert pl['html'].strip() and pl.get('css'), key


def test_skipped_section_reports_no_data(temp_db, xml_path):
    """The honest-gating guard (the #1 past defect): a section the renderer omits must
    report 'no_data', not a 'ready' item that renders empty."""
    ctx = _ctx_both(xml_path)
    items = _items(ctx)
    for key in SKIPPED:
        it = items[f'revcompare:{key}']
        assert it.availability(ctx) == 'no_data', key
        assert it.produce(ctx)['kind'] == 'no_data', key


def test_every_item_produces_without_raising(temp_db, xml_path):
    ctx = _ctx_both(xml_path)
    for it in _items(ctx).values():
        pl = it.produce(ctx)
        assert isinstance(pl, dict) and 'kind' in pl


def test_summary_mirrors_feature_renderer(temp_db, xml_path):
    """The sliced Executive Summary carries the feature's own markup (the 'Bottom line'
    verdict + the 'Revision snapshot' Rev.00→Rev.01 block) — reuse, not a hand-rebuilt
    block — and its own heading (the <div class="secmark"> title with its <h2>) is stripped
    so the Studio's numbered heading is the only title."""
    ctx = _ctx_both(xml_path)
    html = _items(ctx)['revcompare:summary'].produce(ctx)['html']
    assert 'bottomline' in html and 'Revision snapshot' in html
    assert '<h2' not in html and 'secmark' not in html
