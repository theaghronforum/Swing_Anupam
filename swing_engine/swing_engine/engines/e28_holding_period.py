"""Engine 28: Position Holding Period Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.enums import Asset
from ..core.indicators import clamp
from ..core.models import EngineContext
from ..core.registry import register


@register
class HoldingPeriodEngine(BaseEngine):
    """28. Optimal holding period and staleness detection."""

    engine_id = 28
    name = "Position Holding Period Engine"
    min_history = 20

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ad, ix = ctx.asset_data, ctx.indicators
        warnings = []
        strength = ctx.out(5, "trend_strength", 50)
        base_days = int(clamp(3 + strength / 10, 3, 15))

        dte = ad.x("days_to_expiry")
        time_decay = None
        if ctx.asset in (Asset.FNO,) and dte is not None:
            base_days = min(base_days, max(1, dte - 1))
            time_decay = "theta accelerates near expiry" if dte <= 5 else "manageable"
            if dte <= 3:
                warnings.append(self.warn("near expiry — theta risk"))

        confidence = clamp(strength * 0.7 + ctx.out(10, "continuation_score", 50) * 0.3)
        time_exit = f"Exit if target not approached within {base_days} sessions."

        outputs = {
            "expected_holding_days": base_days,
            "holding_confidence_score": round(confidence, 1),
            "time_decay_warning": time_decay,
            "time_based_exit_condition": time_exit,
            "segment_guidance": {ctx.asset.value: f"{base_days}d swing"},
            "final_holding_instruction": "hold" if confidence > 55 else "reduce",
        }
        return {"outputs": outputs, "score": round(confidence, 1),
                "decision": f"{base_days}d", "warnings": warnings}
