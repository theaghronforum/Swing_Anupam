"""Engine 13: Smart Money Accumulation Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.indicators import clamp
from ..core.models import EngineContext
from ..core.registry import register


@register
class SmartMoneyEngine(BaseEngine):
    """13. Detect institutional accumulation / distribution."""

    engine_id = 13
    name = "Smart Money Accumulation Engine"
    min_history = 30

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ad, ix = ctx.asset_data, ctx.indicators
        df = ad.daily
        warnings = []

        # Price-volume absorption: rising price on rising volume = accumulation.
        ret5 = (df["close"].iloc[-1] / df["close"].iloc[-6] - 1) if len(df) > 6 else 0.0
        vol_trend = ix.rel_volume - 1.0

        fii = ad.x("fii_dii", {})            # {"fii_net": ..., "dii_net": ...}
        fii_net = (fii or {}).get("fii_net", 0.0)
        cot = ad.x("cot_net") or ad.x("cot_commercial")   # forex/commodities
        block = bool(ad.x("block_deal"))

        flow_bias = fii_net + (cot or 0.0)
        absorb = ret5 > 0 and vol_trend > 0

        score = clamp(50 + ret5 * 200 + vol_trend * 20 +
                      (15 if flow_bias > 0 else -15 if flow_bias < 0 else 0) +
                      (10 if block else 0))

        if absorb and flow_bias >= 0:
            signal, bias, decision = "accumulation", "buying", "follow accumulation"
        elif ret5 < 0 and vol_trend > 0 and flow_bias <= 0:
            signal, bias, decision = "distribution", "selling", "avoid distribution"
            warnings.append(self.warn("distribution signature"))
        elif abs(ret5) < 0.005 and vol_trend > 0.5:
            signal, bias, decision = "accumulation", "rotating", "wait for confirmation"
        elif ix.rel_volume > 2.5 and abs(ret5) < 0.003:
            signal, bias, decision = "distribution", "trapping", "protect position"
        else:
            signal, bias, decision = "neutral", "neutral", "wait for confirmation"

        outputs = {
            "accumulation_distribution_signal": signal,
            "smart_money_bias": bias,
            "absorption_zone": [round(ix.support[0] if ix.support else ix.last_close * 0.97, 4),
                                 round(ix.last_close, 4)],
            "institutional_participation_confidence": round(score, 1),
            "net_flow_proxy": round(flow_bias, 2),
            "final_smart_money_decision": decision,
        }
        return {"outputs": outputs, "score": round(score, 1),
                "decision": decision, "warnings": warnings}
