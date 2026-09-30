"""Owner point 14 — pagination findings of the one-document reports (step pagination:F5).

ALL-PDF-SIZE: the EVM, Calendar and Schedule Health reports declared only ``@page`` margins,
so any path that printed their HTML without the export layer (the reports' own PDF routes)
came out on Chrome's default US Letter (612 x 792 pt) while the Word export and the
Narrative / Studio PDFs are A4 — PDF and Word then paginated differently. Every portrait
report now declares ``size: A4 portrait`` itself.
"""
import os
import re
import tempfile
from datetime import datetime

import pytest

import report_theme as rt

META = {'project_name': 'Synthetic', 'data_date': '11-Dec-2025', 'report_date': '30-Sep-2026',
        'source_file': 'synthetic.xml'}


def _evm_result(n_cats=3):
    cats = {f'Category {i}': {'weight': 1.0 / n_cats, 'planned_pct': 0.5, 'actual_pct': 0.4}
            for i in range(n_cats)}
    return {'pv': 1e6, 'ev': 9e5, 'ac': 9e5, 'spi': 0.9, 'cpi': 1.0, 'delay_days': 5,
            'overall_planned_pct': 0.5, 'overall_actual_pct': 0.4,
            'data_date': datetime(2025, 12, 11), 'categories': cats}


def _renders():
    from p6_audit.float_report import render_float_report
    from p6_audit.report import render_module_report, render_summary_report
    from p6_calendar.report import render_calendar_report
    from p6_evm.evm_report import render_evm_report
    return {
        'evm': render_evm_report(_evm_result(), META),
        'calendar': render_calendar_report({}, META),
        'health summary': render_summary_report({'score': 90, 'sub_features': []}, META),
        'health module': render_module_report({'module': 'dangling', 'name': 'Dangling',
                                               'findings': []}, META),
        'float': render_float_report({'module': 'float', 'name': 'Float Analysis'}, META),
    }


# ── ALL-PDF-SIZE ────────────────────────────────────────────────────────────────
def test_every_one_document_report_declares_a4_portrait_itself():
    for name, html in _renders().items():
        sizes = re.findall(r'@page\b[^{]*\{[^}]*\bsize\s*:\s*([^;}]+)', html)
        assert sizes and all(s.strip() == 'A4 portrait' for s in sizes), (name, sizes)
        # the export layer never adds a second (conflicting) size rule
        assert 'rpt-page-size' not in rt.with_pagination(html), name


def test_the_reports_own_pdf_route_prints_on_a4_not_letter():
    """The EVM / Calendar / Health routes print the renderer HTML as-is (no export layer):
    Chrome's default paper is US Letter unless the report declares its size."""
    try:
        import pymupdf
    except ImportError:
        pytest.skip('PyMuPDF not installed')
    from p6_export.pdf import chrome_candidates, run_chrome
    found = chrome_candidates(None)
    if not found:
        pytest.skip('no Chromium installed')
    html = _renders()['evm']
    with tempfile.TemporaryDirectory() as folder:
        src, out = os.path.join(folder, 'evm.html'), os.path.join(folder, 'evm.pdf')
        with open(src, 'w', encoding='utf-8') as fh:
            fh.write(html)
        run_chrome(found[0], [f'--print-to-pdf={out}', '--no-pdf-header-footer',
                              'file:///' + src.replace(os.sep, '/')], timeout=120)
        with pymupdf.open(out) as d:
            w, h = d[0].rect.width, d[0].rect.height
    assert abs(w - 595.3) < 2 and abs(h - 841.9) < 2, (w, h)          # A4, not 612 x 792
