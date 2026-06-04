"""Engine 23: Global Market Impact Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.enums import GlobalSentiment, Severity
from ..core.indicators import atr as _atr_series, clamp
from ..core.models import EngineContext
from ..core.registry import register


@register
class GlobalMarketImpactEngine(BaseEngine):
    """23. Global cues that support or damage the swing trade."""

    engine_id = 23
    name = "Global Market Impact Engine"
    min_history = 5

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ad = ctx.asset_data
        warnings = []
        cues = ad.x("global_cues", {}) or {}
        # cues e.g. {"us_futures":+0.4,"asia":-0.2,"yields":+0.1,"crude":+1.2,"vix":18,"gift_nifty":+0.3}
        us = cues.get("us_futures", 0.0)
        asia = cues.get("asia", 0.0)
        europe = cues.get("europe", 0.0)
        gift = cues.get("gift_nifty", 0.0)
        vix = cues.get("vix", ad.x("vix") or 15)

        net = us + asia + europe + gift
        influence = clamp(50 + net * 15)

        if vix > 28:
            sentiment = GlobalSentiment.PANIC
            warnings.append(self.warn("global panic conditions", Severity.HIGH))
        elif net > 1.0 and vix < 16:
            sentiment = GlobalSentiment.RISK_ON
        elif net < -1.0:
            sentiment = GlobalSentiment.RISK_OFF
        elif net > 0 and vix > 22:
            sentiment = GlobalSentiment.RECOVERY
        else:
            sentiment = GlobalSentiment.MIXED

        impact_tag = ("supportive" if net > 0.3 else "negative" if net < -0.3 else "neutral")
        if sentiment in (GlobalSentiment.PANIC, GlobalSentiment.RISK_OFF):
            decision = "protect / reduce overnight exposure"
        elif impact_tag == "supportive":
            decision = "continue"
        else:
            decision = "monitor overnight"

        outputs = {
            "global_influence_score": round(influence, 1),
            "overnight_risk": {"us": us, "asia": asia, "europe": europe,
                                "gift_nifty": gift, "vix": vix},
            "global_sentiment": sentiment.value,
            "asset_impact_tag": impact_tag,
            "final_global_decision": decision,
        }
        return {"outputs": outputs, "score": round(influence, 1),
                "decision": decision, "warnings": warnings}
