"""§12 Activity IDs — derive a colour-coded anatomy of the project's Activity-ID coding,
then one breakdown per ID *type* found in the schedule.

FULLY GENERIC: the ID families, segment structure, roles and every plain-language meaning
are auto-derived live from the loaded schedule — no project-specific hardcoding. This is the
engine twin of :func:`p6_narrative.report._activity_ids`; it emits DATA only, and both the
HTML renderer (:mod:`p6_narrative.html`) and the Word renderer (:mod:`p6_narrative.docx_writer`)
draw straight from this payload (no re-derivation), so Preview == PDF == Print.

The derivation is ported verbatim from the approved standalone mock-up (``mock_s12.py``):

  * families = the first ID token, splitting ``CONS`` further by the 'Type of Works' code;
  * the LAST segment is ALWAYS the "Sequencing serial" (even a letter-prefixed one, e.g.
    ``A1020``);
  * segment meanings are auto-derived DISTINCTIVELY — the activity-code value specific to a
    token's holders (held by most of them but NOT global to the whole schedule), else the
    dominant significant word in those activities' names;
  * family titles from the common name bigram (``CONS`` → "Construction — <trade>");
  * the anatomy shows a representative construction family (Civil Works), else the smallest
    family.

Return shape::

    {'intro':   <str section intro>,
     'anatomy': {'sample': str, 'cols': [{'code', 'meaning', 'role'}, ...]} | None,
     'blocks':  [{'title', 'sample', 'cols': [{'code', 'meaning', 'role'}],
                  'note', 'count'}, ...]}

None-safe: no activities / no ids → ``{'intro': ..., 'anatomy': None, 'blocks': []}``.
"""
import re
from collections import Counter, OrderedDict

# role → colour (the innovation: a segment's ROLE is colour-coded consistently everywhere)
ROLE_HEX = {'stage': '1F4E79', 'step': '7A5AA6', 'work': '2E9E5B',
            'area': 'E8A33D', 'serial': '9AA4B0', 'other': '5A6470'}
ROLE_NAME = {'stage': 'Phase / stage', 'step': 'Workflow step', 'work': 'Work type',
             'area': 'Area / structure', 'serial': 'Sequencing serial', 'other': 'Code'}
AREA_HINT = ('area', 'silo', 'building', 'zone', 'location', 'tower', 'unit',
             'facility', 'structure', 'block', 'sector', 'system', 'name')
WORK_HINT = ('work', 'type', 'trade', 'discipline', 'civil', 'element', 'craft')
_STOP = {'the', 'and', 'for', 'from', 'works', 'work', 'phase', 'silo', 'tower', 'main'}

# fixed generic prose (not project-specific) — the section intro and the 12.1 anatomy intro
INTRO = ('Every activity in this baseline carries a structured, dot-separated Activity ID that '
         'encodes what the activity is and where it sits in the works. This section explains that '
         'coding — first how to read any ID, then a breakdown for each ID type in the schedule '
         '— so any Activity ID quoted elsewhere in this report can be traced straight back to P6. '
         'The ID types, segments and code lists are read directly from this schedule; the plain-'
         'language meanings are auto-suggested from the activities and are fully editable, so your '
         'team can refine any in-house abbreviation.')
ANATOMY_INTRO = ('An Activity ID reads left to right as dot-separated segments. Each segment has a '
                 'role, shown here in a consistent colour: the phase / stage, the work type, the area '
                 'or structure, and the final sequence number. The order of the middle segments can '
                 'differ between scopes, so each is decoded by its meaning — not by a fixed '
                 'position.')


_SEP = ['.']          # the separator(s) THIS schedule's IDs use, set per analysis ('.' by default)
_SPLIT = [None]       # compiled splitter for this schedule; None = split on _SEP[0]
_SEPS = ('.', '-', '_', '/', ' ')
_SEP_WORD = {'.': 'dot', '-': 'dash', '_': 'underscore', '/': 'slash', ' ': 'space'}


