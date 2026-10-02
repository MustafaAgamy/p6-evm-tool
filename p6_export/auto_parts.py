"""Automatic PARTS for the Report Contents picker (owner comment 1).

The picker has two levels: SECTIONS (a renderer wraps each one in ``data-sec="<key>"``) and the
PARTS inside them (``data-part="<key>.<part>"`` — one table, one chart, one group of tiles).
A renderer may mark its parts by hand (Earned Value, Calendar Audit do). For every other report
this module finds them: inside each ``[data-sec]`` that has no hand-marked part, every distinct
block — a sub-heading with what follows it, a table, a chart, a row of tiles — becomes a part
with a readable label, so the planner can print any single piece of any feature.

``annotate(html)`` returns the same HTML with only ``data-part`` attributes (or, for a
sub-heading + its blocks, a ``display:contents`` wrapper) added.  Nothing is moved, restyled or
removed, so the report prints exactly as before when everything is ticked.  A section that would
give fewer than two parts is left alone (its single part is the section itself).  Any doubt →
the original HTML is returned unchanged.
"""
import html as _html
import re

_VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param',
         'source', 'track', 'wbr'}
_RAW = {'script', 'style', 'textarea', 'title'}
_LEAF = {'table', 'svg', 'canvas', 'ul', 'ol', 'dl', 'select'}        # never looked inside
_SEC_HEAD = {'h1', 'h2'}
_SUB_HEAD = {'h3', 'h4', 'h5', 'h6'}
_SUB_CLASS = re.compile(r'(^|[\s_-])(sub|sub2|subh|subhead|h3title|sectitle|blocktitle|grp-h|cap|caption)($|[\s_-])', re.I)
_CHART_CLASS = re.compile(r'chart|bar|curve|gantt|donut|pie|heat|spark|timeline|histogram|waterfall|lane|strip', re.I)
_KPI_CLASS = re.compile(r'kpi|tile|card|stat|band|score|gauge|metric|headline|dash', re.I)
_NOTE_CLASS = re.compile(r'note|hint|legend|foot|leg|caveat|basis', re.I)
_TAG_OPEN = re.compile(r'<([a-zA-Z][\w:-]*)')
_TAG_CLOSE = re.compile(r'</\s*([a-zA-Z][\w:-]*)\s*[^>]*>')
_ATTR = re.compile(r'([^\s"\'=<>/]+)(?:\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s"\'=<>`]+)))?')
MAX_LABEL = 70
AUTO_ATTR = 'data-auto-part'


class _El:
    __slots__ = ('tag', 'attrs_src', 'start', 'tag_end', 'inner_end', 'end', 'parent', 'children')

    def __init__(self, tag, attrs_src, start, tag_end, parent):
        self.tag, self.attrs_src, self.start, self.tag_end = tag, attrs_src, start, tag_end
        self.inner_end = self.end = tag_end
        self.parent, self.children = parent, []

    def attr(self, name):
        for m in _ATTR.finditer(self.attrs_src):
            if m.group(1).lower() == name:
                v = m.group(2) if m.group(2) is not None else (m.group(3) if m.group(3) is not None else m.group(4))
                return _html.unescape(v or '')
        return None

    def cls(self):
        return self.attr('class') or ''


def _tag_end(s, j):
    """Index just past the '>' that ends the start tag whose name ends at j (quotes respected)."""
    q, n = None, len(s)
    while j < n:
        c = s[j]
        if q:
            if c == q:
                q = None
        elif c in '"\'':
            q = c
        elif c == '>':
            return j + 1
        j += 1
    return n


def _leaf_end(s, tag, start_from):
    """End of a leaf element (table / svg / list): the matching close tag, nested same-tag aware."""
    low = s.lower()
    depth, i = 1, start_from
    open_pat, close_pat = '<' + tag, '</' + tag
    while depth:
        nc = low.find(close_pat, i)
        if nc < 0:
            return len(s), len(s)
        no = low.find(open_pat, i)
        if 0 <= no < nc and not low[no + len(open_pat)].isalnum():
            depth += 1
            i = no + len(open_pat)
            continue
        if 0 <= no < nc:
            i = no + len(open_pat)
            continue
        depth -= 1
        i = nc + len(close_pat)
        if not depth:
            gt = s.find('>', nc)
            return nc, (len(s) if gt < 0 else gt + 1)
    return len(s), len(s)


