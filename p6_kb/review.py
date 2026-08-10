"""Rule-based Constructability Review — the engine.

schedule → detect sub-type → compare against the Knowledge Base → findings
(illogical relationships, missing activities, missing WBS) → score → report.
No AI, fully offline. Everything advisory.
"""
from p6_kb.detect import detect_subtype, score_entries
from p6_kb.kb import load_kb
from p6_kb.model import schedule_view
from p6_kb.scoring import compute_score


def _matches(name, keywords):
    n = (name or '').lower()
    return any(k.lower() in n for k in (keywords or []))


def _find(view, keywords):
    return [a for a in view['activities'] if _matches(a['name'], keywords)]


def _preds(view, code):
    out = []
    for r in view['relationships']:
        if r['succ'] == code:
            p = view['by_code'].get(r['pred'])
            out.append({'id': r['pred'], 'name': p['name'] if p else '', 'rel': r['type']})
    return out


def _succs(view, code):
    out = []
    for r in view['relationships']:
        if r['pred'] == code:
            s = view['by_code'].get(r['succ'])
            out.append({'id': r['succ'], 'name': s['name'] if s else '', 'rel': r['type']})
    return out


def _share_word(a, b):
    return any(len(w) >= 4 and w in b for w in a.split())


def _resolve(view, name):
    """Best-effort: map a KB activity name to a schedule activity (code+name)."""
    if not name:
        return {'id': '', 'name': ''}
    nl = name.lower()
    for a in view['activities']:
        an = a['name'].lower()
        if an and (an in nl or nl in an or _share_word(an, nl)):
            return {'id': a['id'], 'name': a['name']}
    return {'id': '', 'name': name}


def _wbs_present(view, kb_wbs):
    hay = [w['name'].lower() for w in view['wbs']] + [a['wbs_path'].lower() for a in view['activities']]
    return any(any(k.lower() in h for h in hay) for k in kb_wbs.get('keywords', []))


def _mk_illogical(act, preds, succs, rule, entry, suggested_preds):
    return {
        'activity_id': act['id'], 'activity_name': act['name'], 'wbs_path': act['wbs_path'],
        'current_preds': preds, 'current_succs': succs,
        'why': rule.get('reason', ''),
        'suggested_preds': suggested_preds,
        'suggested_succs': [{'id': s['id'], 'name': s['name'], 'rel': s['rel'], 'kind': 'keep'} for s in succs],
        'impact': rule.get('impact', 'Minor'),
        'source': f"{entry['type']} standard",
    }


def _illogical_findings(view, entry):
    findings, flagged = [], set()
    for rule in entry.get('logic_rules', []):
        after_acts = _find(view, rule.get('after_keywords', []))
        before_ids = {b['id'] for b in _find(view, rule.get('before_keywords', []))}
        for act in after_acts:
            if act['id'] in flagged or act['id'] in before_ids:
                continue
            preds = _preds(view, act['id'])
            succs = _succs(view, act['id'])
            from_before = [p for p in preds if p['id'] in before_ids]
            finding = None
            if from_before:
                bad = [p for p in from_before if p['rel'] != 'FS']
                if bad:
                    b = bad[0]
                    finding = _mk_illogical(act, preds, succs, rule, entry,
                        [{'id': b['id'], 'name': b['name'], 'rel': 'FS', 'kind': 'change'}])
            elif before_ids:
                b = view['by_code'][sorted(before_ids)[0]]
                finding = _mk_illogical(act, preds, succs, rule, entry,
                    [{'id': b['id'], 'name': b['name'], 'rel': 'FS', 'kind': 'add'}])
            if finding:
                findings.append(finding)
                flagged.add(act['id'])
    return findings


