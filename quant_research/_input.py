"""Input handling for the quant_research package (PRIVATE module).

Not part of the public API — everything here is underscore-prefixed on
import. This module implements and documents the package-wide input
contract, which every public function follows:

Array-like inputs
    Every public function that takes a data series accepts numpy
    arrays, Python lists, tuples, ``range`` objects and generators
    (generators are consumed exactly once). Inputs are converted to
    1-D ``float64`` numpy arrays via ``np.asarray(x, dtype=np.float64)``
    so integer and float inputs behave identically. A bare scalar
    (int/float) is rejected with ``ValueError`` because treating it as
    a one-observation series hides bugs.

Missing values
    NaN and Inf entries are treated as *missing observations*:

    - statistical functions drop them and then enforce the documented
      minimum remaining count (raising ``ValueError`` when the usable
      sample is too small);
    - position-aligned functions (z-scores, rolling windows) keep
      missing values as NaN in the affected output positions, as
      documented in each docstring.

Empty results
    Statistic-computing functions raise ``ValueError`` on empty input.
    Pure algebra functions (returns converters, cumulative products)
    return empty arrays, matching numpy's own conventions.

Determinism
    All input handling is deterministic: no hidden randomness, no
    input-dependent branching beyond the documented policies, and no
    state carried between calls (zero hidden state).
"""

import numpy as np


def as_float_array(x, name="input"):
    """Coerce x to a 1-D float64 numpy array.

    Accepts any array-like (numpy array, list, tuple, range, generator;
    generators are consumed exactly once). Strings are rejected with
    TypeError. Scalars and 2-D+ inputs are rejected with ValueError so
    that silently wrong shapes become loud errors.
    """
    if isinstance(x, np.ndarray):
        arr = np.asarray(x, dtype=np.float64)
    elif isinstance(x, (list, tuple, range)):
        arr = np.asarray(x, dtype=np.float64)
    elif isinstance(x, str):
        raise TypeError("%s must be an array-like, got str" % name)
    elif hasattr(x, "__iter__"):
        arr = np.asarray(list(x), dtype=np.float64)
    else:
        raise ValueError(
            "%s must be an array-like of observations, got a scalar" % name
        )
    if arr.ndim == 0:
        raise ValueError(
            "%s must be an array-like of observations, got a scalar" % name
        )
    if arr.ndim != 1:
        raise ValueError(
            "%s must be 1-D, got shape %s" % (name, tuple(arr.shape))
        )
    return arr


def as_binary(x, name="outcomes"):
    """Coerce x to a 1-D float64 array of 0.0/1.0 values.

    Raises ValueError if any element is not exactly 0 or 1 (NaN is not
    a valid outcome)."""
    arr = as_float_array(x, name)
    if np.any((arr != 0.0) & (arr != 1.0)):
        raise ValueError("%s must contain only 0/1 values" % name)
    return arr


def finite_only(x, name="input"):
    """Drop NaN/Inf entries from an array-like; returns a 1-D float64
    array (possibly empty)."""
    arr = as_float_array(x, name)
    return arr[np.isfinite(arr)]


def check_min(x, k, name="input"):
    """Raise ValueError unless x has at least k finite observations.

    x must already be a float64 array. The error message states the
    documented minimum, so callers never have to guess why a small
    sample was rejected.
    """
    n = int(np.isfinite(x).sum())
    if n < k:
        raise ValueError(
            "%s needs >= %d finite observations, got %d" % (name, k, n)
        )
