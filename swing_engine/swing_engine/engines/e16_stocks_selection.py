"""Engine 16: Stocks Swing Selection Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.enums import Asset
from ..core.indicators import clamp, slope
from ..core.models import EngineContext
from ..core.registry import register


@register
class StocksSwingSelectionEngine(BaseEngine):
    """16. Scores a stock candidate and emits its swing plan."""

    engine_id = 16
    name = "Stocks Swing Selection Engine"
    min_history = 50

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ad, ix = ctx.asset_data, ctx.indicators
        warnings = []
        trend = ctx.out(5, "trend_strength", 50.0)
        vol_tag = ctx.out(12, "final_volume_validation", "unconfirmed")
        rs = ctx.out(14, "stock_vs_index_strength", 50.0)
        struct = ctx.out(6, "structure_quality_score", 50.0)

        quality = clamp(trend * 0.35 + rs * 0.25 + struct * 0.20 +
                        (15 if vol_tag in ("confirmed", "partially confirmed") else 0) + 5)

        # Best setup type.
        if ctx.out(8, "breakout_status") == "valid breakout":
            setup = "breakout"
        elif ctx.out(9, "final_pullback_decision") == "buy dip":
            setup = "pullback"
        elif ctx.out(11, "reversal_type", "").endswith("reversal") and ctx.out(11, "reversal_probability", 0) > 55:
            setup = "reversal"
        elif ctx.out(13, "accumulation_distribution_signal") == "accumulation":
            setup = "accumulation"
        else:
            setup = "momentum"

        earnings_soon = bool(ad.x("earnings_in_days") and ad.x("earnings_in_days") <= 5)
        if earnings_soon:
            warnings.append(self.warn("earnings within 5 days"))

        signal = "buy" if quality >= 60 else "wait" if quality >= 45 else "avoid"
        lvl = ctx.out(7, "level_map", {})
        plan = {
            "entry": lvl.get("entry", ix.last_close),
            "stop_loss": lvl.get("stop_loss"),
            "target": lvl.get("target_1"),
            "holding_days": ctx.out(28, "expected_holding_days", 7),
            "confidence": round(quality, 1),
        }

        outputs = {
            "signal": signal,
            "stock_quality_score": round(quality, 1),
            "best_setup_type": setup,
            "swing_plan": plan,
            "earnings_risk": earnings_soon,
            "selected": signal == "buy",
        }
        return {"outputs": outputs, "score": round(quality, 1),
                "decision": signal, "warnings": warnings}
