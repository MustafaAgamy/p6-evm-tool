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


def tiles(project_id=None, item_ids=None, inputs=None, snapshot_id=None, mode='light'):
    """Per-item dashboard tiles for the selected items + dashboard meta.

    ``mode`` themes any reused feature-report sections (kind 'html'); when the
    board holds such a section the response also carries ``theme_css`` — the
    report_theme token block those sections need to render styled on the board."""
    import report_theme
    mode = report_theme.normalize(mode)
    ctx = _ctx(project_id, snapshot_id, inputs, mode=mode)
    rendered = registry.render(ctx, item_ids or [])
    from p6_special import dash_payload
    out = [dash_payload.map_tile(it) for it in rendered]
    theme_css = report_theme.theme_style_tag(mode) if any(t.get('kind') == 'html' for t in out) else ''
    meta = {
        'project_name': ctx.project_name,
        'data_date': ctx.data_date,
        'activity_count': (ctx.evm or {}).get('activity_count'),
    }
    return {'tiles': out, 'meta': meta, 'theme_css': theme_css}


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


def docx(path, project_id=None, item_ids=None, report_name='Special Report', meta=None,
         letterhead=None, inputs=None, snapshot_id=None, chrome=None, mode='light'):
    """Write a Word ``.docx`` report to ``path`` that is a pixel-exact copy of the PDF.

    The Word file must match the PDF *exactly* (Ibrahim's standing requirement), so —
    when ``chrome`` (an absolute path to a Chrome/Chromium executable, supplied by the
    server) and PyMuPDF are both available — we render the SAME HTML the PDF uses, print
    it to a PDF with the SAME Chrome flags, and drop each PDF page into the document as a
    full-page image (see :mod:`p6_special.docx_pdf`). That makes page layout, contents
    page numbers, and every table's styling identical to the PDF by construction.

    If Chrome or PyMuPDF is unavailable (or the PDF render fails), we fall back to the
    native python-docx builder (:mod:`p6_special.docx_report`) — an editable, best-effort
    match — so the export never hard-fails. ``mode`` is the appearance mode."""
    import report_theme
    mode = report_theme.normalize(mode)
    ctx = _ctx(project_id, snapshot_id, inputs, mode=mode)
    rendered = registry.render(ctx, item_ids or [])

    # Preferred path: Word == PDF, page for page. Render the SAME two-pass PDF the PDF
    # export produces (correct contents page numbers) and rasterise each page into the
    # .docx, so Word and PDF are byte-identical in layout.
    if chrome:
        tmp_pdf = None
        try:
            import os
            import tempfile
            from p6_special import pdf_render, docx_pdf

            def _build(page_numbers):
                return render_html.build_document(report_name, _meta(ctx, meta), rendered,
                                                  mode=mode, letterhead=letterhead,
                                                  page_numbers=page_numbers)

            fd, tmp_pdf = tempfile.mkstemp(suffix='.pdf')
            os.close(fd)
            pdf_render.render_document_pdf(tmp_pdf, _build, chrome)
            docx_pdf.pdf_to_docx(path, tmp_pdf)
            return
        except Exception:
            # The native builder below is a DIFFERENT-looking (editable, best-effort)
            # document, so a fall-back here means the user did NOT get the PDF-exact
            # copy they asked for. Never swallow this silently — log the traceback so a
            # regression in the PDF-exact path is diagnosable instead of masquerading as
            # a quiet format switch (CI never runs the exe, and the handler returns ok).
            import traceback
            traceback.print_exc()
        finally:
            if tmp_pdf and os.path.exists(tmp_pdf):
                try:
                    os.remove(tmp_pdf)
                except OSError:
                    pass

    from p6_special import docx_report
    docx_report.build_docx(path, report_name, _meta(ctx, meta), rendered,
                           letterhead=letterhead, chrome=chrome, mode=mode)


def render_pdf(pdf_path, project_id=None, item_ids=None, report_name='Special Report',
               mode='light', meta=None, letterhead=None, inputs=None, snapshot_id=None,
               chrome=None):
    """Render the Special Report to a PDF at ``pdf_path`` with correct contents-page
    numbers via a two-pass render (see :mod:`p6_special.pdf_render`). ``chrome`` is
    required. Returns ``pdf_path``."""
    if not chrome:
        raise RuntimeError('chrome executable required to render the PDF')
    import report_theme
    mode = report_theme.normalize(mode)
    ctx = _ctx(project_id, snapshot_id, inputs, mode=mode)
    rendered = registry.render(ctx, item_ids or [])
    from p6_special import pdf_render

    def _build(page_numbers):
        return render_html.build_document(report_name, _meta(ctx, meta), rendered,
                                          mode=mode, letterhead=letterhead,
                                          page_numbers=page_numbers)

    return pdf_render.render_document_pdf(pdf_path, _build, chrome)


def excel(path, project_id=None, item_ids=None, report_name='Special Report', meta=None,
          inputs=None, snapshot_id=None):
    """Write the picked results to an .xlsx workbook at ``path`` — the DATA behind the
    Document / Dashboard (Contents sheet + one sheet per result). Appearance mode does
    not apply to a data workbook, so it takes no ``mode``."""
    ctx = _ctx(project_id, snapshot_id, inputs)
    rendered = registry.render(ctx, item_ids or [])
    from p6_special import excel_export
    excel_export.build_excel(path, report_name, _meta(ctx, meta), rendered)