def _tree(s):
    """A tolerant element tree of the document (tables, lists and SVGs are leaves)."""
    root = _El('#root', '', 0, 0, None)
    root.inner_end = root.end = len(s)
    stack, i, n = [root], 0, len(s)
    while i < n:
        lt = s.find('<', i)
        if lt < 0:
            break
        if s.startswith('<!--', lt):
            e = s.find('-->', lt + 4)
            i = n if e < 0 else e + 3
            continue
        nxt = s[lt + 1:lt + 2]
        if nxt in ('!', '?'):
            e = s.find('>', lt)
            i = n if e < 0 else e + 1
            continue
        if nxt == '/':
            m = _TAG_CLOSE.match(s, lt)
            if not m:
                i = lt + 1
                continue
            tag = m.group(1).lower()
            k = len(stack) - 1
            while k > 0 and stack[k].tag != tag:
                k -= 1
            if k > 0:
                while len(stack) > k:
                    el = stack.pop()
                    el.inner_end = lt
                    el.end = m.end() if len(stack) == k else lt
            i = m.end()
            continue
        m = _TAG_OPEN.match(s, lt)
        if not m:
            i = lt + 1
            continue
        tag = m.group(1).lower()
        te = _tag_end(s, m.end())
        attrs_src = s[m.end():te - 1]
        el = _El(tag, attrs_src, lt, te, stack[-1])
        stack[-1].children.append(el)
        if tag in _VOID or attrs_src.rstrip().endswith('/'):
            i = te
            continue
        if tag in _RAW or tag in _LEAF:
            el.inner_end, el.end = _leaf_end(s, tag, te)
            i = el.end
            continue
        stack.append(el)
        i = te
    while len(stack) > 1:
        el = stack.pop()
        el.inner_end = el.end = len(s)
    return root


def _walk(el):
    for c in el.children:
        yield c
        yield from _walk(c)


def _text(s, el, limit=400):
    raw = s[el.tag_end:el.inner_end] if el.tag not in _VOID else ''
    raw = re.sub(r'<(script|style)\b[\s\S]*?</\1\s*>', ' ', raw, flags=re.I)
    raw = re.sub(r'<[^>]*>', ' ', raw[:limit * 12])
    return re.sub(r'\s+', ' ', _html.unescape(raw)).strip()


def _has(s, el, pattern):
    return re.search(pattern, s[el.tag_end:el.inner_end], re.I) is not None


def _is_sub_heading(s, el):
    if el.tag in _SUB_HEAD or el.tag in _SEC_HEAD:        # a second h2 inside one section opens a part
        return True
    if el.tag in ('div', 'p', 'span') and _SUB_CLASS.search(el.cls()):
        return not _has(s, el, r'<(table|svg|canvas|img)\b') and 0 < len(_text(s, el)) <= 110
    return False


def _is_text_only(s, el):
    if el.tag in _LEAF or el.tag in ('img', 'canvas', 'figure'):
        return False
    if _has(s, el, r'<(table|svg|canvas|img|ul|ol)\b'):
        return False
    if _CHART_CLASS.search(el.cls()) or _KPI_CLASS.search(el.cls()):
        return False
    # a sentence (a <p>, or a div holding at most one inline child) — not a row built of cells
    inline = el.tag in ('p', 'span', 'small', 'em', 'i', 'b', 'strong', 'label')
    if not inline and len(el.children) > 1:
        return False
    return len(el.children) <= 3 and len(_text(s, el, 700)) <= 600


def _clip(text):
    text = re.sub(r'\s+', ' ', text or '').strip(' :—-·')
    return text if len(text) <= MAX_LABEL else text[:MAX_LABEL - 1].rstrip() + '…'


def _first_title(s, el):
    """The block's own short opening line (a card title, a chart caption), when it has one."""
    whole = len(_text(s, el, 300))
    if _has(s, el, r'<(table|svg|canvas|img)\b'):
        whole += 1                   # a caption over a chart IS the title, even when it is all the text
    node = el
    for _ in range(3):
        kids = [c for c in node.children if c.tag not in _RAW and c.tag != 'br']
        if not kids:
            return ''
        first = kids[0]
        if first.tag in _LEAF or first.tag in ('img', 'canvas'):
            return ''
        t = _text(s, first, 120)
        if 3 <= len(t) <= 60 and len(t) < whole:
            # a tile's value ('0.74 CPLI', 'Previous 5.9% Current 41.5%') is not a title
            numeric = [w for w in t.split() if any(ch.isdigit() for ch in w)]
            if t[:1].isdigit() or len(numeric) > 2 or '%' in t:
                return ''
            return _clip(t)
        node = first
    return ''


