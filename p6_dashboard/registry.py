"""
Result registry — the core of the Professional Dashboard's auto-discovery.

Features are never hardcoded here. Each feature exposes a **provider**: a callable
that, given a :class:`~p6_dashboard.context.DashboardContext`, returns the list of
dashboard components it can show for that project. The dashboard reads whatever
providers are registered — so a new feature appears in the catalog automatically
once it registers a provider. No dashboard code changes.

Two ways a provider gets registered:
  1. Built-ins — modules in ``p6_dashboard/providers/`` loaded by ``load_builtins``.
  2. Future features — any top-level ``p6_<feature>/dashboard.py`` that calls
     :func:`register_provider` at import time. :func:`discover` auto-imports them.

A **component descriptor** is a plain dict::

    {
      'id':        str,      # unique, stable across runs (e.g. 'evm.spi')
      'title':     str,      # default human title (user may override; remembered)
      'source':    str,      # feature name — the catalog group
      'type':      str,      # one of COMPONENT_TYPES (drives rendering)
      'category':  str|None, # optional coarse grouping ('Time'|'Cost'|'Logic'|...)
      'size':      1|2,      # 1 = single column, 2 = wide
      'default_on':bool,     # ticked on a fresh board
      'available': bool,     # is the data present for this project right now?
      'note':      str|None, # shown when unavailable ("Run Consultant Review ...")
      'produce':   callable(ctx) -> payload dict,   # only called when rendered
    }

The catalog omits ``produce`` (metadata only); :func:`render` calls it for the
requested ids. A payload is ``{'type', 'data', ...}`` shaped for the component type
— see ``payload_*`` helpers below and ``ui/modules/dashboard.js`` for the renderers.
"""

import os
import sys
import importlib

# Component types the UI + exporters know how to render. A new component of an
# existing type needs no new renderer — that is the client half of extensibility.
COMPONENT_TYPES = (
    'kpi', 'score', 'status', 'chart', 'trend',
    'findings', 'table', 'summary', 'text', 'image',
)

# Coarse categories used to auto-order/soft-group the board sensibly.
CATEGORIES = ('Overview', 'Time', 'Cost', 'Progress', 'Logic', 'Quality', 'Custom')

_PROVIDERS = []          # list[callable(ctx) -> list[descriptor]]
_discovered = False


# ── Registration & discovery ────────────────────────────────────────────────

def register_provider(fn):
    """Register a provider. Idempotent. Usable as a decorator."""
    if fn not in _PROVIDERS:
        _PROVIDERS.append(fn)
    return fn


def clear_providers():
    """Test helper — drop all providers and force re-discovery next call."""
    global _discovered
    _PROVIDERS.clear()
    _discovered = False


def discover():
    """Load built-in providers and auto-import any feature self-registrations.

    Idempotent and defensive: a feature whose ``dashboard.py`` fails to import must
    never break the dashboard — it is skipped with a stderr note.
    """
    global _discovered
    if _discovered:
        return
    _discovered = True

    # 1. Built-in providers for the features that exist today.
    try:
        from p6_dashboard.providers import load_builtins
        load_builtins()
    except Exception as exc:  # pragma: no cover - defensive
        print(f'[dashboard] built-in providers failed: {exc}', file=sys.stderr)

    # 2. Future features that self-register via p6_<feature>/dashboard.py.
    _scan_feature_dashboards()


def _scan_feature_dashboards():
    """Import ``p6_<feature>.dashboard`` for every top-level ``p6_*`` package that
    ships one. Importing runs its ``register_provider`` calls. Skips this package
    and anything that fails to import."""
    roots = []
    try:
        from utils import resource_path
        roots.append(resource_path('.'))
    except Exception:
        pass
    roots.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    seen = set()
    for root in roots:
        if not root or not os.path.isdir(root) or root in seen:
            continue
        seen.add(root)
        try:
            names = sorted(os.listdir(root))
        except OSError:
            continue
        for name in names:
            if not name.startswith('p6_') or name == 'p6_dashboard':
                continue
            if not os.path.isfile(os.path.join(root, name, 'dashboard.py')):
                continue
            mod = f'{name}.dashboard'
            if mod in sys.modules:
                continue
            try:
                importlib.import_module(mod)
            except Exception as exc:  # pragma: no cover - defensive
                print(f'[dashboard] {mod} skipped: {exc}', file=sys.stderr)


# ── Enumeration & rendering ─────────────────────────────────────────────────

