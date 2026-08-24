"""Built-in Special Report providers — one module per feature.

Each module exposes ``provide(ctx) -> list[registry.Item]``. Keep ``provide``
cheap (no parsing); do any heavy recompute inside each item's ``produce``
closure via ``ctx`` memoization.
"""
