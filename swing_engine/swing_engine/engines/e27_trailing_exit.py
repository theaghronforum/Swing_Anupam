"""Engine 27: Trailing Exit Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.enums import Asset
from ..core.indicators import clamp
from ..core.models import EngineContext
from ..core.registry import register


@register
class TrailingExitEngine(BaseEngine):
    """27. Manages profitable trades and protects gains."""

    engine_id = 27
    name = "Trailing Exit Engine"
    min_history = 20

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ix = ctx.indicators
        warnings = []
        price = ix.last_close
        entry = ctx.out(24, "entry_zone", {}).get("primary", price)
        open_profit = price - entry

        ma_trail = ix.ema20
        atr_trail = price - ix.atr14 * 2
        struct_trail = ix.swing_low
        trail = max(ma_trail, atr_trail, struct_trail)
        trail = min(trail, price * 0.999)

        if ix.adx > 28:
            method = "moving average trail"
        elif ctx.out(21, "volatility_state") in ("high", "unstable"):
            method = "atr trail"
        elif ctx.out(6, "break_of_structure"):
            method = "structure trail"
        else:
            method = "candle trail"

        protection = clamp((trail - entry) / max(open_profit, 1e-6) * 100) if open_profit > 0 else 0
        weakening = ctx.out(11, "reversal_probability", 0) > 55 or ix.rel_volume < 0.6
        target_hit = price >= ctx.out(26, "target_1", price * 2)

        if target_hit:
            decision = "book partial"
        elif weakening:
            decision = "exit fully"
            warnings.append(self.warn("trend weakening — protect gains"))
        elif open_profit > ix.atr14:
            decision = "trail"
        else:
            decision = "hold"

        outputs = {
            "trailing_stop_level": round(trail, 4),
            "trail_method": method,
            "profit_protection_score": round(protection, 1),
            "exit_trigger_alert": bool(weakening or target_hit),
            "final_trail_or_exit_decision": decision,
        }
        return {"outputs": outputs, "score": round(protection, 1),
                "decision": decision, "warnings": warnings}
