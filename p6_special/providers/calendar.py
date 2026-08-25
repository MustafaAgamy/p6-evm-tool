"""Calendar & Weather provider — the feature's OWN report sections (parse-free)."""
from p6_special import payloads as P
from p6_special import feature_reports as FR
from p6_special.registry import Item

FEATURE = 'calendar'
FEATURE_TITLE = 'Calendar & Weather'


def _ready(ctx):
    return 'ready' if ctx.calendar else 'no_data'


def _mk(key, title):
    return Item(f'calendar:{key}', FEATURE, FEATURE_TITLE, title, 'section',
                lambda ctx, k=key: FR.calendar_section(ctx, k) or P.NO_DATA, _ready)


def provide(ctx):
    return [_mk(k, t) for k, t in FR.CALENDAR_SECS]
