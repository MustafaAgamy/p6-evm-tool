"""Update Analysis provider — offers the feature's OWN report sections (exact
detailed results + real charts), recomputed on demand from the imported file."""
from p6_special import payloads as P
from p6_special import feature_reports as FR
from p6_special.registry import Item

FEATURE = 'update'
FEATURE_TITLE = 'Update Analysis'


def _ready(ctx):
    return 'ready' if ctx.has_xml() else 'no_data'


def _mk(key, title):
    return Item(f'update:{key}', FEATURE, FEATURE_TITLE, title, 'section',
                lambda ctx, k=key: FR.update_section(ctx, k) or P.NO_DATA, _ready)


def provide(ctx):
    return [_mk(k, t) for k, t in FR.UPDATE_SECS]
