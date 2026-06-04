"""Engine 9: Pullback Quality Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.indicators import clamp
from ..core.models import EngineContext
from ..core.registry import register


@register
class PullbackQualityEngine(BaseEngine):
    """9. Healthy pullback vs trend-failure."""

    engine_id = 9
    name = "Pullback Quality Engine"
    min_history = 30

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        df, ix = ctx.asset_data.daily, ctx.indicators
        warnings = []
        rng = max(ix.swing_high - ix.swing_low, 1e-9)
        depth = (ix.swing_high - ix.last_close) / rng  # 0=top, 1=at swing low
        vol_now = df["volume"].iloc[-1] if "volume" in df else 0
        avg_vol = df["volume"].tail(20).mean() if "volume" in df else 1
        low_vol_decline = vol_now < avg_vol
        above_ma = ix.last_close > ix.ema50
        rsi_reset = 40 <= ix.rsi14 <= 55

        if depth <= 0.382 and low_vol_decline and above_ma:
            ptype = "healthy pullback"
            decision = "buy dip"
        elif depth <= 0.618 and above_ma:
            ptype = "deep pullback"
            decision = "wait"
        elif not above_ma and depth > 0.618:
            ptype = "reversal pullback"
            decision = "avoid"
            warnings.append(self.warn("pullback breaking trend"))
        elif not low_vol_decline and depth > 0.5:
            ptype = "trap pullback"
            decision = "avoid"
        else:
            ptype = "weak pullback"
            decision = "wait"

        trend_respect = clamp(100 - depth * 90 + (10 if above_ma else -20))
        buyer_control = clamp(60 + (15 if low_vol_decline else -15) + (ix.rsi14 - 50))
        entry_zone = [round(ix.ema20, 4), round(ix.ema50, 4)]
        invalidation = round(ix.swing_low, 4)

        outputs = {
            "pullback_type": ptype,
            "pullback_depth_ratio": round(depth, 3),
            "pullback_zone": entry_zone,
            "ideal_entry_zone": entry_zone,
            "invalidation_level": invalidation,
            "trend_respect_score": round(trend_respect, 1),
            "buyer_seller_control": {ctx.asset.value: round(buyer_control, 1)},
            "final_pullback_decision": decision,
        }
        return {"outputs": outputs, "score": round(trend_respect, 1),
                "decision": decision, "warnings": warnings}
