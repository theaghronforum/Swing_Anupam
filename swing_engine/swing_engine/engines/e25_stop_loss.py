"""Engine 25: Stop-Loss Placement Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.enums import Asset
from ..core.indicators import clamp
from ..core.models import EngineContext
from ..core.registry import register


@register
class StopLossPlacementEngine(BaseEngine):
    """25. Places the stop from structure + volatility + risk budget."""

    engine_id = 25
    name = "Stop-Loss Placement Engine"
    min_history = 20

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ix = ctx.indicators
        warnings = []
        price = ix.last_close
        atr_stop = price - ix.atr14 * ctx.config.get("atr_stop_mult", 1.5)
        structural_stop = min(ix.swing_low, ix.support[0] if ix.support else price)
        # Use the tighter of structural vs ATR but not absurdly close.
        sl = min(structural_stop, atr_stop)
        sl = min(sl, price * 0.995)
        stop_distance = round(price - sl, 4)

        vol_state = ctx.out(21, "volatility_state", "normal")
        if vol_state in ("high", "unstable", "expanding"):
            sl_type = "volatility-based"
            sl = price - ix.atr14 * 2.0
            stop_distance = round(price - sl, 4)
        elif abs(structural_stop - sl) < 1e-6:
            sl_type = "technical"
        else:
            sl_type = "fixed"

        risk_per_unit = stop_distance
        qty = ctx.out(3, "position_size_qty", 0)
        capital_at_risk = round(risk_per_unit * qty, 2)
        risk_pct = stop_distance / price * 100
        if risk_pct > 6:
            warnings.append(self.warn("stop wider than 6% — size down"))

        outputs = {
            "stop_loss_level": round(sl, 4),
            "stop_loss_type": sl_type,
            "invalidation_reason": "Close beyond this level breaks the swing thesis "
                                   "(structure + volatility buffer).",
            "stop_distance": stop_distance,
            "stop_distance_pct": round(risk_pct, 2),
            "capital_at_risk": capital_at_risk,
            "final_stop_instruction": f"{sl_type} stop at {round(sl, 4)}",
        }
        return {"outputs": outputs, "score": round(clamp(100 - risk_pct * 10), 1),
                "decision": sl_type, "warnings": warnings}
