"""Format-agnostic engineering-log reader (Earned Value ▸ Engineering Progress).

A consultant's drawings / shop-drawing / submittal log can come in any layout: headings on
row 7 under a code legend and summary counts, two-row merged headings, two columns both
called "Type", per-discipline sheets plus a Summary sheet, text dates, review codes as
letters, numbers or words, revisions as separate rows keyed by drawing number, CSV exports.

This module reads such a log the way a planner would — offline, deterministic, explainable:

  inspect_log(path)        → a LAYOUT proposal: per sheet, where the headings are, what each
                             column means (with a confidence 0–1 and a plain-English reason),
                             the review codes the file uses (its own legend wins over the
                             defaults) and a preview of the counts per discipline. Saves nothing.
  read_rows(path, layout)  → the row dicts ``e1_log.summarize_e1`` already counts, so the
                             owner's counting rules are unchanged: a drawing counts ONCE (by its
                             drawing number when the log has one); once approved at any revision
                             it stays approved, otherwise its LATEST revision decides (awaiting
                             a reply = Under review and Submitted; C / D = Not approved);
                             % Submitted = (Submitted − Rejected) ÷ Req.
  refresh_layout(path, l)  → re-derives the preview / codes / notes after the planner edits
                             a column, a sheet switch or a code.
  remember_layout(layout)  → stores the planner's confirmed layout keyed by a signature of the
                             sheet names + headings, so next week's log opens pre-filled.

Techniques: header scoring over the first 40 rows; a second heading row merged in; each
column's CONTENT profiled (dates incl. text dates, review codes, ID-like numbers, free text,
disciplines, submittal types) and weighed against its heading; duplicate headings resolved
by content; the code legend read from the rows above the headings; summary / legend sheets
and exact copies of a register left out, each with its reason.

``suggest_columns_with_local_ai`` is an OPTIONAL hook: when (and only when) the offline AI
brain (p6_chat.llm — in-process, never a cloud call) is set up, low-confidence columns can
be sent (heading + a few sample values, nothing else) for a second opinion, shown as a
labelled suggestion that is never applied by itself. Everything works identically without it.
"""
import copy
import csv
import hashlib
import io
import json
import os
import re
import time
from collections import Counter, defaultdict
from datetime import date, datetime

from p6_evm.classify import (E1_FIELD_SYNONYMS, VERDICTS, classify_action_code,
                             is_not_sent_status, legend_code_candidates, status_says_sent)
from p6_evm.e1_log import _as_dt, _latest, _rev_key, _sheet_trade, summarize_e1

# ── fields ────────────────────────────────────────────────────────────────────────────────
FIELDS = ('drawing_no', 'description', 'trade', 'submittal_type', 'building', 'revision',
          'reference', 'submitted', 'returned', 'planned', 'action_code')
FIELD_LABELS = {
    'drawing_no': 'Drawing No.',
    'description': 'Title / description',
    'trade': 'Discipline (trade)',
    'submittal_type': 'Submittal type',
    'building': 'Area / building',
    'revision': 'Revision',
    'reference': 'Transmittal / reference',
    'submitted': 'Date sent (submitted)',
    'returned': 'Reply date (returned)',
    'planned': 'Planned date',
    'action_code': 'Review code / status',
    'ignore': 'Ignore',
}
VERDICT_LABELS = {'approved': 'Approved', 'not_approved': 'Not approved',
                  'under_review': 'Under review', 'ignore': 'Ignore'}
DATE_FIELDS = ('submitted', 'returned', 'planned')
HEADER_SCAN_ROWS = 40
PROFILE_ROWS = 400
MAX_ROWS = 60000
MAX_COLS = 400
LOW_CONFIDENCE = 0.5
_MIN_ASSIGN = 0.3
STORE_FILE = 'layouts.json'
_STORE_CAP = 60

# ── heading vocabulary: the old E1 synonyms, extended ─────────────────────────────────────
_EXTRA_SYNONYMS = {
    'trade': ['discpline', 'dicipline', 'disipline', 'desipline', 'discipline name'],
    'submittal_type': ['submission type', 'type of document', 'type of drawing', 'drawing category'],
    'building': ['facility', 'building name'],
    'description': ['document description', 'drawing description', 'sheet title', 'manual title',
                    'item description', 'equipment'],
    'drawing_no': ['drawing no', 'drawings no', 'drawing number', 'drawings number', 'dwg no',
                   'dwgs no', 'dwg number', 'dwg', 'document no', 'document number', 'doc no',
                   'doc number', 'sheet no', 'drawing ref', 'drawing code', 'document code',
                   'document id', 'drawing id'],
    'revision': ['rev', 'revision', 'rev no', 'revision no', 'rev number', 'revision number'],
    'reference': ['transmittal no', 'transmittal number', 'transmittal ref', 'transmittal reference',
                  'transmittal', 'submittal no', 'submittal ref', 'submittal number', 'ref no',
                  'reference no', 'reference', 'letter ref'],
    'submitted': ['sent date', 'date sent', 'actual date of submission', 'date of submission',
                  'submission date', 'submitted date', 'issue date', 'issued date', 'date issued',
                  'actual submission', 'actual submission date'],
    'returned': ['received date', 'date received', 'reply date', 'date of reply', 'response date',
                 'return date', 'returned date', 'date returned', 'returned', 'consultant reply date',
                 'review date', 'approval date', 'received'],
    'planned': ['planned date', 'plan date', 'planned submission date', 'target date',
                'baseline date', 'due date', 'scheduled date', 'planed'],
    'action_code': ['current status', 'consultant status', 'consultant reply', 'reply',
                    'review status', 'approval status', 'approval code', 'status code',
                    'consultant action', 'consultant code', 'final status', 'latest status',
                    'reply status'],
}
# single words that say little on their own — a lower starting weight
_GENERIC = {'type', 'status', 'code', 'action', 'sent', 'area', 'zone', 'system', 'rev',
            'response', 'target', 'planned', 'submission', 'submitted', 'reply', 'received',
            'reference', 'forecast', 'baseline', 'location', 'block', 'subject', 'deliverable',
            'dwg', 'transmittal', 'equipment', 'returned', 'planed', 'division', 'disposition',
            'facility', 'speciality', 'specialty'}
_SERIAL_HEADERS = {'no', 'n', 'nr', 'sn', 's n', 'sr', 'sr no', 's no', 'ser', 'ser no', 'serial',
                   'serial no', 'item', 'item no', 'seq', 'sl', 'sl no', 'sno', 'srl', 'id'}


def _norm_text(v):
    return re.sub(r'[^a-z0-9]+', ' ', str(v).lower()).strip() if v is not None else ''


def _build_synonyms():
    table = defaultdict(dict)
    for field, words in list(E1_FIELD_SYNONYMS.items()) + list(_EXTRA_SYNONYMS.items()):
        for w in words:
            p = _norm_text(w)
            if not p:
                continue
            weight = 0.95 if ' ' in p else (0.7 if p in _GENERIC else 0.85)
            table[field][p] = max(weight, table[field].get(p, 0))
    return {f: sorted(d.items(), key=lambda kv: -len(kv[0])) for f, d in table.items()}


_SYN = _build_synonyms()


