"""[pagination:STUDIO] Reporting Studio Document PDF + Word with a RICH multi-feature
selection (GBT: overview, EVM, every Schedule Health module, Calendar Audit, Update
Analysis, Baseline Revision Comparison, Baseline Narrative - ~60 results).

Findings fixed in this step (each test fails without its fix):

* STUDIO-RICH-1 - a big selection could not be exported: every Chrome print of the Studio
  had a flat 180 s allowance (90 s for a Word section picture); the GBT document with the
  Baseline Revision 'Key Findings' is 6.4 MB / ~1 800 pages and prints in ~210 s a pass,
  so the PDF export stopped with 'did not finish within 180 s' while Chrome was still
  printing normally. The allowance now grows a minute per MB of markup.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ── STUDIO-RICH-1: the print allowance grows with the document ─────────────────────────
def test_print_timeout_grows_with_the_document():
    from p6_special.pdf_render import print_timeout
    assert print_timeout('', 180) == 180                    # a small document: the base
    assert print_timeout('x' * 1000, 180) == 180
    big = 'x' * 6_400_000                                   # the GBT rich selection
    assert print_timeout(big, 180) >= 180 + 6 * 60          # > the ~210 s a pass it needs
    assert print_timeout(big, 90) >= 90 + 6 * 60            # Word section pictures too
    assert print_timeout(None, 180) == 180


def test_chrome_pdf_passes_the_scaled_allowance(monkeypatch, tmp_path):
    import p6_export.pdf as P
    from p6_special import pdf_render
    seen = {}

    def fake_run_chrome(chrome, args, timeout=180):
        seen['timeout'] = timeout
    monkeypatch.setattr(P, 'run_chrome', fake_run_chrome)
    html = '<html><body>' + ('<div>row</div>' * 400_000) + '</body></html>'   # ~5.6 MB
    pdf_render.chrome_pdf(html, 'chrome.exe', str(tmp_path / 'out.pdf'))
    assert seen['timeout'] > 180 + 5 * 60, seen     # was a flat 180 s


def test_word_section_picture_gets_the_scaled_allowance(monkeypatch):
    import p6_export.pdf as P
    from p6_special import docx_report
    seen = {}

    def fake_run_chrome(chrome, args, timeout=180):
        seen['timeout'] = timeout
        raise RuntimeError('stop here')              # the slicer falls back quietly
    monkeypatch.setattr(P, 'run_chrome', fake_run_chrome)
    frag = '<div class="lanes">' + ('<div class="lane">#1 link</div>' * 120_000) + '</div>'
    assert docx_report._slice_section(frag, '', 'light', 'chrome.exe', 700.0, 600.0) is None
    assert seen['timeout'] > 90 + 3 * 60, seen      # was a flat 90 s
