"""Tests for the Update Analysis Special Report provider.

Covers the per-activity-code-dimension coverage: Section 2 (Planned vs Actual by
activity code) and Section 5 (Scope Weight & Recommendation) each expose one item
per code dimension in the schedule, rendered through the feature's OWN renderer,
with availability that exactly complements produce.
"""
import db
from p6_special.providers import update
from p6_special.context import SpecialContext


# ── a small multi-dimension, cost-loaded update XML (Discipline + Area) ────────
def _xml():
    codes_defs = (
        '<ActivityCodeType><ObjectId>901</ObjectId><Name>Discipline</Name></ActivityCodeType>'
        '<ActivityCode><ObjectId>902</ObjectId><CodeValue>Civil</CodeValue><CodeTypeObjectId>901</CodeTypeObjectId></ActivityCode>'
        '<ActivityCode><ObjectId>903</ObjectId><CodeValue>Mechanical</CodeValue><CodeTypeObjectId>901</CodeTypeObjectId></ActivityCode>'
        '<ActivityCodeType><ObjectId>911</ObjectId><Name>Area</Name></ActivityCodeType>'
        '<ActivityCode><ObjectId>912</ObjectId><CodeValue>Zone A</CodeValue><CodeTypeObjectId>911</CodeTypeObjectId></ActivityCode>'
    )
    acts = [
        # oid, id, name, pct, dur, {code type oid: value oid} for Discipline + Area
        (10, 'C1', 'Civil 1', 0.2, 800, 902, 912),
        (11, 'M1', 'Mech 1', 0.7, 80, 903, 912),
    ]
    body = baseline = ras = ''
    for oid, code, name, pct, dur, disc_oid, area_oid in acts:
        body += (f'<Activity><ObjectId>{oid}</ObjectId><Id>{code}</Id><Name>{name}</Name>'
                 f'<Type>Task Dependent</Type><WBSObjectId>100</WBSObjectId><CalendarObjectId></CalendarObjectId>'
                 f'<PercentComplete>{pct}</PercentComplete>'
                 f'<PlannedDuration>{dur}</PlannedDuration><RemainingDuration>{dur}</RemainingDuration>'
                 f'<RemainingEarlyStartDate>2025-01-01T00:00:00</RemainingEarlyStartDate>'
                 f'<RemainingEarlyFinishDate>2025-12-31T00:00:00</RemainingEarlyFinishDate>'
                 f'<Code><TypeObjectId>901</TypeObjectId><ValueObjectId>{disc_oid}</ValueObjectId></Code>'
                 f'<Code><TypeObjectId>911</TypeObjectId><ValueObjectId>{area_oid}</ValueObjectId></Code>'
                 f'</Activity>\n')
        baseline += (f'<Activity><ObjectId>{oid + 1000}</ObjectId><Id>{code}</Id>'
                     f'<PlannedStartDate>2025-01-01T00:00:00</PlannedStartDate>'
                     f'<PlannedFinishDate>2025-12-31T00:00:00</PlannedFinishDate></Activity>\n')
        ras += (f'<ResourceAssignment><ActivityObjectId>{oid}</ActivityObjectId>'
                f'<PlannedCost>{dur * 100}</PlannedCost></ResourceAssignment>\n')
    return ('<?xml version="1.0"?>\n<APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">\n'
            f'{codes_defs}'
            '  <Project><ObjectId>1</ObjectId><Id>P1</Id><Name>Proj</Name><DataDate>2025-07-02T00:00:00</DataDate>\n'
            '    <WBS><ObjectId>100</ObjectId><Name>Proj</Name><ParentObjectId></ParentObjectId></WBS>\n'
            f'{body}{ras}  </Project>\n'
            f'  <BaselineProject>\n{baseline}  </BaselineProject>\n</APIBusinessObjects>\n')


def _seed(tmp_path):
    p = tmp_path / 'update.xml'
    p.write_text(_xml(), encoding='utf-8')
    pid = db.upsert_project('P1', 'Proj')
    sid = db.insert_snapshot(pid, '2025-07-02', str(p), str(p), 'h', 2, 1)
    db.insert_metrics(sid, {'pv': 1e5, 'ev': 6e4, 'ac': 5e4, 'spi': 0.6, 'cpi': 0.8,
                            'delay_days': 3, 'overall_planned_pct': 0.5,
                            'overall_actual_pct': 0.3, 'variance': -0.2})
    return pid