def _lev1(a, b):
    """True when a and b are exactly one edit apart (a typo: 'Discpline', 'PLANED')."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b):
        a, b = b, a
    for i in range(len(b)):
        if a == b[:i] + b[i + 1:]:
            return True
    return False


def _looks_serial(values):
    """A running number column (1, 2, 3 … restarting at 1 per section) with no heading."""
    nums, other = [], 0
    for v in values:
        if _empty(v):
            continue
        try:
            f = float(str(v).strip()) if not isinstance(v, bool) else None
        except ValueError:
            f = None
        if f is None or not f.is_integer():
            other += 1                       # a stray banner / note in the column
            continue
        nums.append(int(f))
    if len(nums) < 3 or other > 0.1 * (len(nums) + other):
        return False
    steps = sum(1 for a, b in zip(nums, nums[1:]) if b == a + 1 or b == 1)
    return steps >= 0.8 * (len(nums) - 1)


def _is_serial_header(header):
    return _norm_text(header) in _SERIAL_HEADERS or str(header or '').strip() == '#'


def _header_candidates(header):
    """{field: (weight 0–1, matched phrase)} for one heading, by whole-word phrase match
    (so 'rev' never matches inside 'previous') plus a one-typo match for long words."""
    h = _norm_text(header)
    out = {}
    if not h or _is_serial_header(header):
        return out
    padded, words = f' {h} ', h.split()
    for field, phrases in _SYN.items():
        for phrase, w in phrases:
            if f' {phrase} ' in padded:
                ww = min(1.0, w + (0.05 if phrase == h else 0.0))
            elif ' ' not in phrase and len(phrase) >= 6 and any(
                    len(x) >= 5 and _lev1(x, phrase) for x in words):
                ww = w * 0.85
            else:
                continue
            if ww > out.get(field, (0.0, ''))[0]:
                out[field] = (ww, phrase)
    if 'action_code' in out:
        w, p = out['action_code']
        ws = set(words)
        if ws & {'previous', 'prior', 'old', 'first', 'initial', 'last'}:
            out['action_code'] = (w * 0.5, p)
        elif ws & {'current', 'latest', 'final'}:
            out['action_code'] = (min(1.0, w + 0.05), p)
    return out


# ── cell helpers ────────────────────────────────────────────────────────────────────────
_BLANK_TOKENS = {'', '-', '--', '---', 'n/a', 'na', 'n.a', 'n.a.', 'nil', 'none', 'null', 'tbd',
                 'tba', 'tbc', '.', '…', '...', '?', 'x'}


def _empty(v):
    return v is None or (isinstance(v, str) and not v.strip())


def _is_blank(v):
    """Empty, or a placeholder a planner types for 'nothing yet' (N/A, TBD, -, …)."""
    if v is None:
        return True
    if isinstance(v, str):
        return ' '.join(v.split()).lower() in _BLANK_TOKENS
    return False


def _disp(v):
    """A short display string for a cell (dates as 05-Mar-2024, whole floats as ints)."""
    if v is None:
        return ''
    if isinstance(v, datetime):
        return v.strftime('%d-%b-%Y')
    if isinstance(v, date):
        return v.strftime('%d-%b-%Y')
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return ' '.join(str(v).split())


_NUM_RE = re.compile(r'^[-+]?\d+(?:[.,]\d+)?\s*%?$')


def _looks_number(v):
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    return isinstance(v, str) and bool(_NUM_RE.match(v.strip()))


# ── dates ───────────────────────────────────────────────────────────────────────────────
_MONTHS = {m: i + 1 for i, m in enumerate(
    ('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'))}
_MONTH_FULL = ('january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
               'september', 'october', 'november', 'december')
_ISO = re.compile(r'^(\d{4})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{1,2})$')
_NUM_DMY = re.compile(r'^(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{2}|\d{4})$')
_D_MON_Y = re.compile(r'^(\d{1,2})(?:st|nd|rd|th)?[\s\-/.,]*([A-Za-z]{3,9})\.?[\s\-/.,]*(\d{2}|\d{4})$')
_MON_D_Y = re.compile(r'^([A-Za-z]{3,9})\.?[\s\-/.]*(\d{1,2})(?:st|nd|rd|th)?,?[\s\-/.,]*(\d{2}|\d{4})$')
_TIME_TAIL = re.compile(r'[ T]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?\s*(?:am|pm)?$', re.I)


def _month(word):
    w = word.lower().rstrip('.')
    if len(w) < 3:
        return None
    if w in ('sept',):
        return 9
    if w[:3] in _MONTHS and (len(w) == 3 or any(f.startswith(w) for f in _MONTH_FULL)):
        return _MONTHS[w[:3]]
    return None


def parse_date(value, dayfirst=True):
    """A cell as a datetime, or None. Accepts real Excel dates and text dates:
    27-3-2024, 3/4/24 (day first unless told otherwise), 05-Mar-24, 5 March 2024,
    Mar 5, 2024, 2024-03-05, 12.8.2024. Impossible dates (31-2-2024) → None."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if not isinstance(value, str):
        return None
    if len(value) > 60 or not any(ch.isdigit() for ch in value):
        return None                                   # every date form carries digits
    s = ' '.join(value.split())
    if not s or len(s) > 40:
        return None
    s = _TIME_TAIL.sub('', s).strip()
    y = mo = d = None
    m = _ISO.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = _NUM_DMY.match(s)
        if m:
            a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            d, mo = (a, b) if dayfirst else (b, a)
        else:
            m = _D_MON_Y.match(s)
            if m:
                d, mo, y = int(m.group(1)), _month(m.group(2)), int(m.group(3))
            else:
                m = _MON_D_Y.match(s)
                if m:
                    mo, d, y = _month(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (y and mo and d):
        return None
    if y < 100:
        y += 2000 if y < 70 else 1900
    if not 1950 <= y <= 2100:
        return None
    try:
        return datetime(y, mo, d)
    except ValueError:
        return None


def detect_dayfirst(values):
    """Is a column of text dates written day-first? Evidence decides: one value like
    '12/25/2024' (second part > 12) proves month-first; otherwise day-first (the usual
    way on construction sites in the region, and what 27-3-2024 shows)."""
    day = month = 0
    for v in values:
        if not isinstance(v, str):
            continue
        m = _NUM_DMY.match(' '.join(v.split()))
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if a > 12 >= b:
            day += 1
        elif b > 12 >= a:
            month += 1
    return not month > day


def _as_date(v, dayfirst=True):
    d = parse_date(v, dayfirst)
    if d is None and isinstance(v, (int, float)) and not isinstance(v, bool) and 20000 < v < 80000:
        try:                                          # an Excel serial number in a date column
            from datetime import timedelta
            d = datetime(1899, 12, 30) + timedelta(days=float(v))
        except (OverflowError, ValueError):
            d = None
    return d


# ── content vocabularies ─────────────────────────────────────────────────────────────────
_DISC_STRONG = {'civil', 'structural', 'structure', 'structures', 'steel', 'arch', 'architectural',
                'architecture', 'mep', 'mechanical', 'electrical', 'plumbing', 'hvac', 'landscape',
                'landscaping', 'infrastructure', 'instrumentation', 'firefighting'}
_DISC_EXACT = _DISC_STRONG | {
    'civil works', 'steel structure', 'steel structures', 'steelwork', 'steel works', 'mech', 'elec',
    'electric', 'fire fighting', 'fire alarm', 'fire protection', 'infra', 'process', 'piping',
    'telecom', 'low current', 'elv', 'bms', 'interior', 'interiors', 'facade', 'roads', 'utilities',
    'geotechnical', 'survey', 'csa', 'e i', 'i c', 'ict', 'security', 'drainage', 'sanitary',
    'fit out', 'finishing', 'finishes', 'marine', 'cladding', 'lifts', 'elevators', 'automation',
    'mechanical electrical', 'arch structure', 'm e p'}
_SUBTYPES = {
    'sd', 'shop', 'shop drawing', 'shop drawings', 'shop dwg', 'shop dwgs', 'bbs',
    'bar bending schedule', 'bar list', 'bar schedule', 'ms', 'method statement',
    'method statements', 'mar', 'mir', 'material', 'materials', 'material submittal',
    'material approval', 'material approval request', 'ifc', 'issued for construction', 'ifa',
    'schematic', 'schematic design', 'detailed', 'detailed design', 'detail design', 'design',
    'concept', 'concept design', 'preliminary', 'basic design', 'calculation', 'calculations',
    'calc', 'calcs', 'design calculation', 'as built', 'asbuilt', 'as built drawing', 'o m',
    'o m manual', 'sample', 'samples', 'mock up', 'mockup', 'technical submittal', 'ts', 'tds',
    'datasheet', 'data sheet', 'catalogue', 'catalog', 'prequalification', 'pq', 'itp', 'rfi',
    'report', 'specification', 'document', 'drawing', 'drawings', 'dwg', 'coordination',
    'coordination drawing', 'combined services', 'csd', 'dd', 'cd', 'wd', 'working drawing',
    'ifr', 'afc', 'gad', 'general arrangement'}
_SUBTYPE_PREFIX = ('shop drawing', 'method statement', 'material ', 'detailed ', 'schematic ',
                   'as built', 'technical submittal', 'bar bending')


def _is_discipline(v):
    n = _norm_text(v)
    if not n or len(n) > 30:
        return False
    if n in _DISC_EXACT:
        return True
    w = n.split()
    return len(w) <= 3 and w[0] in _DISC_STRONG


def _is_subtype(v):
    n = _norm_text(v)
    if not n or len(n) > 40:
        return False
    return n in _SUBTYPES or any(n.startswith(p) for p in _SUBTYPE_PREFIX)


_ID_RE = re.compile(r'^(?=.*\d)(?=.*[A-Za-z0-9]\s*[-_/.]\s*[A-Za-z0-9])[A-Za-z0-9][A-Za-z0-9 \-_/.&()#]{1,70}$')
_SHORT_TOKEN = re.compile(r'^(?:rev\.?\s*)?[A-Za-z]?\d{0,3}[A-Za-z]?$', re.I)


def _is_idlike(v):
    if not isinstance(v, str):
        return False
    s = ' '.join(v.split())
    return len(s) <= 70 and s.count(' ') <= 4 and bool(_ID_RE.match(s)) and parse_date(s) is None


def _is_short_token(v):
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return 0 <= v < 100 and float(v).is_integer()
    s = str(v).strip()
    return 0 < len(s) <= 6 and bool(_SHORT_TOKEN.match(s))


def _is_codeish(v):
    """A short code-like value: A, B, C1, 2, (B), 'Code 3', U.A — or anything the rule reads."""
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return float(v).is_integer() and 0 <= v <= 9
    s = str(v).strip()
    compact = re.sub(r'[^A-Za-z0-9]', '', s)
    return 0 < len(compact) <= 3 or bool(re.match(r'^\(?\s*code\s*[A-Za-z0-9]{1,2}\s*\)?$', s, re.I))


def _verdict_of(raw, legend_verdicts):
    if legend_verdicts:
        for code in legend_code_candidates(raw):
            v = legend_verdicts.get(code)
            if v:
                return v if v in VERDICTS else None
    return classify_action_code(raw)


# ── column content profile ───────────────────────────────────────────────────────────────
def _profile(values, legend_verdicts):
    raw_filled = [v for v in values if not _empty(v)]
    vals = [v for v in raw_filled if not _is_blank(v)]
    n = len(vals)
    total = max(1, len(values))
    p = {'n': n, 'rows': len(values), 'fill': len(raw_filled) / total, 'empty': n == 0,
         'date': 0.0, 'text_date': 0.0, 'num': 0.0, 'verdict': 0.0, 'codeish': 0.0, 'id': 0.0,
         'long': 0.0, 'disc': 0.0, 'sub': 0.0, 'short': 0.0, 'mark': 0.0, 'distinct': 0,
         'samples': []}
    if not n:
        return p
    c = Counter()
    seen, samples = set(), []
    for v in vals:
        d = parse_date(v) if not isinstance(v, (int, float)) else None
        if d is not None:
            c['date'] += 1
            if isinstance(v, str):
                c['text_date'] += 1
        elif isinstance(v, str) and _mark_kind(v) in ('yes', 'no'):
            c['mark'] += 1                     # 'Yes' / 'Done' / 'Not submitted' in a date column
        if _looks_number(v):
            c['num'] += 1
        if _verdict_of(v, legend_verdicts) is not None or is_not_sent_status(v):
            c['verdict'] += 1                 # a status ('Approved', 'Under preparation')
        if _is_codeish(v):
            c['codeish'] += 1
        if _is_idlike(v):
            c['id'] += 1
        if isinstance(v, str) and len(v.strip()) >= 25 and len(v.split()) >= 3:
            c['long'] += 1
        if _is_discipline(v):
            c['disc'] += 1
        if _is_subtype(v):
            c['sub'] += 1
        if _is_short_token(v):
            c['short'] += 1
        s = _disp(v)
        if s not in seen:
            seen.add(s)
            if len(samples) < 8:
                samples.append(s[:60])
    for k in ('date', 'text_date', 'num', 'verdict', 'codeish', 'id', 'long', 'disc', 'sub', 'short', 'mark'):
        p[k] = c[k] / n
    p['distinct'] = len(seen)
    p['samples'] = samples
    return p


def _pct(x):
    return f'{round(100 * x)}%'


def _eg(p, k=2):
    s = ', '.join(p['samples'][:k])
    return f' (e.g. {s})' if s else ''


def _fit(field, p):
    """How well a column's CONTENT fits a field: (0–1, reason)."""
    if p['empty']:
        return (0.5 if field in DATE_FIELDS + ('action_code', 'revision') else 0.45,
                'the column is empty so far')
    heavy = p['date'] > 0.5 or p['num'] > 0.8
    if field in DATE_FIELDS:
        dm = p['date'] + 0.8 * p['mark']
        if dm < 0.2:
            return 0.0, f'its values are not dates{_eg(p)}'
        extra = ' — text dates read day-first' if p['text_date'] > 0.2 else ''
        if p['mark'] >= 0.05:
            extra += f'; {_pct(p["mark"])} are words like "yes" / "not yet" instead of a date'
        return min(1.0, dm), f'{_pct(p["date"])} of its values are dates{extra}'
    if p['date'] > 0.5:
        return 0.05, 'its values are dates'
    if field == 'action_code':
        f = max(p['verdict'], 0.6 * p['codeish'])
        if p['long'] > 0.5:
            f = min(f, 0.3)
        return f, (f'{_pct(p["verdict"])} of its values read as review codes{_eg(p, 4)}'
                   if p['verdict'] >= 0.5 else f'short code-like values{_eg(p, 4)}')
    if field == 'revision':
        return p['short'], f'short revision-like values{_eg(p, 4)}'
    if field in ('drawing_no', 'reference'):
        if p['num'] > 0.8:
            return 0.1, 'its values are plain numbers'
        return 0.45 + 0.55 * p['id'], (f'ID-like values{_eg(p)}' if p['id'] >= 0.5 else f'text values{_eg(p)}')
    if field == 'trade':
        if heavy:
            return 0.1, 'its values are numbers'
        return 0.65 + 0.35 * p['disc'], (f'its values are disciplines{_eg(p)}' if p['disc'] >= 0.5
                                         else f'values{_eg(p)}')
    if field == 'submittal_type':
        if heavy:
            return 0.1, 'its values are numbers'
        if p['disc'] >= 0.8 and p['sub'] < 0.2:
            return 0.3, f'its values look like disciplines{_eg(p)}'
        return 0.5 + 0.5 * p['sub'], (f'its values are submittal types{_eg(p)}' if p['sub'] >= 0.5
                                      else f'values{_eg(p)} are not usual submittal types')
    if field == 'building':
        return (0.1, 'its values are numbers') if heavy else (0.8, f'values{_eg(p)}')
    if field == 'description':
        if heavy:
            return 0.1, 'its values are numbers'
        return min(1.0, 0.55 + 0.3 * p['fill'] + 0.15 * p['long']), f'titles{_eg(p, 1)}'
    return 0.5, ''


def _content_only(p):
    """Fields a column's values alone can prove, without a helpful heading."""
    out = {}
    if p['n'] >= 2 and p['date'] < 0.2:
        if p['disc'] >= 0.8:
            out['trade'] = (0.7 * p['disc'], f'its values are disciplines{_eg(p)}')
        if p['sub'] >= 0.8 and p['disc'] < 0.5:
            out['submittal_type'] = (0.65 * p['sub'], f'its values are submittal types{_eg(p)}')
        if p['verdict'] >= 0.9 and p['short'] >= 0.8 and p['num'] < 0.5:
            out['action_code'] = (0.55, f'its values are review codes{_eg(p, 4)}')
    return out


# ── loading ─────────────────────────────────────────────────────────────────────────────
def _trim(row):
    row = list(row[:MAX_COLS])
    while row and _empty(row[-1]):
        row.pop()
    return [(v.strip() if isinstance(v, str) else v) for v in row]


def _load(path):
    """[(sheet title, rows)], 'xlsx' | 'csv'. Rows are lists of cell values (trailing empties
    trimmed; strings stripped)."""
    ext = os.path.splitext(str(path))[1].lower()
    if ext == '.xls':
        raise ValueError('This is an old .xls (Excel 97-2003) file. Open it in Excel and save '
                         'it as .xlsx, then load it again.')
    if ext in ('.csv', '.txt', '.tsv'):
        return [(os.path.splitext(os.path.basename(path))[0], _read_csv(path))], 'csv'
    import openpyxl
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception as exc:
        raise ValueError(f'Could not open the log as an Excel .xlsx workbook: {exc}')
    out = []
    try:
        for ws in wb.worksheets:
            rows, blank_run = [], 0
            for r in ws.iter_rows(values_only=True):
                t = _trim(r)
                rows.append(t)
                blank_run = blank_run + 1 if not t else 0
                if len(rows) >= MAX_ROWS or blank_run > 2000:
                    break
            while rows and not rows[-1]:
                rows.pop()
            out.append((ws.title, rows))
    finally:
        try:
            wb.close()
        except Exception:
            pass
    return out, 'xlsx'


def _read_csv(path):
    raw = open(path, 'rb').read()
    text = None
    for enc in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
        delim = dialect.delimiter
    except csv.Error:
        first = sample.splitlines()[0] if sample else ''
        delim = max(',;\t|', key=first.count)
    rows = []
    for r in csv.reader(io.StringIO(text), delimiter=delim):
        rows.append(_trim([c if c != '' else None for c in r]))
        if len(rows) >= MAX_ROWS:
            break
    while rows and not rows[-1]:
        rows.pop()
    return rows


# ── sheet anatomy: headings, continuation row, sections, legend ─────────────────────────
def _cells(row):
    return [(j, v) for j, v in enumerate(row) if not _empty(v)]


def _is_texty(v):
    return isinstance(v, str) and not _looks_number(v) and parse_date(v) is None


def _is_dataish(v):
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float, datetime, date)):
        return True
    return isinstance(v, str) and (_looks_number(v) or parse_date(v) is not None)


