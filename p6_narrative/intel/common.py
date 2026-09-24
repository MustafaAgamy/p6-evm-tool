"""Schedule Intelligence — the small deterministic primitives every slice shares.

No schedule knowledge lives here. These are the numeric and set helpers that keep the
intelligence layer reproducible: medians without a statistics import, a modal value with
an explicit tie-break, Jaccard overlap, normalised entropy, and a stable content
signature for comparing two assignment sets byte-for-byte.

Sets and tuples are used freely *inside* these helpers; none of them ever returns one
into the public contract (the contract is JSON-serialisable and explicitly sorted).
"""
import hashlib
import math
from collections import Counter

_PAIR_SEP = '\x1f'
_KV_SEP = '\x1e'


def median(values):
    """Median of an iterable of numbers; ``0.0`` when empty. Deterministic."""
    vals = sorted(values)
    n = len(vals)
    if not n:
        return 0.0
    mid = n // 2
    if n % 2:
        return float(vals[mid])
    return (float(vals[mid - 1]) + float(vals[mid])) / 2.0


def modal(items):
    """Most common item, ties broken by the item's own sort order. Deterministic."""
    counts = Counter(items)
    if not counts:
        return None
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def uniq(seq):
    """First-occurrence-order de-duplication of a sequence."""
    out, seen = [], set()
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def num(x):
    """Compact number for a human-readable exception string ('5', '7.5')."""
    return '%g' % round(float(x), 2)


def clamp01(x):
    """Clamp to the 0..1 interval every score in this layer is defined on."""
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))


def jaccard(a, b):
    """|A n B| / |A u B| for two iterables; ``0.0`` when both are empty."""
    sa, sb = set(a), set(b)
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / float(len(union))


def mean(values):
    vals = list(values)
    return (sum(vals) / float(len(vals))) if vals else 0.0


def normalised_entropy(counts):
    """Shannon entropy of a value distribution, scaled to 0..1 by ``log(distinct)``.

    1.0 = every value carries the same number of activities (a perfectly even
    partition); near 0 = one value swallows the schedule. Undefined for fewer than two
    values, which is reported as 0.0 (a single value partitions nothing).
    """
    vals = [float(c) for c in counts if c > 0]
    k = len(vals)
    if k < 2:
        return 0.0
    total = sum(vals)
    h = -sum((c / total) * math.log(c / total) for c in vals)
    return clamp01(h / math.log(k))


def spread(values):
    """Normalised distinctness of a list: 0.0 = all identical, 1.0 = all different.

    ``(distinct - 1) / (n - 1)`` — the only two structurally meaningful endpoints for
    "does this label mark the instance or the family?".
    """
    vals = list(values)
    n = len(vals)
    if n < 2:
        return 0.0
    return (len(set(vals)) - 1) / float(n - 1)


def concentration(values):
    """Share of the most common value: 1.0 = all identical, 1/n = all different."""
    vals = list(values)
    if not vals:
        return 0.0
    return max(Counter(vals).values()) / float(len(vals))


def rescale(x, lo):
    """Rescale ``x`` from the ``[lo, 1]`` interval onto ``[0, 1]``.

    Structural measures such as :func:`concentration` cannot go below a floor set by the
    group size (with 5 fronts the least concentrated case is 0.2). Comparing raw values
    across groups of different size would therefore be unfair; this removes the floor.
    """
    if lo >= 1.0:
        return 0.0
    return clamp01((x - lo) / (1.0 - lo))


def signature(pairs):
    """Stable hex signature of an ordered ``(key, value)`` sequence.

    Used to decide whether two activity-code dimensions carry *identical* assignments.
    Hashing (rather than keeping the pairs) keeps the comparison O(1) per pair of
    dimensions and the reported signature short, and it is content-addressed, so two
    runs of the same file always produce the same value.
    """
    blob = _PAIR_SEP.join('%s%s%s' % (k, _KV_SEP, v) for k, v in pairs)
    return hashlib.sha1(blob.encode('utf-8')).hexdigest()