def _detect_sep(ids):
    """How THIS schedule's Activity IDs are built - works for any project's coding (comment 103):
    'CONS.PL.S1.1010' -> '.', 'EX-1000-GC-CON-BAT' -> '-', 'CIV_FDN_1000' -> '_', mixed
    'B1-CIV.1000' -> both, and P6's default 'A1000' (no separator) -> letters | number runs.
    Sets the splitter used by _segs and returns the plain-language description of the coding."""
    ids = [i for i in ids if i]
    n = len(ids) or 1
    share = {sep: sum(1 for i in ids if sep in i.strip()) / n for sep in _SEPS}
    used = [sep for sep in _SEPS if share[sep] >= 0.2]
    if used and max(share[u] for u in used) >= 0.5:
        _SEP[0] = max(used, key=lambda u: share[u])
        _SPLIT[0] = re.compile('[%s]+' % ''.join(re.escape(u) for u in used)) if len(used) > 1 else None
        words = ' / '.join('%s ("%s")' % (_SEP_WORD[u], u) for u in sorted(used, key=lambda u: -share[u]))
        return '%s-separated' % words if len(used) == 1 else 'separated by %s' % words
    # no separator: split letters from numbers (A1000 -> A | 1000; ACT1020B -> ACT | 1020 | B)
    _SEP[0] = ''
    _SPLIT[0] = 'runs'
    return 'letters-and-numbers'


def _segs(i):
    i = (i or '').strip()
    if _SPLIT[0] == 'runs':
        return re.findall(r'[A-Za-z]+|\d+', i) or [i]
    if _SPLIT[0] is not None:
        return [t for t in _SPLIT[0].split(i) if t] or [i]
    return i.split(_SEP[0])


def _is_serial(tok):
    return bool(re.fullmatch(r'[A-Za-z]{0,2}\d{2,}[A-Za-z]?', tok or ''))


_STOP_ABBR = {'of', 'and', 'the', 'for', 'to', 'in', 'on', 'at', 'a', 'by', 'with', '&'}


def _subseq(t, w):
    it = iter(w)
    return all(ch in it for ch in t)


def _acode(a, dim):
    return (a.get('activity_codes') or {}).get(dim)