def wrap_part(key, label, html, tag='div'):
    """Mark one PART by hand (level 2): ``key`` is '<section>.<part>'. Empty content → nothing.
    A section with any hand-marked part is left exactly as the renderer wrote it."""
    if not html:
        return ''
    return '<%s data-part="%s" data-part-label="%s">%s</%s>' % (
        tag, _html.escape(str(key), quote=True), _html.escape(str(label), quote=True), html, tag)


def _small(s, el):
    return (el.tag not in _LEAF and not _has(s, el, r'<(table|svg|canvas)\b')
            and len(_text(s, el, 400)) <= 260)


def _sig(el):
    cls = el.cls()
    return (el.tag, cls.split(' ')[0] if cls else '')


def _merge_runs(s, groups):
    """Three or more consecutive small blocks of the same kind (same tag and class — the rows of
    a bar list, a set of chips) are one part; big look-alike blocks (a chart per milestone) stay
    separate parts."""
    out, i = [], 0
    while i < len(groups):
        _label_i, els, headed = groups[i]
        if headed or len(els) != 1 or not _small(s, els[0]):
            out.append(groups[i])
            i += 1
            continue
        sig, j = _sig(els[0]), i + 1
        while (j < len(groups) and not groups[j][2] and len(groups[j][1]) == 1
               and _small(s, groups[j][1][0]) and _sig(groups[j][1][0]) == sig):
            j += 1
        if j - i >= 3:
            run = [e for g in groups[i:j] for e in g[1]]
            cls = els[0].cls()
            name = 'Chart' if _CHART_CLASS.search(cls) else ('Key figures' if _KPI_CLASS.search(cls) else 'List')
            out.append([name, run, False])
            i = j
        else:
            out.append(groups[i])
            i += 1
    return out


def _label(s, el):
    """A readable name for one block when no sub-heading names it."""
    for name in ('data-part-label', 'aria-label', 'data-title'):
        v = el.attr(name)
        if v:
            return _clip(v)
    inner = s[el.tag_end:el.inner_end]
    m = re.search(r'<(caption|h[3-6])\b[^>]*>([\s\S]*?)</\1\s*>', inner, re.I)
    if m:
        t = _clip(re.sub(r'<[^>]*>', ' ', _html.unescape(m.group(2))))
        if t:
            return t
    m = re.search(r'<(div|p|span)\b[^>]*class\s*=\s*["\'][^"\']*\b(title|cap|sub|sub2|h3title|lbl-h|head)\b[^"\']*["\'][^>]*>([\s\S]*?)</\1\s*>', inner, re.I)
    if m:
        t = _clip(re.sub(r'<[^>]*>', ' ', _html.unescape(m.group(3))))
        if t and len(t) <= 60:
            return t
    t = _first_title(s, el)
    if t:
        return t
    if el.tag == 'table' or re.search(r'<table\b', inner, re.I):
        src = s[el.start:el.end]
        heads = [_clip(re.sub(r'<[^>]*>', ' ', _html.unescape(h))) for h in re.findall(r'<th\b[^>]*>([\s\S]*?)</th\s*>', src, re.I)[:6]]
        heads = [h for h in heads if h][:3]
        return _clip('Table — ' + ' · '.join(heads)) if heads else 'Table'
    cls = el.cls()
    if el.tag in ('svg', 'canvas', 'img', 'figure') or _CHART_CLASS.search(cls) or re.search(r'<(svg|canvas)\b', inner, re.I):
        return 'Chart'
    if _KPI_CLASS.search(cls):
        return 'Key figures'
    if el.tag in ('ul', 'ol'):
        return 'List'
    words = _text(s, el, 120).split()
    return _clip(' '.join(words[:7]) + ('…' if len(words) > 7 else '')) if words else 'Block'


