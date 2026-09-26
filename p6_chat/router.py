"""Route a freely typed question to one of the 15 merged answers — and to the exact original sub-question.

Scores the text (TF-IDF cosine, construction synonyms, light stemming) against all 182 original library
questions and the 15 merged questions, so "are we going to be late for handover?" lands on q02 with the
contract-date sub-question in focus. Keeps the thread: short follow-ups ("why?", "how do I fix it?",
"more detail") continue from the last topic. Offline, deterministic, no model.
"""
import math
import re

STOP = set("""a an the and or but of to in on at for by with from as is are was were be been being do does did
i me my we our us you your it its this that these those what which who whom whose how where can could
should would will shall may might must have has had not no yes please tell show give let get got any some all
there their them they he she his her so than then too very just also about into up down out more most
much many one two project schedule time work works job update our""".split())

SYN = {
    'late': 'delay', 'behind': 'delay', 'slip': 'delay', 'slipped': 'delay', 'slippage': 'delay', 'delayed': 'delay',
    'lateness': 'delay', 'overrun': 'delay',
    'finish': 'completion', 'finished': 'completion', 'end': 'completion', 'handover': 'completion',
    'complete': 'completion', 'completed': 'completion', 'date': 'completion',
    'money': 'cost', 'budget': 'cost', 'spend': 'cost', 'spent': 'cost', 'spending': 'cost', 'costs': 'cost',
    'crew': 'manpower', 'labour': 'manpower', 'labor': 'manpower', 'worker': 'manpower', 'workforce': 'manpower',
    'resource': 'manpower', 'histogram': 'manpower', 'headcount': 'manpower',
    'claim': 'eot', 'extension': 'eot', 'entitlement': 'eot', 'fidic': 'eot', 'prolongation': 'eot',
    'recover': 'recovery', 'catch': 'recovery', 'accelerate': 'recovery', 'acceleration': 'recovery',
    'crash': 'recovery', 'mitigate': 'recovery', 'speed': 'recovery', 'shorten': 'recovery',
    'rain': 'weather', 'wind': 'weather', 'climate': 'weather',
    'revision': 'baseline', 'rebaseline': 'baseline', 're-baseline': 'baseline',
    'drawing': 'engineering', 'drawings': 'engineering', 'design': 'engineering', 'ifc': 'engineering',
    'delivery': 'procurement', 'deliveries': 'procurement', 'purchase': 'procurement', 'longlead': 'procurement',
    'subcontractor': 'subcontractor', 'subcontractors': 'subcontractor', 'subs': 'subcontractor', 'package': 'subcontractor',
    'testing': 'commissioning', 'startup': 'commissioning',
    'logic': 'logic', 'dcma': 'health', 'quality': 'health', 'healthy': 'health',
    'driving': 'critical', 'longest': 'critical',
    'spi': 'spi', 'cpi': 'cpi', 'ev': 'earned', 'pv': 'planned',
    'client': 'employer', 'owner': 'employer', 'employer': 'employer',
}

FOLLOW = [
    (r'^(why|why\?|how come|what caused|what is causing|cause|reason)\b', 'cause'),
    (r'\b(fix|recover|catch up|mitigate|what can (i|we) do|how do (i|we) (fix|recover|get back))\b', 'q05'),
    (r'\b(claim|eot|extension of time|entitle)', 'q13'),
    (r'^(more|detail|details|explain|elaborate|expand|go on|continue|tell me more|and\??|so\??)\b', 'same'),
    (r'\b(what should (i|we) do|next steps?|actions?)\b', 'q15'),
]
MIN_SCORE = 0.12


def _stem(w):
    if len(w) > 5 and w.endswith('ing'):
        w = w[:-3]
    elif len(w) > 4 and w.endswith('ed'):
        w = w[:-2]
    elif len(w) > 4 and w.endswith('ies'):
        w = w[:-3] + 'y'
    elif len(w) > 3 and w.endswith('s') and not w.endswith('ss'):
        w = w[:-1]
    return w


def tokens(text):
    out = []
    for raw in re.findall(r"[a-z0-9][a-z0-9\-']*", (text or '').lower()):
        raw = raw.strip("-'")
        if not raw or raw in STOP:
            continue
        w = SYN.get(raw) or SYN.get(_stem(raw)) or _stem(raw)
        out.append(w)
    return out


_INDEX = None


def _index():
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    from p6_chat.merged import catalog
    docs = []                                       # (qid, original_id|None, tokens)
    for q in catalog()['questions']:
        docs.append((q['id'], None, tokens(q['q'] + ' ' + ' '.join(q['covers']))))
        for al in q.get('aliases', []):         # planner phrasings: short docs that match everyday wording
            docs.append((q['id'], None, tokens(al)))
        for o in q['originals']:
            docs.append((q['id'], o['id'], tokens(o['q'])))
    df = {}
    for _, _, toks in docs:
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    n = len(docs)
    idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
    vecs = []
    for qid, oid, toks in docs:
        v = {}
        for t in toks:
            v[t] = v.get(t, 0) + idf[t]
        norm = math.sqrt(sum(x * x for x in v.values())) or 1
        vecs.append((qid, oid, {t: x / norm for t, x in v.items()}))
    _INDEX = (idf, vecs)
    return _INDEX


def route(text, last_qid=None):
    """-> {'qid', 'focus' (original id or None), 'score', 'followup', 'alternatives': [qid...], 'matched'}"""
    t = (text or '').strip().lower()
    if last_qid:
        for pat, target in FOLLOW:
            if re.search(pat, t) and len(tokens(t)) <= 6:
                if target == 'same':
                    return {'qid': last_qid, 'focus': None, 'score': 1.0, 'followup': 'expand',
                            'alternatives': [], 'matched': True}
                if target == 'cause':
                    q = 'q03' if last_qid in ('q01', 'q02', 'q04') else last_qid
                    return {'qid': q, 'focus': None, 'score': 1.0, 'followup': 'cause', 'alternatives': [], 'matched': True}
                return {'qid': target, 'focus': None, 'score': 1.0, 'followup': 'topic', 'alternatives': [],
                        'matched': True}
    idf, vecs = _index()
    qv = {}
    for tok in tokens(t):
        if tok in idf:
            qv[tok] = qv.get(tok, 0) + idf[tok]
    qn = math.sqrt(sum(x * x for x in qv.values())) or 1
    scored = []
    for qid, oid, v in vecs:
        s = sum(w / qn * v.get(tok, 0) for tok, w in qv.items())
        if s > 0:
            scored.append((s, qid, oid))
    scored.sort(key=lambda s: s[0], reverse=True)
    if not scored or scored[0][0] < MIN_SCORE:
        return {'qid': None, 'focus': None, 'score': scored[0][0] if scored else 0.0, 'followup': None,
                'alternatives': [q for _, q, _ in _distinct(scored)[:3]], 'matched': False}
    best = scored[0]
    alts = [q for _, q, _ in _distinct(scored) if q != best[1]][:2]
    return {'qid': best[1], 'focus': best[2], 'score': round(best[0], 3), 'followup': None,
            'alternatives': alts, 'matched': True}


def _distinct(scored):
    seen, out = set(), []
    for s in scored:
        if s[1] not in seen:
            seen.add(s[1])
            out.append(s)
    return out
