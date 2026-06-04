"""Vectorised technical indicators used by the engines.

Everything here is pure-function and dependency-light (pandas + numpy only) so
it can be reused for both back-test/training feature generation and live
inference. No look-ahead: every function uses only past/most-recent data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
# Moving averages / slope
# --------------------------------------------------------------------------- #
def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def slope(series: pd.Series, lookback: int = 10) -> float:
    """Normalised slope (% per bar) of the last `lookback` points."""
    s = series.dropna().tail(lookback)
    if len(s) < 2:
        return 0.0
    x = np.arange(len(s))
    coef = np.polyfit(x, s.values, 1)[0]
    base = s.mean() if s.mean() != 0 else 1.0
    return float(coef / base * 100.0)


# --------------------------------------------------------------------------- #
# Oscillators
# --------------------------------------------------------------------------- #
def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


# --------------------------------------------------------------------------- #
# Volatility / range
# --------------------------------------------------------------------------- #
def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return true_range(df).ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def historical_volatility(series: pd.Series, period: int = 20) -> float:
    rets = np.log(series / series.shift(1)).dropna().tail(period)
    if len(rets) < 2:
        return 0.0
    return float(rets.std() * np.sqrt(252) * 100.0)


def bollinger_bandwidth(series: pd.Series, period: int = 20, mult: float = 2.0) -> pd.Series:
    mid = sma(series, period)
    std = series.rolling(period, min_periods=period).std()
    upper, lower = mid + mult * std, mid - mult * std
    return (upper - lower) / mid.replace(0.0, np.nan) * 100.0


# --------------------------------------------------------------------------- #
# Trend strength
# --------------------------------------------------------------------------- #
def adx(df: pd.DataFrame, period: int = 14):
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = true_range(df)
    atr_ = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(
        alpha=1 / period, adjust=False
    ).mean() / atr_.replace(0.0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(
        alpha=1 / period, adjust=False
    ).mean() / atr_.replace(0.0, np.nan)
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan) * 100
    adx_ = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx_.fillna(0.0), plus_di.fillna(0.0), minus_di.fillna(0.0)


# --------------------------------------------------------------------------- #
# Structure: swing pivots, support/resistance
# --------------------------------------------------------------------------- #
def swing_points(df: pd.DataFrame, left: int = 3, right: int = 3):
    """Return (swing_highs, swing_lows) as lists of (index_pos, price)."""
    highs, lows = [], []
    h, l = df["high"].values, df["low"].values
    n = len(df)
    for i in range(left, n - right):
        window_h = h[i - left : i + right + 1]
        window_l = l[i - left : i + right + 1]
        if h[i] == window_h.max() and (window_h == h[i]).sum() == 1:
            highs.append((i, float(h[i])))
        if l[i] == window_l.min() and (window_l == l[i]).sum() == 1:
            lows.append((i, float(l[i])))
    return highs, lows


def recent_levels(df: pd.DataFrame, n_levels: int = 3, left: int = 3, right: int = 3):
    """Nearest support and resistance levels relative to last close."""
    highs, lows = swing_points(df, left, right)
    price = float(df["close"].iloc[-1])
    res = sorted({round(p, 4) for _, p in highs if p > price})[:n_levels]
    sup = sorted({round(p, 4) for _, p in lows if p < price}, reverse=True)[:n_levels]
    return sup, res


def fibonacci_levels(swing_low: float, swing_high: float) -> dict:
    diff = swing_high - swing_low
    return {
        "0.236": swing_high - 0.236 * diff,
        "0.382": swing_high - 0.382 * diff,
        "0.5": swing_high - 0.5 * diff,
        "0.618": swing_high - 0.618 * diff,
        "0.786": swing_high - 0.786 * diff,
        "1.272_ext": swing_high + 0.272 * diff,
        "1.618_ext": swing_high + 0.618 * diff,
    }


# --------------------------------------------------------------------------- #
# Volume
# --------------------------------------------------------------------------- #
def relative_volume(df: pd.DataFrame, period: int = 20) -> float:
    if "volume" not in df or df["volume"].dropna().empty:
        return 1.0
    avg = df["volume"].rolling(period, min_periods=1).mean().iloc[-1]
    last = df["volume"].iloc[-1]
    return float(last / avg) if avg else 1.0


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return float(max(lo, min(hi, value)))


def pct_change(a: float, b: float) -> float:
    """Percentage move from b to a."""
    return (a - b) / b * 100.0 if b else 0.0
