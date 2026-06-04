"""Engine 21: Volatility Expansion Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.enums import GlobalSentiment, Severity
from ..core.indicators import atr as _atr_series, clamp
from ..core.models import EngineContext
from ..core.registry import register


@register
class VolatilityExpansionEngine(BaseEngine):
    """21. Detects volatility expansion / compression for sizing & stops."""

    engine_id = 21
    name = "Volatility Expansion Engine"
    min_history = 30

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ad, ix = ctx.asset_data, ctx.indicators
        df = ad.daily
        warnings = []
        atr_now = ix.atr14
        atr_prev = float(_atr_series(df).iloc[-20]) if len(df) > 35 else atr_now
        expanding = atr_now > atr_prev * 1.15
        compressed = ix.bb_width and ix.bb_width < 6
        vix = ad.x("vix")

        if compressed:
            state = "compressed"
        elif expanding and ix.atr_pct > 4:
            state = "high"
            warnings.append(self.warn("high volatility", Severity.HIGH))
        elif expanding:
            state = "expanding"
        elif ix.atr_pct < 1:
            state = "low"
        elif vix and vix > 25:
            state = "unstable"
        else:
            state = "normal"

        breakout_prob = clamp((6 - (ix.bb_width or 6)) * 12 + (20 if compressed else 0))
        vol_risk = clamp(ix.atr_pct * 12 + (vix or 0))
        expected_move = round(atr_now * 2, 4)

        decision = ("enter" if state in ("compressed", "normal", "expanding") else
                    "reduce size" if state == "high" else
                    "widen stop" if state == "unstable" else "wait")

        outputs = {
            "volatility_state": state,
            "volatility_breakout_probability": round(breakout_prob, 1),
            "volatility_risk_score": round(vol_risk, 1),
            "atr_expected_move": expected_move,
            "vol_adjusted_stop_distance": round(atr_now * 1.5, 4),
            "vol_adjusted_target_distance": round(atr_now * 2.5, 4),
            "final_volatility_decision": decision,
        }
        return {"outputs": outputs, "score": round(vol_risk, 1),
                "decision": decision, "warnings": warnings}
