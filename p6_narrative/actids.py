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


def _segs(i):
    return (i or '').split('.')


def _acode(a, dim):
    return (a.get('activity_codes') or {}).get(dim)


def activity_id_analysis(activities, code_types=None):
    """Return the §12 payload (see module docstring). Generic and None-safe."""
    acts = [a for a in (activities or []) if a.get('id')]
    code_dims = list(code_types or [])
    if not acts:
        return {'intro': INTRO, 'anatomy': None, 'blocks': []}

    # ── GENERIC per-token meaning: dominant activity-code value among the activities that
    #    carry that token as a segment, else the dominant significant word in their names. ──
    _tok_cache = {}
    _Nall = len(acts)
    _dim_val_global = {}                              # (dim, value) -> fraction of ALL activities
    for _dim in code_dims:
        _c = Counter(_acode(a, _dim) for a in acts if _acode(a, _dim))
        for _v, _n in _c.items():
            _dim_val_global[(_dim, _v)] = _n / max(_Nall, 1)

    def token_meaning(tok, pool):
        """A DISTINCTIVE, data-grounded meaning for a segment code: the activity-code value that
        is specific to the code's holders (held by most of them, but NOT shared by most of the
        whole schedule, so a global 'Phase 1' is rejected in favour of 'Pile Works'); else the
        dominant significant word in those activities' names. Returns (meaning, dim|None)."""
        if tok in _tok_cache:
            return _tok_cache[tok]
        holders = [a for a in pool if tok in _segs(a['id'])]
        best, best_score = (tok, None), 0.0
        if holders:
            for dim in code_dims:
                vals = Counter(_acode(a, dim) for a in holders if _acode(a, dim))
                if not vals:
                    continue
                v, n = vals.most_common(1)[0]
                if not v:
                    continue
                frac_in = n / len(holders)
                gfrac = _dim_val_global.get((dim, v), 1.0)     # how global this value is
                if frac_in >= 0.6 and gfrac < 0.45:            # specific to this token, not global
                    score = frac_in * (1.0 - gfrac)
                    if score > best_score:
                        base = re.split(r'\s*[-–]\s', v, 1)[0].strip()   # drop " - <area>" suffix
                        best, best_score = (base, dim), score
            if best[1] is None:                                # no distinctive code → name words
                words = Counter(w.title() for a in holders
                                for w in re.findall(r'[A-Za-z]{3,}', a.get('name') or '')
                                if w.lower() not in _STOP)
                if words:
                    best = (words.most_common(1)[0][0], None)
        _tok_cache[tok] = best
        return best

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
        p = _segs(a['id']); f = p[0]
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
        # non-construction family: label by the most common 2-word PHRASE (bigram) in the names
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
        for pos in range(npos):
            toks = sorted({_segs(a['id'])[pos] for a in reps if len(_segs(a['id'])) > pos})
            if pos == npos - 1:                                  # the LAST segment is ALWAYS the serial
                ex_serial = _segs(sample)[-1]                    # e.g. "1010", or "A1020" (letter-prefixed)
                cols.append((ex_serial, 'Sequencing serial — P6 sequence number ordering the '
                                        'activities within the group', 'serial'))
                continue
            # role: first = stage; else by the dominant dimension of the tokens' meanings
            roles = Counter()
            meanings = OrderedDict()
            for t in toks[:8]:
                mn, dim = token_meaning(t, members)
                meanings[mn] = None
                roles[dim_role(dim)] += 1
            if pos == 0:
                role = 'stage'
            else:
                r = roles.most_common(1)[0][0]
                role = r if r in ('area', 'work') else 'step'
            code_str = '/'.join(toks[:6]) + ('…' if len(toks) > 6 else '')
            mean_str = ' / '.join(list(meanings)[:6]) or code_str
            cols.append((code_str, mean_str, role))
        note = 'For %s activities' % family_title(key, members)
        return {'title': family_title(key, members), 'sample': sample, 'cols': cols,
                'note': note, 'count': len(members)}

    def _cols_out(cols):
        return [{'code': c, 'meaning': m, 'role': r} for (c, m, r) in cols]

    blocks_raw = [build_block(k, m) for k, m in families if len(m) >= 3]  # skip 1-off stray ids

    # ── the colour-coded anatomy: a representative construction family (Civil Works), else the
    #    smallest family (blocks_raw[-1]). Ported verbatim; None-safe when no family qualifies. ──
    if 'CONS|Civil Works' in fam:
        anatomy_raw = build_block('CONS|Civil Works', fam['CONS|Civil Works'])
    elif blocks_raw:
        anatomy_raw = blocks_raw[-1]
    else:
        anatomy_raw = None

    anatomy = None
    if anatomy_raw:
        anatomy = {'sample': anatomy_raw['sample'], 'cols': _cols_out(anatomy_raw['cols'])}

    blocks = [{'title': b['title'], 'sample': b['sample'], 'cols': _cols_out(b['cols']),
               'note': b['note'], 'count': b['count']} for b in blocks_raw]

    return {'intro': INTRO, 'anatomy': anatomy, 'blocks': blocks}
