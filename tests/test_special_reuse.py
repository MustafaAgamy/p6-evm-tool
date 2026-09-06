"""Tests for the feature-section reuse helpers (slice + CSS scope)."""
from p6_special.reuse import extract_section, extract_styles, scope_css


def test_extract_section_basic():
    html = ('<html><head><style>.a{color:red}</style></head><body>'
            '<section data-sec="x"><p>hi</p></section>'
            '<section data-sec="y">no</section></body></html>')
    assert extract_section(html, 'x').strip() == '<p>hi</p>'
    assert 'no' in extract_section(html, 'y')
    assert extract_section(html, 'z') == ''


def test_extract_section_nested():
    html = '<section data-sec="x">A<section>inner</section>B</section>'
    frag = extract_section(html, 'x')
    assert 'A' in frag and 'inner' in frag and 'B' in frag


def test_extract_styles():
    s = extract_styles('<style>.a{x:1}</style><style>.b{y:2}</style>')
    assert '.a' in s and '.b' in s


def test_scope_css_prefixes():
    s = scope_css('.note{color:red} h2{margin:0}', '.srf-up')
    assert '.srf-up .note' in s and '.srf-up h2' in s


def test_scope_css_body_maps_to_scope():
    s = scope_css('body{font-size:12px}', '.srf-up')
    assert '.srf-up {' in s and 'font-size:12px' in s


def test_scope_css_drops_page():
    s = scope_css('@page{margin:1mm} .a{x:1}', '.srf-up')
    assert '@page' not in s and '.srf-up .a' in s


def test_scope_css_media_scoped():
    s = scope_css('@media print{.a{x:1}}', '.srf-up')
    assert '@media print' in s and '.srf-up .a' in s


def test_strip_leading_header_nested_div():
    from p6_special.feature_reports import _strip_leading_header
    frag = ('<div class="rh"><div>title</div><div class="win">meta</div></div>'
            '<section>keep</section>')
    out = _strip_leading_header(frag).strip()
    assert out.startswith('<section>') and 'keep' in out and 'title' not in out


def test_strip_leading_header_absent():
    from p6_special.feature_reports import _strip_leading_header
    frag = '<section>x</section>'
    assert _strip_leading_header(frag) == frag