def _data_like(row):
    c = _cells(row)
    return len(c) >= 2 and (any(_is_dataish(v) for _, v in c) or len(c) >= 3)


def _row_fields(row):
    fields = set()
    for _, v in _cells(row):
        if _is_texty(v) and len(v) <= 80:
            c = _header_candidates(v)
            if c:
                fields.add(max(c, key=lambda f: c[f][0]))
    return fields


def _find_header(grid):
    best = None
    for i in range(min(len(grid), HEADER_SCAN_ROWS)):
        cells = _cells(grid[i])
        if len(cells) < 2:
            continue
        texts = [v for _, v in cells if _is_texty(v) and len(v) <= 80]
        fields = _row_fields(grid[i])
        if len(fields) < 2 or len(texts) < 2:
            continue
        datai = sum(1 for _, v in cells if _is_dataish(v))
        below = any(_data_like(grid[k]) for k in range(i + 1, min(len(grid), i + 7)))
        score = 2.0 * len(fields) + 0.3 * min(len(texts), 20) - 1.5 * datai + (1.0 if below else -2.0)
        if best is None or score > best[0] + 1e-9:
            best = (score, i)
    return best[1] if best else None


_FOOTER_RE = re.compile(r'^\s*(?:\*|(?:sub\s*-?\s*|grand\s+)?totals?\b|notes?\b|remarks?\b)', re.I)
_TOTAL_RE = re.compile(r'^\s*(?:sub\s*-?\s*|grand\s+)?totals?\b', re.I)


