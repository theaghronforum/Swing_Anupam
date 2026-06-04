"""Training labels — exactly the outcomes your spec lists.

For each historical bar t we look forward and compute:
  * fwd_ret_{h}      : forward return over h trading days (h in 3,5,10,15)
  * mfe_{h}          : max favourable excursion within h days (best unrealised gain)
  * mae_{h}          : max adverse excursion within h days (worst unrealised draw)
  * stop_hit         : did an ATR/structure stop trigger before the target?
  * target_hit       : did the target trigger before the stop?
  * holding_outcome  : 'target' | 'stop' | 'timeout'
  * label_bin        : 1 if target_hit before stop_hit (the default classifier target)

The stop/target distances default to ATR multiples (long-side); pass
`direction=-1` for short setups. No look-ahead leaks into features because
labels are computed only from data AFTER t.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd

from ..core.indicators import atr


def make_labels(
    daily: pd.DataFrame,
    horizons: Sequence[int] = (3, 5, 10, 15),
    stop_atr_mult: float = 1.5,
    target_atr_mult: float = 3.0,
    direction: int = 1,
    max_horizon: int | None = None,
) -> pd.DataFrame:
    """Return a DataFrame (same index as `daily`) of forward-looking labels.

    Rows near the end with insufficient forward data are dropped.
    """
    df = daily.copy()
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    atr_series = atr(df).bfill()
    n = len(df)
    horizons = sorted(horizons)
    max_h = max_horizon or max(horizons)

    out = {f"fwd_ret_{h}": np.full(n, np.nan) for h in horizons}
    out.update({f"mfe_{h}": np.full(n, np.nan) for h in horizons})
    out.update({f"mae_{h}": np.full(n, np.nan) for h in horizons})
    stop_hit = np.full(n, np.nan)
    target_hit = np.full(n, np.nan)
    holding = np.array([None] * n, dtype=object)
    days_to_exit = np.full(n, np.nan)

    c = close.values
    h_arr, l_arr = high.values, low.values
    a = atr_series.values

    for t in range(n - 1):
        entry = c[t]
        if not np.isfinite(entry) or entry <= 0:
            continue
        stop_dist = a[t] * stop_atr_mult
        tgt_dist = a[t] * target_atr_mult
        if direction == 1:
            stop_lvl, tgt_lvl = entry - stop_dist, entry + tgt_dist
        else:
            stop_lvl, tgt_lvl = entry + stop_dist, entry - tgt_dist

        # forward returns / excursions per horizon
        for hh in horizons:
            end = min(t + hh, n - 1)
            if end <= t:
                continue
            fwd = c[end]
            out[f"fwd_ret_{hh}"][t] = direction * (fwd - entry) / entry * 100
            window_h = h_arr[t + 1:end + 1]
            window_l = l_arr[t + 1:end + 1]
            if len(window_h):
                if direction == 1:
                    out[f"mfe_{hh}"][t] = (window_h.max() - entry) / entry * 100
                    out[f"mae_{hh}"][t] = (window_l.min() - entry) / entry * 100
                else:
                    out[f"mfe_{hh}"][t] = (entry - window_l.min()) / entry * 100
                    out[f"mae_{hh}"][t] = (entry - window_h.max()) / entry * 100

        # stop vs target race over max horizon
        end = min(t + max_h, n - 1)
        outcome, exit_day = "timeout", max_h
        s_hit = tg_hit = 0
        for k in range(t + 1, end + 1):
            hit_stop = (l_arr[k] <= stop_lvl) if direction == 1 else (h_arr[k] >= stop_lvl)
            hit_tgt = (h_arr[k] >= tgt_lvl) if direction == 1 else (l_arr[k] <= tgt_lvl)
            if hit_stop and hit_tgt:
                outcome, s_hit, tg_hit, exit_day = "stop", 1, 0, k - t  # conservative
                break
            if hit_stop:
                outcome, s_hit, exit_day = "stop", 1, k - t
                break
            if hit_tgt:
                outcome, tg_hit, exit_day = "target", 1, k - t
                break
        stop_hit[t] = s_hit
        target_hit[t] = tg_hit
        holding[t] = outcome
        days_to_exit[t] = exit_day

    res = pd.DataFrame(out, index=df.index)
    res["stop_hit"] = stop_hit
    res["target_hit"] = target_hit
    res["holding_outcome"] = holding
    res["days_to_exit"] = days_to_exit
    res["label_bin"] = (res["target_hit"] == 1).astype("float")
    # drop tail rows with no forward window
    res = res.iloc[: n - max_h] if n > max_h else res.iloc[0:0]
    return res
