"""Calendar & Weather provider — the feature's OWN report sections (parse-free)."""
from p6_special import payloads as P
from p6_special import feature_reports as FR
from p6_special.registry import Item

FEATURE = 'calendar'
FEATURE_TITLE = 'Calendar & Weather'


def _avail(ctx, key, fn):
    """Honest per-section gating: 'ready' only if this section actually produces
    content for the current schedule. Several sections are conditional — Weather is
    empty without a weather estimate, Exceptions without holidays/shutdowns ahead,
    Comparison with a single calendar — so gating the whole feature on 'a calendar
    exists' would advertise empty sections as ready (a silent-empty section). The
    render is memoized, so this costs nothing extra when the section is selected."""
    if not ctx.calendar:
        return 'no_data'
    return 'ready' if fn(ctx, key) else 'no_data'


def _mk(key, title, fn):
    return Item(f'calendar:{key}', FEATURE, FEATURE_TITLE, title, 'section',
                lambda ctx, k=key: fn(ctx, k) or P.NO_DATA,
                lambda ctx, k=key: _avail(ctx, k, fn))


def provide(ctx):
    # Calendar Audit sections (feature's own report) + the 7 Bad-Weather sub-sections,
    # each reused verbatim so a picked result matches the feature's own screen.
    items = [_mk(k, t, FR.calendar_section) for k, t in FR.CALENDAR_SECS]
    items += [_mk(k, t, FR.weather_section) for k, t in FR.WEATHER_SECS]
    return items