def activity_id_analysis(activities, code_types=None):
    """Return the §12 payload (see module docstring). Generic and None-safe."""
    acts = [a for a in (activities or []) if a.get('id')]
    code_dims = list(code_types or [])
    if not acts:
        return {'intro': INTRO, 'anatomy': None, 'blocks': []}
    coding = _detect_sep([a['id'] for a in acts])

    # ── GENERIC per-token meaning: dominant activity-code value among the activities that
    #    carry that token as a segment, else the dominant significant word in their names. ──
    _tok_cache = {}
    _Nall = len(acts)
    _dim_val_global = {}                              # (dim, value) -> fraction of ALL activities
    for _dim in code_dims:
        _c = Counter(_acode(a, _dim) for a in acts if _acode(a, _dim))
        for _v, _n in _c.items():
            _dim_val_global[(_dim, _v)] = _n / max(_Nall, 1)

    # WBS names count as candidate meanings too (many IDs are built from the WBS)
    _WBS = '(WBS)'

    def _vals(a, dim):
        if dim == _WBS:
            return [x.strip() for x in re.split(r'\s*>\s*', a.get('wbs_path') or '') if x.strip()]
        v = _acode(a, dim)
        return [v] if v else []
    _glob = Counter()
    for _a in acts:
        for _dim in list(code_dims) + [_WBS]:
            for _v in set(_vals(_a, _dim)):
                _glob[(_dim, _v)] += 1

    def _abbrev(tok, value):
        """How much ``tok`` reads like an abbreviation of ``value`` (0..1): BAT -> Batch Area,
        SOL -> Soil Replacement, SS -> Steel Structure, EXC -> Execution, CB3C -> CB3C Conveyor."""
        t = re.sub(r'[^a-z0-9]', '', tok.lower())
        if len(t) < 2:
            return 0.0
        words = [w for w in re.findall(r'[a-z0-9]+', value.lower()) if w not in _STOP_ABBR]
        if not words:
            return 0.0
        if any(w == t for w in words) or words[0].startswith(t):
            return 1.0
        if any(w.startswith(t) for w in words):
            return 0.95
        initials = ''.join(w[0] for w in words)
        if len(t) >= 2 and (initials == t or initials.startswith(t)):
            return 0.9
        for w in words:                                  # SOL in "soil", BLD in "building"
            if len(t) >= 3 and w[0] == t[0] and _subseq(t, w):
                return 0.8
        return 0.0

    def _name_evidence(value, holders):
        """Share of the activities carrying the segment whose NAME mentions the value (any of its
        significant words) - the check that a meaning fits what those activities actually are."""
        words = [w for w in re.findall(r'[a-z]{4,}', (value or '').lower()) if w not in _STOP_ABBR]
        if not words or not holders:
            return 0.0
        hit = sum(1 for a in holders if any(w[:5] in (a.get('name') or '').lower() for w in words))
        return hit / len(holders)

    def token_meaning(tok, pool, siblings=True):
        """The meaning of one ID segment, read from the ACTIVITY CODES (Ibrahim, comment 103):
        among the activities whose ID carries the segment, the code value (or WBS name) they
        share - preferring a value the segment abbreviates (BAT -> Batch Area, SOL -> Soil
        Replacement Works). Else the dominant word in their names. Returns (meaning, dim|None)."""
        key = (tok, id(pool), siblings)
        if key in _tok_cache:
            return _tok_cache[key]
        holders = [a for a in pool if tok in _segs(a['id'])]
        best, best_score = (tok, None), 0.0
        if holders:
            n = len(holders)
            npool = max(len(pool), 1)
            for dim in list(code_dims) + [_WBS]:
                vals = Counter(v for a in holders for v in set(_vals(a, dim)))
                grp = Counter(v for a in pool for v in set(_vals(a, dim))) if len(holders) < len(pool) else None
                for v, k in vals.most_common(12):
                    if grp is not None and grp[v] / npool >= 0.8 and (siblings or not _abbrev(tok, v)):
                        continue        # shared by the whole group (a lone code may still spell it: CVL = Civil)
                    prec = k / n                                   # share of the holders with v
                    rec = k / max(_glob.get((dim, v), k), 1)       # share of v's activities carrying tok
                    ab = _abbrev(tok, v) if prec >= 0.5 else 0.0     # the letters count only if the activities agree
                    if prec < 0.4:
                        continue
                    score = prec * (0.5 + 0.5 * rec) + ab * 2.0 + 0.6 * _name_evidence(v, holders)
                    if dim == _WBS:
                        score *= 0.9                               # an activity code says it first
                    if score > best_score:
                        base = re.split(r'\s*[-–]\s', v, 1)[0].strip() if not ab else v.strip()
                        best, best_score = (base, dim), score
            if best[1] is None:                                # no code fits -> name words
                words = Counter(w.title() for a in holders
                                for w in re.findall(r'[A-Za-z]{3,}', a.get('name') or '')
                                if w.lower() not in _STOP)
                if words:
                    best = (words.most_common(1)[0][0], None)
        _tok_cache[key] = best
        return best

    def column_reading(pos, toks, reps):
        """The SMART step (Ibrahim, comment 103): decide which activity code a whole segment
        POSITION stands for, by comparing its sibling values. In ARC / CON / SS the code whose
        values differ between the siblings (Trade: Arc. Works / Civil Works / Steel Structure
        Works) is the one the position encodes - not a code all of them share (Type of Work:
        Construction). Returns ({token: (meaning, dim)}, dim) or (None, None)."""
        by_tok = {}
        for t in toks[:16]:
            h = [a for a in reps if len(_segs(a['id'])) > pos and _segs(a['id'])[pos] == t]
            if h:
                by_tok[t] = h
        if len(by_tok) < 2:
            return None, None
        best, best_score = None, 0.0
        nrep = max(len(reps), 1)
        for dim in list(code_dims) + [_WBS]:
            picks, precs, abbs = {}, [], []
            grp = Counter(v for a in reps for v in set(_vals(a, dim)))
            for t, h in by_tok.items():
                c = Counter(v for a in h for v in set(_vals(a, dim)))
                # a value the WHOLE group shares (Construction, Submittal…) can't be what ONE part means
                c = Counter({v: k for v, k in c.items() if grp[v] / nrep < 0.8}) or (c if len(c) == 1 else Counter())
                if not c:
                    precs.append(0.0); abbs.append(0.0); continue
                # within this code, the value the token abbreviates wins, else the most shared one
                v, k = max(c.items(), key=lambda kv: (_abbrev(t, kv[0]) > 0 and kv[1] / len(h) >= 0.5, kv[1]))
                picks[t] = v
                precs.append(k / len(h))
                abbs.append(1.0 if (_abbrev(t, v) and k / len(h) >= 0.5) else 0.0)
                abbs[-1] += 0.5 * _name_evidence(v, h)
            if not picks:
                continue
            distinct = len(set(picks.values())) / len(by_tok)
            mprec = sum(precs) / len(precs)
            score = (mprec * distinct + 0.35 * (sum(abbs) / len(abbs))) * (0.8 if dim == _WBS else 1.0)
            if mprec >= 0.5 and distinct >= 0.6 and score > best_score:
                best, best_score = (dim, picks), score
        if not best:
            return None, None
        dim, picks = best
        return {t: (v, dim) for t, v in picks.items()}, dim

    def dim_role(dim):
        if not dim:
            return None
        dl = dim.lower()
        if any(h in dl for h in AREA_HINT):
            return 'area'
        if any(h in dl for h in WORK_HINT):
            return 'work'
        return 'other'

    # ── GENERIC family detection: first token, split construction by the Type-of-Works code ──
    def trade_of(a):
        return _acode(a, 'Type of Works') or _acode(a, 'Trade Design')

    fam = OrderedDict()
    for a in acts:
        p = _segs(a['id'])
        # the family = the first coded (non-number) segment; IDs that are only numbers form one family
        f = next((t for t in p if not _is_serial(t) and not t.isdigit()), None) or 'ALL'
        if f == 'CONS':
            f = 'CONS|' + (trade_of(a) or 'Other')
        fam.setdefault(f, []).append(a)

    # order families: milestones/inputs/design/eng/proc first (few segs / non-CONS), then CONS trades
    def fam_sort(kv):
        k, l = kv
        cons = k.startswith('CONS|')
        return (1 if cons else 0, -len(l))
    families = sorted(fam.items(), key=fam_sort)

    def family_title(key, members):
        if key.startswith('CONS|'):
            tr = key.split('|', 1)[1]
            return 'Construction — %s' % (tr if tr != 'Other' else 'other works')
        # what the activity codes say this group is (SDS -> Shop Drawing Submittal, DE -> Design)
        code_m, code_dim = token_meaning(key, members, siblings=False) if key != 'ALL' else (None, None)
        if code_dim is not None and code_m and code_m != key:
            return code_m
        # else: label by the most common 2-word PHRASE (bigram) in the names
        # that names the deliverable/stage (e.g. "Detailed Design", "Shop Drawing"), skipping area
        # words — a phrase is far more stable than picking two frequent single words.
        bg = Counter()
        for a in members:
            ws = [w.title() for w in re.findall(r'[A-Za-z]{3,}', a.get('name') or '')
                  if w.lower() not in _STOP]
            for i in range(len(ws) - 1):
                bg[(ws[i], ws[i + 1])] += 1
        if bg:
            (w1, w2), n = bg.most_common(1)[0]
            if n >= max(3, 0.25 * len(members)):
                return '%s %s' % (w1, w2)
        m, _ = token_meaning(key, members)
        return m if m and m != key else ('%s activities' % key)

    def build_block(key, members):
        lens = Counter(len(_segs(a['id'])) for a in members)
        modal = lens.most_common(1)[0][0]
        reps = [a for a in members if len(_segs(a['id'])) == modal] or members
        sample = reps[0]['id']
        cols = []
        npos = modal
        # the serial is the segment that is a number in most IDs - the LAST one in a dot coding
        # (CONS.PL.S1.1010), the 2nd in Saint Gobain's dash coding (EX-1000-GC-CON-BAT)
        share = [sum(1 for a in reps if _is_serial(_segs(a['id'])[pos])) / len(reps) for pos in range(npos)]
        serial_pos = npos - 1
        if share[serial_pos] < 0.6:
            # the number can sit anywhere (EX-1000-GC…, 1000-CIV-B1); none at all = free-text IDs
            cand = max(range(npos), key=lambda k: (share[k], k))
            serial_pos = cand if share[cand] >= 0.6 else (serial_pos if share[serial_pos] >= 0.3 else None)
        for pos in range(npos):
            toks = sorted({_segs(a['id'])[pos] for a in reps if len(_segs(a['id'])) > pos})
            if pos == serial_pos:                                # the serial segment
                ex_serial = _segs(sample)[pos]                   # e.g. "1010", or "A1020" (letter-prefixed)
                cols.append((ex_serial, 'Sequencing serial — P6 sequence number ordering the '
                                        'activities within the group', 'serial'))
                continue
            # role: first = stage; else by the dominant dimension of the tokens' meanings
            roles = Counter()
            meanings = OrderedDict()
            pairs = []
            col, _cdim = column_reading(pos, toks, reps) if pos > 0 else (None, None)
            for t in toks[:8]:
                if col and t in col and _abbrev(t, col[t][0]):
                    mn, dim = col[t]
                elif col and t in col:
                    mn, dim = col[t]
                    tm = token_meaning(t, members)
                    if tm[1] is not None and _abbrev(t, tm[0]):
                        mn, dim = tm                              # the code that spells it wins
                else:
                    mn, dim = token_meaning(t, members, siblings=len(toks) > 1)
                    if pos > 0 and len(toks) == 1 and dim is not None and not _abbrev(t, mn):
                        # one code on every activity of the group and no activity code spells it:
                        # it carries no information of its own - say so instead of guessing
                        mn, dim = 'fixed code for the whole group (not found in the activity codes)', None
                meanings[mn] = None
                pairs.append((t, mn))
                roles[dim_role(dim)] += 1
            if pos == 0 or (pos == 1 and serial_pos == 0):
                role = 'stage'
            else:
                r = roles.most_common(1)[0][0]
                role = r if r in ('area', 'work') else 'step'
            code_str = '/'.join(toks[:6]) + ('…' if len(toks) > 6 else '')
            mean_str = (pairs[0][1] if len(pairs) == 1 else
                        ' · '.join('%s = %s' % (t, m) for t, m in pairs[:6]) + (' …' if len(toks) > 6 else '')) or code_str
            cols.append((code_str, mean_str, role))
        note = 'For %s activities' % family_title(key, members)
        return {'title': family_title(key, members), 'sample': sample, 'cols': cols,
                'note': note, 'count': len(members)}

    def _cols_out(cols):
        return [{'code': c, 'meaning': m, 'role': r} for (c, m, r) in cols]

    blocks_raw = [build_block(k, m) for k, m in families if len(m) >= 3]  # skip 1-off stray ids
    if not blocks_raw:
        # no repeating ID family (e.g. plain numbers, or every ID unique): still explain the coding
        # from ALL the activities, so the section is never empty for any project
        blocks_raw = [build_block('ALL', acts)]
        blocks_raw[0]['title'] = 'All activities'
        blocks_raw[0]['note'] = 'For all activities'

    # ── the colour-coded anatomy: a representative construction family (Civil Works), else the
    #    smallest family (blocks_raw[-1]). Ported verbatim; None-safe when no family qualifies. ──
    if 'CONS|Civil Works' in fam:
        anatomy_raw = build_block('CONS|Civil Works', fam['CONS|Civil Works'])
    elif blocks_raw:
        # any other coding: the biggest ID family is the one a reader meets most
        anatomy_raw = max(blocks_raw, key=lambda b: b['count'])
    else:
        anatomy_raw = None

    anatomy = None
    if anatomy_raw:
        anatomy = {'sample': anatomy_raw['sample'], 'cols': _cols_out(anatomy_raw['cols'])}

    blocks = [{'title': b['title'], 'sample': b['sample'], 'cols': _cols_out(b['cols']),
               'note': b['note'], 'count': b['count']} for b in blocks_raw]

    intro = INTRO.replace('dot-separated', coding)
    if anatomy:
        anatomy['intro'] = ANATOMY_INTRO.replace('dot-separated', coding)
    return {'intro': intro, 'anatomy': anatomy, 'blocks': blocks}
