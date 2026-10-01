"""Reporting Studio PDF page composition (owner point 14 — finding STUDIO-PDF-1).

The Studio prints its whole body inside ONE table cell (the ``.sr-doc`` shell, so the
running header / footer repeat on every page). The print-time composer treated every
element inside a table cell as table data, so in the Studio it paired no heading with its
content and never let a mid-size table continue: a reused Narrative "Major Milestones"
section left its heading + lead-in alone at a page bottom with the table on the next page,
and a "Key Dates" table was pushed whole, leaving the page above it a third blank. These
tests print a synthetic Studio document with Chrome and prove both are gone.
"""
import os
import re
import tempfile

import pytest

from p6_narrative.html import render_narrative_html
from p6_special import reuse, render_html
from p6_special.providers import narrative as NP

_P = ('<p>This paragraph stands for a long passage of an earlier Studio section: it describes '
      'the scope, the methodology and the phasing in enough words to be a real body paragraph '
      'of the composed report, so the page fills realistically.</p>')


def _studio_html(kd=24, ms=60, fill=9):
    def rows(label, n):
        return [['%s number %02d of the synthetic baseline' % (label, i), '%02d-Jan-2027' % (i % 28 + 1)]
                for i in range(1, n + 1)]
    doc = {'meta': {'project_name': 'Synthetic', 'data_date': '11 Dec 2025'}, 'sections': [
        {'number': 1, 'title': 'Major Milestones', 'kind': 'ms_table',
         'payload': {'columns': ['Milestone', 'Date'], 'rows': rows('Milestone', ms)}},
        {'number': 2, 'title': 'Key Dates', 'kind': 'ms_table',
         'payload': {'columns': ['Milestone', 'Date'], 'rows': rows('Keydate', kd)}},
    ]}
    full = render_narrative_html(doc)
    css = reuse.scope_css(reuse.extract_styles(full), '.' + NP._WRAP)

    def narrative(n):          # exactly how the Studio's narrative provider reuses a section
        frag = NP._strip_leading_h1(NP._extract_section(full, n))
        return {'kind': 'html', 'feature': 'narrative', 'css': css,
                'html': '<div class="%s">%s</div>' % (NP._WRAP, frag)}

    def filler(n):
        return {'kind': 'html', 'feature': 'x', 'css': '', 'html': '<div>' + _P * n + '</div>'}

    def item(iid, title, payload):
        return {'id': iid, 'title': title, 'feature': iid.split(':')[0], 'feature_title': 'F',
                'ctype': 'section', 'payload': payload}
    rendered = [item('x:a', 'Executive read', filler(fill)),
                item('narrative:keydates', 'Key Dates', narrative(2)),
                item('x:b', 'Scope notes', filler(fill + 3)),
                item('narrative:milestones', 'Major Milestones', narrative(1))]
    return render_html.build_document('Synthetic Studio', {'project_name': 'Synthetic'},
                                      rendered, 'light')


def _pre_fix(html):
    """The same document with the composer's pre-fix model: everything inside a table
    cell counted as table data (no shell), no lead-in chaining."""
    for old, new in (("function inCell(e){", "function inCell(e){return !!(e.parentElement&&"
                      "e.parentElement.closest('td,th'));"),
                     ("function shell(t){", "function shell(t){return false;"),
                     ("if(led<2&&", "if(0&&")):
        assert html.count(old) == 1, old
        html = html.replace(old, new)
    return html


def _chrome():
    from p6_export.pdf import chrome_candidates
    found = chrome_candidates(None)
    if not found:
        pytest.skip('no Chromium installed')
    return found[0]


def _print(html, chrome, folder, name):
    from p6_export.pdf import run_chrome
    src = os.path.join(folder, name + '.html')
    with open(src, 'w', encoding='utf-8') as fh:
        fh.write(html)
    out = os.path.join(folder, name + '.pdf')
    run_chrome(chrome, [f'--print-to-pdf={out}', '--no-pdf-header-footer',
                        'file:///' + src.replace(os.sep, '/')], timeout=120)
    return out


def _pages(pdf):
    import pymupdf
    out = []
    with pymupdf.open(pdf) as d:
        for pg in d:
            t = pg.get_text()
            out.append({'text': ' '.join(t.split()),
                        'kd': len(re.findall(r'Keydate number', t)),
                        'ms': len(re.findall(r'Milestone number', t))})
    return out


def test_studio_shell_cell_is_a_page_container_for_the_composer():
    html = _studio_html(3, 3, 1)
    assert 'function inCell(e)' in html and 'shellReserve()' in html
    # the pre-fix emulation used by the Chrome proof below still applies cleanly
    assert _pre_fix(html) != html


def test_chrome_studio_milestone_sections_keep_heading_with_rows_and_continue():
    chrome = _chrome()
    html = _studio_html()
    with tempfile.TemporaryDirectory() as folder:
        after_pdf = _print(html, chrome, folder, 'after')
        before_pdf = _print(_pre_fix(html), chrome, folder, 'before')
        from p6_export import pagination_check as pc
        after_flags = pc.check_pdf(after_pdf)['flags']
        before_flags = pc.check_pdf(before_pdf)['flags']
        after, before = _pages(after_pdf), _pages(before_pdf)

    def start(pages, title):     # the section's own page (the contents page lists every title)
        return next(i for i, p in enumerate(pages) if i > 1 and title in p['text'])

    # BEFORE: the Major Milestones heading + lead-in end a page, the rows start on the next
    s = start(before, 'Major Milestones')
    assert before[s]['ms'] == 0, before[s]
    assert any(f['type'] in ('heading_separated_from_block', 'orphaned_heading') for f in before_flags), \
        before_flags
    # … and the 24-row Key Dates table was pushed whole to a page of its own
    assert len([p for p in before if p['kd']]) == 1

    # AFTER: every heading starts its table on the same page, each table page repeats the
    # header and holds >= 3 rows, and the page checker finds nothing
    for key, title in (('kd', 'Key Dates'), ('ms', 'Major Milestones')):
        s = start(after, title)
        assert after[s][key] >= 3, (title, after[s])
        span = [p for p in after if p[key]]
        for p in span:
            assert p[key] >= 3, (title, [q[key] for q in span])
            assert 'Milestone Date' in p['text'], (title, p['text'][:120])
    # the Key Dates table (over a third of a page) now continues rather than being pushed
    assert len([p for p in after if p['kd']]) == 2
    assert after_flags == [], after_flags
