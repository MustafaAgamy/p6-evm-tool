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
    import importlib
    from p6_dashboard.registry import register_provider
    for name in _BUILTINS:
        try:
            mod = importlib.import_module(f'p6_dashboard.providers.{name}')
            # Register explicitly (not only via the module's @register_provider decorator)
            # so discovery is repeatable after clear_providers(): decorators run once per
            # process, but register_provider is idempotent.
            if hasattr(mod, 'provide'):
                register_provider(mod.provide)
        except Exception as exc:  # pragma: no cover - defensive
            print(f'[dashboard] builtin provider {name} skipped: {exc}', file=sys.stderr)
