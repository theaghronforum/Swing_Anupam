"""Engine 10: Momentum Continuation Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.indicators import clamp
from ..core.models import EngineContext
from ..core.registry import register


@register
class MomentumContinuationEngine(BaseEngine):
    """10. Can momentum continue 3-15 trading days?"""

    engine_id = 10
    name = "Momentum Continuation Engine"
    min_history = 30

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ix = ctx.indicators
        warnings = []
        direction = "long" if ix.macd_hist > 0 and ix.last_close > ix.ema20 else \
                    "short" if ix.macd_hist < 0 and ix.last_close < ix.ema20 else "neutral"

        cont = clamp(50 + ix.macd_hist / max(ix.atr14, 1e-9) * 20 +
                     (ix.rel_volume - 1) * 15 + (ix.rsi14 - 50) * 0.6)

        if ix.rsi14 > 78 or ix.rsi14 < 22:
            phase = "exhausted"
        elif ix.adx > 30 and 55 < ix.rsi14 < 70:
            phase = "expanding"
        elif 45 < ix.rsi14 < 55:
            phase = "early"
        elif ix.adx < 18:
            phase = "reversing"
        else:
            phase = "mature"

        too_far = abs((ix.last_close - ix.ema20) / ix.ema20) > 0.08
        if too_far:
            warnings.append(self.warn("price extended from mean — chase risk"))

        target = round(ix.last_close + ix.atr14 * 2 * (1 if direction == "long" else -1), 4)
        signal = {"long": "continue long", "short": "continue short",
                  "neutral": "reduce"}[direction]
        if phase in ("exhausted", "reversing"):
            signal = "trail" if direction != "neutral" else "exit"

        outputs = {
            "momentum_direction": direction,
            "continuation_score": round(cont, 1),
            "momentum_phase": phase,
            "follow_through_zone": [round(ix.last_close, 4), target],
            "likely_continuation_target": target,
            "momentum_risk_warning": too_far,
            "final_momentum_signal": signal,
        }
        return {"outputs": outputs, "score": round(cont, 1),
                "decision": signal, "warnings": warnings}
