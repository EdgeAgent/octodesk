"""THE DOUBLING LAB — pure exponential math. Playful, and labelled everywhere
as math, not a promise: doubling is what numbers do on paper; markets have
never once agreed to it.
"""

from __future__ import annotations

import math

MOON_KM = 384_400  # mean Earth–Moon distance


def doubling_ladder(start, steps):
    """[start, start*2, start*4, ...] with `steps` doublings (steps+1 values)."""
    return [start * (2 ** i) for i in range(steps + 1)]


def steps_to_target(start, target, factor=2):
    """Smallest n with start * factor**n >= target."""
    if start >= target:
        return 0
    return math.ceil(math.log(target / start, factor))


def fold_distance_km(folds, thickness_mm=0.1):
    """Distance covered if a sheet `thickness_mm` thick could fold `folds` times."""
    return thickness_mm * (2 ** folds) / 1_000_000  # mm -> km


def compound_series(principal, rate_per_period, periods):
    """Balance after each period at a fixed rate. A fantasy curve — smooth by
    construction, which is exactly the point of showing it next to real NAV."""
    return [principal * (1.0 + rate_per_period) ** i for i in range(periods + 1)]
