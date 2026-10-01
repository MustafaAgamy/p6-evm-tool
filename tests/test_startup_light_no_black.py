"""Owner comment 40 — opening Controlyx shows no black window.

The one-file exe showed a dark picture that printed the name of every file it unpacked
('numpy.libs\\libscipy_openblas64_...dll'), then a dark window, then a dark loading screen.
Now every start-up surface is light and the first picture carries no file names: the picture
shown while the exe unpacks, the window's own background, the page's first paint, the
animated loading screen (which counts to 100 %) and the two retry pages.
"""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DARK = ('#06090f', '#0a1330', '#14284f', '#111a2e')


def _read(*parts):
    return open(os.path.join(ROOT, *parts), encoding='utf-8').read()


def _lum(rgb):
    r, g, b = rgb[:3]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_unpack_picture_has_no_text_line_so_no_file_names():
    spec = _read('controlyx.spec')
    kw = spec[spec.index('_splash_kw = dict('):].split('\n', 1)[0]
    for arg in ('text_pos', 'text_default', 'text_size', 'text_color'):
        assert arg not in kw, arg                 # a text position makes the bootloader print file names
    assert "Splash(str(Path(SPECPATH) / 'packaging' / 'splash.png')" in spec


def test_unpack_picture_is_light():
    Image = pytest.importorskip('PIL.Image')
    im = Image.open(os.path.join(ROOT, 'packaging', 'splash.png')).convert('RGB')
    assert im.size == (480, 270)
    for xy in ((3, 3), (476, 3), (3, 266), (476, 266), (240, 20), (60, 135)):
        assert _lum(im.getpixel(xy)) > 200, xy    # light corners, edges and field
    src = _read('packaging', 'splash.html')
    assert 'Loading' in src and not any(c in src for c in DARK)


def test_window_opens_on_the_light_startup_colour():
    app = _read('app.py')
    m = re.search(r"background_color='(#[0-9a-fA-F]{6})'", app)
    assert m and m.group(1).lower() == '#eef3fb'


@pytest.mark.parametrize('parts', [('ui', 'index.html'), ('ui', 'modules', 'boot.js'), ('ui', 'startup_guard.js')])
def test_no_dark_startup_colour_left_in_the_page(parts):
    src = _read(*parts)
    for c in DARK:
        assert c not in src, (parts, c)


def test_loading_screen_is_light_and_still_counts_to_100():
    boot = _read('ui', 'modules', 'boot.js')
    assert '#ffffff 0%, #eef3fb 45%, #dde6f5 100%' in boot
    assert 'class="barf"' in boot or '.barf' in boot          # the progress bar is still there
    idx = _read('ui', 'index.html')
    assert '#ffffff 0%,#eef3fb 45%,#dde6f5 100%' in idx and 'id="cx-cover-stage"' in idx


def test_server_waiting_page_is_light():
    srv = _read('server.py')
    assert "background:#eef3fb;color:#41506a;" in srv and 'background:#06090f' not in srv
