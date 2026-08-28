"""High-level orchestration for Special Report — ties context + registry +
renderer/exporters together. The server handlers stay thin by calling these.
"""
import db
from p6_special import registry, render_html, word_export
from p6_special.context import SpecialContext


def _ctx(project_id=None, snapshot_id=None, inputs=None, mode='light'):
    if not project_id and snapshot_id:
        project_id = db.get_project_id_for_snapshot(snapshot_id)
    return SpecialContext(project_id, snapshot_id=snapshot_id, inputs=inputs, mode=mode)


def catalog(project_id=None, snapshot_id=None, inputs=None):
    """Grouped catalog of every available result for a project (with availability
    computed against any attached ``inputs``)."""
    return registry.catalog(_ctx(project_id, snapshot_id, inputs))


def _meta(ctx, meta):
    m = dict(ctx.meta or {})
    if meta:
        m.update({k: v for k, v in meta.items() if v})
    return m


def build_html(project_id=None, item_ids=None, report_name='Special Report', mode='light',
               meta=None, letterhead=None, inputs=None, snapshot_id=None):
    """Full themed HTML document (screen preview + Chrome PDF)."""
    ctx = _ctx(project_id, snapshot_id, inputs, mode=mode)
    rendered = registry.render(ctx, item_ids or [])
    return render_html.build_document(report_name, _meta(ctx, meta), rendered,
                                      mode=mode, letterhead=letterhead)


def build_word(project_id=None, item_ids=None, report_name='Special Report', mode='light',
               meta=None, letterhead=None, inputs=None, snapshot_id=None):
    """Word-openable document (best-effort match to the PDF)."""
    ctx = _ctx(project_id, snapshot_id, inputs, mode=mode)
    rendered = registry.render(ctx, item_ids or [])
    return word_export.build_word_document(report_name, _meta(ctx, meta), rendered,
                                           mode=mode, letterhead=letterhead)
