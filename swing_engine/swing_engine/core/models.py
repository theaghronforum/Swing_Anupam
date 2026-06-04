"""Data contracts that flow through the pipeline.

`AssetData`  -> everything you fetched for one instrument.
`UserProfile`-> KYC / risk / capital / permissions.
`IndicatorBundle` -> indicators computed once and cached.
`EngineContext`   -> what every engine receives.
`EngineResult`    -> standardised, serialisable output of every engine.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from . import indicators as ind
from .enums import Asset


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
@dataclass
class AssetData:
    """All data you fetched for a single instrument.

    `daily`/`weekly` are OHLCV DataFrames with columns:
        open, high, low, close, volume   (DatetimeIndex, ascending).
    `extras` carries every asset-specific field the docs list, e.g.:
        F&O      : oi, change_in_oi, pcr, iv, iv_percentile, greeks, max_pain,
                   futures_price, days_to_expiry, basis, rollover_pct
        INDEX    : vix, breadth (adv/dec/new_highs/new_lows), sector_strength
        FOREX    : dxy, rate_differential, session, cot_net, spread_pips
        COMMODITY: dxy, inventory_trend, cot_commercial, term_structure,
                   seasonality_bias
        Common   : fii_dii, sector_index (DataFrame), benchmark_index (DataFrame),
                   events (list[dict]), global_cues (dict), corp_actions (list)
    Missing keys are tolerated; engines degrade gracefully.
    """

    asset: Asset
    symbol: str
    daily: pd.DataFrame
    weekly: Optional[pd.DataFrame] = None
    intraday: Optional[pd.DataFrame] = None
    extras: Dict[str, Any] = field(default_factory=dict)

    def x(self, key: str, default: Any = None) -> Any:
        """Convenience accessor for `extras`."""
        return self.extras.get(key, default)


@dataclass
class UserProfile:
    """Suitability / capital / permission inputs (Engine 1 & 3 mainly)."""

    user_id: str
    capital: float = 0.0
    cash_balance: float = 0.0
    risk_per_trade_pct: float = 1.0           # % of capital risked per trade
    max_portfolio_risk_pct: float = 6.0       # aggregate open risk cap
    max_exposure_pct: float = 100.0
    experience_years: float = 0.0
    stop_loss_discipline: float = 0.5         # 0..1 behavioural score
    avg_drawdown_pct: float = 0.0
    permissions: Dict[str, bool] = field(default_factory=dict)   # {"FNO": True,...}
    risk_appetite: str = "balanced"           # conservative|balanced|aggressive
    open_positions: List[Dict[str, Any]] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)

    def can_trade(self, asset: Asset) -> bool:
        return self.permissions.get(asset.value, asset in (Asset.STOCK, Asset.INDEX))


# --------------------------------------------------------------------------- #
# Cached indicators
# --------------------------------------------------------------------------- #
@dataclass
class IndicatorBundle:
    """Standard indicator set computed once per asset and reused everywhere."""

    last_close: float
    ema20: float
    ema50: float
    ema200: float
    ema20_slope: float
    rsi14: float
    macd_hist: float
    adx: float
    plus_di: float
    minus_di: float
    atr14: float
    atr_pct: float
    hist_vol: float
    bb_width: float
    rel_volume: float
    support: List[float]
    resistance: List[float]
    swing_high: float
    swing_low: float

    @classmethod
    def build(cls, df: pd.DataFrame) -> "IndicatorBundle":
        close = df["close"]
        adx_, p_di, m_di = ind.adx(df)
        _, _, hist = ind.macd(close)
        atr14 = float(ind.atr(df).iloc[-1]) if len(df) >= 14 else float(ind.true_range(df).iloc[-1])
        last = float(close.iloc[-1])
        sup, res = ind.recent_levels(df)
        highs, lows = ind.swing_points(df)
        return cls(
            last_close=last,
            ema20=float(ind.ema(close, 20).iloc[-1]) if len(df) >= 20 else last,
            ema50=float(ind.ema(close, 50).iloc[-1]) if len(df) >= 50 else last,
            ema200=float(ind.ema(close, 200).iloc[-1]) if len(df) >= 200 else last,
            ema20_slope=ind.slope(ind.ema(close, 20)),
            rsi14=float(ind.rsi(close).iloc[-1]),
            macd_hist=float(hist.iloc[-1]) if not hist.empty else 0.0,
            adx=float(adx_.iloc[-1]),
            plus_di=float(p_di.iloc[-1]),
            minus_di=float(m_di.iloc[-1]),
            atr14=atr14,
            atr_pct=atr14 / last * 100 if last else 0.0,
            hist_vol=ind.historical_volatility(close),
            bb_width=float(ind.bollinger_bandwidth(close).iloc[-1]) if len(df) >= 20 else 0.0,
            rel_volume=ind.relative_volume(df),
            support=sup or [last * 0.97],
            resistance=res or [last * 1.03],
            swing_high=highs[-1][1] if highs else float(df["high"].tail(20).max()),
            swing_low=lows[-1][1] if lows else float(df["low"].tail(20).min()),
        )


# --------------------------------------------------------------------------- #
# Context + result
# --------------------------------------------------------------------------- #
@dataclass
class EngineContext:
    """Everything an engine needs. `upstream` holds results of earlier engines
    keyed by engine_id, enabling later engines to consume earlier decisions."""

    asset_data: AssetData
    user: UserProfile
    indicators: IndicatorBundle
    upstream: Dict[int, "EngineResult"] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)

    @property
    def asset(self) -> Asset:
        return self.asset_data.asset

    def out(self, engine_id: int, key: str, default: Any = None) -> Any:
        """Read a single output value from an upstream engine result."""
        res = self.upstream.get(engine_id)
        return res.outputs.get(key, default) if res else default


@dataclass
class EngineResult:
    """Standard, JSON-serialisable result emitted by every engine."""

    engine_id: int
    engine_name: str
    asset: Asset
    symbol: str
    outputs: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0                     # primary 0..100 score (engine-specific)
    decision: str = ""                     # the engine's headline verdict
    warnings: List[str] = field(default_factory=list)
    degraded: bool = False                 # True when run on partial data
    error: Optional[str] = None
    elapsed_ms: float = 0.0
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        d = self.__dict__.copy()
        d["asset"] = self.asset.value
        return d
