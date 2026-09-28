"""A small, dependency-free CSS engine for the one-document exporters.

The report HTML that drives every export (PDF · Word · HTML · Excel) is styled with
class selectors and ``var(--rpt-*)`` theme tokens. Chrome resolves those for the PDF;
Word, Excel and PyMuPDF (SVG rasterising) cannot — they need CONCRETE colours, sizes
and weights. This module computes them the way a browser would, for the subset of CSS
the report renderers actually use:

* stylesheet parsing — rules, ``@media`` (print/all kept, screen-only dropped), ``@supports``,
  ``@page`` (size / margin captured), everything else skipped;
* selectors — type, ``*``, ``.class``, ``#id``, ``[attr]`` / ``[attr=v]`` (``~= |= ^= $= *=``),
  descendant / ``>`` / ``+`` / ``~`` combinators, ``:root :first-child :last-child
  :only-child :nth-child() :nth-last-child() :nth-of-type() :first-of-type :last-of-type
  :empty :not() :is() :where()``; state pseudo-classes (``:hover`` …) and pseudo-elements
  never match (nothing is interactive or generated in an export);
* cascade — specificity, source order, ``!important``, inline ``style=""``, SVG
  presentation attributes and HTML ``bgcolor`` / ``align`` at the lowest precedence;
* computed values — inheritance, custom properties + ``var()`` (with fallbacks),
  ``inherit`` / ``initial``, ``currentColor``, ``color-mix(in srgb, …)``, ``rgb()/rgba()``,
  hex, named colours, font-size units (px pt em rem % mm cm in keywords).

Pure functions over an ``lxml`` element tree; no browser, no network.
"""
import re

# ── colours ────────────────────────────────────────────────────────────────────
NAMED = {
    'black': (0, 0, 0), 'white': (255, 255, 255), 'red': (255, 0, 0), 'green': (0, 128, 0),
    'blue': (0, 0, 255), 'yellow': (255, 255, 0), 'orange': (255, 165, 0), 'purple': (128, 0, 128),
    'gray': (128, 128, 128), 'grey': (128, 128, 128), 'silver': (192, 192, 192),
    'maroon': (128, 0, 0), 'olive': (128, 128, 0), 'lime': (0, 255, 0), 'aqua': (0, 255, 255),
    'cyan': (0, 255, 255), 'teal': (0, 128, 128), 'navy': (0, 0, 128), 'fuchsia': (255, 0, 255),
    'magenta': (255, 0, 255), 'darkgray': (169, 169, 169), 'darkgrey': (169, 169, 169),
    'lightgray': (211, 211, 211), 'lightgrey': (211, 211, 211), 'dimgray': (105, 105, 105),
    'dimgrey': (105, 105, 105), 'gainsboro': (220, 220, 220), 'whitesmoke': (245, 245, 245),
    'darkred': (139, 0, 0), 'darkgreen': (0, 100, 0), 'darkblue': (0, 0, 139),
    'darkorange': (255, 140, 0), 'gold': (255, 215, 0), 'goldenrod': (218, 165, 32),
    'crimson': (220, 20, 60), 'firebrick': (178, 34, 34), 'tomato': (255, 99, 71),
    'coral': (255, 127, 80), 'salmon': (250, 128, 114), 'pink': (255, 192, 203),
    'steelblue': (70, 130, 180), 'royalblue': (65, 105, 225), 'dodgerblue': (30, 144, 255),
    'skyblue': (135, 206, 235), 'lightblue': (173, 216, 230), 'slategray': (112, 128, 144),
    'slategrey': (112, 128, 144), 'lightgreen': (144, 238, 144), 'seagreen': (46, 139, 87),
    'forestgreen': (34, 139, 34), 'limegreen': (50, 205, 50), 'indigo': (75, 0, 130),
    'violet': (238, 130, 238), 'brown': (165, 42, 42), 'tan': (210, 180, 140),
    'beige': (245, 245, 220), 'ivory': (255, 255, 240), 'khaki': (240, 230, 140),
    'lavender': (230, 230, 250), 'linen': (250, 240, 230), 'mintcream': (245, 255, 250),
    'aliceblue': (240, 248, 255), 'honeydew': (240, 255, 240), 'ghostwhite': (248, 248, 255),
}

_HEX_RE = re.compile(r'#([0-9a-fA-F]{3,8})\b')
_FUNC_COLOR_RE = re.compile(r'(rgba?|hsla?)\(([^()]*)\)', re.I)


