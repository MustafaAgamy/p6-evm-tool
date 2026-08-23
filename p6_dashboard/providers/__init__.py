"""Built-in dashboard providers — one module per existing feature.

Each module calls ``registry.register_provider`` at import time. ``load_builtins``
imports them all; a module that fails to import is skipped so one broken provider
never takes down the dashboard. Future features do NOT go here — they self-register
via ``p6_<feature>/dashboard.py`` (auto-imported by ``registry.discover``).
"""

import sys

_BUILTINS = (
    'overview',
    'evm',
    'audit',
    'calendar',
    'constructability',
    'update',
    'twofile',
)


def load_builtins():
    # STATIC imports (not importlib by computed name) so PyInstaller's import graph
    # collects every provider into the .exe — a dynamic import would ship an empty
    # catalog. Registering explicitly (not only via each module's @register_provider
    # decorator) also keeps discovery repeatable after clear_providers(): decorators
    # run once per process, but register_provider is idempotent.
    from p6_dashboard.registry import register_provider
    from p6_dashboard.providers import (
        overview, evm, audit, calendar, constructability, update, twofile,
    )
    for mod in (overview, evm, audit, calendar, constructability, update, twofile):
        prov = getattr(mod, 'provide', None)
        if prov is not None:
            try:
                register_provider(prov)
            except Exception as exc:  # pragma: no cover - defensive
                print(f'[dashboard] provider {mod.__name__} skipped: {exc}', file=sys.stderr)
