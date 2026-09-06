"""Runtime result registry for Special Report.

Each feature ships a provider — a ``provide(ctx) -> list[Item]`` function.
Built-in providers are registered explicitly by :func:`load_builtins` (so
discovery survives :func:`clear_providers`); :func:`discover` additionally
imports any top-level ``p6_<feature>/special_report.py`` it finds, so a
future/in-progress feature appears in the catalog with **zero** Special Report
edits — the core auto-discovery rule.
"""
import importlib
import pkgutil

_PROVIDERS = []      # list of provide() callables
_LOADED = False


class Item:
    """A selectable result. ``produce(ctx)`` returns a payload (see payloads.py).

    ``requires`` declares extra inputs the result needs beyond the open file —
    each ``{'role': str, 'label': str, 'accept': str, 'hint': str}`` (e.g. a
    Critical Path item requires a baseline XER). The UI reads this to highlight
    the requirement and offer an attach control; the attached paths arrive back
    on ``ctx.inputs`` keyed by ``role``. ``availability(ctx)`` returns
    ``'ready' | 'needs_input' | 'no_data'``.
    """
    __slots__ = ('id', 'feature', 'feature_title', 'title', 'ctype',
                 'produce', 'availability', 'requires')

    def __init__(self, id, feature, feature_title, title, ctype, produce,
                 availability=None, requires=None):
        self.id = id
        self.feature = feature
        self.feature_title = feature_title
        self.title = title
        self.ctype = ctype                 # kpi|table|chart|findings|text|score|summary
        self.produce = produce             # produce(ctx) -> payload dict
        self.requires = list(requires or [])
        self.availability = availability or (lambda ctx: 'ready')

    def descriptor(self, ctx):
        try:
            avail = self.availability(ctx)
        except Exception:
            avail = 'ready'
        return {
            'id': self.id,
            'feature': self.feature,
            'feature_title': self.feature_title,
            'title': self.title,
            'ctype': self.ctype,
            'availability': avail,
            'requires': [dict(r) for r in self.requires],
        }


def register_provider(fn):
    """Register a ``provide(ctx) -> list[Item]`` callable (idempotent)."""
    if fn not in _PROVIDERS:
        _PROVIDERS.append(fn)
    return fn


def clear_providers():
    global _PROVIDERS, _LOADED
    _PROVIDERS = []
    _LOADED = False


def load_builtins():
    """Register the built-in feature providers explicitly."""
    from p6_special.providers import (evm, audit, calendar, update,
                                       constructability, twofile)
    for mod in (evm, audit, calendar, update, constructability, twofile):
        fn = getattr(mod, 'provide', None)
        if callable(fn):
            register_provider(fn)


def discover():
    """Import any top-level ``p6_<feature>/special_report.py`` to auto-register.

    This is how a feature merged later introduces its results with no change to
    Special Report: it ships ``p6_<feature>/special_report.py`` with a
    ``provide(ctx)`` function.
    """
    for _finder, name, ispkg in pkgutil.iter_modules():
        if not (ispkg and name.startswith('p6_') and name != 'p6_special'):
            continue
        try:
            mod = importlib.import_module(f'{name}.special_report')
        except ModuleNotFoundError:
            continue
        except Exception:
            continue
        fn = getattr(mod, 'provide', None)
        if callable(fn):
            register_provider(fn)


def ensure_loaded():
    global _LOADED
    if not _LOADED:
        load_builtins()
        discover()
        _LOADED = True


def _all_items(ctx):
    ensure_loaded()
    items = []
    for provide in _PROVIDERS:
        try:
            items.extend(provide(ctx) or [])
        except Exception:
            continue
    return items


def catalog(ctx):
    """Catalog grouped by feature, preserving provider order:
    ``[{feature, feature_title, items: [descriptor, ...]}, ...]``."""
    groups = []
    index = {}
    for it in _all_items(ctx):
        if it.feature not in index:
            g = {'feature': it.feature, 'feature_title': it.feature_title, 'items': []}
            index[it.feature] = g
            groups.append(g)
        index[it.feature]['items'].append(it.descriptor(ctx))
    return groups


def render(ctx, item_ids):
    """Produce payloads for the selected item ids, in the given order.

    Unknown ids are skipped; a producer that raises or returns nothing yields a
    ``no_data`` payload (rendered as a friendly "No data available" line).
    """
    by_id = {it.id: it for it in _all_items(ctx)}
    out = []
    for iid in item_ids:
        it = by_id.get(iid)
        if it is None:
            continue
        try:
            payload = it.produce(ctx)
        except Exception as exc:
            payload = {'kind': 'no_data', 'error': str(exc)}
        out.append({
            'id': it.id,
            'title': it.title,
            'feature': it.feature,
            'feature_title': it.feature_title,
            'ctype': it.ctype,
            'payload': payload or {'kind': 'no_data'},
        })
    return out