def _split_top(s, sep=','):
    """Split ``s`` on ``sep`` at parenthesis depth 0 (and outside quotes)."""
    out, depth, cur, quote = [], 0, [], None
    for ch in s:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in '"\'':
            quote = ch
        elif ch == '(':
            depth += 1
        elif ch == ')':
            depth = max(0, depth - 1)
        if ch == sep and depth == 0:
            out.append(''.join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append(''.join(cur))
    return out


def _hsl_to_rgb(h, s, l):
    h = (h % 360) / 360.0
    def f(n):
        k = (n + h * 12) % 12
        a = s * min(l, 1 - l)
        return l - a * max(-1, min(k - 3, 9 - k, 1))
    return (round(f(0) * 255), round(f(8) * 255), round(f(4) * 255))


def parse_color(value, current=None):
    """Parse one CSS colour → ``(r, g, b, a)`` (0-255 ints, alpha 0-1) or ``None``.

    ``current`` is the element's ``color`` (for ``currentColor``)."""
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    low = v.lower()
    if low == 'transparent':
        return (0, 0, 0, 0.0)
    if low == 'currentcolor':
        return current
    if low in NAMED:
        r, g, b = NAMED[low]
        return (r, g, b, 1.0)
    if low.startswith('#'):
        h = low[1:]
        try:
            if len(h) in (3, 4):
                r, g, b = (int(c * 2, 16) for c in h[:3])
                a = int(h[3] * 2, 16) / 255 if len(h) == 4 else 1.0
                return (r, g, b, a)
            if len(h) in (6, 8):
                r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
                a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
                return (r, g, b, a)
        except ValueError:
            return None
        return None
    m = re.match(r'(rgba?|hsla?)\((.*)\)$', low, re.S)
    if m:
        fn, args = m.group(1), m.group(2)
        parts = [p for p in re.split(r'[\s,/]+', args.strip()) if p]
        try:
            if fn.startswith('rgb'):
                vals = []
                for p in parts[:3]:
                    vals.append(round(float(p[:-1]) * 2.55) if p.endswith('%') else round(float(p)))
                a = 1.0
                if len(parts) > 3:
                    a = float(parts[3][:-1]) / 100 if parts[3].endswith('%') else float(parts[3])
                return (max(0, min(255, vals[0])), max(0, min(255, vals[1])),
                        max(0, min(255, vals[2])), max(0.0, min(1.0, a)))
            hh = float(parts[0].replace('deg', ''))
            ss = float(parts[1].rstrip('%')) / 100
            ll = float(parts[2].rstrip('%')) / 100
            a = 1.0
            if len(parts) > 3:
                a = float(parts[3][:-1]) / 100 if parts[3].endswith('%') else float(parts[3])
            r, g, b = _hsl_to_rgb(hh, ss, ll)
            return (r, g, b, a)
        except (ValueError, IndexError):
            return None
    m = re.match(r'color-mix\((.*)\)$', low, re.S)
    if m:
        return _color_mix(m.group(1), current)
    return None


def _color_mix(args, current):
    """``color-mix(in srgb, A p%, B q%)`` with premultiplied-alpha interpolation."""
    parts = [p.strip() for p in _split_top(args)]
    if len(parts) < 3:
        return None
    items = []
    for p in parts[1:3]:
        pm = re.search(r'\s(\d+(?:\.\d+)?)%\s*$', ' ' + p)
        pct = float(pm.group(1)) / 100 if pm else None
        col = p[:pm.start() - 1].strip() if pm else p
        items.append((parse_color(col, current), pct))
    (c1, p1), (c2, p2) = items
    if c1 is None or c2 is None:
        return None
    if p1 is None and p2 is None:
        p1, p2 = 0.5, 0.5
    elif p1 is None:
        p1 = 1 - p2
    elif p2 is None:
        p2 = 1 - p1
    tot = p1 + p2
    if tot <= 0:
        return None
    alpha_mult = min(1.0, tot)
    p1, p2 = p1 / tot, p2 / tot
    a = c1[3] * p1 + c2[3] * p2
    if a <= 0:
        return (0, 0, 0, 0.0)
    rgb = tuple(round((c1[i] * c1[3] * p1 + c2[i] * c2[3] * p2) / a) for i in range(3))
    return rgb + (a * alpha_mult,)


def find_color(value, current=None):
    """First colour token inside a shorthand value (``background: #fff url(x)``,
    ``border-left: 3px solid var(--x)`` after var resolution, a gradient's first stop)."""
    if value is None:
        return None
    v = str(value).strip()
    direct = parse_color(v, current)
    if direct is not None:
        return direct
    for tok in _split_top(v, ' '):
        tok = tok.strip().rstrip(',')
        if not tok:
            continue
        low = tok.lower()
        if low.startswith(('linear-gradient', 'radial-gradient', 'conic-gradient',
                           'repeating-linear-gradient')):
            inner = tok[tok.index('(') + 1:-1]
            for arg in _split_top(inner):
                c = find_color(arg.strip(), current)
                if c is not None:
                    return c
            continue
        c = parse_color(tok, current)
        if c is not None:
            return c
    return None


def blend(color, over=(255, 255, 255)):
    """Flatten an rgba colour over an opaque background → ``(r, g, b)``."""
    if color is None:
        return None
    r, g, b, a = color
    if a >= 0.999:
        return (r, g, b)
    return tuple(round(c * a + o * (1 - a)) for c, o in zip((r, g, b), over[:3]))


def to_hex(color, over=(255, 255, 255)):
    """rgba/rgb tuple → ``'RRGGBB'`` (alpha flattened over ``over``); None stays None."""
    if color is None:
        return None
    rgb = blend(color if len(color) == 4 else tuple(color) + (1.0,), over)
    return '%02X%02X%02X' % rgb


# ── length helpers ─────────────────────────────────────────────────────────────
_FONT_KEYWORDS = {'xx-small': 9, 'x-small': 10, 'small': 13, 'medium': 16, 'large': 18,
                  'x-large': 24, 'xx-large': 32, 'xxx-large': 48}


def length_px(value, font_px=16.0, root_px=16.0, percent_of=None):
    """A CSS length → px (float), or None when it is not a plain length."""
    if value is None:
        return None
    v = str(value).strip().lower()
    if not v:
        return None
    m = re.match(r'^(-?\d*\.?\d+)(px|pt|pc|em|rem|%|mm|cm|in|q|ex|ch|vw|vh)?$', v)
    if not m:
        return None
    n = float(m.group(1))
    unit = m.group(2) or 'px'
    if unit == 'px':
        return n
    if unit == 'pt':
        return n * 96 / 72
    if unit == 'pc':
        return n * 16
    if unit == 'em':
        return n * font_px
    if unit == 'rem':
        return n * root_px
    if unit == '%':
        return None if percent_of is None else n * percent_of / 100
    if unit == 'mm':
        return n * 96 / 25.4
    if unit == 'cm':
        return n * 96 / 2.54
    if unit == 'in':
        return n * 96
    if unit == 'q':
        return n * 96 / 101.6
    if unit in ('ex', 'ch'):
        return n * font_px * 0.5
    return None


def length_mm(value, default=None):
    px = length_px(value)
    return default if px is None else px * 25.4 / 96


# ── stylesheet parsing ─────────────────────────────────────────────────────────
_COMMENT_RE = re.compile(r'/\*.*?\*/', re.S)


def parse_declarations(text):
    """``'a: 1; b: 2 !important'`` → ``[(prop, value, important)]`` in source order."""
    out = []
    for chunk in _split_top(text or '', ';'):
        if ':' not in chunk:
            continue
        prop, _, val = chunk.partition(':')
        prop = prop.strip().lower() if not prop.strip().startswith('--') else prop.strip()
        val = val.strip()
        if not prop or not val:
            continue
        important = False
        m = re.search(r'!\s*important\s*$', val, re.I)
        if m:
            important = True
            val = val[:m.start()].strip()
        out.append((prop, val, important))
    return out


def _find_block_end(text, start):
    """Index of the ``}`` closing the block whose ``{`` is at ``start``."""
    depth, i, n, quote = 0, start, len(text), None
    while i < n:
        ch = text[i]
        if quote:
            if ch == '\\':
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in '"\'':
            quote = ch
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def _media_applies(query, page_width_px):
    q = query.lower().strip()
    if not q or q == 'all':
        return True
    for alt in _split_top(q):
        alt = alt.strip()
        if alt.startswith('not ') or 'prefers-' in alt or 'hover' in alt or 'pointer' in alt:
            continue
        if 'screen' in alt and 'print' not in alt:
            continue
        ok = True
        for m in re.finditer(r'\((min|max)-width\s*:\s*([^)]+)\)', alt):
            px = length_px(m.group(2).strip())
            if px is None:
                continue
            if m.group(1) == 'min' and page_width_px < px:
                ok = False
            if m.group(1) == 'max' and page_width_px > px:
                ok = False
        if re.search(r'\((min|max)-(height|resolution|aspect)', alt):
            ok = False
        if ok:
            return True
    return False


class Rule:
    __slots__ = ('selector', 'decls', 'order')

    def __init__(self, selector, decls, order):
        self.selector = selector
        self.decls = decls
        self.order = order


class StyleSheet:
    """All the ``<style>`` text of a document, parsed + indexed for matching."""

    def __init__(self, css_texts=(), page_width_px=720):
        self.rules = []
        self.page = {}                      # merged @page declarations {prop: value}
        self._by_id, self._by_class, self._by_tag, self._universal = {}, {}, {}, []
        self._order = 0
        self.page_width_px = page_width_px
        for t in css_texts:
            self.add(t)

    def add(self, css_text):
        self._parse(_COMMENT_RE.sub('', css_text or ''))

    def _parse(self, text):
        i, n = 0, len(text)
        while i < n:
            brace = text.find('{', i)
            semi = text.find(';', i)
            if brace == -1:
                break
            if semi != -1 and semi < brace and text[i:semi].strip().startswith('@'):
                i = semi + 1                   # @import / @charset / @namespace
                continue
            prelude = text[i:brace].strip()
            end = _find_block_end(text, brace)
            inner = text[brace + 1:end]
            i = end + 1
            if not prelude:
                continue
            if prelude.startswith('@'):
                low = prelude.lower()
                if low.startswith('@media'):
                    if _media_applies(prelude[6:], self.page_width_px):
                        self._parse(inner)
                elif low.startswith('@supports') or low.startswith('@layer') or low.startswith('@container'):
                    self._parse(inner)
                elif low.startswith('@page'):
                    rest = prelude[5:].strip()
                    if not rest.startswith(':'):          # skip :first / :left / :right
                        for prop, val, _imp in parse_declarations(inner):
                            self.page[prop] = val
                continue                       # @font-face / @keyframes / … skipped
            decls = parse_declarations(inner)
            if not decls:
                continue
            for sel_text in _split_top(prelude):
                sel = parse_selector(sel_text.strip())
                if sel is None:
                    continue
                rule = Rule(sel, decls, self._order)
                self._order += 1
                self.rules.append(rule)
                self._index(rule)

    def _index(self, rule):
        key = rule.selector.key
        if key is None:
            self._universal.append(rule)
        elif key[0] == '#':
            self._by_id.setdefault(key[1:], []).append(rule)
        elif key[0] == '.':
            self._by_class.setdefault(key[1:], []).append(rule)
        else:
            self._by_tag.setdefault(key, []).append(rule)

    def prune_to(self, doc):
        """Drop every rule that can never match ``doc`` because a compound of its selector needs
        a class or id no element of the document carries. printView documents inline the whole
        app stylesheet (~300 KB, ~1,800 class buckets); this cuts it to the rules the report can
        actually use before any matching. Returns the number of rules dropped."""
        classes, ids = set(), set()
        for el in doc.iter():
            if is_element(el):
                c = el.get('class')
                if c:
                    classes.update(c.split())
                i = el.get('id')
                if i:
                    ids.add(i)
        keep = [r for r in self.rules if _can_match(r.selector, classes, ids)]
        dropped = len(self.rules) - len(keep)
        if dropped:
            self.rules = keep
            self._by_id, self._by_class, self._by_tag, self._universal = {}, {}, {}, []
            for r in keep:
                self._index(r)
        return dropped

    def candidates(self, el):
        out = list(self._universal)
        out += self._by_tag.get(tag_of(el), ())
        eid = el.get('id')
        if eid:
            out += self._by_id.get(eid, ())
        for c in classes_of(el):
            out += self._by_class.get(c, ())
        return out

    def matching(self, el):
        """Rules matching ``el``, sorted by (specificity, source order)."""
        hits = [r for r in self.candidates(el) if r.selector.matches(el)]
        hits.sort(key=lambda r: (r.selector.specificity, r.order))
        return hits


# ── selectors ──────────────────────────────────────────────────────────────────
def tag_of(el):
    t = el.tag
    if not isinstance(t, str):
        return ''
    if '}' in t:
        t = t.split('}', 1)[1]
    return t.lower()


def classes_of(el):
    c = el.get('class')
    return c.split() if c else []


def is_element(node):
    return node is not None and isinstance(node.tag, str)


def _can_match(sel, classes, ids):
    """False when some compound of ``sel`` needs a class / id absent from the document
    (conservative: ``:not``/``:is`` arguments and attribute selectors are never used to drop)."""
    for _comb, comp in sel.parts:
        if comp.never:
            return False
        if comp.classes and not all(c in classes for c in comp.classes):
            return False
        if comp.ids and not any(i in ids for i in comp.ids):
            return False
    return True


# Element-only child list + each child's index, built ONCE per parent and shared by every
# structural pseudo-class check (:nth-child, :first/:last-child, …-of-type) of every rule.
# Rebuilding the list per check made matching quadratic in a big table's row count (F4).
# An entry is checked against the parent's child count and the element's own slot, so a
# changed tree just rebuilds it. Resolver() and parse_report() clear it (no stale refs).
_SIB_CACHE = {}


def clear_sibling_cache():
    _SIB_CACHE.clear()


def _sib_entry(p, el):
    ent = _SIB_CACHE.get(p)
    if ent is not None and ent[0] == len(p):
        i = ent[2].get(el)
        if i is not None and ent[1][i] is el:
            return ent, i
    sibs = [c for c in p if is_element(c)]
    ent = (len(p), sibs, {c: k for k, c in enumerate(sibs)}, {})
    _SIB_CACHE[p] = ent
    return ent, ent[2][el]


def _sib_position(el, of_type=False):
    """``(1-based index, count)`` of ``el`` among its element siblings (of its tag)."""
    p = el.getparent()
    if p is None:
        return 1, 1
    (_n, sibs, _pos, typed), i = _sib_entry(p, el)
    if not of_type:
        return i + 1, len(sibs)
    t = tag_of(el)
    tent = typed.get(t)
    if tent is None:
        same = [s for s in sibs if tag_of(s) == t]
        tent = typed[t] = ({s: k for k, s in enumerate(same)}, len(same))
    return tent[0][el] + 1, tent[1]


class Compound:
    __slots__ = ('tag', 'ids', 'classes', 'attrs', 'pseudos', 'never')

    def __init__(self):
        self.tag = None
        self.ids = []
        self.classes = []
        self.attrs = []
        self.pseudos = []
        self.never = False

    def specificity(self):
        a = len(self.ids)
        b = len(self.classes) + len(self.attrs)
        c = 1 if self.tag and self.tag != '*' else 0
        for name, arg in self.pseudos:
            if name in ('not', 'is'):
                sub = [s.specificity for s in (arg or [])]
                if sub:
                    m = max(sub)
                    a, b, c = a + m[0], b + m[1], c + m[2]
            elif name == 'where':
                pass
            else:
                b += 1
        return (a, b, c)

    def matches(self, el):
        if self.never:
            return False
        if self.tag and self.tag != '*' and tag_of(el) != self.tag:
            return False
        if self.ids and el.get('id') not in self.ids:
            return False
        if self.classes:
            cls = set(classes_of(el))
            if not all(c in cls for c in self.classes):
                return False
        for name, op, val in self.attrs:
            av = el.get(name)
            if av is None:
                return False
            if op is None:
                continue
            if op == '=' and av != val:
                return False
            if op == '~=' and val not in av.split():
                return False
            if op == '|=' and not (av == val or av.startswith(val + '-')):
                return False
            if op == '^=' and not av.startswith(val):
                return False
            if op == '$=' and not av.endswith(val):
                return False
            if op == '*=' and val not in av:
                return False
        for name, arg in self.pseudos:
            if not _pseudo_matches(el, name, arg):
                return False
        return True


def _nth(arg):
    """Parse an ``an+b`` expression → (a, b)."""
    s = (arg or '').replace(' ', '').lower()
    if s == 'even':
        return 2, 0
    if s == 'odd':
        return 2, 1
    m = re.match(r'^([+-]?\d*)n([+-]\d+)?$', s)
    if m:
        a = m.group(1)
        a = 1 if a in ('', '+') else (-1 if a == '-' else int(a))
        b = int(m.group(2) or 0)
        return a, b
    try:
        return 0, int(s)
    except ValueError:
        return None


def _nth_ok(idx, ab):
    if ab is None:
        return False
    a, b = ab
    if a == 0:
        return idx == b
    n = (idx - b) / a
    return n >= 0 and n == int(n)


def _pseudo_matches(el, name, arg):
    if name == 'root':
        return el.getparent() is None
    if name == 'empty':
        return len([c for c in el if is_element(c)]) == 0 and not (el.text or '').strip()
    if name in ('first-child', 'last-child', 'only-child', 'nth-child', 'nth-last-child',
                'first-of-type', 'last-of-type', 'nth-of-type', 'only-of-type', 'nth-last-of-type'):
        idx, cnt = _sib_position(el, name.endswith('of-type'))
        if name in ('first-child', 'first-of-type'):
            return idx == 1
        if name in ('last-child', 'last-of-type'):
            return idx == cnt
        if name in ('only-child', 'only-of-type'):
            return cnt == 1
        if name in ('nth-child', 'nth-of-type'):
            return _nth_ok(idx, _nth(arg))
        return _nth_ok(cnt - idx + 1, _nth(arg))
    if name == 'not':
        return not any(s.matches(el) for s in (arg or []))
    if name in ('is', 'where', 'matches'):
        return any(s.matches(el) for s in (arg or []))
    return False                     # :hover / :focus / :checked … never in an export


_NEVER_PSEUDO = {'hover', 'focus', 'active', 'visited', 'link', 'focus-within', 'focus-visible',
                 'checked', 'disabled', 'enabled', 'placeholder-shown', 'target', 'indeterminate',
                 'invalid', 'valid', 'required', 'optional', 'read-only', 'read-write', 'default',
                 'fullscreen', 'modal', 'autofill', 'any-link', 'scope', 'defined', 'open'}
_IDENT = r'-?[_a-zA-Z -￿][-_a-zA-Z0-9 -￿]*'


class Selector:
    """A complex selector: compounds joined by combinators (matched right-to-left)."""
    __slots__ = ('parts', 'specificity', 'key')

    def __init__(self, parts):
        self.parts = parts                     # [(combinator_before, Compound)] left→right
        spec = [0, 0, 0]
        for _, comp in parts:
            s = comp.specificity()
            spec = [spec[0] + s[0], spec[1] + s[1], spec[2] + s[2]]
        self.specificity = tuple(spec)
        last = parts[-1][1]
        if last.ids:
            self.key = '#' + last.ids[0]
        elif last.classes:
            self.key = '.' + last.classes[0]
        elif last.tag and last.tag != '*':
            self.key = last.tag
        else:
            self.key = None

    def matches(self, el):
        return self._match_at(el, len(self.parts) - 1)

    def _match_at(self, el, i):
        comb, comp = self.parts[i]
        if not comp.matches(el):
            return False
        if i == 0:
            return True
        if comb == '>':
            p = el.getparent()
            return p is not None and self._match_at(p, i - 1)
        if comb == ' ':
            p = el.getparent()
            while p is not None:
                if self._match_at(p, i - 1):
                    return True
                p = p.getparent()
            return False
        if comb == '+':
            prev = el.getprevious()
            while prev is not None and not is_element(prev):
                prev = prev.getprevious()
            return prev is not None and self._match_at(prev, i - 1)
        if comb == '~':
            prev = el.getprevious()
            while prev is not None:
                if is_element(prev) and self._match_at(prev, i - 1):
                    return True
                prev = prev.getprevious()
            return False
        return False


def parse_selector(text):
    """Parse one complex selector; ``None`` when it is empty or unparseable."""
    s = text.strip()
    if not s:
        return None
    parts, comb, i, n = [], None, 0, len(s)
    comp = None
    try:
        while i < n:
            ch = s[i]
            if ch.isspace():
                j = i
                while j < n and s[j].isspace():
                    j += 1
                if j < n and s[j] in '>+~':
                    i = j
                    continue
                if comp is not None:
                    parts.append((comb, comp))
                    comp, comb = None, ' '
                i = j
                continue
            if ch in '>+~':
                if comp is not None:
                    parts.append((comb, comp))
                    comp = None
                comb = ch
                i += 1
                while i < n and s[i].isspace():
                    i += 1
                continue
            if comp is None:
                comp = Compound()
            if ch == '*':
                comp.tag = '*'
                i += 1
            elif ch == '#':
                m = re.match(_IDENT, s[i + 1:])
                comp.ids.append(m.group(0))
                i += 1 + len(m.group(0))
            elif ch == '.':
                m = re.match(_IDENT, s[i + 1:])
                comp.classes.append(m.group(0))
                i += 1 + len(m.group(0))
            elif ch == '[':
                j = s.index(']', i)
                body = s[i + 1:j].strip()
                m = re.match(r'^([-\w:]+)\s*(?:([~|^$*]?=)\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s\]]+)))?(?:\s+[iIsS])?$', body)
                if not m:
                    return None
                val = m.group(3) if m.group(3) is not None else (m.group(4) if m.group(4) is not None else m.group(5))
                comp.attrs.append((m.group(1).lower(), m.group(2), val))
                i = j + 1
            elif ch == ':':
                if s[i:i + 2] == '::':
                    comp.never = True              # pseudo-element — no generated content
                    m = re.match(r'-?[-\w]+', s[i + 2:])
                    i += 2 + (len(m.group(0)) if m else 0)
                    if i < n and s[i] == '(':
                        i = _skip_parens(s, i)
                    continue
                m = re.match(r'-?[-\w]+', s[i + 1:])
                name = m.group(0).lower()
                i += 1 + len(name)
                arg = None
                if i < n and s[i] == '(':
                    j = _skip_parens(s, i)
                    arg = s[i + 1:j - 1]
                    i = j
                if name in ('before', 'after', 'first-line', 'first-letter', 'marker', 'selection'):
                    comp.never = True
                elif name in ('not', 'is', 'where', 'matches'):
                    subs = [parse_selector(x) for x in _split_top(arg or '')]
                    subs = [x for x in subs if x is not None]
                    comp.pseudos.append((name, subs))
                elif name in _NEVER_PSEUDO or name.startswith('-'):
                    comp.never = True
                else:
                    comp.pseudos.append((name, arg))
            else:
                m = re.match(_IDENT, s[i:])
                if not m:
                    return None
                comp.tag = m.group(0).lower()
                i += len(m.group(0))
        if comp is not None:
            parts.append((comb, comp))
        if not parts:
            return None
        parts[0] = (None, parts[0][1])
        return Selector(parts)
    except (ValueError, AttributeError, IndexError):
        return None


def _skip_parens(s, i):
    depth = 0
    while i < len(s):
        if s[i] == '(':
            depth += 1
        elif s[i] == ')':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


# ── computed style ─────────────────────────────────────────────────────────────
INHERITED = frozenset((
    'color', 'font-family', 'font-size', 'font-weight', 'font-style', 'font-variant',
    'font-variant-numeric', 'text-align', 'white-space', 'visibility', 'line-height',
    'letter-spacing', 'text-transform', 'list-style-type', 'direction', 'word-break',
    'overflow-wrap', 'fill', 'stroke', 'stroke-width', 'fill-opacity', 'stroke-opacity',
    'stroke-dasharray', 'stroke-linecap', 'stroke-linejoin', 'text-anchor', 'font-stretch',
    'paint-order', 'fill-rule', 'clip-rule',
))

ROOT_DEFAULTS = {
    'color': '#000000', 'font-family': 'Segoe UI, Arial, sans-serif', 'font-size': '16px',
    'font-weight': '400', 'font-style': 'normal', 'text-align': 'start', 'white-space': 'normal',
    'visibility': 'visible', 'fill': 'black', 'stroke': 'none', 'stroke-width': '1',
    'text-transform': 'none', 'text-anchor': 'start',
}

_BLOCK_TAGS = {
    'html', 'body', 'div', 'p', 'section', 'article', 'main', 'header', 'footer', 'aside',
    'nav', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'dl', 'dt', 'dd', 'figure',
    'figcaption', 'blockquote', 'pre', 'hr', 'form', 'fieldset', 'address', 'details',
    'summary', 'table', 'center', 'legend', 'menu',
}
_TABLE_DISPLAY = {'table': 'table', 'thead': 'table-header-group', 'tbody': 'table-row-group',
                  'tfoot': 'table-footer-group', 'tr': 'table-row', 'td': 'table-cell',
                  'th': 'table-cell', 'caption': 'table-caption', 'colgroup': 'table-column-group',
                  'col': 'table-column'}
_HIDDEN_TAGS = {'head', 'script', 'style', 'template', 'noscript', 'meta', 'link', 'title', 'base'}

# SVG presentation attributes (lowest precedence, below any stylesheet rule)
_SVG_PRES = ('fill', 'stroke', 'stroke-width', 'opacity', 'fill-opacity', 'stroke-opacity',
             'stroke-dasharray', 'stroke-linecap', 'stroke-linejoin', 'font-size', 'font-family',
             'font-weight', 'font-style', 'text-anchor', 'dominant-baseline', 'display',
             'visibility', 'color', 'text-decoration', 'letter-spacing', 'fill-rule',
             'clip-rule', 'paint-order')
_SVG_TAGS = {'svg', 'g', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon', 'path',
             'text', 'tspan', 'textpath', 'use', 'defs', 'marker', 'lineargradient',
             'radialgradient', 'stop', 'clippath', 'mask', 'pattern', 'symbol', 'title', 'desc',
             'foreignobject', 'image'}

_VAR_RE = re.compile(r'var\(\s*(--[-\w]+)\s*(?:,\s*)?')


def resolve_vars(value, custom, depth=0):
    """Substitute every ``var(--x[, fallback])`` in ``value`` from ``custom``.
    An unknown variable with no fallback yields ``None`` (declaration invalid)."""
    if value is None or 'var(' not in value:
        return value
    if depth > 12:
        return None
    out, i = [], 0
    while True:
        m = _VAR_RE.search(value, i)
        if not m:
            out.append(value[i:])
            break
        out.append(value[i:m.start()])
        # find the closing paren of this var(
        open_idx = value.index('(', m.start())
        close = _skip_parens(value, open_idx)
        inner = value[open_idx + 1:close - 1]
        name, _, fallback = inner.partition(',')
        name = name.strip()
        rep = custom.get(name)
        if rep is None:
            rep = fallback.strip() if fallback else None
        if rep is None:
            return None
        rep = resolve_vars(rep, custom, depth + 1)
        if rep is None:
            return None
        out.append(rep)
        i = close
    return ''.join(out)


class ComputedStyle(dict):
    """A computed-value mapping plus convenience accessors."""

    def color(self):
        return self.get('_color')

    def background(self):
        """The element's OWN opaque-ish background colour (rgba) or None."""
        return self.get('_bg')

    def font_px(self):
        return self.get('_font_px', 16.0)

    def is_bold(self):
        w = str(self.get('font-weight', '400')).strip().lower()
        if w in ('bold', 'bolder'):
            return True
        try:
            return float(w) >= 600
        except ValueError:
            return False

    def is_italic(self):
        return str(self.get('font-style', 'normal')).lower() in ('italic', 'oblique')

    def display(self):
        return self.get('display', 'inline')


class Resolver:
    """Compute styles for elements of one lxml document against one StyleSheet."""

    def __init__(self, sheet, root_font_px=16.0):
        self.sheet = sheet
        self.root_font_px = root_font_px
        self._memo = {}
        clear_sibling_cache()

    def style(self, el):
        key = el
        hit = self._memo.get(key)
        if hit is not None:
            return hit
        parent = el.getparent()
        while parent is not None and not is_element(parent):
            parent = parent.getparent()
        pst = self.style(parent) if parent is not None else None
        st = self._compute(el, pst)
        self._memo[key] = st
        return st

    def _declared(self, el):
        """Winning declared value per property as ``{prop: (value, seq)}``: presentation
        hints < stylesheet rules (by specificity, then source order) < inline ``style``,
        with ``!important`` beating every normal declaration. ``seq`` is the cascade
        rank, so shorthands and longhands can be applied in their true order."""
        out = {}
        seq = 0
        tag = tag_of(el)

        def put(prop, val, rank):
            out[prop] = (val, rank)

        if tag in _SVG_TAGS or self._in_svg(el):
            for a in _SVG_PRES:
                v = el.get(a)
                if v is not None and v != '':
                    seq += 1
                    put(a, v, seq)
        bg = el.get('bgcolor')
        if bg:
            seq += 1
            put('background-color', bg, seq)
        al = el.get('align')
        if al and tag in ('td', 'th', 'tr', 'div', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            seq += 1
            put('text-align', al, seq)
        col = el.get('color') if tag == 'font' else None
        if col:
            seq += 1
            put('color', col, seq)
        importants = []
        for rule in self.sheet.matching(el):
            for prop, val, imp in rule.decls:
                seq += 1
                if imp:
                    importants.append((prop, val))
                else:
                    put(prop, val, seq)
        inline = el.get('style')
        inline_imp = []
        if inline:
            for prop, val, imp in parse_declarations(inline):
                seq += 1
                if imp:
                    inline_imp.append((prop, val))
                else:
                    put(prop, val, seq)
        for prop, val in importants + inline_imp:
            seq += 1
            put(prop, val, 1_000_000 + seq)
        return out

    def _in_svg(self, el):
        p = el.getparent()
        while p is not None:
            if tag_of(p) == 'svg':
                return True
            p = p.getparent()
        return False

    def _compute(self, el, pst):
        declared = self._declared(el)
        ordered = sorted(declared.items(), key=lambda kv: kv[1][1])
        st = ComputedStyle()
        # custom properties (inherited)
        custom = dict(pst.get('_custom', {})) if pst is not None else {}
        for prop, (val, _r) in ordered:
            if prop.startswith('--'):
                custom[prop] = val
        for k in list(custom):
            if 'var(' in (custom[k] or ''):
                r = resolve_vars(custom[k], custom)
                if r is not None:
                    custom[k] = r
        st['_custom'] = custom
        if pst is not None:
            for p in INHERITED:
                if p in pst:
                    st[p] = pst[p]
        else:
            st.update(ROOT_DEFAULTS)
        parent_font = pst.font_px() if pst is not None else self.root_font_px
        font_declared = False
        color_declared = False
        bg_decl = None
        for prop, (val, _r) in ordered:
            if prop.startswith('--'):
                continue
            v = resolve_vars(val, custom)
            if v is None:
                continue
            low = v.strip().lower()
            if low == 'inherit':
                if pst is not None and prop in pst:
                    st[prop] = pst[prop]
                    if prop == 'font-size':
                        font_declared = False
                continue
            if low in ('initial', 'unset', 'revert'):
                if prop in INHERITED and low != 'initial' and pst is not None and prop in pst:
                    st[prop] = pst[prop]
                else:
                    st.pop(prop, None)
                    if prop in ROOT_DEFAULTS and prop in INHERITED:
                        st[prop] = ROOT_DEFAULTS[prop]
                if prop in ('background', 'background-color'):
                    bg_decl = None
                continue
            st[prop] = v
            if prop in ('background', 'background-color'):
                bg_decl = v
            elif prop == 'font':
                self._font_shorthand(st, v)
                font_declared = True
            elif prop == 'font-size':
                font_declared = True
            elif prop == 'color':
                color_declared = True
            elif prop == 'border' or (prop.startswith('border-') and prop[7:] in ('top', 'right', 'bottom', 'left')):
                self._border_shorthand(st, prop, v)
        # display
        tag = tag_of(el)
        if 'display' not in st or 'display' not in declared:
            if tag in _HIDDEN_TAGS:
                st['display'] = 'none'
            elif tag in _TABLE_DISPLAY:
                st['display'] = _TABLE_DISPLAY[tag]
            elif tag == 'li':
                st['display'] = 'list-item'
            elif tag in _BLOCK_TAGS:
                st['display'] = 'block'
            else:
                st['display'] = 'inline'
        if el.get('hidden') is not None:
            st['display'] = 'none'
        # font size (inherits the parent's COMPUTED px unless declared here)
        fpx = None
        if font_declared:
            low = str(st.get('font-size', '')).strip().lower()
            if low in _FONT_KEYWORDS:
                fpx = float(_FONT_KEYWORDS[low])
            elif low == 'smaller':
                fpx = parent_font / 1.2
            elif low == 'larger':
                fpx = parent_font * 1.2
            else:
                fpx = length_px(low, font_px=parent_font, root_px=self.root_font_px,
                                percent_of=parent_font)
        st['_font_px'] = fpx if fpx is not None else parent_font
        # colours
        pcol = pst.color() if pst is not None else (0, 0, 0, 1.0)
        c = parse_color(st.get('color'), pcol) if color_declared else None
        st['_color'] = c if c is not None else pcol
        bg = find_color(bg_decl, st['_color']) if bg_decl else None
        if bg is not None and bg[3] <= 0.001:
            bg = None
        st['_bg'] = bg
        return st

    @staticmethod
    def _font_shorthand(st, v):
        toks = v.split()
        for t in toks:
            low = t.lower()
            if low in ('bold', 'bolder') or re.fullmatch(r'[1-9]00', low):
                st['font-weight'] = low
            elif low in ('italic', 'oblique'):
                st['font-style'] = low
            elif re.match(r'^\d*\.?\d+(px|pt|em|rem|%)(/.*)?$', low):
                st['font-size'] = low.split('/')[0]
        m = re.search(r'(?:px|pt|em|rem|%)(?:/\S+)?\s+(.+)$', v)
        if m:
            st['font-family'] = m.group(1)

    @staticmethod
    def _border_shorthand(st, prop, v):
        sides = ('top', 'right', 'bottom', 'left')
        if prop == 'border':
            targets = sides
        elif prop.startswith('border-') and prop[7:] in sides:
            targets = (prop[7:],)
        else:
            return
        for s in targets:
            st[f'border-{s}'] = v

    # ── convenience ──
    def border_color(self, el, side):
        """(width_px, rgba) of a border side, or None when there is no visible border."""
        st = self.style(el)
        v = st.get(f'border-{side}')
        colv = st.get(f'border-{side}-color') or st.get('border-color')
        width = None
        style_ok = True
        if v:
            if re.search(r'\b(none|hidden)\b', v) or v.strip() == '0':
                return None
            for tok in v.split():
                px = length_px(tok)
                if px is not None:
                    width = px
            col = find_color(v, st.color())
            if col is None and colv:
                col = find_color(colv, st.color())
        elif colv:
            col = find_color(colv, st.color())
            style_ok = bool(st.get(f'border-{side}-style') or st.get('border-style'))
        else:
            return None
        if not style_ok or col is None or col[3] <= 0.001:
            return None
        return (width if width is not None else 1.0, col)

    def is_hidden(self, el):
        st = self.style(el)
        if st.display() == 'none':
            return True
        return str(st.get('visibility', 'visible')).lower() in ('hidden', 'collapse')


def stylesheet_for(doc, page_width_px=720):
    """Build a StyleSheet from every ``<style>`` element in an lxml document."""
    texts = []
    for st in doc.iter('style'):
        texts.append(st.text or '')
    return StyleSheet(texts, page_width_px=page_width_px)


def page_setup(sheet):
    """``@page`` → ``{'width_mm', 'height_mm', 'orientation', 'margins_mm': (t, r, b, l)}``.
    Defaults: A4 portrait, Chrome's default ~10 mm margins."""
    sizes = {'a4': (210, 297), 'a3': (297, 420), 'a5': (148, 210), 'letter': (215.9, 279.4),
             'legal': (215.9, 355.6), 'ledger': (279.4, 431.8), 'b5': (176, 250)}
    w, h = 210.0, 297.0
    orient = 'portrait'
    size = (sheet.page.get('size') or '').strip().lower()
    if size:
        toks = size.split()
        lens = [length_mm(t) for t in toks if length_mm(t) is not None]
        named = [t for t in toks if t in sizes]
        if named:
            w, h = sizes[named[0]]
        if len(lens) == 2:
            w, h = lens
        elif len(lens) == 1:
            w = h = lens[0]
        if 'landscape' in toks:
            w, h = max(w, h), min(w, h)
        elif 'portrait' in toks:
            w, h = min(w, h), max(w, h)
    if w > h:
        orient = 'landscape'
    margins = [10.0, 10.0, 10.0, 10.0]
    mv = sheet.page.get('margin')
    if mv:
        vals = [length_mm(t, 10.0) for t in mv.split()]
        if len(vals) == 1:
            margins = vals * 4
        elif len(vals) == 2:
            margins = [vals[0], vals[1], vals[0], vals[1]]
        elif len(vals) == 3:
            margins = [vals[0], vals[1], vals[2], vals[1]]
        elif len(vals) >= 4:
            margins = vals[:4]
    for i, side in enumerate(('top', 'right', 'bottom', 'left')):
        sv = sheet.page.get(f'margin-{side}')
        if sv:
            margins[i] = length_mm(sv, margins[i])
    return {'width_mm': w, 'height_mm': h, 'orientation': orient, 'margins_mm': tuple(margins)}
