"""Calendar & Weather provider — the feature's OWN report sections (parse-free)."""
from p6_special import payloads as P
from p6_special import feature_reports as FR
from p6_special.registry import Item

FEATURE = 'calendar'
FEATURE_TITLE = 'Calendar & Weather'


def _avail(ctx, key):
    """Honest per-section gating: 'ready' only if this section actually produces
    content for the current schedule. Several calendar sections are conditional —
    Weather is empty without a weather estimate, Exceptions without holidays/
    shutdowns ahead, Comparison with a single calendar, Conflicts when none — so
    gating the whole feature on 'a calendar exists' would advertise empty sections
    as ready (a silent-empty section). The render is memoized, so this costs
    nothing extra when the section is later selected."""
    if not ctx.calendar:
        return 'no_data'
    return 'ready' if FR.calendar_section(ctx, key) else 'no_data'


def _mk(key, title):
    return Item(f'calendar:{key}', FEATURE, FEATURE_TITLE, title, 'section',
                lambda ctx, k=key: FR.calendar_section(ctx, k) or P.NO_DATA,
                lambda ctx, k=key: _avail(ctx, k))


def provide(ctx):
    return [_mk(k, t) for k, t in FR.CALENDAR_SECS]
