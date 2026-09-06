"""Reuse each feature's OWN report sections in a Special Report.

Feature renderers emit a full ``<html>`` doc with class-based CSS in ``<head>``
and ``<section data-sec="KEY">…</section>`` fragments in the body. To compose the
real sections (exact detailed results + real charts) from several features into
one document we: slice the requested ``<section>`` fragment, and scope that
feature's CSS to a wrapper class so multiple features' stylesheets don't collide.
The composed document keeps the features' own markup, so it looks exactly like
each feature's report; the shared ``report_theme`` tokens theme it in any mode.
"""
import re

_STYLE_RE = re.compile(r'<style[^>]*>(.*?)</style>', re.S | re.I)


def extract_styles(html):
    """All CSS text from the document's <style> blocks, concatenated."""
    return '\n'.join(m.group(1) for m in _STYLE_RE.finditer(html or ''))


def extract_section(html, key):
    """Inner HTML of ``<section data-sec="KEY">…</section>`` (brace-safe on nested
    <section> tags), or '' if not found."""
    if not html:
        return ''
    start = re.search(r'<section[^>]*\bdata-sec="%s"[^>]*>' % re.escape(key), html, re.I)
    if not start:
        return ''
    i = start.end()
    depth = 1
    tag = re.compile(r'<(/?)section\b', re.I)
    pos = i
    while depth and pos < len(html):
        m = tag.search(html, pos)
        if not m:
            break
        depth += -1 if m.group(1) else 1
        pos = m.end()
        if depth == 0:
            return html[i:m.start()]
    return html[i:]


def _strip_comments(css):
    return re.sub(r'/\*.*?\*/', '', css or '', flags=re.S)


def _scope_selector(sel, scope):
    sel = sel.strip()
    if not sel:
        return sel
    # html/body/:root map to the wrapper itself; * and others get prefixed.
    if sel in ('html', 'body', ':root', 'html, body') or sel in ('html,body',):
        return scope
    if sel.startswith('@'):
        return sel
    return f'{scope} {sel}'


def scope_css(css, scope):
    """Prefix every rule's selectors with ``scope`` so this feature's CSS only
    affects its own wrapped sections. Drops @page (Special Report sets its own);
    keeps @media/@supports and scopes their inner rules; keeps @keyframes/@font-face."""
    css = _strip_comments(css)
    out = []
    i, n = 0, len(css)
    while i < n:
        brace = css.find('{', i)
        if brace == -1:
            break
        prelude = css[i:brace].strip()
        # find matching close brace for this block
        depth, j = 1, brace + 1
        while j < n and depth:
            if css[j] == '{':
                depth += 1
            elif css[j] == '}':
                depth -= 1
            j += 1
        body = css[brace + 1:j - 1]
        low = prelude.lower()
        if low.startswith('@page'):
            pass  # drop — the composed doc controls page size
        elif low.startswith('@media') or low.startswith('@supports'):
            out.append(f'{prelude} {{ {scope_css(body, scope)} }}')
        elif low.startswith('@keyframes') or low.startswith('@font-face') or low.startswith('@'):
            out.append(f'{prelude} {{ {body} }}')
        else:
            sels = ','.join(_scope_selector(s, scope) for s in prelude.split(','))
            out.append(f'{sels} {{ {body} }}')
        i = j
    return '\n'.join(out)
