"""Tests for the Baseline Narrative Special Report provider.

The provider reuses the RICH Baseline Narrative Report feature (``p6_narrative``): it builds
the document exactly as ``server._handle_narrative`` does — ``p6_narrative.report.build_report
(data, path=…, setup=None)`` rendered with ``p6_narrative.html.render_narrative_html`` — then
exposes one ``section``-type Item per section, each sliced verbatim from that render. These
tests seed a snapshot pointing at the ``minimal.xml`` fixture (so the context re-parses the
real file, as the feature does), then assert:
  * the provider exposes the rich sections (stable ids + the feature's own titles);
  * each ``produce(ctx)`` returns a real ``html`` payload without raising;
  * a produced section is byte-for-byte the same fragment the feature's own renderer emits
    for that section (parity by construction);
  * availability exactly complements produce (ready when the section renders, else no_data),
    and the whole feature is gated on the schedule being on disk.
"""
import db
from p6_special.providers import narrative
from p6_special.context import SpecialContext

# The exact section slugs + the feature's own section titles, in report order.
_EXPECTED = [
    ('narrative:overview',   'Project Overview'),
    ('narrative:layout',     'Project Layout'),
    ('narrative:brief',      'Project Brief'),
    ('narrative:milestones', 'Major Milestones'),
    ('narrative:keydates',   'Key Dates'),
    ('narrative:value',      'Contract Value'),
    ('narrative:scope',      'Scope of Work'),
    ('narrative:calendars',  'Project Calendars & Holidays'),
    ('narrative:wbs',        'Work Breakdown Structure'),
    ('narrative:codes',      'Activity Codes'),
    ('narrative:sequence',   'Sequence of Work'),
]


def _seed(fixture):
    """A project + snapshot whose original/cached path is the fixture, so ``ctx.xml_path``
    resolves to a real file on disk and the narrative can re-parse it (as the feature does)."""
    pid = db.upsert_project('P1', 'Grain')
    sid = db.insert_snapshot(pid, '2026-01-01', str(fixture), str(fixture), 'h', 10, 2)
    db.insert_metrics(sid, {
        'pv': 1e6, 'ev': 6e5, 'ac': 7e5, 'spi': 0.6, 'cpi': 0.857, 'delay_days': 5,
        'overall_planned_pct': 0.614, 'overall_actual_pct': 0.404, 'variance': -0.21,
    })
    db.insert_category_metrics(sid, {
        'Construction': {'weight': 0.855, 'planned_pct': 0.58, 'actual_pct': 0.38,
                         'bac': 1e6, 'ac': 7e5, 'activity_count': 50, 'overridden': False},
    })
    return pid


def _items(ctx):
    return {i.id: i for i in narrative.provide(ctx)}


def _feature_render(fixture):
    """The feature's OWN document + HTML, built the SAME way the server handler builds it —
    the source of truth the provider must reproduce."""
    from p6_evm.parser import parse_file
    from p6_narrative.report import build_report
    from p6_narrative.html import render_narrative_html
    data = parse_file(str(fixture))
    doc_dict = build_report(data, path=str(fixture), setup=None).to_dict()
    return doc_dict, render_narrative_html(doc_dict)


# ── the provider exposes the rich feature's sections ──────────────────────────────────
def test_provides_the_rich_narrative_sections(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    items = narrative.provide(ctx)
    assert [(i.id, i.title) for i in items] == _EXPECTED
    # every item is a reused feature-report 'section', under the Baseline Narrative feature.
    for i in items:
        assert i.ctype == 'section'
        assert i.feature == 'narrative'
        assert i.feature_title == 'Baseline Narrative'
        assert not i.requires        # the default report needs no extra uploaded input


def test_slugs_track_the_report_titles(temp_db, xml_path):
    """The provider's static slug->title map must match the feature's actual section titles
    for the fixture (so a picked item names the real section)."""
    doc_dict, _ = _feature_render(xml_path)
    feature_titles = [s['title'] for s in doc_dict['sections']]
    assert [t for _, t in _EXPECTED] == feature_titles


# ── every item produces a real html payload without raising ───────────────────────────
def test_every_item_produces_an_html_payload(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    for iid, it in _items(ctx).items():
        pl = it.produce(ctx)
        assert isinstance(pl, dict), iid
        assert pl.get('kind') == 'html', iid
        assert pl.get('feature') == 'narrative', iid
        assert pl.get('html') and pl.get('css'), iid
        assert pl['html'].startswith('<div class="srf-narrative">'), iid
        assert '.srf-narrative' in pl['css'], iid


def test_section_is_byte_for_byte_the_feature_render(temp_db, xml_path):
    """A produced section == the exact fragment the feature's own renderer emits for that
    section (heading stripped, wrapped) — parity by construction, no hand-rebuilt markup."""
    ctx = SpecialContext(_seed(xml_path))
    doc_dict, feature_html = _feature_render(xml_path)
    number_by_title = {s['title']: str(s['number']) for s in doc_dict['sections']}
    items = _items(ctx)
    for iid, title in _EXPECTED:
        number = number_by_title[title]
        expected_frag = narrative._strip_leading_h1(
            narrative._extract_section(feature_html, number))
        assert expected_frag.strip(), title           # the feature really renders this section
        pl = items[iid].produce(ctx)
        assert pl['html'] == '<div class="srf-narrative">%s</div>' % expected_frag


def test_extract_section_does_not_confuse_1_and_11(temp_db, xml_path):
    """The data-section slicer must not let key '1' match '<section data-section="11">' —
    the §1 Overview fragment and the §11 Sequence fragment are distinct."""
    _, feature_html = _feature_render(xml_path)
    s1 = narrative._extract_section(feature_html, '1')
    s11 = narrative._extract_section(feature_html, '11')
    assert s1 and s11 and s1 != s11
    assert 'Project Overview' in s1
    assert 'Sequence' in s11


# ── availability exactly complements produce() ────────────────────────────────────────
def test_availability_ready_and_produce_renders(temp_db, xml_path):
    """With the schedule on disk every section renders, so availability is 'ready' AND
    produce returns a non-no_data payload — the two never disagree."""
    ctx = SpecialContext(_seed(xml_path))
    for it in narrative.provide(ctx):
        avail = it.availability(ctx)
        pl = it.produce(ctx)
        assert avail == 'ready', it.id
        assert pl.get('kind') != 'no_data', it.id


def test_availability_no_data_without_schedule(temp_db):
    """No schedule on disk (unknown project) → the whole feature is gated: every item
    reports 'no_data' AND produce returns the NO_DATA sentinel (never a ready-but-empty
    item — the #1 past provider defect)."""
    ctx = SpecialContext(9999)
    assert not ctx.has_xml()
    for it in narrative.provide(ctx):
        assert it.availability(ctx) == 'no_data', it.id
        assert it.produce(ctx)['kind'] == 'no_data', it.id
