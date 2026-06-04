"""Engine 26: Target Projection Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.enums import Asset
from ..core.indicators import clamp
from ..core.models import EngineContext
from ..core.registry import register


@register
class TargetProjectionEngine(BaseEngine):
    """26. Target 1 / 2 / extended with risk-reward."""

    engine_id = 26
    name = "Target Projection Engine"
    min_history = 20

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ix = ctx.indicators
        warnings = []
        price = ix.last_close
        sl = ctx.out(25, "stop_loss_level", price - ix.atr14 * 1.5)
        risk = max(price - sl, 1e-6)

        res = ix.resistance
        t1 = res[0] if res else price + risk * 1.5
        t1 = max(t1, price + risk * 1.0)
        t2 = (res[1] if len(res) > 1 else price + risk * 2.5)
        t2 = max(t2, t1 + risk)
        extended = price + risk * 4

        rr = round((t1 - price) / risk, 2)
        move_pct = round((t1 - price) / price * 100, 2)
        confidence = clamp(ctx.out(5, "trend_strength", 50) * 0.6 +
                           ctx.out(6, "structure_quality_score", 50) * 0.4)
        if rr < 1.5:
            warnings.append(self.warn("risk-reward below 1.5"))

        outputs = {
            "target_1": round(t1, 4),
            "target_2": round(t2, 4),
            "extended_target": round(extended, 4),
            "expected_reward": round(t1 - price, 4),
            "expected_move_pct": move_pct,
            "risk_reward_ratio": rr,
            "target_confidence_score": round(confidence, 1),
            "partial_booking_plan": {"book_50pct_at": round(t1, 4),
                                      "trail_rest_to": round(t2, 4)},
            "target_map": {"t1": round(t1, 4), "t2": round(t2, 4),
                            "extended": round(extended, 4)},
        }
        return {"outputs": outputs, "score": round(confidence, 1),
                "decision": f"RR {rr}", "warnings": warnings}
