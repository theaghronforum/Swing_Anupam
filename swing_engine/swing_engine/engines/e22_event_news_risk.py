"""Engine 22: Event & News Risk Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.enums import GlobalSentiment, Severity
from ..core.indicators import atr as _atr_series, clamp
from ..core.models import EngineContext
from ..core.registry import register


@register
class EventNewsRiskEngine(BaseEngine):
    """22. Identifies events that can impact the swing hold."""

    engine_id = 22
    name = "Event & News Risk Engine"
    min_history = 5

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ad = ctx.asset_data
        warnings = []
        # events: list[{"type":..,"in_days":int,"impact":"positive|negative|binary"}]
        events = ad.x("events", []) or []
        horizon = ctx.config.get("event_horizon_days", 10)
        upcoming = [e for e in events if e.get("in_days", 99) <= horizon]

        if not upcoming:
            level, etype, impact, action = "low", "none", "uncertain", "continue"
        else:
            nearest = min(upcoming, key=lambda e: e.get("in_days", 99))
            etype = nearest.get("type", "macro data")
            impact = nearest.get("impact", "uncertain")
            days = nearest.get("in_days", horizon)
            binary = impact == "binary" or etype in ("earnings", "central bank", "policy", "result")
            if binary and days <= 2:
                level, action = "extreme", "exit before event"
                warnings.append(self.warn(f"binary {etype} in {days}d", Severity.EXTREME))
            elif binary and days <= 5:
                level, action = "high", "reduce"
            elif days <= 3:
                level, action = "medium", "hedge"
            else:
                level, action = "low", "continue"

        risk_num = {"low": 20, "medium": 50, "high": 75, "extreme": 95}[level]
        instruction = ("Trade is event-safe." if level == "low"
                       else f"Manage around {etype}: {action}.")

        outputs = {
            "event_risk_level": level,
            "event_type": etype,
            "expected_impact_direction": impact,
            "trade_action_around_event": action,
            "upcoming_events": upcoming,
            "final_event_instruction": instruction,
        }
        return {"outputs": outputs, "score": float(risk_num),
                "decision": level, "warnings": warnings}
