"""Engine 1: Swing Trader Suitability Engine.

NOTE: You mentioned Engine 1 is already built on your side. This is a complete,
spec-matching reference implementation so the 1->30 pipeline runs end to end.
Replace the body of `evaluate` with your existing logic if you prefer — the
input (`UserProfile`) and output keys already match the spec.
"""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.enums import Asset, SegmentAccess, SuitabilityStatus
from ..core.indicators import clamp
from ..core.models import EngineContext
from ..core.registry import register

# Minimum capital (account currency) considered adequate per segment.
_SEGMENT_CAPITAL_FLOOR = {
    Asset.STOCK: 25_000,
    Asset.INDEX: 50_000,
    Asset.FNO: 150_000,
    Asset.FOREX: 50_000,
    Asset.COMMODITY: 100_000,
}


@register
class SwingTraderSuitabilityEngine(BaseEngine):
    """1. Decides whether the user is suitable for swing trading and which
    asset segments should be allowed, from risk/capital/behaviour/experience."""

    engine_id = 1
    name = "Swing Trader Suitability Engine"
    min_history = 1  # user-level engine; does not require price history

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        u = ctx.user
        warnings = []

        # --- readiness components (0..100) -------------------------------- #
        exp_score = clamp(u.experience_years * 18)                 # 5.5y -> ~100
        capital_score = clamp((u.capital / 200_000) * 100)         # 2L -> 100
        discipline_score = clamp(u.stop_loss_discipline * 100)     # behavioural 0..1
        drawdown_score = clamp(100 - u.avg_drawdown_pct * 4)       # 25% dd -> 0
        readiness = round(
            exp_score * 0.25 + capital_score * 0.25 +
            discipline_score * 0.30 + drawdown_score * 0.20, 1
        )

        # --- suitability status ------------------------------------------ #
        if u.capital < _SEGMENT_CAPITAL_FLOOR[Asset.STOCK]:
            status = SuitabilityStatus.NOT_SUITABLE
            warnings.append(self.warn("capital below minimum for swing trading"))
        elif u.experience_years < 0.5 or readiness < 35:
            status = SuitabilityStatus.EDUCATION_REQUIRED
            warnings.append(self.warn("limited experience — education recommended"))
        elif u.avg_drawdown_pct > 20 or u.stop_loss_discipline < 0.3:
            status = SuitabilityStatus.HIGH_RISK
            warnings.append(self.warn("weak risk discipline / high past drawdown"))
        elif readiness < 60:
            status = SuitabilityStatus.LIMITED_ACCESS
        else:
            status = SuitabilityStatus.ELIGIBLE

        # --- swing profile ----------------------------------------------- #
        perms = u.permissions
        derivative_focused = perms.get("FNO") and not perms.get("STOCK", True)
        multi_asset = sum(bool(perms.get(a.value)) for a in Asset) >= 4
        if derivative_focused:
            profile = "derivative-focused"
        elif multi_asset:
            profile = "multi-asset swing trader"
        else:
            profile = {"conservative": "conservative", "balanced": "balanced",
                       "aggressive": "aggressive"}.get(u.risk_appetite, "balanced")

        # --- per-segment access ------------------------------------------ #
        allowed: Dict[str, str] = {}
        for a in Asset:
            if not u.can_trade(a):
                allowed[a.value] = SegmentAccess.BLOCKED.value
            elif u.capital < _SEGMENT_CAPITAL_FLOOR[a]:
                allowed[a.value] = SegmentAccess.WATCH_ONLY.value
            elif status in (SuitabilityStatus.HIGH_RISK, SuitabilityStatus.LIMITED_ACCESS) \
                    and a in (Asset.FNO, Asset.FOREX, Asset.COMMODITY):
                allowed[a.value] = SegmentAccess.RESTRICTED.value
            else:
                allowed[a.value] = SegmentAccess.ENABLED.value

        # --- risk / holding ceilings ------------------------------------- #
        max_risk_level = {
            "conservative": 0.5, "balanced": 1.0, "aggressive": 2.0,
        }.get(u.risk_appetite, 1.0)
        if status in (SuitabilityStatus.HIGH_RISK, SuitabilityStatus.LIMITED_ACCESS):
            max_risk_level = min(max_risk_level, 0.75)
        max_holding_days = 20 if u.risk_appetite == "conservative" else \
            15 if u.risk_appetite == "balanced" else 10

        outputs = {
            "suitability_status": status.value,
            "user_swing_profile": profile,
            "allowed_swing_segments": allowed,
            "max_recommended_risk_pct": max_risk_level,
            "max_holding_period_days": max_holding_days,
            "warning_flags": [w for w in warnings],
            "final_user_readiness_score": readiness,
            "component_scores": {
                "experience": round(exp_score, 1),
                "capital": round(capital_score, 1),
                "discipline": round(discipline_score, 1),
                "drawdown": round(drawdown_score, 1),
            },
        }
        return {"outputs": outputs, "score": readiness,
                "decision": status.value, "warnings": warnings}
