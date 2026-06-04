"""Engine 17: Index Swing Direction Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.enums import Asset
from ..core.indicators import clamp, slope
from ..core.models import EngineContext
from ..core.registry import register


@register
class IndexSwingDirectionEngine(BaseEngine):
    """17. Direction for index products and index-linked decisions."""

    engine_id = 17
    name = "Index Swing Direction Engine"
    min_history = 50

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ad, ix = ctx.asset_data, ctx.indicators
        warnings = []
        trend_dir = ctx.out(5, "trend_direction", "sideways")
        vix = ad.x("vix")
        breadth = ctx.out(14, "market_breadth", "narrow participation")

        if trend_dir == "uptrend":
            direction = "bullish"
        elif trend_dir == "downtrend":
            direction = "bearish"
        elif ctx.out(11, "reversal_probability", 0) > 55:
            direction = "reversal watch"
        else:
            direction = "sideways"

        confidence = clamp(ctx.out(5, "trend_strength", 50) * 0.7 +
                           (20 if "broad" in breadth else 0) -
                           (15 if (vix and vix > 22) else 0))
        if vix and vix > 25:
            warnings.append(self.warn("high VIX — index whipsaw risk"))

        atr = ix.atr14
        move_range = [round(ix.last_close - atr * 2, 2), round(ix.last_close + atr * 2, 2)]
        style = ("index futures" if ctx.user.can_trade(Asset.FNO) and confidence > 60
                 else "index options" if vix and vix > 20
                 else "direct index" if confidence > 55 else "wait")

        outputs = {
            "index_direction": direction,
            "level_map": ctx.out(7, "level_map", {}),
            "breadth_sector_confirmation": breadth,
            "index_trade_style": style,
            "confidence": round(confidence, 1),
            "expected_move_range": move_range,
        }
        return {"outputs": outputs, "score": round(confidence, 1),
                "decision": direction, "warnings": warnings}
