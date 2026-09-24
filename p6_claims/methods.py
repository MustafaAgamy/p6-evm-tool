"""Delay-analysis method registry — the copilot's method knowledge.

The copilot KNOWS every method (to explain it and recommend the right one); only
some are EXECUTABLE (the tool can run the impact end-to-end) in the current build.
Time Impact Analysis is executable now; the rest are known + explained only.

AACE labels follow Recommended Practice 29R-03 (Forensic Schedule Analysis MIPs).
"""

METHODS = {
    'tia': {
        'key': 'tia',
        'name': 'Time impact analysis',
        'aace_mip': 'MIP 3.7',
        'needs': 'the update as it stood at the time of the event',
        'description': (
            'Insert the delay into the programme as it stood just before the event, then '
            'reschedule (F9). The SCL-preferred prospective method for an extension of time.'
        ),
        'executable': True,
    },
    'iap': {
        'key': 'iap',
        'name': 'Impacted as-planned',
        'aace_mip': 'MIP 3.6',
        'needs': 'the baseline only',
        'description': (
            'Insert the delay into the baseline programme and reschedule to model the push.'
        ),
        'executable': False,
    },
    'windows': {
        'key': 'windows',
        'name': 'Windows analysis',
        'aace_mip': 'MIP 3.3',
        'needs': 'a series of updates across the period',
        'description': (
            'Split the period into windows and measure the delay that accrued in each, '
            'window by window.'
        ),
        'executable': False,
    },
    'but_for': {
        'key': 'but_for',
        'name': 'Collapsed as-built (but-for)',
        'aace_mip': 'MIP 3.8',
        'needs': 'the baseline versus the current update',
        'description': (
            'Remove the delaying events from the as-built to show what would have happened '
            'but for them. Already available as the Consultant Review.'
        ),
        'executable': False,
    },
}

# Stable display order: the executable method leads, the rest follow as "known".
ORDER = ['tia', 'iap', 'windows', 'but_for']

DEFAULT_METHOD = 'tia'


def get_method(key):
    """Return the method dict for ``key``, or ``None`` if unknown."""
    return METHODS.get(key)


def list_methods():
    """All methods in display order (executable first)."""
    return [METHODS[k] for k in ORDER if k in METHODS]


def executable_methods():
    """Only the methods the tool can run end-to-end today."""
    return [m for m in list_methods() if m['executable']]


def is_executable(key):
    m = METHODS.get(key)
    return bool(m and m['executable'])