def _is_section(cells):
    if len(cells) != 1:
        return False
    j, v = cells[0]
    if not isinstance(v, str):
        return False
    s = ' '.join(v.split())
    return (j <= 1 and 0 < len(s) <= 40 and not _FOOTER_RE.match(s)
            and not _looks_number(s) and parse_date(s) is None)


def _is_continuation(grid, h):
    """Is the row under the heading row a second heading line ('TO SUBMIT O&M' under
    'PLANNED DATE')? Only text, not a section title, sitting under headed columns, and not
    values that repeat further down (which would make it data)."""
    if h + 1 >= len(grid):
        return False
    nxt, hdr = _cells(grid[h + 1]), dict(_cells(grid[h]))
    if not nxt or _is_section(nxt):
        return False
    if any(not _is_texty(v) or len(v) > 60 for _, v in nxt):
        return False
    if not any(j in hdr for j, _ in nxt):
        return False
    if len(nxt) > max(1, int(0.7 * len(hdr))):
        return False
    if sum(1 for _, v in nxt if _is_discipline(v) or _is_subtype(v)) > len(nxt) / 2:
        return False
    later = grid[h + 2: h + 40]
    for j, v in nxt:
        key = _norm_text(v)
        if any(j < len(r) and _norm_text(r[j]) == key for r in later if not _empty(r[j] if j < len(r) else None)):
            return False
    return True


_LEG1 = re.compile(r'^(?P<m>[A-Za-z][A-Za-z &/,.\'-]*?)\s*\(\s*(?:code\s*)?(?P<c>[A-Za-z0-9]{1,3})\s*\)$', re.I)
_LEG2 = re.compile(r'^(?:code\s*)?(?P<c>[A-Za-z0-9]{1,3})\s*[-–—=:)]\s*(?P<m>[A-Za-z].*)$', re.I)
_LEG3 = re.compile(r'^(?P<m>[A-Za-z][A-Za-z &/,.\'-]*?)\s*[-–—=:]\s*(?:code\s*)?(?P<c>[A-Za-z0-9]{1,3})$', re.I)


_REVIEW_WORDS = re.compile(r'approv|reject|resubmit|revise|pending|review|objection|accept|await|'
                           r'comment|noted|exception|hold|waiting', re.I)


def _legend_verdict(meaning):
    m = ' '.join(str(meaning).split())
    if len(re.sub(r'[^A-Za-z]', '', m)) < 3 or not _REVIEW_WORDS.search(m):
        return None
    first = re.split(r'[,;(]|\s[-–—]\s', m)[0]
    return classify_action_code(first) or classify_action_code(m)


def _find_legend(rows):
    """Code legend cells ('Approved ( A )', 'A - Approved', 'Code 1 – Approved',
    'Approved as Noted (B)') → {CODE: {'meaning', 'verdict'}}."""
    found = {}
    for row in rows:
        for _, v in _cells(row):
            if not isinstance(v, str) or len(v) > 120:
                continue
            s = ' '.join(v.split())
            for rx in (_LEG1, _LEG2, _LEG3):
                m = rx.match(s)
                if not m:
                    continue
                verdict = _legend_verdict(m.group('m'))
                if verdict:
                    found.setdefault(m.group('c').upper(), {'meaning': m.group('m').strip(' -–:'),
                                                            'verdict': verdict})
                    break
    return found


_SUMMARY_TITLE = re.compile(r'summ|overview|dashboard|statistic|chart|kpi|cover|contents|index|report card', re.I)
_LEGEND_TITLE = re.compile(r'legend|codes?\b|instruction|lookup|read ?me', re.I)
_GENERIC_SHEET = re.compile(r'^(sheet|tabelle|feuil|hoja|data|export|table)\s*\d*$', re.I)


def _numeric_share(rows):
    tot = num = dates = 0
    for r in rows:
        for _, v in _cells(r):
            tot += 1
            if _looks_number(v):
                num += 1
            elif isinstance(v, (datetime, date)):
                dates += 1
    return (num / tot if tot else 0.0), (dates / tot if tot else 0.0)


# ── per-sheet analysis ───────────────────────────────────────────────────────────────────
def _sheet_label(title):
    """Discipline / type named by a sheet: noise words dropped ('Civil Drawings' → 'Civil',
    'O&M LOG' → 'O&M', 'SPARE PARTS LOG(Arch)' → 'SPARE PARTS (Arch)')."""
    return _sheet_trade(re.sub(r'\s*\(', ' (', str(title or '')).strip())


def _col_letter(i):
    s, i = '', i + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _level(conf):
    return 'high' if conf >= 0.75 else ('medium' if conf >= 0.5 else 'check')


def _analyze_sheet(title, grid, legend_all, fmt):
    sh = {'sheet': title, 'kind': 'skip', 'include': False, 'reason': '', 'header_rows': [],
          'data_start': None, 'row_count': 0, 'columns': [], 'sections': [], 'warnings': [],
          'trade_source': None, 'type_source': None}
    if not any(grid):
        sh['reason'] = 'The sheet is empty.'
        return sh, {}
    h = _find_header(grid)
    legend = _find_legend(grid[:h] if h is not None else grid[:HEADER_SCAN_ROWS])
    for k, v in legend.items():
        legend_all.setdefault(k, v)
    if _SUMMARY_TITLE.search(title or '') and fmt != 'csv':
        sh['kind'] = 'summary'
        sh['reason'] = f'"{title}" is a summary sheet — its numbers are totals, not a list of drawings.'
        return sh, legend
    if h is None:
        numeric, _ = _numeric_share(grid[:200])
        if legend and (_LEGEND_TITLE.search(title or '') or numeric < 0.5):
            sh['kind'] = 'legend-only'
            sh['reason'] = 'Only a legend of review codes — used to read the codes, nothing counted.'
        elif numeric >= 0.4:
            sh['kind'] = 'summary'
            sh['reason'] = 'A table of counts (totals per trade), not a list of drawings — not counted.'
        else:
            sh['reason'] = 'No column headings recognised on this sheet — not counted.'
        return sh, legend

    two = _is_continuation(grid, h)
    header_idx = [h, h + 1] if two else [h]
    heads = {}
    for r in header_idx:
        for j, v in _cells(grid[r]):
            t = _disp(v)
            heads[j] = f'{heads[j]} {t}'.strip() if j in heads and t not in heads[j] else heads.get(j, t)
    start = header_idx[-1] + 1
    sh['header_rows'] = [r + 1 for r in header_idx]
    sh['data_start'] = start + 1

    data, sections = [], []
    hdr_norm = [_norm_text(v) for v in grid[h]]
    for r in range(start, len(grid)):
        kind = _row_kind(grid[r], hdr_norm)
        if kind == 'data':
            data.append(grid[r])
        elif kind == 'section':
            s = _disp(_cells(grid[r])[0][1])
            if s not in sections:
                sections.append(s)
    sh['row_count'] = len(data)
    sh['sections'] = sections

    ncols = max([max(heads) + 1 if heads else 0] + [len(r) for r in data[:PROFILE_ROWS]])
    legend_verdicts = {k: v['verdict'] for k, v in legend_all.items()}
    cols = []
    for j in range(min(ncols, MAX_COLS)):
        header = heads.get(j, '')
        prof = _profile([r[j] if j < len(r) else None for r in data[:PROFILE_ROWS]], legend_verdicts)
        if not header and prof['n'] == 0:
            continue
        scored = {}
        for f, (w, phrase) in _header_candidates(header).items():
            fit, why = _fit(f, prof)
            scored[f] = (w * fit, f'heading says "{phrase}"' + (f'; {why}' if why else ''))
        for f, (s, why) in _content_only(prof).items():
            if s > scored.get(f, (0.0, ''))[0]:
                scored[f] = (s, why)
        serial = _is_serial_header(header) if header else _looks_serial(
            [r[j] if j < len(r) else None for r in data[:PROFILE_ROWS]])
        cols.append({'index': j, 'letter': _col_letter(j), 'header': header,
                     'samples': prof['samples'][:6], '_scored': scored, '_prof': prof,
                     '_serial': serial})

    taken = {}
    ranked = sorted(((s, c['index'], f, why, c) for c in cols for f, (s, why) in c['_scored'].items()),
                    key=lambda t: (-t[0], t[1]))
    for s, _, f, why, c in ranked:
        if s < _MIN_ASSIGN:
            break
        if f in taken or 'field' in c:
            continue
        c.update(field=f, confidence=round(min(1.0, s), 2), reason=_cap(why))
        taken[f] = c
    for c in cols:
        if 'field' in c:
            continue
        c['field'] = 'ignore'
        rivals = [(s, f) for f, (s, _) in c['_scored'].items() if f in taken and s >= 0.2]
        if c['_serial']:
            c['confidence'], c['reason'] = 0.9, 'A running serial number — not needed for counting.'
        elif rivals:
            s, f = max(rivals)
            other = taken[f]
            c['confidence'] = 0.65
            c['reason'] = (f'Could be {FIELD_LABELS[f]}, but column {other["letter"]} '
                           f'("{other["header"] or "no heading"}") fits better'
                           + (f' — this one holds {", ".join(c["samples"][:2])}' if c['samples'] else '') + '.')
        elif not c['header']:
            c['confidence'] = 0.35
            c['reason'] = (f'No heading; values like {", ".join(c["samples"][:2])} — not used.'
                           if c['samples'] else 'No heading and no values — not used.')
        else:
            c['confidence'] = 0.8
            c['reason'] = 'Not needed to count drawings.'
    for c in cols:
        c['level'] = _level(c['confidence'])
    sh['columns'] = [{k: v for k, v in c.items() if not k.startswith('_')} for c in cols]

    # a register lists drawings: something that names them + something that tracks them
    names = {'description', 'drawing_no', 'reference'} & set(taken)
    tracks = {'submitted', 'action_code', 'planned', 'returned'} & set(taken)
    numeric, dates = _numeric_share(data[:200])
    code_col = taken.get('action_code')
    if (numeric >= 0.5 and dates < 0.1 and not (code_col and code_col['_prof']['verdict'] >= 0.5)) or \
            any(w in _norm_text(' '.join(heads.values())).split() for w in ('qty', 'quantity')) and numeric >= 0.4:
        sh['kind'] = 'summary'
        eg = ', '.join(_disp(v) for _, v in _cells(data[0])[:4]) if data else ''
        sh['reason'] = ('The rows hold totals and percentages' + (f' ({eg})' if eg else '')
                        + ' — a summary of counts, not a list of drawings. Not counted.')
    elif not names or not tracks or not data:
        sh['reason'] = ('No drawing title / number column found.' if not names else
                        'No submission date or review code column found.' if not tracks else
                        'No rows under the headings.') + ' Not counted.'
    else:
        sh['kind'], sh['include'] = 'register', True
        sh['reason'] = f'A list of drawings — {len(data)} rows under the headings on row {sh["header_rows"][0]}.'
    return sh, legend


