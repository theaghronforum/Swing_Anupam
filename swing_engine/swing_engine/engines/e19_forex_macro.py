"""Engine 19: Forex Macro Swing Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.enums import Asset
from ..core.indicators import clamp, slope
from ..core.models import EngineContext
from ..core.registry import register


@register
class ForexMacroSwingEngine(BaseEngine):
    """19. Macro + technical swing view for currency pairs."""

    engine_id = 19
    name = "Forex Macro Swing Engine"
    min_history = 50

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ad, ix = ctx.asset_data, ctx.indicators
        warnings = []
        rate_diff = ad.x("rate_differential", 0.0)   # base - quote policy rate
        dxy_slope = ad.x("dxy_slope", 0.0)
        cb_event = ad.x("central_bank_event")        # dict or None
        tech = ctx.out(5, "trend_direction", "sideways")

        macro_bias = rate_diff + dxy_slope * (1 if "USD" in ad.symbol[:3] else -1)
        if tech == "uptrend" and macro_bias >= 0:
            bias = "base currency strong"
        elif tech == "downtrend" and macro_bias <= 0:
            bias = "quote currency strong"
        elif ctx.out(11, "reversal_probability", 0) > 55:
            bias = "reversal risk"
        else:
            bias = "range-bound"

        macro_align = clamp(50 + rate_diff * 10 + (ctx.out(5, "trend_strength", 50) - 50) * 0.6)

        event_risk = "central bank" if cb_event else \
            (ad.x("event_type") or "none")
        if cb_event:
            warnings.append(self.warn("central bank event in window"))

        risk_grade = ("high" if event_risk != "none" or ix.atr_pct > 1.5
                      else "medium" if ix.atr_pct > 0.8 else "low")
        signal = ("long" if bias == "base currency strong" else
                  "short" if bias == "quote currency strong" else "wait")

        outputs = {
            "directional_bias": bias,
            "macro_alignment_score": round(macro_align, 1),
            "forex_zones": ctx.out(7, "level_map", {}),
            "event_risk_label": event_risk,
            "signal": signal,
            "holding_period_days": ctx.out(28, "expected_holding_days", 5),
            "risk_grade": risk_grade,
        }
        return {"outputs": outputs, "score": round(macro_align, 1),
                "decision": signal, "warnings": warnings}
