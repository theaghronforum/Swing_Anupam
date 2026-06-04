"""Engine 24: Entry Timing Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.enums import Asset
from ..core.indicators import clamp
from ..core.models import EngineContext
from ..core.registry import register


@register
class EntryTimingEngine(BaseEngine):
    """24. Finds precise entry zones / method for the selected trade."""

    engine_id = 24
    name = "Entry Timing Engine"
    min_history = 20

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ix = ctx.indicators
        warnings = []
        breakout = ctx.out(8, "breakout_status")
        retest_req = ctx.out(8, "retest_requirement")
        pullback = ctx.out(9, "final_pullback_decision")
        chase = ctx.out(10, "momentum_risk_warning", False)

        if breakout == "valid breakout" and retest_req == "enter now":
            method = "breakout entry"
        elif retest_req == "wait for retest":
            method = "retest entry"
        elif pullback in ("buy dip", "sell rise"):
            method = "pullback entry"
        elif chase:
            method = "staged entry"
            warnings.append(self.warn("entry extended — stagger size"))
        elif ctx.out(5, "trend_strength", 0) > 65:
            method = "immediate entry"
        else:
            method = "avoid entry"

        primary = round(ix.last_close, 4)
        secondary = round(ix.ema20, 4)
        confidence = clamp(ctx.out(5, "trend_strength", 50) * 0.5 +
                           ctx.out(8, "follow_through_score", 40) * 0.3 +
                           (20 if not chase else 0))

        valid_window = ctx.config.get("entry_window", "next 1-3 sessions")
        instruction = (f"{method} near {primary}" if method != "avoid entry"
                       else "No valid entry now.")

        outputs = {
            "best_entry_method": method,
            "entry_zone": {"primary": primary, "secondary": secondary},
            "entry_confidence_score": round(confidence, 1),
            "chase_warning": bool(chase),
            "final_entry_instruction": instruction,
            "valid_time_window": valid_window,
        }
        return {"outputs": outputs, "score": round(confidence, 1),
                "decision": method, "warnings": warnings}
