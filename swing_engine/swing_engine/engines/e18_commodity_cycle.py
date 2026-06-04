"""Engine 18: Commodity Cycle Intelligence Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.enums import Asset
from ..core.indicators import clamp, slope
from ..core.models import EngineContext
from ..core.registry import register


@register
class CommodityCycleEngine(BaseEngine):
    """18. Swing cycle stage for commodities + global influence."""

    engine_id = 18
    name = "Commodity Cycle Intelligence Engine"
    min_history = 60

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ad, ix = ctx.asset_data, ctx.indicators
        warnings = []
        long_slope = slope(ad.daily["close"], 40)
        vol_trend = ix.rel_volume - 1

        if long_slope > 0.1 and ix.rsi14 < 65:
            cycle = "markup"
        elif long_slope > 0.1 and ix.rsi14 >= 70:
            cycle = "distribution"
        elif long_slope < -0.1 and ix.rsi14 > 35:
            cycle = "markdown"
        elif abs(long_slope) < 0.05 and ix.last_close < ix.ema200:
            cycle = "accumulation"
        else:
            cycle = "consolidation"

        maturity = clamp(50 + ix.rsi14 - 50 + long_slope * 100)

        dxy = ad.x("dxy") or ad.x("dxy_value")
        inv = ad.x("inventory_trend")          # +rising / -falling
        weather = ad.x("weather_risk")
        geo = ad.x("geopolitical_risk")
        if geo:
            influence = "geopolitical"
        elif weather:
            influence = "weather-driven"
        elif inv is not None:
            influence = "inventory-driven"
        elif dxy is not None:
            influence = "dollar-driven"
        else:
            influence = "demand-driven"

        directional = ("long" if cycle in ("markup", "accumulation") and long_slope >= 0 else
                       "short" if cycle == "markdown" else "wait")
        strategy = directional if directional != "wait" else (
            "hedge" if cycle == "distribution" else "wait")
        if cycle == "distribution":
            warnings.append(self.warn("late-cycle distribution"))

        outputs = {
            "commodity_trend_cycle": cycle,
            "directional_signal": directional,
            "cycle_maturity_score": round(maturity, 1),
            "global_influence_tag": influence,
            "final_commodity_strategy": strategy,
        }
        return {"outputs": outputs, "score": round(maturity, 1),
                "decision": strategy, "warnings": warnings}
