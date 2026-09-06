"""The report component registry — the data model every feature registers into.

A ``ReportComponent`` is one selectable output in a feature's report (a table, a
chart, a summary block, a findings list). A ``ReportSpec`` is one feature's whole
report: a title, its own CSS, and the ordered list of components. Features register
a *spec builder* — a callable taking the feature's report dict and returning a
``ReportSpec`` — because which components exist can depend on the data (e.g. an
optional projection line only when the engine produced one).

Nothing here renders a document; that is the assembler's job (``render.py``), so the
same assembly feeds preview and PDF alike.
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

# the component 'type' vocabulary the selector and the No-data placeholder use
COMPONENT_TYPES = ('summary', 'chart', 'table', 'text', 'findings', 'recommendations')


@dataclass
class ReportComponent:
    """One reportable output the user can include or leave out.

    id            unique within the feature (stable — persisted in the saved selection)
    title         shown as the section heading and in the Report-Contents selector
    type          one of COMPONENT_TYPES — drives the selector icon and grouping
    render        report_dict -> HTML fragment (no <html>/<head>; feature CSS is shared)
    has_data      report_dict -> bool; False makes the section show 'No data available'
                  instead of being silently dropped (a selected-but-empty component)
    default       whether it is ticked on first open / when no saved selection exists
    description   optional one-line hint shown under the title in the selector
    """
    id: str
    title: str
    type: str
    render: Callable[[dict], str]
    has_data: Optional[Callable[[dict], bool]] = None
    default: bool = True
    description: str = ''

    def data_available(self, report: dict) -> bool:
        if self.has_data is None:
            return True
        try:
            return bool(self.has_data(report))
        except Exception:
            return False

    def render_fragment(self, report: dict) -> str:
        try:
            return self.render(report) or ''
        except Exception:
            return ''


@dataclass
class ReportSpec:
    """One feature's complete report definition."""
    feature: str
    title: str
    components: List[ReportComponent]
    subtitle: str = ''
    css: str = ''
    orientation: str = 'landscape'          # 'landscape' | 'portrait' — A4
    footer: str = ''                        # italic note under the last section
    meta_line: str = ''                     # small grey line under the title

    def by_id(self) -> Dict[str, ReportComponent]:
        return {c.id: c for c in self.components}

    def default_ids(self) -> List[str]:
        return [c.id for c in self.components if c.default]


# ── the registry: feature name -> spec builder ───────────────────────────────

_REGISTRY: Dict[str, Callable[[dict], ReportSpec]] = {}


def register(feature: str, spec_builder: Callable[[dict], ReportSpec]) -> None:
    """Register (or replace) a feature's report. ``spec_builder(report) -> ReportSpec``."""
    _REGISTRY[feature] = spec_builder


def get_spec(feature: str, report: dict) -> Optional[ReportSpec]:
    """Build the feature's spec for this report, or None if the feature is unknown."""
    builder = _REGISTRY.get(feature)
    if builder is None:
        return None
    return builder(report or {})


def registered_features() -> List[str]:
    return sorted(_REGISTRY)
