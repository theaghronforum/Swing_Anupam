"""Engine 8: Breakout Validation Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.indicators import clamp
from ..core.models import EngineContext
from ..core.registry import register


@register
class BreakoutValidationEngine(BaseEngine):
    """8. Confirms whether a breakout is genuine enough for a swing entry."""

    engine_id = 8
    name = "Breakout Validation Engine"
    min_history = 30

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        df, ix = ctx.asset_data.daily, ctx.indicators
        warnings = []
        level = ix.swing_high
        last = df.iloc[-1]
        closed_above = ix.last_close > level
        body = abs(last["close"] - last["open"])
        rng = max(last["high"] - last["low"], 1e-9)
        candle_quality = clamp(body / rng * 100)
        vol_confirm = ix.rel_volume >= ctx.config.get("breakout_vol_mult", 1.3)
        breach_pct = (ix.last_close - level) / level * 100 if level else 0.0

        followthrough = clamp(candle_quality * 0.5 + (25 if vol_confirm else 0) + breach_pct * 8)

        if not closed_above:
            status = "no breakout"
            retest = "avoid until confirmation"
        elif vol_confirm and candle_quality > 55 and breach_pct > 0.3:
            status = "valid breakout"
            retest = "enter now"
        elif closed_above and not vol_confirm:
            status = "weak breakout"
            retest = "wait for retest"
            warnings.append(self.warn("breakout without volume"))
        elif breach_pct < 0.15:
            status = "early breakout"
            retest = "wait for retest"
        else:
            status = "fake breakout"
            retest = "failed breakout"
            warnings.append(self.warn("possible fakeout"))

        outputs = {
            "breakout_status": status,
            "breakout_level": round(level, 4),
            "breakout_candle_quality": round(candle_quality, 1),
            "follow_through_score": round(followthrough, 1),
            "volume_confirmation": bool(vol_confirm),
            "volatility_confirmation": ix.atr_pct > 1.0,
            "retest_requirement": retest,
            "breakout_trade_quality_score": round(followthrough, 1),
        }
        return {"outputs": outputs, "score": round(followthrough, 1),
                "decision": status, "warnings": warnings}
