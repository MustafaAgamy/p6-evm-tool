"""Dashboard-view PDF/preview.

The Studio's Dashboard board is rendered client-side (ui/modules/studio_dash.js
``boardHtml``) in the approved ``.pd-*`` style. Rather than re-implement every
tile renderer in Python, the client posts that already-rendered board HTML and we
wrap it with the app's own stylesheet at the chosen appearance mode — so the PDF
is pixel-identical to the on-screen dashboard across all six looks (screen == PDF),
and any future tile automatically prints correctly with no change here.
"""
import os

from utils import resource_path


def _esc(s):
    return (str('' if s is None else s)
            .replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;'))


def _app_css():
    """The app stylesheet (defines the six appearance-mode token palettes AND the
    .pd-* dashboard rules the board HTML uses)."""
    try:
        with open(resource_path('ui/style.css'), encoding='utf-8') as f:
            return f.read()
    except OSError:
        return ''


def build_dashboard_html(board_html, mode='light', title='Dashboard'):
    """Wrap the client's board HTML into a standalone, themed print document.

    ``mode`` is one of the six appearance keys (light/dark/midnight/sepia/
    contrast/blueprint); it is stamped as ``data-appearance`` on the root so the
    app's own token palette themes the page exactly as on screen.
    """
    mode = mode or 'light'
    css = _app_css()
    return (
        '<!doctype html><html data-appearance="' + _esc(mode) + '"><head><meta charset="utf-8">'
        '<title>' + _esc(title) + '</title>'
        '<style>' + css + '</style>'
        # print overrides: the app pins html/body overflow:hidden for the SPA shell;
        # a printed report must flow, and the on-screen toolbar is not part of it.
        '<style>html,body{overflow:visible !important;height:auto !important}'
        'body{background:var(--bg);margin:0;padding:16px}'
        '.studio-dash-wrap .pd-toolbar{display:none}'
        '.pd-sheet{box-shadow:none}</style>'
        '</head><body>' + (board_html or '') + '</body></html>'
    )