def _blocks(s, sec):
    """The section's own content blocks (its heading left out), after stepping through wrappers."""
    container = sec
    for _ in range(4):
        kids = [c for c in container.children if c.tag not in _RAW and c.tag != 'br']
        body = [c for c in kids if c.tag not in _SEC_HEAD]
        if len(body) == 1 and body[0].tag in ('div', 'section', 'article', 'main') and body[0].children:
            only = body[0]
            inner = [c for c in only.children if c.tag not in _RAW]
            sig = {_sig(c) for c in inner}
            # a row of identical SMALL tiles / chips is one block; identical BIG blocks (a chart
            # each) are opened so each chart can be ticked on its own
            if len(inner) >= 3 and len(sig) == 1 and all(_small(s, c) for c in inner):
                break
            container = only
            continue
        break
    kids = [c for c in container.children if c.tag not in _RAW and c.tag != 'br']
    # the section's own title: its first h1/h2 (or a first heading-like div when wrapped that way)
    while kids and (kids[0].tag in _SEC_HEAD or _is_title_block(s, kids[0])):
        kids = kids[1:]
    return kids


def _is_title_block(s, el):
    """A small wrapper around the section's own h1/h2 (number badge + title + sub-title)."""
    return (el.tag in ('div', 'header') and _has(s, el, r'<h[12]\b')
            and not _has(s, el, r'<(table|svg|canvas|img|ul|ol)\b') and len(_text(s, el, 400)) <= 240)


def _groups(s, kids):
    """[(label|None, [elements])] — a sub-heading takes everything up to the next sub-heading;
    without sub-headings every block is its own part (a short note joins the part before it)."""
    groups, cur = [], None
    for el in kids:
        if _is_sub_heading(s, el):
            cur = [_clip(_text(s, el)), [el], True]
            groups.append(cur)
            continue
        if cur is not None and cur[2]:                       # under a sub-heading
            cur[1].append(el)
            continue
        if _is_text_only(s, el):
            if groups and not groups[-1][2]:                 # a note under a table / chart
                groups[-1][1].append(el)
            # an intro paragraph before the first part stays with the section, always shown
            elif not groups:
                continue
            continue
        groups.append([None, [el], False])
    out = []
    for label, els, headed in _merge_runs(s, groups):
        if headed and len(els) == 1:                         # a heading with nothing under it
            continue
        out.append((label, els))
    return out


def annotate(html):
    """Report HTML → the same HTML with automatic ``data-part`` marks inside every ``[data-sec]``
    that has none of its own.  Never raises; returns the input unchanged when unsure."""
    s = html if isinstance(html, str) else ''
    if 'data-sec' not in s:
        return html
    try:
        root = _tree(s)
        edits = []                                           # (position, priority, text) insertions
        for sec in _walk(root):
            key = sec.attr('data-sec') if 'data-sec' in sec.attrs_src else None
            if not key:
                continue
            if (sec.attr('data-parts') or '').lower() == 'none':
                continue                                     # the renderer says: this section is one block
            if re.search(r'\bdata-part\s*=', s[sec.tag_end:sec.inner_end]):
                continue                                     # hand-marked: leave it exactly as written
            groups = _groups(s, _blocks(s, sec))
            if len(groups) < 2:
                continue
            seen, n = {}, 0
            for label, els in groups:
                n += 1
                if not label:
                    label = _label(s, els[0])
                seen[label] = seen.get(label, 0) + 1
                if seen[label] > 1:
                    label = _clip(label)[:MAX_LABEL - 5] + ' (%d)' % seen[label]
                marks = ' data-part="%s.a%d" data-part-label="%s" %s="1"' % (
                    _html.escape(key, quote=True), n, _html.escape(label, quote=True), AUTO_ATTR)
                if len(els) == 1:
                    edits.append((els[0].start + 1 + len(els[0].tag), 1, marks))
                else:
                    edits.append((els[0].start, 1, '<div%s style="display:contents">' % marks))
                    edits.append((els[-1].end, 0, '</div>'))
        if not edits:
            return html
        out = s
        # back to front; at one position an opening wrapper goes in before the closing one of the
        # previous group, so the text reads '</div><div …>'
        for pos, _prio, text in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
            out = out[:pos] + text + out[pos:]
        # sanity: every mark landed, and the wrappers are balanced
        if out.count(AUTO_ATTR) * 1 < 2 or out.count('<div') - s.count('<div') != out.count('</div>') - s.count('</div>'):
            return html
        return out
    except Exception:
        return html


def wrap_section(key, html, tag='div', whole=False):
    """Wrap one report section for the picker (level 1). Empty content → nothing.
    ``whole=True`` marks it as one designed block that is never split into parts."""
    if not html:
        return ''
    return '<%s data-sec="%s"%s>%s</%s>' % (tag, _html.escape(str(key), quote=True),
                                           ' data-parts="none"' if whole else '', html, tag)