def _iter_descriptors(ctx):
    """Yield every provider's descriptors, first-id-wins, each guarded so a broken
    provider cannot break the whole dashboard."""
    seen = set()
    for prov in list(_PROVIDERS):
        try:
            items = prov(ctx) or []
        except Exception as exc:  # pragma: no cover - defensive
            print(f'[dashboard] provider {getattr(prov, "__name__", prov)} '
                  f'failed: {exc}', file=sys.stderr)
            continue
        for d in items:
            cid = d.get('id')
            if not cid or cid in seen:
                continue
            seen.add(cid)
            yield d


def catalog(ctx):
    """All available component descriptors for ``ctx`` (metadata only, no payloads).
    Feeds the Edit-mode component catalog."""
    discover()
    out = []
    for d in _iter_descriptors(ctx):
        meta = {k: v for k, v in d.items() if k != 'produce'}
        meta.setdefault('category', None)
        meta.setdefault('size', 1)
        meta.setdefault('default_on', False)
        meta.setdefault('available', True)
        out.append(meta)
    return out


def render(ctx, ids):
    """Payloads for the requested component ids: ``{id: {'type', 'data', ...}}``.
    ``produce`` runs only for the requested (and available) components."""
    discover()
    want = list(ids or [])
    want_set = set(want)
    payloads = {}
    for d in _iter_descriptors(ctx):
        cid = d.get('id')
        if cid not in want_set or cid in payloads:
            continue
        prod = d.get('produce')
        try:
            payload = prod(ctx) if callable(prod) else {}
        except Exception as exc:  # pragma: no cover - defensive
            print(f'[dashboard] render {cid} failed: {exc}', file=sys.stderr)
            payload = {'type': d.get('type'), 'error': str(exc)}
        payload.setdefault('type', d.get('type'))
        payload.setdefault('title', d.get('title'))
        payload.setdefault('source', d.get('source'))
        payloads[cid] = payload
    return payloads


# ── Descriptor & payload helpers (used by providers) ────────────────────────

def component(id, title, source, type, produce, *, category=None, size=1,
              default_on=False, available=True, note=None, requires=None):
    """Build a component descriptor with validation.

    ``requires`` — extra input files a multi-file result needs beyond the open project,
                   as ``[{'role','label','accept'?,'hint'?}]`` (e.g. a baseline XER). The
                   UI highlights each and lets the user **attach** it inline; the attached
                   path arrives on ``ctx.inputs[role]`` and the provider runs the feature
                   itself — the user never opens that feature's own tab.
    """
    if type not in COMPONENT_TYPES:
        raise ValueError(f'unknown component type {type!r}')
    return {
        'id': id, 'title': title, 'source': source, 'type': type,
        'category': category, 'size': size, 'default_on': default_on,
        'available': available, 'note': note, 'requires': list(requires or []),
        'produce': produce,
    }


# status: 'good' | 'warn' | 'bad' | 'neutral' — semantic colour, theme-mapped in CSS.

def payload_kpi(value, *, note='', status='neutral', trend=None, unit=''):
    return {'type': 'kpi', 'data': {'value': value, 'note': note,
            'status': status, 'trend': trend, 'unit': unit}}


def payload_score(value, *, band='', status='neutral', detail=''):
    return {'type': 'score', 'data': {'value': value, 'band': band,
            'status': status, 'detail': detail}}


def payload_status(label, *, status='neutral', note=''):
    return {'type': 'status', 'data': {'label': label, 'status': status, 'note': note}}


def payload_bars(rows, *, unit=''):
    """rows: [{'label', 'value', 'display'?, 'color'?}]."""
    return {'type': 'chart', 'data': {'kind': 'bars', 'rows': rows, 'unit': unit}}


def payload_line(series, *, y_max=None, x_labels=None):
    """series: [{'name', 'color'?, 'dash'?, 'points': [y, ...]}]."""
    return {'type': 'trend', 'data': {'kind': 'line', 'series': series,
            'y_max': y_max, 'x_labels': x_labels or []}}


def payload_grouped(labels, groups):
    """Grouped bars (+ optional cumulative lines). groups: [{'name','color','values':[..]}]."""
    return {'type': 'chart', 'data': {'kind': 'grouped', 'labels': labels, 'groups': groups}}


def payload_findings(items):
    """items: [{'severity','source'?,'text'}]. severity: 'bad'|'warn'|'info'."""
    return {'type': 'findings', 'data': {'items': items}}


def payload_table(headers, rows):
    return {'type': 'table', 'data': {'headers': headers, 'rows': rows}}


def payload_summary(stats):
    """stats: [{'label','value','status'?}]."""
    return {'type': 'summary', 'data': {'stats': stats}}
