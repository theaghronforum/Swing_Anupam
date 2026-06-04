"""Engine 11: Reversal Probability Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.indicators import clamp
from ..core.models import EngineContext
from ..core.registry import register


@register
class ReversalProbabilityEngine(BaseEngine):
    """11. Chance of trend reversal before/during the swing hold."""

    engine_id = 11
    name = "Reversal Probability Engine"
    min_history = 30

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        df, ix = ctx.asset_data.daily, ctx.indicators
        warnings = []
        # RSI divergence proxy: price higher high but RSI lower.
        close = df["close"]
        from ..core.indicators import rsi as _rsi
        rsi_series = _rsi(close)
        price_hh = close.iloc[-1] > close.iloc[-10:-1].max()
        rsi_lh = rsi_series.iloc[-1] < rsi_series.iloc[-10:-1].max()
        bearish_div = price_hh and rsi_lh
        price_ll = close.iloc[-1] < close.iloc[-10:-1].min()
        rsi_hl = rsi_series.iloc[-1] > rsi_series.iloc[-10:-1].min()
        bullish_div = price_ll and rsi_hl

        overext = ix.rsi14 > 75 or ix.rsi14 < 25
        prob = clamp((30 if overext else 0) + (40 if bearish_div or bullish_div else 0) +
                     (15 if ix.adx < 18 else 0) + (15 if ix.rel_volume > 2 else 0))

        if bearish_div or (ix.rsi14 > 75 and ix.last_close > ix.ema20):
            rtype = "bearish reversal"
            decision = "protect profit"
        elif bullish_div or (ix.rsi14 < 25 and ix.last_close < ix.ema20):
            rtype = "bullish reversal"
            decision = "prepare entry"
        elif ix.rel_volume > 2 and ix.last_close < ix.ema20:
            rtype = "profit-booking reversal"
            decision = "tighten stop"
        else:
            rtype = "false reversal"
            decision = "avoid"

        if prob > 55:
            warnings.append(self.warn("elevated reversal probability"))

        outputs = {
            "reversal_probability": round(prob, 1),
            "reversal_type": rtype,
            "confirmation_required": prob < 60,
            "early_warning_signals": {
                "bearish_divergence": bool(bearish_div),
                "bullish_divergence": bool(bullish_div),
                "overextended": bool(overext),
            },
            "final_reversal_decision": decision,
        }
        return {"outputs": outputs, "score": round(prob, 1),
                "decision": decision, "warnings": warnings}
