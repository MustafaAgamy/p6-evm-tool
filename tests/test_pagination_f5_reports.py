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


# ── HEALTH-PDF-1 ────────────────────────────────────────────────────────────────
def _chrome_or_skip():
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        pytest.skip('PyMuPDF not installed')
    from p6_export.pdf import chrome_candidates
    found = chrome_candidates(None)
    if not found:
        pytest.skip('no Chromium installed')
    return found[0]


def _pdf_pages(html, chrome, folder, name):
    """Print through the one-document export path; page texts in order."""
    import pymupdf
    from p6_export.pdf import html_to_pdf
    out = html_to_pdf(html, os.path.join(folder, name + '.pdf'), chrome=chrome)
    with pymupdf.open(out) as d:
        return [p.get_text() for p in d]


def _health(n_subs, n_areas=30, n_fix=5):
    subs = [{'name': f'Check {i}', 'status': 'Pass', 'score': 95.0, 'weight': 10, 'points': 9.5}
            for i in range(n_subs)]
    areas = [{'name': f'Discipline {i:02d}', 'pct': max(0.1, 30 - i)} for i in range(n_areas)]
    fixes = [{'name': f'Fix {i + 1}', 'score': 90, 'weight': 15, 'lift': 1.0,
              'recommendation': 'Recover the driving path so the completion milestone carries '
                                f'zero or positive total float REC{i + 1}END'}
             for i in range(n_fix)]
    return {'score': 96.6, 'grade': 'A', 'sub_features': subs, 'weight_covered': 85,
            'problem_areas': {'areas': areas}, 'fix_first': fixes, 'statement': 'Overall fine.'}


def _grid_violations(pages, n_fix=5):
    v = []
    low = [t.lower() for t in pages]
    wp = next((i for i, t in enumerate(low) if 'where the problems are' in t), None)
    fp = next((i for i, t in enumerate(low) if 'fix these first' in t), None)
    if wp is None or fp is None:
        return ['a heading is missing']
    if wp != fp:
        v.append(f'headings on different pages ({wp + 1} / {fp + 1})')
    for k in range(1, n_fix + 1):
        on = [i for i, t in enumerate(pages) if re.search(rf'\bFix {k}\b', t) or f'REC{k}END' in t]
        if set(on) != {fp}:
            v.append(f'fix {k} not with its heading on page {fp + 1} (pages {[i + 1 for i in on]})')
    counts = [len(re.findall(r'Discipline \d\d', t)) for t in pages]
    if counts[wp] < 3:
        v.append(f'only {counts[wp]} bar(s) under the heading on page {wp + 1}')
    v += [f'{c} bar(s) stranded on page {i + 1}' for i, c in enumerate(counts) if 0 < c < 3]
    return v


def test_health_problems_and_fixes_start_together_and_never_split_the_fix_list():
    """GBT: the two-column block began at the bottom of page 1 with 3 discipline bars and
    ONE of the five fix items; the rest continued on page 2 (at other lengths the last fix
    row itself was cut: its name on one page, its recommendation on the next)."""
    from p6_audit.report import render_summary_report
    chrome = _chrome_or_skip()
    bad = {}
    with tempfile.TemporaryDirectory() as folder:
        for n in (3, 5, 7, 9, 11):            # moves the block's start down page 1
            html = render_summary_report(_health(n), META)
            v = _grid_violations(_pdf_pages(html, chrome, folder, f'health_{n}'))
            if v:
                bad[n] = v
    assert bad == {}, bad


def test_health_grid_columns_keep_their_start_rows_and_last_three_bars():
    from p6_audit.report import render_summary_report
    html = render_summary_report(_health(9), META)
    grid = html[html.index('<div class="grid2">'):html.index('<h2 class="sec">Conclusion')]
    assert grid.count('<div class="rpt-keep">') == 3            # bars start, bars end, fixes
    assert re.search(r'<div class="rpt-keep"><h2 class="sec">Where the problems are.*?'
                     r'(<div class="wb">.*?){3}', grid)
    assert re.search(r'<div class="rpt-keep"><h2 class="sec">Fix these first', grid)
    # unticked parts stay absent; ticked-but-empty says so
    only = render_summary_report(_health(9), META, sections=['fixes'])
    assert '<h2 class="sec">Where the problems are' not in only
    assert '<h2 class="sec">Fix these first' in only
    empty = render_summary_report(dict(_health(9), fix_first=[]), META, sections=['fixes'])
    assert 'nothing to fix first' in empty