def _items(ctx):
    return {i.id: i for i in update.provide(ctx)}


# ── Section 2 · Planned vs Actual — one item per activity-code dimension ───────
def test_bycode_per_dimension_items_added(temp_db, tmp_path):
    ctx = SpecialContext(_seed(tmp_path))
    items = _items(ctx)
    # activity_code_types is sorted → 'Area', 'Discipline'
    assert 'update:bycode:Area' in items
    assert 'update:bycode:Discipline' in items
    # default item is kept (Hard Rule: never remove existing items)
    assert 'update:bycode' in items


def test_bycode_dimension_ready_and_renders_feature_section(temp_db, tmp_path):
    ctx = SpecialContext(_seed(tmp_path))
    it = _items(ctx)['update:bycode:Discipline']
    assert it.availability(ctx) == 'ready'
    pl = it.produce(ctx)
    # reuses the feature's OWN by-code section (html payload), not a re-derived block
    assert pl['kind'] == 'html'
    # the dimension's own values render (worst-gap-first bars from the feature)
    assert 'Civil' in pl['html'] and 'Mechanical' in pl['html']
    # the report's numbered <h2> banner is stripped (Studio adds its own badge)
    assert '<h2' not in pl['html']


def test_bycode_area_dimension_distinct_from_discipline(temp_db, tmp_path):
    ctx = SpecialContext(_seed(tmp_path))
    area = _items(ctx)['update:bycode:Area'].produce(ctx)
    assert area['kind'] == 'html'
    assert 'Zone A' in area['html']


# ── Section 5 · Scope Weight — one item per cost-loaded dimension ──────────────
def test_scope_per_dimension_items_added(temp_db, tmp_path):
    ctx = SpecialContext(_seed(tmp_path))
    items = _items(ctx)
    assert 'update:scope:Discipline' in items
    assert 'update:scope:Area' in items
    # default item kept
    assert 'update:scope' in items


def test_scope_dimension_ready_and_renders_feature_section(temp_db, tmp_path):
    ctx = SpecialContext(_seed(tmp_path))
    it = _items(ctx)['update:scope:Discipline']
    assert it.availability(ctx) == 'ready'
    pl = it.produce(ctx)
    assert pl['kind'] == 'html'
    # scope weighting header + a recommendation from the feature's renderer
    assert 'Weighting by' in pl['html'] and 'Civil' in pl['html']
    assert '<h2' not in pl['html']


# ── availability exactly complements produce ──────────────────────────────────
def test_no_xml_yields_no_per_dimension_items(temp_db):
    """No open file → the report can't be built → no per-dimension items exist, and
    the default section items report 'no_data' (not a 'ready' item that renders empty)."""
    ctx = SpecialContext(9999)
    items = _items(ctx)
    assert not any(k.startswith('update:bycode:') for k in items)
    assert not any(k.startswith('update:scope:') for k in items)
    assert items['update:bycode'].availability(ctx) == 'no_data'
    assert items['update:scope'].availability(ctx) == 'no_data'


def test_bycode_empty_dimension_gated_no_data(temp_db, tmp_path):
    """A code dimension present in the report but with NO by-code rows must gate
    'no_data' and produce NO_DATA — never a 'ready' item that renders only a
    'No values for this activity code' note (the #1 past defect)."""
    ctx = SpecialContext(_seed(tmp_path))
    rep = update._report(ctx)
    assert rep is not None
    # inject a real-but-empty dimension into the built report (memoized) — mirrors a
    # code type whose activities carry no baseline/cost, so its bucket is empty.
    rep['code_types'] = list(rep['code_types']) + ['Ghost']
    rep['by_code']['Ghost'] = []
    it = {i.id: i for i in update.provide(ctx)}['update:bycode:Ghost']
    assert it.availability(ctx) == 'no_data'
    assert it.produce(ctx)['kind'] == 'no_data'


def test_scope_only_cost_loaded_dimensions(temp_db, tmp_path):
    """Section 5 items come from report['scope'] (scope_all) — only cost-loaded
    dimensions — so an enumerated scope item always renders (never empty)."""
    ctx = SpecialContext(_seed(tmp_path))
    rep = update._report(ctx)
    for t in (rep.get('scope') or {}):
        it = {i.id: i for i in update.provide(ctx)}[f'update:scope:{t}']
        assert it.availability(ctx) == 'ready'
        assert it.produce(ctx)['kind'] == 'html'
