"""The Studio's EVM composite results reuse the EVM Report's OWN sections, so a
pick looks EXACTLY like the EVM Report (style + format) — not a re-derived generic
table/chart. Regression for Ibrahim's report: 'Planned vs Actual by category' in
the Studio must match the EVM Report's category section.
"""
import db
from p6_special import registry
from p6_special.context import SpecialContext


def _seed(fixture):
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
    return pid, sid


def _render_one(pid, sid, item_id):
    ctx = SpecialContext(pid, snapshot_id=sid)
    out = registry.render(ctx, [item_id])
    assert out, f'{item_id} produced nothing'
    return out[0], ctx


def test_category_item_reuses_the_evm_report_section(temp_db, xml_path):
    pid, sid = _seed(xml_path)
    item, ctx = _render_one(pid, sid, 'evm:category_table')

    # It is now a reused HTML section (not a generic re-derived table payload).
    assert item['ctype'] == 'section'
    pl = item['payload']
    assert pl.get('kind') == 'html', f'expected reused html section, got {pl.get("kind")}'
    html = pl.get('html') or ''

    # It carries the EVM Report's OWN category heading + its styled table classes,
    # so it looks identical to the EVM Report's category section.
    assert 'Category Weights' in html
    assert 'WBS Category' in html          # the report table's own header cell
    assert 'class="num"' in html or 'class="tot"' in html   # the report's table styling


def test_category_item_matches_the_real_report_section_verbatim(temp_db, xml_path):
    """The item's fragment is exactly what the EVM Report renders for that section."""
    pid, sid = _seed(xml_path)
    item, ctx = _render_one(pid, sid, 'evm:category_table')
    frag = item['payload']['html']

    from p6_evm.evm_report import render_evm_report
    from p6_special import feature_reports as FR
    ref = render_evm_report(ctx.computed(), {'project_name': ctx.project_name,
                                             'data_date': ctx.data_date},
                            sections=['category'], theme=ctx.mode)
    ref_body = FR._strip_trailing_foot(FR._body_after_head(ref))
    assert ref_body and ref_body in frag       # the item wraps the exact report section


def test_paired_and_value_items_are_also_reused_sections(temp_db, xml_path):
    pid, sid = _seed(xml_path)
    for item_id, needle in (('evm:planned_vs_actual', 'Project Progress'),
                            ('evm:pv_ev_ac', 'Planned Value vs Earned Value')):
        item, _ = _render_one(pid, sid, item_id)
        assert item['ctype'] == 'section'
        assert item['payload'].get('kind') == 'html'
        assert needle in item['payload']['html']
