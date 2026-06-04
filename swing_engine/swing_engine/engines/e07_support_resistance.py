"""Engine 7: Support & Resistance Mapping Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.indicators import clamp, fibonacci_levels, swing_points
from ..core.models import EngineContext
from ..core.registry import register


@register
class SupportResistanceEngine(BaseEngine):
    """7. Builds the level map: entry, stop, targets, trailing & invalidation."""

    engine_id = 7
    name = "Support & Resistance Mapping Engine"
    min_history = 30

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ix = ctx.indicators
        price = ix.last_close
        sup = ix.support
        res = ix.resistance
        nearest_sup = max(sup) if sup else price * 0.97
        nearest_res = min(res) if res else price * 1.03

        fib = fibonacci_levels(ix.swing_low, ix.swing_high)

        # Zone strength: how many touches near level (approx via swing density).
        zone_strength = clamp(50 + (len(sup) + len(res)) * 8)

        # Zone type heuristic.
        if abs(price - nearest_sup) / price < 0.005:
            zone_type = "demand zone"
        elif abs(price - nearest_res) / price < 0.005:
            zone_type = "supply zone"
        else:
            zone_type = "tested zone"

        # Level map for a long bias (Engine 25/26 refine for direction).
        entry = round(price, 4)
        stop = round(nearest_sup - ix.atr14 * 0.25, 4)
        t1 = round(nearest_res, 4)
        t2 = round(nearest_res + (nearest_res - entry), 4)
        trail = round(entry + ix.atr14, 4)
        invalidation = round(min(stop, ix.swing_low), 4)

        outputs = {
            "nearest_support": [round(s, 4) for s in sup],
            "nearest_resistance": [round(r, 4) for r in res],
            "major_zone_strength": round(zone_strength, 1),
            "zone_type": zone_type,
            "distance_to_support_pct": round((price - nearest_sup) / price * 100, 2),
            "distance_to_resistance_pct": round((nearest_res - price) / price * 100, 2),
            "fibonacci_levels": {k: round(v, 4) for k, v in fib.items()},
            "invalidation_level": invalidation,
            "level_map": {"entry": entry, "stop_loss": stop,
                          "target_1": t1, "target_2": t2, "trailing_zone": trail},
        }
        return {"outputs": outputs, "score": round(zone_strength, 1),
                "decision": zone_type, "warnings": []}
