"""Engine 29: Swing Trade Rebalancing Engine."""
from __future__ import annotations

from typing import Any, Dict, List

from ..core.base_engine import BaseEngine
from ..core.enums import ApprovalStatus, ExecutionPriority
from ..core.indicators import clamp
from ..core.models import EngineContext
from ..core.registry import register


@register
class RebalancingEngine(BaseEngine):
    """29. Rebalances open swing trades as conditions / risk change."""

    engine_id = 29
    name = "Swing Trade Rebalancing Engine"
    min_history = 10

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        u = ctx.user
        warnings = []
        positions: List[Dict[str, Any]] = u.open_positions or []

        # Theme/sector concentration.
        themes: Dict[str, int] = {}
        for p in positions:
            t = p.get("theme") or p.get("sector") or p.get("asset", "misc")
            themes[t] = themes.get(t, 0) + 1
        concentrated = any(c >= max(2, len(positions) * 0.5) for c in themes.values()) if positions else False

        regime = ctx.out(4, "regime_label", "sideways")
        global_dec = ctx.out(23, "final_global_decision", "monitor overnight")
        risk_status = ctx.out(3, "risk_utilisation", "moderate")

        if risk_status == "overexposed" or "reduce" in global_dec:
            action = "reduce"
        elif regime in ("volatile", "reversal zone"):
            action = "hedge"
        elif ctx.out(11, "reversal_probability", 0) > 60:
            action = "exit"
        elif ctx.out(5, "trend_strength", 0) > 65 and risk_status in ("safe", "moderate"):
            action = "add"
        elif concentrated:
            action = "rotate"
        else:
            action = "hold"

        # Find weakest open position to replace.
        replacement = None
        if positions:
            weakest = min(positions, key=lambda p: p.get("trend_score", 50))
            if weakest.get("trend_score", 50) < 40:
                replacement = weakest.get("symbol")
                warnings.append(self.warn(f"replace underperformer {replacement}"))

        if concentrated:
            warnings.append(self.warn("theme concentration risk"))

        outputs = {
            "rebalance_action": action,
            "exposure_adjustment": {ctx.asset.value: action},
            "underperformer_replacement": replacement,
            "concentration_warning": bool(concentrated),
            "theme_distribution": themes,
            "final_rebalanced_allocation": ctx.out(3, "allocation_by_segment", {}),
        }
        return {"outputs": outputs, "score": round(clamp(60 - len(warnings) * 15), 1),
                "decision": action, "warnings": warnings}
