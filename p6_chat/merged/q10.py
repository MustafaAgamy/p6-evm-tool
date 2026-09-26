"""q10 — Engineering & procurement: design status, critical deliverables, and long-lead items.

Covers: engineering in isolation (each design / procurement line's own SPI, read against its weight), the
design submittal register, whether late design threatens construction or sits inside float, which IFC
deliverables are critical, whether late client / consultant information is driving the delay, where
procurement stands, long-lead items ranked by float, required-on-site dates and delivery-slip impact, and
the two checks planners miss (install-before-delivery, lead time hidden in lags) — for ANY project.

Everything is derived from F (DB facts) and N (network re-read). Design / procurement lines are found by
their category names; the input that releases a design line, its key date and the finish-chain work named
for the same scope are tied by the names in the file — never by anything project-specific.
"""
import re
from datetime import datetime

from . import _kit2 as K

_ENG = ('design', 'engineer', 'ifc', 'drawing', 'detailing')
_PROC = ('procure', 'purchas', 'supply', 'vendor', 'long lead', 'long-lead', 'material', 'fabricat', 'manufactur')
_ROMAN = {'i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x'}
_GENERIC = {'phase', 'stage', 'package', 'design', 'engineering', 'engineer', 'procurement', 'and', 'of', 'the',
            'for', 'to', 'from', 'work', 'all', 'general', 'detailed', 'schematic', 'construction', 'completion'}
_DESIGN_INPUT = re.compile(r'design|drawing|layout|\bifc\b|detail', re.I)
_ITEM_NAME = re.compile(r'\bdeliver(?:y|ies|ed)?\s+(?:for|of)\b|shipment|free[- ]issue|furnished|supply of', re.I)
_INFO_NAME = re.compile(r'approv|design|drawing|layout|\bloads?\b|information|\bdata\b|review|comment|\blevel\b'
                        r'|survey|permit|offer', re.I)
_ITEM_WBS = re.compile(r'deliver|shipment|material|equipment|steel|free[- ]issue|furnished', re.I)
_DELIVERY = re.compile(r'\bdeliver|shipment|\bsupply\b|arrival|on site|\bros\b', re.I)
_WORDS = {1: 'One', 2: 'Two', 3: 'Three', 4: 'Four', 5: 'Five', 6: 'Six', 7: 'Seven', 8: 'Eight', 9: 'Nine',
          10: 'Ten'}


# ── small helpers ──────────────────────────────────────────────────────────────
def _clean(s):
    return ' '.join(str(s or '').split())


def _short(s, n=46):
    s = _clean(s)
    if len(s) <= n:
        return s
    return s[:n].rsplit(' ', 1)[0].rstrip(' ,;:-&') + '…'


def _num(n, cap=False):
    w = _WORDS.get(n)
    return (w if cap else w.lower()) if w else str(n)


def _join(items):
    items = [i for i in items if i]
    if len(items) <= 1:
        return ''.join(items)
    return ', '.join(items[:-1]) + ' and ' + items[-1]


def _sg(n):
    """Signed whole number with a real minus: +58 / −48 / 0."""
    if n is None:
        return '—'
    n = int(round(n))
    return f"+{n}" if n > 0 else (f"−{abs(n)}" if n < 0 else '0')


def _date(s):
    try:
        return datetime.strptime(s, '%d-%b-%Y')
    except (TypeError, ValueError):
        return None


def _toks(s):
    out = set()
    for t in re.findall(r'[a-z0-9]+', str(s or '').lower()):
        out.add(t[:-1] if len(t) > 3 and t.endswith('s') else t)
    return out


def _distinct(name):
    """The words that make a line's name specific (not 'phase', 'design', roman numerals…)."""
    return {t for t in _toks(name) if t not in _GENERIC and t not in _ROMAN and len(t) > 1 and not t.isdigit()}


def _kind(d):
    n = (d.get('name') or '').lower()
    if any(k in n for k in _ENG):
        return 'design'
    if any(k in n for k in _PROC):
        return 'procurement'
    return None


def _input_kind(x):
    """Client input type: 'item' (something the client supplies), 'info' (approval / information), 'access'."""
    n, w = _clean(x.get('name')), x.get('wbs') or ''
    if _ITEM_NAME.search(n):
        return 'item'
    if _INFO_NAME.search(n):
        return 'info'
    if _ITEM_WBS.search(w):
        return 'item'
    return 'access'


def _lbl(x):
    return f"{x['id']} {_clean(x['name'])}"


def _isp(x):
    try:
        p, a = float(x.get('planned')), float(x.get('actual'))
    except (TypeError, ValueError):
        return None
    return a / p if p > 0 else None


def _front(chain):
    """The WBS front at the head of the finish chain (last two WBS levels)."""
    if not chain:
        return None
    parts = [p for p in (chain[0].get('wbs') or '').split(' / ') if p]
    return ' / '.join(parts[-2:]) if parts else None


