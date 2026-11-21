"""Small analysis helpers shared by the lab notebooks."""
import numpy as np


def running_average(x, n=5):
    """Centered running average of x over n points (n odd).

    Each output point is the mean of the n points centered on it: point k averages
    x[k - n//2] ... x[k + n//2]. Near the two ends the window is cut off, and a point averages
    only the points that exist (the first point of a 5-point average uses x[0], x[1], x[2]).
    The result has the same length as x, so it lines up with the sweep it came from.

    Averaging n readings with independent random noise lowers that noise by about sqrt(n)
    (n = 5: from 0.9 to about 0.4 ADC count). It also rounds off features narrower than the
    window, so keep the window short compared with the curve: on a sweep in 16.5 mV steps,
    n = 5 spans 82 mV.

    x: a list, numpy array or pandas Series (one sweep). A Series comes back as a Series with the
    same index and name (so it also works in groupby(...).transform); anything else comes back as
    a numpy float array. A NaN in x makes every output point whose window holds it NaN.

        >>> running_average([0, 0, 3, 0, 0], n=3)
        array([0., 1., 1., 1., 0.])
    """
    n = int(n)
    if n < 1 or n % 2 == 0:
        raise ValueError(f"n must be a positive odd number of points, not {n}")
    values = np.asarray(x, dtype=float)
    if values.ndim != 1:
        raise ValueError("running_average works on one sweep at a time (a 1-D list, array or Series)")
    half = n // 2
    k = np.arange(len(values))
    lo = np.maximum(k - half, 0)                    # first point of each window
    hi = np.minimum(k + half + 1, len(values))      # one past its last point
    nan = np.isnan(values)
    total = np.concatenate([[0.0], np.cumsum(np.where(nan, 0.0, values))])
    bad = np.concatenate([[0], np.cumsum(nan)])
    out = (total[hi] - total[lo]) / np.maximum(hi - lo, 1)
    out[(bad[hi] - bad[lo]) > 0] = np.nan
    try:
        import pandas as pd
    except ImportError:
        return out
    if isinstance(x, pd.Series):
        return pd.Series(out, index=x.index, name=x.name)
    return out