def _missing_activities(view, entry):
    used = set(view['by_code'])
    counter = [0]

    def new_id():
        while True:
            counter[0] += 1
            cand = f"SUG-{counter[0]:03d}"
            if cand not in used:
                used.add(cand)
                return cand

    missing = []
    for kact in entry.get('activities', []):
        if _find(view, kact.get('keywords', [])):
            continue  # present in the schedule
        kb_wbs = next((w for w in entry.get('wbs', []) if w['name'] == kact.get('wbs')), None)
        new_wbs = not (kb_wbs and _wbs_present(view, kb_wbs))
        missing.append({
            'suggested_id': new_id(),
            'name': kact.get('name', ''),
            'wbs': kact.get('wbs', ''),
            'new_wbs': new_wbs,
            'preds': [_resolve(view, kact.get('typical_pred'))] if kact.get('typical_pred') else [],
            'succs': [_resolve(view, kact.get('typical_succ'))] if kact.get('typical_succ') else [],
            'why': kact.get('why', ''),
            'basis': f"{entry['type']} standard",
        })
    return missing


def _wbs_review(view, entry):
    review, missing = [], []
    for w in entry.get('wbs', []):
        present = _wbs_present(view, w)
        review.append({'name': w['name'], 'status': 'ok' if present else 'missing',
                       'note': '' if present else f"Standard branch for {entry['type']}, not found."})
        if not present:
            missing.append({'name': w['name'], 'why': f"Standard WBS branch for {entry['type']} is absent."})
    return review, missing


def run_review(data, entries=None, cfg=None, forced_type=None):
    cfg = cfg or {}
    ai_cfg = cfg.get('score') or {}
    view = schedule_view(data)
    entries = entries if entries is not None else load_kb()

    scored = score_entries(view, entries)
    available = [{'category': e.get('category', ''), 'type': e.get('type', '')} for e, _ in scored]

    entry = None
    if forced_type:
        entry = next((e for e in entries if e.get('type') == forced_type), None)
    if entry is None:
        entry, _ = detect_subtype(view, entries)

    if entry is None:
        return {
            'mode': 'knowledge_base', 'detected': None, 'available_types': available,
            'project_type': 'Unrecognised', 'dashboard': {}, 'score': None,
            'illogical': [], 'missing': [], 'missing_wbs': [], 'wbs_review': [],
            'conclusion': "Could not match this schedule to a known project type in the "
                          "Knowledge Base. Pick the sub-type to review against.",
        }

    illogical = _illogical_findings(view, entry)
    missing = _missing_activities(view, entry)
    wbs_review, missing_wbs = _wbs_review(view, entry)

    total_rel = view['relationship_count']
    total_act = view['activity_count']
    illogical_pct = 100.0 * len(illogical) / max(total_rel, 1)
    missing_pct = 100.0 * len(missing) / max(total_act, 1)
    suggestion_count = len(illogical) + len(missing) + len(missing_wbs)
    score = compute_score(illogical_pct=illogical_pct, missing_pct=missing_pct,
                          missing_wbs=len(missing_wbs), suggestion_count=suggestion_count,
                          activity_count=total_act, cfg=ai_cfg)
    critical = any(f.get('impact') == 'Critical' for f in illogical)

    if illogical or missing or missing_wbs:
        gaps = (f"{len(illogical)} illogical link(s), {len(missing)} missing activities and "
                f"{len(missing_wbs)} missing WBS branch(es) found. ")
    else:
        gaps = "No constructability gaps found against the knowledge base. "
    conclusion = (f"Scored {score['overall']}/100 — {score['band_label']} against the "
                  f"{entry['category']} › {entry['type']} standard. " + gaps +
                  "Produced offline from the Construction Knowledge Base — advisory, review before acting.")

    return {
        'mode': 'knowledge_base',
        'detected': {'category': entry['category'], 'type': entry['type'],
                     'status': entry.get('status', '')},
        'available_types': available,
        'project_type': f"{entry['category']} › {entry['type']}",
        'dashboard': {
            'illogical_count': len(illogical), 'illogical_pct': round(illogical_pct, 1),
            'total_relationships': total_rel,
            'missing_count': len(missing), 'missing_pct': round(missing_pct, 1),
            'total_activities': total_act,
            'missing_wbs': len(missing_wbs), 'critical_affected': critical,
        },
        'score': score,
        'illogical': illogical,
        'missing': missing,
        'missing_wbs': missing_wbs,
        'wbs_review': wbs_review,
        'conclusion': conclusion,
    }
