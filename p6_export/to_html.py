"""The final report HTML → a self-contained ``.html`` file (email it, open it anywhere).

The preview already holds the exact document (feature render + appearance mode + the
picker's pruning), so this only makes it SAFE TO SHIP on its own:

* ``<meta charset="utf-8">`` first in ``<head>`` (else — · ≥ mojibake when opened from disk);
* a ``<title>``;
* no script, no external stylesheet / font / image reference (everything the report
  needs is inline already: its ``<style>`` blocks, the theme tokens, inline SVG, data URIs);
* the picker-only hooks (``data-part`` …) are harmless and kept, so the file can be
  re-opened in the tool later.
"""
import html as _html
import re

_SCRIPT_RE = re.compile(r'<script\b[^>]*>.*?</script\s*>', re.I | re.S)
_LINK_RE = re.compile(r'<link\b[^>]*>', re.I)
_CHARSET_RE = re.compile(r'<meta\b[^>]*charset[^>]*>', re.I)
_BASE_RE = re.compile(r'<base\b[^>]*>', re.I)
_IMPORT_RE = re.compile(r'@import\s+(?:url\()?\s*["\']?(?:https?:)?//[^;]*;', re.I)
_EXT_URL_RE = re.compile(r'url\(\s*["\']?(?:https?:)?//[^)]*\)', re.I)
_EXT_SRC_RE = re.compile(r'\s(?:src|srcset)\s*=\s*["\'](?:https?:)?//[^"\']*["\']', re.I)
_ON_ATTR_RE = re.compile(r'\son[a-z]+\s*=\s*("[^"]*"|\'[^\']*\')', re.I)


def standalone_html(html, title=None):
    """Return a self-contained, UTF-8 declared copy of ``html``."""
    doc = html or ''
    if isinstance(doc, bytes):
        doc = doc.decode('utf-8', 'replace')
    doc = doc.lstrip('﻿')
    doc = _SCRIPT_RE.sub('', doc)
    doc = _LINK_RE.sub('', doc)
    doc = _BASE_RE.sub('', doc)
    doc = _IMPORT_RE.sub('', doc)
    doc = _EXT_URL_RE.sub('none', doc)
    doc = _EXT_SRC_RE.sub('', doc)
    doc = _ON_ATTR_RE.sub('', doc)
    doc = _CHARSET_RE.sub('', doc)
    if not re.search(r'<html\b', doc, re.I):
        doc = f'<html><head></head><body>{doc}</body></html>'
    if not re.search(r'<head\b', doc, re.I):
        doc = re.sub(r'(<html\b[^>]*>)', r'\1<head></head>', doc, count=1, flags=re.I)
    head_add = '<meta charset="utf-8">'
    if title and not re.search(r'<title\b', doc, re.I):
        head_add += f'<title>{_html.escape(title)}</title>'
    doc = re.sub(r'(<head\b[^>]*>)', lambda m: m.group(1) + head_add, doc, count=1, flags=re.I)
    if not doc.lstrip().lower().startswith('<!doctype'):
        doc = '<!DOCTYPE html>\n' + doc
    return doc


def write_html(html, path, title=None):
    out = standalone_html(html, title)
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(out)
    return path
