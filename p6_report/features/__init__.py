"""Built-in feature report specs. Importing this package registers each feature's
report into the framework registry, so ``get_spec(feature, report)`` finds it.

Add a module here per feature and import it below to register it.
"""
from p6_report.features import constructability  # noqa: F401

__all__ = ['constructability']