def _cap(s):
    s = s.strip()
    return (s[0].upper() + s[1:] + ('' if s.endswith('.') else '.')) if s else s


def _row_kind(row, hdr_norm):
    cells = _cells(row)
    if not cells:
        return 'blank'
    if len(cells) == 1:
        return 'section' if _is_section(cells) else 'note'
    first = cells[0][1]
    if isinstance(first, str) and _TOTAL_RE.match(first):
        return 'footer'
    if hdr_norm:
        same = sum(1 for j, v in cells if j < len(hdr_norm) and hdr_norm[j] and _norm_text(v) == hdr_norm[j])
        if same >= max(2, int(0.6 * len(cells))):
            return 'header'
    return 'data'


# ── fields → rows ────────────────────────────────────────────────────────────────────────
def _code_key(raw):
    """How a review-code value is shown/keyed: whole numbers as '1', short codes upper-case,
    words with their spacing tidied ('Approved (Code B)')."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return str(int(raw)) if float(raw).is_integer() else str(raw)
    s = ' '.join(str(raw).split())
    if not s or _is_blank(s):
        return None
    m = re.match(r'^(\d+)\.0+$', s)
    if m:                                     # '2.0' typed as text = code 2
        return m.group(1).lstrip('0') or '0'
    return s.upper() if len(re.sub(r'[^A-Za-z0-9]', '', s)) <= 3 and len(s) <= 5 else s


def _sanitize(layout):
    lay = layout if isinstance(layout, dict) else {}
    cm = lay.get('code_map') if isinstance(lay.get('code_map'), dict) else {}
    code_map = {str(k): v for k, v in cm.items() if v in VERDICTS + ('ignore',)}
    legend = lay.get('legend') if isinstance(lay.get('legend'), dict) else {}
    sheets = []
    for s in lay.get('sheets') or []:
        if not isinstance(s, dict) or not isinstance(s.get('sheet'), str):
            continue
        cols = []
        for c in s.get('columns') or []:
            if not isinstance(c, dict):
                continue
            idx, f = c.get('index'), c.get('field')
            if not isinstance(idx, int) or isinstance(idx, bool) or not 0 <= idx < MAX_COLS:
                continue
            cols.append({'index': idx, 'field': f if f in FIELDS else 'ignore'})
        try:
            ds = int(s.get('data_start') or 0)
        except (TypeError, ValueError):
            ds = 0
        hr = [int(x) for x in (s.get('header_rows') or []) if isinstance(x, int) and not isinstance(x, bool)]
        sheets.append({'sheet': s['sheet'], 'include': bool(s.get('include')), 'data_start': ds,
                       'header_rows': hr, 'columns': cols})
    return {'sheets': sheets, 'code_map': code_map, 'legend': legend}


_TR_REV = re.compile(r'[\s_\-/]*\(?\s*(?:rev(?:ision)?\s*\.?\s*[-_]?\s*\d+|r\d{1,2})\s*\)?\s*$', re.I)


def _transmittal_base(ref):
    s = ' '.join(str(ref).split())
    base = _TR_REV.sub('', s).strip()
    return (base or s).upper()


def _build_rows(sheet_grids, layout, filename=''):
    """Rows (the dicts summarize_e1 counts) + per-sheet notes, from a sanitized layout."""
    lay = _sanitize(layout)
    code_map = lay['code_map']
    legend_verdicts = {}
    for k, v in lay['legend'].items():
        verdict = code_map.get(str(k).upper(), (v or {}).get('verdict') if isinstance(v, dict) else None)
        if verdict:
            legend_verdicts[str(k).upper()] = verdict

    def verdict_for(raw):
        key = _code_key(raw)
        if key is None:
            return None
        if key in code_map:
            v = code_map[key]
            return v if v in VERDICTS else None
        return _verdict_of(raw, legend_verdicts)

    grids = dict(sheet_grids)
    default_type = ('Shop Drawing' if 'shop' in filename.lower() else
                    'Design' if 'design' in filename.lower() else 'Drawings')
    all_rows, notes = [], {}
    for s in lay['sheets']:
        if not s['include'] or s['sheet'] not in grids:
            continue
        grid = grids[s['sheet']]
        fields = {}
        for c in sorted(s['columns'], key=lambda c: c['index']):
            if c['field'] in FIELDS:
                fields.setdefault(c['field'], c['index'])
        start = s['data_start'] - 1 if s['data_start'] >= 1 else 0
        start = min(max(start, 0), len(grid))
        hr0 = s['header_rows'][0] if s['header_rows'] else 0
        hdr_norm = [_norm_text(v) for v in grid[hr0 - 1]] if 1 <= hr0 <= len(grid) else []
        sheet_trade = _sheet_label(s['sheet'])
        generic_name = bool(_GENERIC_SHEET.match(s['sheet'].strip()))
        body = grid[start:]
        dayfirst = {f: detect_dayfirst([r[fields[f]] for r in body if fields[f] < len(r)])
                    for f in DATE_FIELDS if f in fields}
        note = {'inferred_sent': 0, 'no_trade': 0, 'no_type': 0, 'multi_sheet': 0, 'multi_tr': 0,
                'by_transmittal': 0, 'tracked': 0, 'not_sent': Counter(),
                'words': {'submitted': Counter(), 'returned': Counter()},
                'unknown_codes': Counter(), 'rows': 0}

        def get(row, f):
            j = fields.get(f)
            return row[j] if j is not None and j < len(row) else None

        section, recs = None, []
        for off, row in enumerate(body):
            kind = _row_kind(row, hdr_norm)
            if kind == 'section':
                section = _disp(_cells(row)[0][1])
                continue
            if kind != 'data':
                continue
            if 'trade' in fields:
                trade = get(row, 'trade')
                trade = None if _is_blank(trade) else trade
                trade = trade if trade is not None else section
            else:
                trade = section or (None if generic_name else sheet_trade) or 'General'
            if 'submittal_type' in fields:
                typ = get(row, 'submittal_type')
                typ = None if _is_blank(typ) else typ
            else:
                typ = (sheet_trade if 'trade' in fields or section else None) or default_type
                if generic_name and 'trade' in fields:
                    typ = default_type
            trade_s, typ_s = _disp(trade) if trade is not None else '', _disp(typ) if typ is not None else ''
            if not trade_s:
                note['no_trade'] += 1
                continue
            if not typ_s:
                note['no_type'] += 1
                continue
            vals = {f: get(row, f) for f in ('description', 'drawing_no', 'reference', 'submitted',
                                              'action_code', 'planned', 'building', 'returned')}
            if all(_is_blank(v) for v in vals.values()):
                continue
            action = get(row, 'action_code')
            action = None if _is_blank(action) else action
            marks = {}
            for f in ('submitted', 'returned'):
                raw = get(row, f)
                marks[f], kind = _read_mark(raw, dayfirst.get(f, True))
                if kind in ('yes', 'no', 'word'):
                    note['words'][f][('yes' if kind == 'yes' else 'no', _disp(raw)[:40])] += 1
            rec = {
                'trade': trade_s,
                'submittal_type': typ_s,
                'building': get(row, 'building'),
                'description': get(row, 'description'),
                'drawing_no': None if _is_blank(get(row, 'drawing_no')) else _disp(get(row, 'drawing_no')),
                'revision': None if _is_blank(get(row, 'revision')) else _disp(get(row, 'revision')),
                'reference': None if _is_blank(get(row, 'reference')) else _disp(get(row, 'reference')),
                'submitted': marks['submitted'],
                'returned': marks['returned'],
                'planned': _as_date(get(row, 'planned'), dayfirst.get('planned', True)),
                'action_code': action,
                'verdict': verdict_for(action),
                'sheet': s['sheet'], 'row': start + off + 1, 'section': section,
            }
            if action is not None and rec['verdict'] is None:
                if is_not_sent_status(action):            # 'Under preparation', 'Pending submission'
                    note['not_sent'][_code_key(action)] += 1
                elif _code_key(action) not in code_map:
                    note['unknown_codes'][_code_key(action)] += 1
            # proof it was sent although the log has no date: a REPLY (approved / not
            # approved, or a reply date) or wording that puts it WITH the consultant
            # ('Under review', 'U.A'). A bare W / P / 'Pending' is not a reply.
            replied = rec['verdict'] in ('approved', 'not_approved') or isinstance(rec['returned'], datetime)
            with_reviewer = rec['verdict'] == 'under_review' and status_says_sent(action)
            if rec['submitted'] is None and (replied or with_reviewer):
                rec['submitted'] = rec['returned'] if isinstance(rec['returned'], datetime) else True
                note['inferred_sent'] += 1
            if rec['submitted'] is not None or rec['verdict'] is not None:
                note['tracked'] += 1
            recs.append(rec)
        note['rows'] = len(recs)

        if 'drawing_no' in fields:
            _drawing_keys(recs, note)
        notes[s['sheet']] = note
        all_rows.extend(recs)

    for f in ('trade', 'submittal_type'):              # 'plumbing' / 'Plumbing ' → one group
        spell = defaultdict(Counter)
        for r in all_rows:
            spell[r[f].casefold()][r[f]] += 1
        canon = {k: c.most_common(1)[0][0] for k, c in spell.items()}
        for r in all_rows:
            r[f] = canon[r[f].casefold()]
    return all_rows, notes


# Words typed in a date column instead of a date. Only a clear YES counts as "it happened";
# a no / not-yet word, or any other text, is nothing (and the sheet notes list them).
_NEG_MARK = re.compile(r'^(?:not\b|no\b|non\b|pending|await|waiting|to be\b|tbs\b|under\s*prep|in\s*prep'
                       r'|prep|yet\b|n\s*/?\s*s\b|n\.\s*s\b|outstanding|on\s*hold|hold\b|cancel|withdrawn)',
                       re.I)
_POS_MARK = re.compile(r'^(?:yes|y|done|ok|okay|(?:re-?\s?)?submitted|sent|issued|delivered|received'
                       r'|returned|replied|[\u2713\u2714\u221a\u2611])(?:\W|$)', re.I)


def _mark_kind(s):
    s = ' '.join(str(s).split())
    if _NEG_MARK.match(s):
        return 'no'
    if _POS_MARK.match(s):
        return 'yes'
    return 'word'


def _read_mark(v, dayfirst):
    """A submitted / returned cell → (value, kind). kind: 'blank' (empty, N/A, TBD, -),
    'date' (value = the date), 'yes' ('Yes', 'Done', 'Submitted', a tick — value kept: it
    happened, no date), 'no' ('Not submitted', 'Not yet', 'No', 'Pending' — value None) or
    'word' (any other text — value None: not a date and not a clear yes)."""
    if _is_blank(v):
        return None, 'blank'
    d = _as_date(v, dayfirst)
    if d is not None:
        return d, 'date'
    if isinstance(v, bool):
        return (v, 'yes') if v else (None, 'no')
    if isinstance(v, (int, float)):
        return (v, 'yes') if v else (None, 'no')
    kind = _mark_kind(v)
    return (v if kind == 'yes' else None), kind


def _date_or_mark(v, dayfirst):
    """A submitted / returned cell: its date, a clear yes-word kept as-is, else None."""
    return _read_mark(v, dayfirst)[0]


def _title_key(v):
    return ' '.join(str(v or '').split()).casefold()


def _drawing_keys(recs, note):
    """Drawing identity when the log has a Drawing No. column:
      * the drawing number (revisions of one number = one drawing, whatever the title says);
      * a number shared by several sheets IN ONE SUBMISSION (same transmittal + revision,
        different titles) = one drawing per sheet title;
      * no number (blank / N/A) = the transmittal's revision chain ('T-11', 'T-11 Rev.01');
      * nothing at all = the old (area, title) key (summarize_e1's default)."""
    subs = defaultdict(set)
    for r in recs:
        dn = ' '.join((r['drawing_no'] or '').split()).upper()
        if dn:
            chain = 'dwg:' + dn
        elif r['reference']:
            chain = 'tr:' + _transmittal_base(r['reference'])
            note['by_transmittal'] += 1
        else:
            chain = None
        r['_chain'] = chain
        if chain:
            sub = (r['reference'] or '', r['revision'] or '',
                   '' if r['reference'] else _disp(r['submitted']) if isinstance(r['submitted'], datetime) else '')
            subs[(chain, sub)].add(_title_key(r['description']))
    multi = {chain for (chain, _), titles in subs.items() if len(titles) > 1}
    note['multi_sheet'] = sum(1 for c in multi if c.startswith('dwg:'))
    note['multi_tr'] = len(multi) - note['multi_sheet']
    for r in recs:
        chain = r.pop('_chain')
        if chain:
            r['drawing_key'] = chain + ('|' + _title_key(r['description']) if chain in multi else '')


def _rejected_then_resent(rows):
    """{sheet: number of drawings} returned Not approved (C/D) whose LATEST submission is
    back under review (a W / pending code, or sent with no reply yet) and that have not been
    approved. Owner decision ELOG-4 (2026-09-27): the latest revision decides, so these count
    as Under review (and Submitted), not Not approved — this tells the planner how many.
    "Latest" is judged exactly as summarize_e1 judges it."""
    per = defaultdict(list)
    for i, r in enumerate(rows):
        dk = r.get('drawing_key') or (str(r.get('building') or '').strip(),
                                      str(r.get('description') or '').strip())
        per[(r.get('sheet'), r['trade'], r['submittal_type'], dk)].append((i, r))
    out = Counter()
    for (sheet, *_), rs in per.items():
        subs = []
        for i, r in rs:
            v = r.get('verdict')
            if (v is None and r.get('submitted') is not None and r.get('action_code') is None
                    and r.get('returned') is None):
                v = 'under_review'                   # sent, no reply yet
            if v == 'approved':
                subs = None
                break
            if v in ('not_approved', 'under_review'):
                subs.append((_rev_key(r.get('revision')), _as_dt(r.get('submitted')), i, v))
        if subs and any(s[3] == 'not_approved' for s in subs) and _latest(subs)[3] == 'under_review':
            out[sheet] += 1
    return out


# ── proposal assembly ───────────────────────────────────────────────────────────────────
def _signature(sheet_grids, sheets, fmt):
    parts = []
    for (title, grid), sh in zip(sheet_grids, sheets):
        heads = [_norm_text(c.get('header')) for c in sh['columns']] if sh['kind'] == 'register' else []
        parts.append(['#csv' if fmt == 'csv' else title, sh['kind'], heads])
    return hashlib.sha1(json.dumps(parts, sort_keys=True).encode('utf-8')).hexdigest()[:16]


def _sheet_sig(sh):
    return hashlib.sha1(json.dumps([_norm_text(c.get('header')) for c in sh['columns']]).encode()).hexdigest()[:12]


def _dedupe_registers(sheets, sheet_grids, filename):
    """Two sheets holding the same list (an old and a new copy of the O&M log) would count
    every item twice: keep the fuller one, switch the other off — with the reason."""
    regs = [s for s in sheets if s['kind'] == 'register' and s['include']]
    keysets = {}
    for s in regs:
        rows, _ = _build_rows(sheet_grids, {'sheets': [s], 'code_map': {}, 'legend': {}}, filename)
        keysets[s['sheet']] = ({(_title_key(r['description']), r['trade'].casefold()) for r in rows
                                if _title_key(r['description'])}, len(rows),
                               sum(1 for r in rows if r['verdict'] or r['submitted']))
    for i, a in enumerate(regs):
        for b in regs[i + 1:]:
            if not (a['include'] and b['include']):
                continue
            ka, kb = keysets[a['sheet']], keysets[b['sheet']]
            small = min(len(ka[0]), len(kb[0]))
            if small < 3 or len(ka[0] & kb[0]) < 0.8 * small:
                continue
            keep, drop = (a, b) if (ka[2], ka[1]) > (kb[2], kb[1]) else (b, a)
            drop['include'] = False
            drop['duplicate_of'] = keep['sheet']
            drop['reason'] = (f'Looks like a copy of sheet "{keep["sheet"]}" (the same items) — switched off '
                              f'so nothing counts twice. Switch it on if it is a different register.')


def _finalize(prop, sheet_grids):
    """(Re)derive everything that follows from the chosen fields: where discipline and type
    come from, the review codes found, notes, and the preview counts."""
    filename = prop.get('file') or ''
    legend = prop.get('legend') or {}
    code_map = prop.setdefault('code_map', {})
    grids = dict(sheet_grids)

    counts, raw_of = Counter(), {}
    for sh in prop['sheets']:
        fields = {c['field']: c for c in sorted(sh['columns'], key=lambda c: c['index'])[::-1]
                  if c['field'] in FIELDS}
        tcol, ycol = fields.get('trade'), fields.get('submittal_type')
        sheet_trade = _sheet_label(sh['sheet'])
        generic = bool(_GENERIC_SHEET.match(sh['sheet'].strip()))
        if tcol:
            sh['trade_source'] = {'kind': 'column', 'value': tcol['header'] or f'column {tcol["letter"]}'}
        elif sh.get('sections'):
            sh['trade_source'] = {'kind': 'section', 'value': ', '.join(sh['sections'][:6])}
        else:
            sh['trade_source'] = {'kind': 'sheet-name', 'value': (None if generic else sheet_trade) or 'General'}
        if ycol:
            sh['type_source'] = {'kind': 'column', 'value': ycol['header'] or f'column {ycol["letter"]}'}
        elif (tcol or sh.get('sections')) and sheet_trade and not generic:
            sh['type_source'] = {'kind': 'sheet-name', 'value': sheet_trade}
        else:
            dt = ('Shop Drawing' if 'shop' in filename.lower() else
                  'Design' if 'design' in filename.lower() else 'Drawings')
            sh['type_source'] = {'kind': 'default', 'value': dt}
        acol = fields.get('action_code')
        if sh['include'] and acol is not None and sh['sheet'] in grids:
            grid = grids[sh['sheet']]
            start = max(0, (sh.get('data_start') or 1) - 1)
            hdr = [_norm_text(v) for v in (grid[sh['header_rows'][0] - 1] if sh.get('header_rows') else [])]
            for row in grid[start:]:
                if _row_kind(row, hdr) != 'data':
                    continue
                v = row[acol['index']] if acol['index'] < len(row) else None
                k = _code_key(v)
                if k is not None:
                    counts[k] += 1
                    raw_of.setdefault(k, v)

    codes = []
    for k, n in counts.most_common():
        cands = legend_code_candidates(raw_of[k])
        leg = next((c for c in cands if c in legend), None)
        if leg:
            auto, source, meaning = legend[leg]['verdict'], 'legend', legend[leg]['meaning']
        else:
            auto = classify_action_code(raw_of[k])
            source = 'rule' if auto else 'unknown'
            meaning = VERDICT_LABELS[auto] if auto else 'Not recognised — choose what it means'
        not_sent = not auto and is_not_sent_status(raw_of[k])
        if not_sent:
            source, meaning = 'rule', 'Not sent yet — counted as required, not submitted'
        verdict = code_map.get(k) or auto or 'ignore'
        code_map.setdefault(k, verdict)
        codes.append({'value': k, 'count': n, 'verdict': code_map[k], 'auto': auto or 'ignore',
                      'source': source, 'meaning': meaning, 'known': bool(auto) or not_sent})
    for k, v in legend.items():
        if k not in counts:
            code_map.setdefault(k, v['verdict'])
            codes.append({'value': k, 'count': 0, 'verdict': code_map[k], 'auto': v['verdict'],
                          'source': 'legend', 'meaning': v['meaning'], 'known': True})
    prop['codes'] = codes

    rows, notes = _build_rows(sheet_grids, prop, filename)
    resent = _rejected_then_resent(rows)
    for sh in prop['sheets']:
        w = []
        n = notes.get(sh['sheet'])
        sh['tracked_rows'] = n['tracked'] if n else 0
        sh['untracked'] = bool(n and n['rows'] and not n['tracked'])
        if resent.get(sh['sheet']):
            w.append(f'{resent[sh["sheet"]]} drawing(s) came back Not approved (C/D) and have been '
                     f'resubmitted — the latest revision decides, so they count as Under review '
                     f'(and Submitted), not Not approved.')
        if n:
            if n['inferred_sent']:
                w.append(f'{n["inferred_sent"]} row(s) have a reply (a review code or a reply date) or a status '
                         f'placing them with the consultant, but no submission date — counted as submitted '
                         f'(a reply means it was sent).')
            if n['not_sent']:
                ks = ', '.join(f'"{k}"' for k, _ in n['not_sent'].most_common(3))
                w.append(f'{sum(n["not_sent"].values())} row(s) say the drawing is not sent yet ({ks}) — '
                         f'counted as required, not submitted and not under review.')
            if n['multi_sheet']:
                w.append(f'{n["multi_sheet"]} drawing number(s) cover several sheets in one submission '
                         f'— each sheet title counted as its own drawing.')
            if n['multi_tr']:
                w.append(f'{n["multi_tr"]} transmittal(s) without drawing numbers list several sheets '
                         f'— each sheet title counted as its own drawing.')
            if n['by_transmittal']:
                w.append(f'{n["by_transmittal"]} row(s) have no drawing number — grouped by their '
                         f'transmittal and its revisions.')
            if n['rows'] and not n['tracked']:
                w.append('Nothing on this sheet has a submission date or a review code yet — its items '
                         'count as not submitted. Switch the sheet off if it is not part of the log, or '
                         'pick the column that holds the status.')
            for f, said_yes, said_no in (('submitted', 'sent', 'not sent'),
                                         ('returned', 'replied', 'no reply yet')):
                cnt = n['words'][f]
                if not cnt:
                    continue
                col = next((c for c in sh['columns'] if c.get('field') == f), None)
                name = (col.get('header') or f'column {col.get("letter", "")}') if col else f
                parts = []
                for kind, label in (('no', said_no), ('yes', said_yes)):
                    ws_ = [(wd, k) for (kk, wd), k in cnt.most_common() if kk == kind][:5]
                    if ws_:
                        parts.append(f'read as {label}: ' + ', '.join(
                            f'"{wd}"' + (f' ×{k}' if k > 1 else '') for wd, k in ws_))
                w.append(f'{sum(cnt.values())} cell(s) in the "{name}" column are words, not dates — '
                         + '; '.join(parts) + '. Type a date in the log (or pick another column) if that is wrong.')
            if n['no_trade']:
                w.append(f'{n["no_trade"]} row(s) have no discipline — not counted.')
            if n['no_type']:
                w.append(f'{n["no_type"]} row(s) have no submittal type — not counted.')
            if n['unknown_codes']:
                ks = ', '.join(f'"{k}"' for k, _ in n['unknown_codes'].most_common(5))
                w.append(f'Review code(s) {ks} not recognised — not counted as approved, rejected or '
                         f'under review until you choose what they mean.')
        if sh['include'] and sh['trade_source'] and sh['trade_source']['kind'] == 'sheet-name':
            w.append(f'No discipline column — the discipline is taken from the sheet name '
                     f'("{sh["trade_source"]["value"]}").')
        if sh['include'] and sh['type_source'] and sh['type_source']['kind'] == 'sheet-name':
            w.append(f'No submittal-type column — the type is taken from the sheet name '
                     f'("{sh["type_source"]["value"]}").')
        sh['warnings'] = w

    summ = summarize_e1(rows)
    groups = [{'trade': t, 'submittal_type': ty, **v} for (t, ty), v in sorted(summ.items())]
    by_trade = {}
    for g in groups:
        a = by_trade.setdefault(g['trade'], {'trade': g['trade'], 'req': 0, 'submitted_rows': 0,
                                             'approved_rows': 0, 'not_approved_rows': 0,
                                             'under_review_rows': 0})
        for k in ('req', 'submitted_rows', 'approved_rows', 'not_approved_rows', 'under_review_rows'):
            a[k] += g[k]
    for a in by_trade.values():
        req = a['req']
        a['approved_pct'] = round(100.0 * a['approved_rows'] / req, 1) if req else 0.0
        a['submitted_pct'] = round(100.0 * (a['submitted_rows'] - a['not_approved_rows']) / req, 1) if req else 0.0
    prop['preview'] = {'rows_read': len(rows), 'drawings': sum(g['req'] for g in groups),
                       'groups': groups, 'by_trade': list(by_trade.values())}
    prop['warnings'] = [f'{sh["sheet"]}: {x}' for sh in prop['sheets'] if sh['include'] for x in sh['warnings']]
    return prop


# ── public API ──────────────────────────────────────────────────────────────────────────
def inspect_log(path, store_dir=None):
    """Read a log and propose how to count it (see the module docstring). ``store_dir``
    (the per-user layout memory) is only consulted when given."""
    sheet_grids, fmt = _load(path)
    legend = {}
    sheets = []
    for title, grid in sheet_grids:
        sh, _ = _analyze_sheet(title, grid, legend, fmt)
        sheets.append(sh)
    fname = os.path.basename(str(path))
    _dedupe_registers(sheets, sheet_grids, fname)
    prop = {
        'file': fname, 'path': str(path), 'format': fmt,
        'signature': _signature(sheet_grids, sheets, fmt),
        'sheets': sheets, 'legend': legend, 'code_map': {},
        'fields': [{'key': k, 'label': FIELD_LABELS[k]} for k in FIELDS + ('ignore',)],
        'verdicts': [{'key': k, 'label': v} for k, v in VERDICT_LABELS.items()],
        'remembered': None,
    }
    for sh in sheets:
        sh['sig'] = _sheet_sig(sh)
    if store_dir:
        _apply_remembered(prop, store_dir)
    prop = _finalize(prop, sheet_grids)
    if not prop.get('remembered') and _switch_off_untracked(prop['sheets']):
        prop['code_map'] = {}
        prop = _finalize(prop, sheet_grids)
    return prop


def _switch_off_untracked(sheets):
    """A register with rows but nothing submitted or coded (an empty spare-parts list beside
    the real O&M log) would pull % approved down with no visible reason: switch it off — with
    the reason, so the planner can switch it back on — when another counted register does
    carry submissions. A log where nothing at all is submitted yet stays as it is."""
    on = [s for s in sheets if s['kind'] == 'register' and s['include']]
    if not any(s.get('tracked_rows') for s in on):
        return False
    off = [s for s in on if s.get('untracked')]
    for s in off:
        s['include'] = False
        s['auto_off'] = 'untracked'
        s['reason'] = ('Nothing on this sheet has a submission date or a review code yet — switched off '
                       'so its items do not pull % Approved down. Switch it on if it is part of the log.')
    return bool(off)


def refresh_layout(path, layout):
    """The planner changed a column / sheet / code: re-derive the codes, notes and preview
    for that layout (headings and the chosen fields stay as given)."""
    sheet_grids, fmt = _load(path)
    lay = _sanitize(layout)
    prop = copy.deepcopy(layout) if isinstance(layout, dict) else {}
    prop['file'] = prop.get('file') or os.path.basename(str(path))
    prop['format'] = fmt
    prop['code_map'] = dict(lay['code_map'])
    prop['legend'] = lay['legend']
    known = {s['sheet']: s for s in lay['sheets']}
    out_sheets = []
    for s in prop.get('sheets') or []:
        if not isinstance(s, dict) or s.get('sheet') not in known:
            continue
        clean = known[s['sheet']]
        by_idx = {c['index']: c['field'] for c in clean['columns']}
        s['include'] = clean['include']
        s['columns'] = [dict(c, field=by_idx.get(c.get('index'), 'ignore')) for c in s.get('columns') or []
                        if isinstance(c, dict)]
        s.setdefault('sections', [])
        s.setdefault('warnings', [])
        out_sheets.append(s)
    prop['sheets'] = out_sheets
    return _finalize(prop, sheet_grids)


def read_rows(path, layout):
    """The rows summarize_e1 counts, read with a (confirmed) layout. Unknown fields,
    out-of-range columns and switched-off sheets are ignored."""
    sheet_grids, _ = _load(path)
    rows, _ = _build_rows(sheet_grids, layout, os.path.basename(str(path)))
    return rows


# ── layout memory ───────────────────────────────────────────────────────────────────────
def default_store_dir():
    from utils import app_data_dir
    return os.path.join(app_data_dir(), 'elog_layouts')


def _store_load(store_dir):
    try:
        with open(os.path.join(store_dir, STORE_FILE), encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def remember_layout(layout, store_dir=None, path=None):
    """Keep the planner's confirmed layout (sheets switched on/off, each column's meaning,
    the review-code choices), keyed by the log's signature."""
    if not isinstance(layout, dict) or not layout.get('signature'):
        return False
    store_dir = store_dir or default_store_dir()
    os.makedirs(store_dir, exist_ok=True)
    lay = _sanitize(layout)
    entry = {'file': layout.get('file') or (os.path.basename(path) if path else ''),
             'saved_at': time.strftime('%Y-%m-%d %H:%M'), 'code_map': lay['code_map'], 'sheets': {}}
    heads = {s.get('sheet'): s for s in layout.get('sheets') or [] if isinstance(s, dict)}
    for s in lay['sheets']:
        src = heads.get(s['sheet'], {})
        hdr = {c.get('index'): c.get('header') for c in src.get('columns') or [] if isinstance(c, dict)}
        entry['sheets'][s['sheet']] = {
            'include': s['include'], 'sig': src.get('sig'),
            'columns': {str(c['index']): {'field': c['field'], 'header': hdr.get(c['index']) or ''}
                        for c in s['columns']}}
    data = _store_load(store_dir)
    data[layout['signature']] = entry
    if len(data) > _STORE_CAP:
        for k in sorted(data, key=lambda k: data[k].get('saved_at', ''))[:len(data) - _STORE_CAP]:
            data.pop(k, None)
    tmp = os.path.join(store_dir, STORE_FILE + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(store_dir, STORE_FILE))
    return True


def _apply_remembered(prop, store_dir):
    entry = _store_load(store_dir).get(prop['signature'])
    if not entry:
        return
    by_sig = {v.get('sig'): v for v in entry.get('sheets', {}).values() if v.get('sig')}
    who = entry.get('file') or 'an earlier log'
    for sh in prop['sheets']:
        e = entry.get('sheets', {}).get(sh['sheet']) or by_sig.get(sh.get('sig'))
        if not e:
            continue
        sh['include'] = bool(e.get('include'))
        for c in sh['columns']:
            ec = (e.get('columns') or {}).get(str(c['index']))
            if not ec or _norm_text(ec.get('header')) != _norm_text(c.get('header')):
                continue
            f = ec.get('field')
            if f not in FIELDS + ('ignore',):
                continue
            c['field'] = f
            c['confidence'] = max(c.get('confidence') or 0, 0.95)
            c['level'] = 'high'
            c['remembered'] = True
            c['reason'] = f'Remembered from {who} — your confirmed choice.'
    for k, v in (entry.get('code_map') or {}).items():
        if v in VERDICTS + ('ignore',):
            prop['code_map'][k] = v
    prop['remembered'] = {'file': entry.get('file'), 'saved_at': entry.get('saved_at')}


# ── optional offline-AI second opinion (off unless the local brain is installed) ─────────
_AI_SYSTEM = ('You map the columns of a construction drawings / submittal log to fields. '
              'Answer ONLY with JSON: {"suggestions": [{"index": <int>, "field": "<field>"}]}. '
              'Allowed fields: ' + ', '.join(FIELDS + ('ignore',)) + '. Use "ignore" when unsure.')


def local_ai_ready():
    """True only when the OFFLINE brain (p6_chat.llm, in-process llama.cpp) is set up."""
    try:
        from p6_chat import llm
        if not llm._model_ready():        # no model downloaded → never load the engine DLL
            return False
        return bool(llm.status().get('ready'))
    except Exception:
        return False


def _parse_ai_json(text):
    try:
        m = re.search(r'\{.*\}', text or '', re.S)
        data = json.loads(m.group(0)) if m else {}
        sugg = data.get('suggestions') if isinstance(data, dict) else None
        return [s for s in sugg or [] if isinstance(s, dict)]
    except (ValueError, AttributeError):
        return []


def suggest_columns_with_local_ai(proposal, generate=None, threshold=LOW_CONFIDENCE):
    """Ask the offline AI brain about LOW-confidence columns only (heading + up to 8 sample
    values each — never whole rows). Returns a copy where those columns carry
    'ai_suggestion' (+ a label); their 'field' is never changed. No brain → unchanged."""
    if generate is None:
        if not local_ai_ready():
            return proposal
        from p6_chat import llm

        def generate(system, user):
            return llm.generate(system, user, temperature=0.0, max_tokens=400)
    out = copy.deepcopy(proposal)
    allowed = set(FIELDS) | {'ignore'}
    for sh in out.get('sheets') or []:
        if not sh.get('include'):
            continue
        low = [c for c in sh.get('columns') or [] if (c.get('confidence') or 0) < threshold]
        if not low:
            continue
        payload = {'sheet': sh.get('sheet'),
                   'columns': [{'index': c['index'], 'header': c.get('header') or '',
                                'samples': [str(x)[:40] for x in (c.get('samples') or [])[:8]]} for c in low]}
        try:
            reply = generate(_AI_SYSTEM, json.dumps(payload, ensure_ascii=False))
        except Exception:
            continue
        by_idx = {c['index']: c for c in low}
        for s in _parse_ai_json(reply):
            c, f = by_idx.get(s.get('index')), s.get('field')
            if c is not None and f in allowed and f != c.get('field'):
                c['ai_suggestion'] = f
                c['ai_label'] = 'Suggested by the offline AI — not used until you pick it.'
    return out