def build(F, N, role):
    nok = bool(N and N.get('ok'))
    d = F.get('delay_days')
    behind, ahead = (d or 0) > 0, (d or 0) < 0
    spi = F.get('spi')
    drv = K.main_driver(F)
    dd = F.get('data_date') or ((N or {}).get('data_date') if nok else None)
    fin = (N.get('finish_milestone') or {}) if nok else {}
    ftf = N.get('finish_tf') if nok else None
    has_audit = bool(F.get('has_audit'))
    audit = F.get('audit') or {}
    thinking = []

    ds = F.get('disciplines') or []
    up = [x for x in ds if _kind(x)]
    field = [x for x in ds if not _kind(x)]
    design = [x for x in up if _kind(x) == 'design']
    proc = [x for x in up if _kind(x) == 'procurement']
    drv_up = bool(drv and _kind(drv))

    acts = ((N.get('kb_view') or {}).get('activities') or []) if nok else []
    client = list(N.get('client_inputs') or []) if nok else []
    client_ids = {x['id'] for x in client}
    open_client = [x for x in client if not x.get('done')]
    late_open = list(N.get('client_inputs_late_open') or []) if nok else []
    late_done = list(N.get('client_inputs_late_done') or []) if nok else []
    chain = list(N.get('chain') or []) if nok else []
    chain_ids = {x['id'] for x in chain}
    milestones = list(N.get('milestones') or []) if nok else []

    def line_acts(x):
        nm = (x.get('name') or '').strip().lower()
        return [a for a in acts if (a.get('wbs_path') or '').split(' / ')[0].strip().lower() == nm]

    def ifc_count(x):
        return sum(1 for a in line_acts(x) if 'ifc' in ((a.get('name') or '') + ' ' + (a.get('wbs_path') or '')).lower())

    # ── tie every upstream line to its key date, the inputs that release it and finish-chain work ─────
    def assess(x):
        a = {'d': x, 'inputs': [], 'ms': None, 'hits': [], 'tf': None}
        kind, dt, full = _kind(x), _distinct(x['name']), _toks(x['name']) - {'and'}
        if nok:
            for m in milestones:
                if not m.get('done') and m['id'] not in client_ids and full and full <= _toks(m['name']):
                    a['ms'] = m
                    break
            if dt:
                for c in open_client:
                    if not (dt & _toks(c['name'])):
                        continue
                    k = _input_kind(c)
                    if (kind == 'design' and k == 'info' and _DESIGN_INPUT.search(c['name'])) or \
                            (kind == 'procurement' and k == 'item'):
                        a['inputs'].append(c)
                a['hits'] = sorted([c for c in chain if dt & _toks(c['name']) and c.get('tf') is not None],
                                   key=lambda c: (c['tf'], -((_date(c['finish']) or datetime.min).toordinal())))
        if (x.get('actual') or 0) >= 100:
            a['state'] = 'complete'
        elif (x.get('gap') or 0) <= 0:
            a['state'] = 'on plan'
        else:
            neg_in = [c for c in a['inputs'] if c.get('tf') is not None and c['tf'] < 0]
            if neg_in:
                a['state'], a['tf'] = 'threat', min(c['tf'] for c in neg_in)
            elif a['ms'] and a['ms'].get('tf') is not None:
                a['tf'] = a['ms']['tf']
                a['state'] = 'threat' if a['tf'] < 0 else 'float'
            elif a['hits']:
                a['state'], a['tf'] = 'linked', a['hits'][0]['tf']
            else:
                a['state'] = 'unknown'
        return a

    A = {x['name']: assess(x) for x in up}
    threats = sorted([a for a in A.values() if a['state'] == 'threat'], key=lambda a: a['tf'])
    floaty = [a for a in A.values() if a['state'] == 'float']
    matched_ids = {c['id'] for a in A.values() for c in a['inputs']}
    design_inputs_late = [c for c in late_open if _input_kind(c) == 'info' and _DESIGN_INPUT.search(c['name'])]
    unmatched_design = [c for c in design_inputs_late if c['id'] not in matched_ids]

    complete = [x for x in design if (x.get('actual') or 0) >= 100]
    behind_design = sorted([x for x in design if (x.get('gap') or 0) > 0], key=lambda x: -(x.get('gap') or 0))
    behind_up = sorted([x for x in up if (x.get('gap') or 0) > 0], key=lambda x: -(x.get('gap') or 0))
    thinking.append(f"Split the {len(ds)} weighted categories into {len(up)} design/procurement "
                    f"line{'s' if len(up) != 1 else ''} and {len(field)} field line{'s' if len(field) != 1 else ''}, "
                    "and read each line's own SPI" if up else
                    f"Looked for design, engineering and procurement lines among the {len(ds)} weighted categories — "
                    "none is broken out")

    # long-lead / delivery items (client-furnished first, then contractor deliveries named as milestones)
    items = [c for c in open_client if _input_kind(c) == 'item']
    items += [m for m in milestones if not m.get('done') and m['id'] not in client_ids and _DELIVERY.search(m['name'])
              and m['id'] not in {i['id'] for i in items}]
    items.sort(key=lambda x: (x['tf'] if x.get('tf') is not None else 10 ** 6, _date(x.get('finish')) or datetime.max))
    items_client = [i for i in items if i['id'] in client_ids]
    late_items = [i for i in items if (i.get('slip_wd') or 0) > 0]
    pinned = [i for i in items if i.get('tf') == 0 and (i.get('slip_wd') or 0) == 0]
    front = _front(chain)

    # ── verdict ─────────────────────────────────────────────────────────────────
    if not up:
        head = ("This file doesn't break engineering or procurement out as their own weighted lines, so I can't isolate "
                "their SPI from the stored numbers")
        if ahead or not behind:
            mg = max((x.get('gap') or 0) for x in ds) if ds else None
            head += (f"; none of the categories it does carry is more than {max(0, mg)} point{'s' if mg != 1 else ''} "
                     "behind plan." if mg is not None and mg <= 5 else '.')
            if ahead:
                head = f"Ahead by about {K.wd(d)} to completion (SPI {K.ratio(spi)}). " + head
        else:
            head += (f"; the slip is carried by {drv['name']}." if drv else '.')
    elif drv_up:
        head = (f"Engineering/procurement is where the weighted gap sits: {drv['name']} is {drv['actual']}% done against "
                f"{drv['planned']}% planned on {round((drv.get('weight') or 0) * 100)}% of the weight — chase it upstream.")
    elif behind:
        head = f"Engineering and procurement aren't what sets the ~{round(d)} wd" + (f" — {drv['name']} is" if drv else '') + '.'
        bits = []
        for a in threats[:2]:
            x = a['d']
            held = (f"held by a late client input on a {_sg(a['tf'])} wd path" if a['inputs'] else
                    f"its key date on {_sg(a['tf'])} wd float")
            bits.append(f"{x['name']} ({x['actual']}% done vs {x['planned']}%, {held})")
        if pinned:
            bits.append(f"{len(pinned)} {'client-furnished ' if all(p['id'] in client_ids for p in pinned) else ''}"
                        f"deliver{'ies' if len(pinned) != 1 else 'y'} with no float left")
        elif late_items:
            bits.append(f"{len(late_items)} late, still-open deliver{'ies' if len(late_items) != 1 else 'y'}")
        if bits:
            head += f" The threat{'s' if len(bits) > 1 else ''} in them {'are' if len(bits) > 1 else 'is'} " + _join(bits)
            head += (", not contractor buying." if proc and all((x.get('gap') or 0) <= 5 for x in proc) else '.')
        elif behind_up and not nok:
            bd = behind_design or behind_up
            head += (" " + _join([f"{x['name']} ({x['actual']}% vs {x['planned']}%)" for x in bd[:2]])
                     + f" {'are' if len(bd[:2]) > 1 else 'is'} behind plan; whether "
                     + f"{'they reach' if len(bd[:2]) > 1 else 'it reaches'} the finish needs the schedule file.")
        elif behind_up:
            head += (" " + _join([x['name'] for x in behind_up[:2]])
                     + f" {'are' if len(behind_up[:2]) > 1 else 'is'} behind, but nothing in the file ties "
                     + f"{'them' if len(behind_up[:2]) > 1 else 'it'} to the finish by name.")
    elif ahead:
        head = (f"Ahead by about {K.wd(d)} to completion, and nothing upstream is holding it back"
                if not behind_up else
                f"Ahead by about {K.wd(d)} to completion overall; upstream, {_join([x['name'] for x in behind_up[:2]])} "
                f"{'are' if len(behind_up[:2]) > 1 else 'is'} behind plan but not driving the date") + '.'
    else:
        head = "On the planned finish; " + (f"{_join([x['name'] for x in behind_up[:2]])} lag upstream." if behind_up
                                            else "every design and procurement line is at or ahead of plan.")

    # ── pills ───────────────────────────────────────────────────────────────────
    pills = []
    if not up:
        pills.append(K.pill(f"SPI {K.ratio(spi)}" + (f" · {K.signed(d)}" if d is not None else ''),
                            'success' if (spi or 0) >= 1 else ('warning' if (spi or 0) >= 0.9 else 'danger')))
        pills.append(K.pill('No design / procurement line weighted', 'neutral'))
    if complete:
        nm = ' & '.join(x['name'] for x in complete)
        pills.append(K.pill(f"{nm} 100%" if len(nm) <= 44 else f"{len(complete)} design lines 100%", 'success'))
    shown = (threats + floaty)[:2]
    shown += [A[x['name']] for x in behind_design if A[x['name']] not in shown][:max(0, 2 - len(shown))]
    for a in shown:
        x = a['d']
        tail = (' · held by client' if a['inputs'] and a['state'] == 'threat' else
                f" · {_sg(a['tf'])} wd float" if a['tf'] is not None else '')
        pills.append(K.pill(f"{_short(x['name'], 26)} {x['actual']}% of {x['planned']}%{tail}",
                            'danger' if a['state'] == 'threat' else 'warning'))
    if len(design_inputs_late) >= 1:
        top = sorted(design_inputs_late, key=lambda c: -(c.get('slip_wd') or 0))[:2]
        pills.append(K.pill(' · '.join(f"{_short(c['name'], 22)} +{c['slip_wd']} wd" for c in top), 'danger'))
    for x in proc[:1]:
        pills.append(K.pill(f"{_short(x['name'], 30)} {x['actual']}%", 'success' if (x.get('gap') or 0) <= 5 else 'warning'))
    if items_client:
        pills.append(K.pill('long-lead risk = client-furnished items', 'accent'))
    elif items:
        pills.append(K.pill(f"{len(items)} open delivery items", 'accent'))

    # ── 1. engineering in isolation ─────────────────────────────────────────────
    p1 = []
    if design:
        lead = []
        if complete:
            lead.append(f"{_join([x['name'] for x in complete])} {'is' if len(complete) == 1 else 'are'} complete.")
        if behind_design:
            lead.append("What's behind is " + _join([f"{x['name']} ({x['actual']}% against {x['planned']}% planned)"
                                                     for x in behind_design[:4]]) + '.')
            dthreat = [a for a in threats if _kind(a['d']) == 'design']
            if dthreat:
                a = dthreat[0]
                why = (f"it can't move until the client input that releases it arrives, and "
                       f"{_clean(a['inputs'][0]['name'])} is {_sg(a['inputs'][0]['slip_wd'])} wd late on a "
                       f"{_sg(a['inputs'][0]['tf'])} wd path" if a['inputs'] else
                       f"its key date, {a['ms']['name']}, sits on {_sg(a['tf'])} wd float")
                only = 'Only ' if len(dthreat) == 1 and len(behind_design) > 1 else ''
                lead.append(f"{only}{a['d']['name']} threatens the finish: {why}.")
            for a in [a for a in floaty if _kind(a['d']) == 'design'][:2]:
                lead.append(f"{a['d']['name']} is {'further ' if dthreat else ''}behind on paper but carries "
                            f"{_sg(a['tf'])} wd float.")
        elif not complete:
            lead.append("Every design line is at or ahead of its planned progress.")
        p1.append('**' + ' '.join(lead) + '**')
        if behind_design:
            isp = [f"{K.ratio(_isp(x))} for {x['name']}" for x in behind_design[:4] if _isp(x) is not None]
            w = max((x.get('weight') or 0) for x in behind_design)
            txt = (f"On their own, the open design line{'s are' if len(behind_design) > 1 else ' is'} the worst on the job"
                   if behind_design[0]['gap'] >= max((x.get('gap') or 0) for x in ds) else
                   f"On their own, the open design line{'s' if len(behind_design) > 1 else ''} "
                   f"{'are' if len(behind_design) > 1 else 'is'} well behind")
            txt += (f". Isolated SPI (done ÷ planned for that line alone) is {_join(isp)}, against {K.ratio(spi)} overall."
                    if isp else '.')
            if w <= 0.05:
                txt += (f" At {round(w * 100)}% weight{' each' if len(behind_design) > 1 else ''} they barely move the "
                        "EVM numbers. That is exactly why weight is the wrong lens for design: what matters is the "
                        "construction each line releases.")
            else:
                top = behind_design[0]
                txt += (f" At {round((top.get('weight') or 0) * 100)}% weight, {top['name']} moves the headline too — "
                        f"about {(top.get('weight') or 0) * (top.get('gap') or 0):.1f} of the "
                        f"{max(0, (F.get('planned_pct') or 0) - (F.get('actual_pct') or 0))} points the job is behind.")
            p1.append(txt)
    elif proc:
        p1.append(f"The weighted categories carry no separate design or engineering line — only procurement "
                  f"({_join([x['name'] for x in proc])}) — so engineering can't be isolated from the stored numbers.")
    else:
        p1.append(f"The weighted categories in this file ({_join([x['name'] for x in ds][:6]) or 'none stored'}) don't "
                  "break design, engineering or procurement out as their own lines, so I can't isolate engineering's "
                  "own SPI from the stored numbers. Code the design and procurement WBS as their own categories (or "
                  "run Update Analysis by activity code) and this answer splits them out.")
        if acts:
            nd = sum(1 for a in acts if re.search(r'design|engineer|drawing|\bifc\b', a.get('wbs_path') or '', re.I))
            if nd:
                p1.append(f"The file itself does hold {nd} activities under design/engineering WBS headings — they just "
                          "aren't weighted as a separate line.")
    note1 = 'Category weights and progress from the file.'
    ifc_done = [(x, ifc_count(x)) for x in complete]
    ifc_done = [(x, n) for x, n in ifc_done if n]
    if ifc_done:
        note1 += ' ' + ' '.join(f"The {x['name']} IFC packages ({n} activities) are issued with the line at 100%."
                                for x, n in ifc_done[:2])
    subs = [r for r in (F.get('submittals') or []) if isinstance(r, dict)]
    shop_done = [r for r in subs if 'shop' in (r.get('submittal_type') or '').lower() and (r.get('planned_sub') or 0) > 0
                 and (r.get('actual_sub') or 0) >= (r.get('planned_sub') or 0)
                 and (r.get('actual_appr') or 0) >= (r.get('planned_appr') or 0)]
    for r in shop_done[:1]:
        note1 += (f" The {str(r.get('trade') or '').rstrip('.')} shop drawings are through: {r.get('actual_sub')} of "
                  f"{r.get('req')} submitted and {r.get('actual_appr')} approved — every one planned to date.")
    rows1 = sorted(up if up else ds, key=lambda x: -(x.get('gap') or 0))
    s_iso = K.sec('Engineering in isolation', *p1,
                  table=K.tbl(['Engineering / procurement line' if up else 'Category', 'Weight', 'Done / plan',
                               'Isolated SPI', 'Gap (pts)'],
                              [[x['name'], f"{round((x.get('weight') or 0) * 100)}%", f"{x.get('actual')}% / {x.get('planned')}%",
                                K.ratio(_isp(x)), x.get('gap')] for x in rows1], note1))

    # ── 2. design submittal register ────────────────────────────────────────────
    def stage(r):
        t = (r.get('submittal_type') or '').lower()
        return 0 if 'schem' in t else 1 if 'detail' in t else 2 if 'ifc' in t else 3 if 'shop' in t else 4

    if subs:
        dz = [r for r in subs if stage(r) in (0, 1)]
        ps, as_ = sum(r.get('planned_sub') or 0 for r in dz), sum(r.get('actual_sub') or 0 for r in dz)
        pa, aa = sum(r.get('planned_appr') or 0 for r in dz), sum(r.get('actual_appr') or 0 for r in dz)
        det = [r for r in subs if stage(r) == 1]
        pdet, adet = sum(r.get('planned_sub') or 0 for r in det), sum(r.get('actual_sub') or 0 for r in det)
        p2 = [f"The file's submittal register shows how big the paper gap is. Across schematic and detailed design, "
              f"{as_} of the {ps} planned submissions have been made and {aa} of the {pa} planned approvals received."
              + (f" Detailed design has {adet} of {pdet} planned submissions made." if det else '')]
        if complete and behind_design:
            p2[0] += (f" Because {_join([x['name'] for x in complete])} {'is' if len(complete) == 1 else 'are'} 100% "
                      f"complete, the open submissions belong to the lines still behind — "
                      f"{_join([x['name'] for x in behind_design])}.")
        stalled = sorted([r for r in subs if (r.get('planned_sub') or 0) > 0 and (r.get('actual_sub') or 0) == 0
                          and (r.get('planned_sub') or 0) >= (r.get('req') or 0) and (r.get('req') or 0) >= 3],
                         key=lambda r: (stage(r), str(r.get('trade') or '')))
        if stalled:
            nm = [f"{str(r.get('trade') or '').rstrip('.')} · {str(r.get('submittal_type') or '').replace(' Design', '')}"
                  f" ({r.get('req')} due, none made)" for r in stalled[:3]]
            p2.append((f"One stage stands out: {nm[0]}." if len(nm) == 1 else
                       f"{_num(len(stalled), True)} stages stand out, with every submission due and none made: {_join(nm)}.")
                      + " A whole stage that hasn't moved usually waits on an input, not on drafting — "
                      + ("check its predecessors against the late design inputs below." if design_inputs_late else
                         "check its predecessors in P6."))
        t2 = K.tbl(['Trade · stage', 'Required', 'Submitted (plan / actual)', 'Approved (plan / actual)'],
                   [[f"{str(r.get('trade') or '').rstrip('.')} · {str(r.get('submittal_type') or '').replace(' Design', '')}",
                     r.get('req'), f"{r.get('planned_sub')} / {r.get('actual_sub')}",
                     f"{r.get('planned_appr')} / {r.get('actual_appr')}"]
                    for r in sorted(subs, key=lambda r: (str(r.get('trade') or ''), stage(r)))],
                   f"Planned counts are due by the {dd} data date; actuals are submissions and approvals the file "
                   "records as started (the register's counting rule).")
        thinking.append(f"Summed the design submittal register: {as_} of {ps} planned submissions, {aa} of {pa} approvals")
    else:
        p2 = ["The per-trade submittal register (submitted and approved against plan) isn't stored with this update, so "
              "I can't give those counts here. Re-import the file — the EVM tab's Engineering panel builds it from the "
              "trade and design-cycle codes on the submittal and approval activities."]
        br = {}
        for a in acts:
            parts = [p for p in (a.get('wbs_path') or '').split(' / ') if p]
            if parts and re.search(r'design|engineer', parts[0], re.I):
                key = ' / '.join(parts[:2])
                br[key] = br.get(key, 0) + 1
        t2 = None
        if br:
            p2.append("What the file does show is where the design volume sits, by WBS branch:")
            t2 = K.tbl(['Design / engineering branch', 'Activities'],
                       [[k, v] for k, v in sorted(br.items(), key=lambda kv: -kv[1])[:10]],
                       'Counted from the activity list in the file; progress per activity is in Update Analysis.')
    s_reg = K.sec('Design submittal register — planned vs actual', *p2, table=t2)

    # ── 3. does it threaten construction? ───────────────────────────────────────
    p3 = []
    if not nok:
        p3.append(K.network_note(N))
        if behind_up:
            p3.append("From the stored numbers alone I can see which lines are behind — "
                      + _join([f"{x['name']} ({x['actual']}% vs {x['planned']}%)" for x in behind_up[:4]])
                      + " — but not whether their float reaches the finish. That needs the network.")
        else:
            p3.append("From the stored numbers, no design or procurement line is behind its planned progress, so nothing "
                      "upstream is holding construction on this update.")
    elif not behind_up:
        p3.append("No design or procurement line is behind its planned progress, so nothing upstream threatens "
                  "construction on this update.")
    else:
        p3.append("Split it by what each line releases." if len(behind_up) > 1 else "Read it by what the line releases.")
        for x in behind_up[:4]:
            a = A[x['name']]
            what = 'design' if _kind(x) == 'design' else 'procurement'
            if a['state'] == 'threat' and a['inputs']:
                ins = sorted(a['inputs'], key=lambda c: c.get('tf') if c.get('tf') is not None else 0)
                t = (f"**{x['name']}** does threaten construction. It is {x['actual']}% done against {x['planned']}% "
                     f"planned, and the client input{'s' if len(ins) > 1 else ''} whose name says "
                     f"{'they release' if len(ins) > 1 else 'it releases'} it {'are' if len(ins) > 1 else 'is'} late: "
                     + '; '.join(f"{_clean(c['name'])} ({c['id']}): {_sg(c.get('slip_wd'))} wd, float {_sg(c.get('tf'))}"
                                 for c in ins[:3]) + '.')
                if a['hits']:
                    h = a['hits'][0]
                    t += (f" Work named for the same scope sits on the finish chain itself — {_clean(h['name'])} "
                          f"({h['id']}, float {_sg(h['tf'])}) — so this {what} has to be through in time for it.")
                if ftf is not None and a['tf'] > ftf:
                    t += (f" This path isn't the one setting today's date (the finish runs at {_sg(ftf)}), but even with "
                          f"that chain fully recovered it would still hold the finish about {abs(a['tf'])} wd late. Any "
                          "recovery plan has to close it.")
                elif ftf is not None:
                    t += " It is as deep as the finish itself, so on this snapshot it is part of what sets the date."
                p3.append(t)
            elif a['state'] == 'threat':
                m = a['ms']
                p3.append(f"**{x['name']}** threatens construction: its key date {m['name']} ({m['id']}) has moved from "
                          f"{m['baseline_finish']} to {m['finish']} ({_sg(m.get('slip_wd'))} wd) and sits on "
                          f"{_sg(a['tf'])} wd float.")
            elif a['state'] == 'float':
                m = a['ms']
                p3.append(f"**{x['name']}** does not threaten the finish. {m['name']} ({m['id']}) has moved from "
                          f"{m['baseline_finish']} to {m['finish']} ({_sg(m.get('slip_wd'))} wd), but it still carries "
                          f"{_sg(a['tf'])} wd float. It is behind, not driving — report it that way.")
            elif a['state'] == 'linked':
                h = a['hits'][0]
                p3.append(f"**{x['name']}** is behind ({x['actual']}% vs {x['planned']}%), and work named for the same "
                          f"scope sits on the finish chain ({_clean(h['name'])}, {h['id']}, float {_sg(h['tf'])}). Trace its "
                          "successors in the Critical Path Analyzer to confirm the design gates that work.")
            elif what == 'procurement' and (x.get('gap') or 0) <= 10:
                p3.append(f"**{x['name']}** is a short tail ({x['actual']}% vs {x['planned']}%) that nothing in the file "
                          "ties to the finish by name — its open items are read under procurement and long-lead items "
                          "below.")
            else:
                p3.append(f"**{x['name']}** is behind ({x['actual']}% vs {x['planned']}%), but the file gives me no key "
                          "date or input I can tie it to by name, so I can't read its float from here — check its "
                          "successors' float in the Critical Path Analyzer before calling it a threat.")
        if unmatched_design:
            c = sorted(unmatched_design, key=lambda c: c.get('tf') if c.get('tf') is not None else 0)[0]
            p3.append(f"One more design input is late without naming the line it feeds: {_clean(c['name'])} ({c['id']}), "
                      f"{_sg(c.get('slip_wd'))} wd, float {_sg(c.get('tf'))}"
                      + (" — the deepest client input in the file" if c.get('tf') is not None and
                         c['tf'] == min((y['tf'] for y in late_open if y.get('tf') is not None), default=c['tf']) else '')
                      + ". Trace its successors in P6 to see which design it holds.")
        thinking.append(f"Tied {len(behind_up)} behind design/procurement line{'s' if len(behind_up) != 1 else ''} to "
                        "key dates, releasing inputs and finish-chain work by name")
    s_threat = K.sec('Does it threaten construction — or is it inside float?', *p3)

    # ── 4. which IFC deliverables are critical ──────────────────────────────────
    order = {'threat': 0, 'linked': 1, 'unknown': 2, 'float': 3, 'on plan': 4, 'complete': 5}
    drows, p4 = [], []
    for x in sorted(design, key=lambda x: (order.get(A[x['name']]['state'], 9),
                                           A[x['name']]['tf'] if A[x['name']]['tf'] is not None else 0)):
        a = A[x['name']]
        n_ifc = ifc_count(x)
        deliv = x['name'] + (f" ({n_ifc} IFC activities)" if n_ifc else '')
        if a['state'] == 'complete':
            status, held, fl = 'issued (100%)', 'construction', 'complete'
        else:
            status = f"{x['actual']}% vs {x['planned']}% planned" + (', not started' if not x.get('actual') else '')
            chainbits = []
            if a['inputs']:
                chainbits.append(' + '.join(_short(c['name'], 34) for c in a['inputs'][:2]))
            elif a['ms']:
                chainbits.append(f"key date {a['ms']['name']}")
            if a['hits']:
                chainbits.append(_short(a['hits'][0]['name'], 34))
            if a['state'] == 'threat' and fin.get('name'):
                chainbits.append(fin['name'])
            held = ' → '.join(chainbits) if chainbits else '—'
            fl = f"{_sg(a['tf'])} wd" if a['tf'] is not None else '—'
        drows.append([deliv, status, held, fl])
    if design:
        crit = [A[x['name']] for x in design if A[x['name']]['state'] == 'threat']
        p4.append("A critical IFC deliverable is one whose release sits on negative float — rank the packages by the "
                  "float of the work they release, not by the design line's own %."
                  + (f" {_join([x['name'] for x in complete])} {'is' if len(complete) == 1 else 'are'} issued." if complete else '')
                  + (f" The critical one{'s are' if len(crit) > 1 else ' is'} {_join([a['d']['name'] for a in crit])}:" if crit
                     else (" None of the open design lines ties to a negative-float input or key date by name:" if nok
                           else '')))
    else:
        n_ifc = sum(1 for a in acts if 'ifc' in ((a.get('name') or '') + ' ' + (a.get('wbs_path') or '')).lower())
        p4.append("With no design line in the weighted categories I can't tell which IFC packages are critical from the "
                  "stored numbers."
                  + (f" The file has {n_ifc} activities named for IFC; rank them by the float of the construction they "
                     "release in the Critical Path Analyzer." if n_ifc else
                     " Rank IFC packages by the float of the construction they release in the Critical Path Analyzer."))
    s_ifc = K.sec('Which IFC deliverables are critical', *p4,
                  table=K.tbl(['Deliverable', 'Status', 'Held by → releases', 'Float'], drows,
                              'Status and float from the file; the float shown is that of the input or key date that gates '
                              'the line.' if nok else 'Status from the stored categories; float needs the schedule file.'))

    # ── 5. is late vendor / consultant info driving the delay? ──────────────────
    p5, t5 = [], None
    if nok and late_open:
        neg = [c for c in late_open if c.get('tf') is not None and c['tf'] < 0]
        tfs = [c['tf'] for c in late_open if c.get('tf') is not None]
        if not neg:
            negtxt = ''
        elif len(neg) == len(late_open):
            negtxt = (f", and {'all ' + str(len(neg)) + ' late items sit' if len(neg) > 1 else 'the late item sits'} on "
                      f"negative float, which makes {'them strong EOT indicators' if len(neg) > 1 else 'it a strong EOT indicator'}")
        else:
            negtxt = (f", and {len(neg)} of the {len(late_open)} late items {'sit' if len(neg) > 1 else 'sits'} on negative "
                      f"float, which makes {'them strong EOT indicators' if len(neg) > 1 else 'it a strong EOT indicator'}")
        p5.append("Late client and consultant information is clearly there" + negtxt
                  + ". This snapshot can't prove it caused the finish slip, though. "
                  f"{_num(len(late_open), True)} input{'s are' if len(late_open) > 1 else ' is'} late and still open at the "
                  "data date (table below).")
        if tfs and ftf is not None:
            lo, hi = min(tfs), max(tfs)
            deep = [c for c in late_open if c.get('tf') is not None and c['tf'] <= ftf]
            t = f"Read their float against the finish. These paths run at {_sg(hi)} to {_sg(lo)} wd. "
            if not deep:
                worst = min(late_open, key=lambda c: c['tf'] if c.get('tf') is not None else 0)
                t += (f"The path that sets today's date runs at {_sg(ftf)}" + (f" through the {front} works" if front else '')
                      + ", and no client input in the file is as negative as that, so on this snapshot the inputs are a "
                        "parallel, concurrent delay rather than the one setting the date. Even so, a fully recovered chain "
                        f"would still leave the {_short(worst['name'], 40)} path {abs(worst['tf'])} wd late.")
            else:
                t += (f"{_join([_short(c['name'], 40) for c in deep[:2]])} {'sit' if len(deep) > 1 else 'sits'} as deep as "
                      f"the finish ({_sg(ftf)}), so on this snapshot a client input is on the path that sets the date.")
            p5.append(t)
        tail = ("Untangling employer delay from contractor delay, and handling the concurrency, is a TIA or windows "
                "analysis: Consultant Review (but-for) plus Update vs Update across the updates where these inputs went late.")
        if F.get('hard_constraints_computable') is False:
            tail += (" One ingest gap: the tool found no contract milestone dates to test against, and the client's "
                     "contractual review periods aren't in the file. Feed those in before quoting entitlement.")
        p5.append(tail)
        rolled = [c for c in late_open if c.get('finish') == dd and not c.get('pct')]
        t5 = K.tbl(['Client / consultant input', 'Baseline → forecast', 'Slip (wd)', 'Float (wd)'],
                   [[_lbl(c), f"{c.get('baseline_finish')} → {c.get('finish')}", _sg(c.get('slip_wd')), _sg(c.get('tf'))]
                    for c in sorted(late_open, key=lambda c: -(c.get('slip_wd') or 0))],
                   (f"A forecast of {dd} means the input is still outstanding. P6 rolls an unstatused milestone to the data "
                    "date, so every week it stays open, its slip grows by a week.") if rolled else
                   'Baseline vs current finish in each activity\'s own calendar; float from the file.')
        thinking.append(f"Checked {len(client)} client/employer inputs: {len(late_open)} late and open, "
                        f"{sum(1 for c in late_open if (c.get('tf') or 0) < 0)} on negative float")
    elif nok:
        p5.append("No client or consultant input in the file is late and still open, so late information isn't what's "
                  "holding the date on this update."
                  + (f" {len(late_done)} input{'s were' if len(late_done) != 1 else ' was'} delivered late earlier — keep "
                     "them in the delay record." if late_done else ''))
        if behind:
            p5.append("If someone blames late drawings, test it: Consultant Review (but-for) against the baseline shows "
                      "whether any late input actually moved the finish.")
    else:
        p5.append("I need the schedule file to list the late client and consultant inputs and read their float against "
                  "the finish; the stored numbers don't carry them.")
        if behind:
            p5.append("Whatever the list shows, a late input is an EOT indicator, not proof: Consultant Review (but-for) and "
                      "Update vs Update separate employer delay from contractor delay.")
    s_info = K.sec('Is late vendor / consultant info driving the delay?', *p5, table=t5)

    # ── 6. where procurement stands ─────────────────────────────────────────────
    p6 = []
    if proc:
        closed = all((x.get('actual') or 0) >= 90 for x in proc)
        onplan = all((x.get('gap') or 0) <= 0 for x in proc)
        state = 'essentially closed' if closed else ('on or ahead of plan' if onplan else 'behind plan')
        lead = (f"Contractor procurement is {state}: "
                + '; '.join(f"{x['name']} stands at {x['actual']}% against {x['planned']}%" for x in proc)
                + (", so on the weighted read it isn't what's moving your finish." if (closed or onplan) and not drv_up
                   else '.'))
    elif nok and items:
        lead = "The weighted categories carry no procurement line of their own, so supply is read from the delivery items in the file."
    else:
        lead = ("The weighted categories carry no procurement line of their own, so contractor procurement can't be read "
                "from the stored numbers.")
    if items_client:
        lead += (f" The long-lead risk on this job is client-furnished: {len(items_client)} client-supplied "
                 f"item{'s are' if len(items_client) > 1 else ' is'} still open in the file.")
        li = [i for i in items_client if (i.get('slip_wd') or 0) > 0]
        solo = len(items_client) == 1
        if li:
            lead += ((" It is already past its baseline date." if solo else
                      f" {_num(len(li), True)} of them {'are' if len(li) > 1 else 'is'} late and still open ("
                      + _join([_short(i['name'], 44) for i in li[:3]]) + ")."))
        pc = [i for i in pinned if i['id'] in client_ids]
        if pc:
            dates = sorted({i['finish'] for i in pc}, key=lambda s: _date(s) or datetime.max)
            lead += (f" {'It' if solo else _num(len(pc), True)} {'are' if len(pc) > 1 else 'is'} due {_join(dates[:3])} "
                     "with no float left.")
    p6.append('**' + lead + '**')
    pb = {}
    for a in acts:
        parts = [p for p in (a.get('wbs_path') or '').split(' / ') if p]
        if parts and re.search(r'procure|purchas', parts[0], re.I):
            k = parts[1] if len(parts) > 1 else parts[0]
            pb[k] = pb.get(k, 0) + 1
    t = ''
    if pb:
        t = (f"The procurement branch has {sum(pb.values())} activities across "
             f"{_join([k for k, _ in sorted(pb.items(), key=lambda kv: -kv[1])][:6])}.")
    tails = [x for x in proc if 0 < (x.get('gap') or 0) <= 10]
    if tails:
        t += (f" The open {tails[0]['gap']}% of {tails[0]['name']} is a short tail — check each open item's successor "
              "float in that branch rather than trusting the percentage.")
    done_items = [c for c in client if c.get('done') and _input_kind(c) == 'item']
    late_arr = [c for c in done_items if (c.get('slip_wd') or 0) > 0]
    if late_arr:
        t += (f" On the client's side, {len(late_arr)} of the {len(done_items)} furnished deliveries recorded as arrived "
              f"came in behind their baseline dates ({_sg(min(c['slip_wd'] for c in late_arr))} to "
              f"{_sg(max(c['slip_wd'] for c in late_arr))} wd). That is history now, but it belongs in the delay record "
              "for any EOT.")
    p6.append(t.strip())
    s_proc = K.sec('Where procurement stands', *p6)

    # ── 7. long-lead items ranked by float ──────────────────────────────────────
    p7, t7 = [], None
    if items:
        on_chain = [i for i in items if i['id'] in chain_ids]
        negi = [i for i in items if i.get('tf') is not None and i['tf'] < 0]
        s = (f"These are the {'client-furnished ' if len(items_client) == len(items) else ''}delivery items still open in "
             "the file, most negative float first. ")
        if ftf is not None:
            s += (f"{'None of them sits' if not on_chain else _join([_short(i['name'], 36) for i in on_chain]) + ' sit'} on "
                  f"the {_sg(ftf)} wd finish chain today.")
        if negi:
            s += f" {_num(len(negi), True)} {'are' if len(negi) > 1 else 'is'} on a negative path"
            s += (f", and {len(pinned)} {'are' if len(pinned) > 1 else 'is'} pinned at zero float." if pinned else '.')
        p7.append(s)

        def status(i):
            if (i.get('slip_wd') or 0) > 0:
                return 'late, open'
            if i.get('tf') == 0:
                return 'due, no margin'
            if i.get('tf') is not None and i['tf'] < 0:
                return 'due, negative float'
            return f"due, {_sg(i.get('tf'))} wd float" if i.get('tf') is not None else 'due'
        t7 = K.tbl(['Long-lead item', 'Required on site (forecast)', 'Slip vs baseline', 'Total float', 'Status'],
                   [[_lbl(i), (f"{i.get('finish')} (baseline {i.get('baseline_finish')})"
                               if i.get('baseline_finish') and i.get('baseline_finish') != i.get('finish') else i.get('finish')),
                     (f"{_sg(i.get('slip_wd'))} wd" if i.get('slip_wd') else '0'), _sg(i.get('tf')), status(i)]
                    for i in items[:12]],
                   ("Zero float with zero slip is the signature of a date constraint (a 'Start On' or similar): P6 pins "
                    "the date, so the float reads 0 and no slip can show. Check the float of the work each one releases — "
                    "if it is already negative, treat the delivery as critical, not comfortable.") if pinned else
                   'Forecast, baseline and float from the file.')
        thinking.append(f"Ranked {len(items)} open delivery item{'s' if len(items) != 1 else ''} by float and due date")
    elif nok:
        p7.append("I found no open delivery or long-lead item in the file — none of the client inputs or milestones is "
                  "named as a delivery, shipment or supply. If long-lead items exist, they're buried inside procurement "
                  "activities or lags; give each a delivery milestone so its float can be ranked.")
    else:
        p7.append("Ranking long-lead items by float needs the schedule file — re-import it and I'll list each open delivery "
                  "with its required-on-site date and float.")
    s_ll = K.sec('Long-lead items on the critical path, ranked by float', *p7, table=t7)

    # ── 8. required-on-site dates & delivery-slip impact ────────────────────────
    p8 = []
    ddt = _date(dd)
    due = [i for i in items if (i.get('slip_wd') or 0) <= 0 and _date(i.get('finish'))]
    if due and ddt:
        groups = {}
        for i in due:
            groups.setdefault(i['finish'], []).append(i)
        gl = sorted(groups.items(), key=lambda kv: _date(kv[0]))
        bits = []
        for dt_s, g in gl[:3]:
            days = (_date(dt_s) - ddt).days
            when = (f"less than two weeks after the {dd} data date" if 0 <= days < 14 else
                    f"{days} days after the {dd} data date" if days >= 0 else f"before the {dd} data date")
            bits.append(f"{_num(len(g), False) if len(g) > 1 else _short(g[0]['name'], 40)} "
                        f"{'items are' if len(g) > 1 else 'is'} due on {dt_s}, {when}")
        t = "The required-on-site date is each delivery milestone's date in the file. " + '; '.join(bits) + '.'
        t = t.replace('. one', '. One').replace('. two', '. Two').replace('. three', '. Three').replace('. four', '. Four') \
             .replace('. five', '. Five').replace('. six', '. Six').replace('. seven', '. Seven')
        if pinned:
            t += (" If constraints are pinning those milestones, a late delivery won't show in P6 until someone moves the "
                  "constraint date. When you hear of a slip, move the date and reschedule straight away rather than "
                  "waiting for the next update.")
        p8.append(t)
    elif items:
        p8.append("Every open delivery item in the file is already past its baseline date, so the required-on-site date "
                  "has effectively arrived — each week it stays open adds a week to its slip.")
    wi = ("For the effect on the finish, the in-tool forward pass gives an estimate; the exact answer comes from the What-if "
          "(the P6 F9 reschedule): enter the slipped or accelerated delivery, reschedule and read "
          + (f"{fin.get('name')}" if fin.get('name') else 'the finish milestone') + ". Don't take it from float alone.")
    ref = [i for i in items if i.get('tf') is not None and i['tf'] < 0 and i not in pinned]
    if ref and ftf is not None and ref[0]['tf'] > ftf:
        r0 = ref[0]
        wi += (f" As a first-order bound: {_short(r0['name'], 44)} sits {r0['tf'] - ftf} wd shallower than the finish "
               f"chain ({_sg(r0['tf'])} vs {_sg(ftf)}), so roughly that much further slip is absorbed before it starts "
               "moving the finish — and cutting its delivery time buys nothing at the finish while the chain stays deeper. "
               "Whether it moves the date after that depends on how the paths merge, and only the reschedule shows that.")
    elif items and ftf is not None:
        wi += " Whether a slip moves the date depends on how the delivery's path compares with the finish chain, and only the reschedule shows that."
    p8.append(wi)
    s_ros = K.sec('Required-on-site dates & delivery-slip impact', *p8)

    # ── 9. two checks planners miss ─────────────────────────────────────────────
    p9 = []
    if has_audit and F.get('oos_count') is not None:
        ok = (audit.get('out_of_sequence') or {}).get('kpis') or {}
        m = re.search(r'concentrated in the (.+?) package \((\d+) of (\d+)', ok.get('executive_conclusion') or '')
        t = (f"Install-before-delivery: an installation that starts before its delivery finishes is out-of-sequence "
             f"logic. The file has {F['oos_count']} out-of-sequence activities ({K.pct(F.get('oos_pct'), 1)})"
             + (f", with {F['critical_oos']} on the critical path" if F.get('critical_oos') is not None else ''))
        if m:
            t += (f", and {m.group(2)} of the {m.group(3)} are in {m.group(1)}"
                  + (" rather than installation" if re.search(r'design|engineer', m.group(1), re.I) else ''))
        t += (". Run OOS Resolve and check the construction ones first, because those are the ones that could be "
              "installing ahead of delivered items.")
        p9.append(t)
    lk = ((audit.get('lag_lead') or {}).get('kpis') or {}) if has_audit else {}
    ms_inputs = [c for c in open_client if 'Milestone' in (c.get('type') or '')]
    ms_share = ((f"both open client inputs are" if len(open_client) == 2 else f"all {len(open_client)} open client inputs are")
                if len(ms_inputs) == len(open_client) and len(open_client) > 1 else
                ("the one open client input is" if len(open_client) == 1 else
                 f"{len(ms_inputs)} of the {len(open_client)} open client inputs are"))
    one_ms = len(ms_inputs) == 1
    ms_pred = (f"{ms_share} {'a zero-duration milestone' if one_ms else 'zero-duration milestones'}, so "
               f"{'its' if one_ms else 'their'} timing comes from a lag, a constraint or whatever precedes "
               f"{'it' if one_ms else 'them'}")
    if lk.get('lagged_count') is not None:
        t = "Lead time hidden in lags: "
        if ms_inputs:
            t += ms_pred + " — not from a modelled review or supply activity. Across"
        else:
            t += "across"
        t += (f" the schedule, {lk['lagged_count']} relationships carry a lag ({K.pct(lk.get('lagged_pct'), 1)}, "
              f"{'over' if (lk.get('lagged_pct') or 0) > (lk.get('dcma_lag_line') or 5) else 'within'} the "
              f"{K.pct(lk.get('dcma_lag_line') or 5)} DCMA guideline)")
        if lk.get('long_count') is not None:
            t += f"; {lk['long_count']} of those lags are longer than {lk.get('long_threshold_days') or 14} working days"
        if lk.get('critical_count') is not None:
            t += f", and {lk['critical_count']} are on the critical path"
        t += (". Run the Lag Report, then replace the long lags on client inputs with real 'submit → review → release' "
              "and 'ship → deliver' activities. That gives you a delivery chain you can progress and slip-test, and a "
              "much cleaner record for any EOT.")
        p9.append(t)
    elif ms_inputs:
        p9.append(f"Lead time hidden in lags: {ms_pred}. Run the Schedule Audit's Lag Report to see how long those lags are.")
    if not p9:
        p9.append("The logic audits (out-of-sequence and lags) aren't stored with this update. Run the Schedule Audit: "
                  "out-of-sequence finds installations started before their delivery finished, and the Lag Report finds "
                  "lead times hidden inside long finish-to-start lags instead of modelled delivery activities.")
    elif has_audit:
        thinking.append("Cross-read the out-of-sequence and lag audits for install-before-delivery and hidden lead time")
    s_chk = K.sec('Two checks planners miss', *p9)

    # ── measured / actions / evidence ───────────────────────────────────────────
    measured = ("Isolated SPI per line is the category's actual % divided by its planned %, from the file's weighted "
                "rollup; weights are the category weights. "
                + ("The submittal register is the file's submittal and approval activities grouped by trade and design "
                   "stage: required, and planned vs actual submitted and approved to the data date. " if subs else '')
                + ("Whether design threatens construction is read by name from the network: each open design line is tied "
                   "to the client input whose name says it releases it, to its own key-date milestone, and to finish-chain "
                   "work named for the same scope. Client inputs and deliveries are the file's client/employer "
                   "activities: baseline vs current finish, slip in working days in each activity's own calendar, and "
                   "total float. " if nok else '')
                + ("Out-of-sequence and lag readings come from the Schedule Audit modules. " if has_audit else '')
                + "Causation (late input → finish slip) is not measured here; it needs Consultant Review (but-for) and "
                  "Update vs Update across the updates where the inputs went late.")
    esc = sorted([c for a in threats for c in a['inputs']] + unmatched_design,
                 key=lambda c: c.get('tf') if c.get('tf') is not None else 0)
    seen, esc_u = set(), []
    for c in esc:
        if c['id'] not in seen:
            seen.add(c['id'])
            esc_u.append(c)
    actions = []
    if esc_u:
        actions.append("Escalate " + _join([f"{_short(c['name'], 70)} ({_sg(c.get('slip_wd'))} wd, float {_sg(c.get('tf'))})"
                                            for c in esc_u[:3]])
                       + f" this week. {'They hold' if len(esc_u) > 1 else 'It holds'} the design that is behind"
                       + (f", which feeds {fin.get('name')}." if fin.get('name') else '.'))
    if late_open:
        actions.append("Issue a formal notice on each late client input now and keep the record current — each one on "
                       "negative float is a strong EOT indicator.")
    for a in floaty[:1]:
        actions.append(f"Don't escalate {a['d']['name']} as a finish threat. It is behind "
                       f"({_sg(a['ms'].get('slip_wd'))} wd at {a['ms']['id']}) but has {_sg(a['tf'])} wd float, so report "
                       "it as behind, not driving.")
    if pinned:
        dates = sorted({i['finish'] for i in pinned}, key=lambda s: _date(s) or datetime.max)
        actions.append(f"Get written confirmation of the {len(pinned)} deliver{'ies' if len(pinned) > 1 else 'y'} due "
                       f"{_join(dates[:3])}. If any date moves, change its constraint and reschedule the same day.")
    li = [i for i in items if (i.get('slip_wd') or 0) > 0]
    if li:
        actions.append("Chase " + _join([f"{_short(i['name'], 70)} ({_sg(i.get('slip_wd'))} wd, float {_sg(i.get('tf'))})"
                                         for i in li[:3]])
                       + f". {'Both are' if len(li) == 2 else 'All are' if len(li) > 2 else 'It is'} late and still open.")
    for x in [x for x in proc if 0 < (x.get('gap') or 0) <= 10][:1]:
        actions.append(f"Close out the last {x['gap']}% of {x['name']} by checking each open delivery's successor float.")
    if late_open or behind:
        actions.append("Run Consultant Review (but-for) and Update vs Update across the updates where the inputs went late. "
                       "That splits employer delay from contractor delay before anyone quotes an EOT figure.")
    if lk.get('lagged_count'):
        actions.append("Run the Lag Report, and replace the long lags on client inputs and deliveries with modelled review "
                       "and delivery activities.")
    if not up:
        actions.append("Weight the design and procurement WBS as their own categories so engineering can be read on its own.")
    if not nok:
        actions.append("Re-import the schedule file to restore the input, delivery and float detail.")

    evid = []
    for x in behind_up[:3]:
        a = A[x['name']]
        v = f"{x['actual']}% / {x['planned']}% · {round((x.get('weight') or 0) * 100)}% weight"
        if a['state'] == 'float':
            v = f"{x['actual']}% / {x['planned']}% · {_sg(a['tf'])} wd float"
        evid.append(K.ev(_short(x['name'], 30), v))
    for a in floaty[:1]:
        m = a['ms']
        evid.append(K.ev(_short(m['name'], 30), f"{m['baseline_finish']} → {m['finish']} ({_sg(m.get('slip_wd'))} wd)"))
    if complete:
        evid.append(K.ev('Design complete', f"{_join([x['name'] for x in complete])} · 100%"))
    if subs:
        dz = [r for r in subs if stage(r) in (0, 1)]
        evid.append(K.ev('Design submittals', f"{sum(r.get('actual_sub') or 0 for r in dz)} of "
                                              f"{sum(r.get('planned_sub') or 0 for r in dz)} planned · "
                                              f"{sum(r.get('actual_appr') or 0 for r in dz)} of "
                                              f"{sum(r.get('planned_appr') or 0 for r in dz)} approvals"))
    for c in sorted(late_open, key=lambda c: -(c.get('slip_wd') or 0))[:3]:
        evid.append(K.ev(_short(c['name'], 30), f"{_sg(c.get('slip_wd'))} wd · float {_sg(c.get('tf'))}"))
    for x in proc[:1]:
        evid.append(K.ev(_short(x['name'], 30), f"{x['actual']}% / {x['planned']}%"))
    if li:
        evid.append(K.ev(_short(li[0]['name'], 30), f"{_sg(li[0].get('slip_wd'))} wd · float {_sg(li[0].get('tf'))} · open"))
    if pinned:
        evid.append(K.ev(f"Deliveries at zero float ({len(pinned)})",
                         f"due {sorted({i['finish'] for i in pinned}, key=lambda s: _date(s) or datetime.max)[0]} · float 0"))
    if has_audit and F.get('oos_count') is not None:
        evid.append(K.ev('Out-of-sequence', f"{F['oos_count']}"
                                            + (f" · {F['critical_oos']} critical" if F.get('critical_oos') is not None else '')))
    if lk.get('lagged_count') is not None:
        evid.append(K.ev('Lags', f"{lk['lagged_count']} ({K.pct(lk.get('lagged_pct'), 1)})"
                                 + (f" · {lk['critical_count']} on the critical path" if lk.get('critical_count') is not None else '')))
    if not up:
        evid.append(K.ev('SPI', K.ratio(spi)))
        evid.append(K.ev('Delay', K.signed(d)))
    seen_k, ev_u = set(), []
    for e in evid:
        if e and e['k'] not in seen_k:
            seen_k.add(e['k'])
            ev_u.append(e)
    evid = ev_u

    if not nok:
        thinking.append("The schedule file couldn't be re-read, so inputs, deliveries and float were answered from the "
                        "stored categories and audits only")
    elif len(thinking) < 2:
        thinking.append(f"Searched the file's {len(client)} client/employer inputs and milestones for late information and "
                        "delivery items")

    a = K.A2(head, [s_iso, s_reg, s_threat, s_ifc, s_info, s_proc, s_ll, s_ros, s_chk], pills=pills,
             measured=measured, actions=actions, evidence=evid,
             drilldowns=[K.drill('q13', 'Do the late client inputs support an EOT, and how many days?') if late_open or behind
                         else K.drill('q02', 'When will we finish, and will we hit the dates?'),
                         K.drill('q05', f"How do I recover the ~{round(d)} days?") if behind
                         else K.drill('q01', 'Where do we stand overall?'),
                         K.drill('q04', "What's driving the date, and how much float is left?")])
    a['thinking'] = thinking[:4]
    return a
