"""Engine 12: Volume Confirmation Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.indicators import clamp
from ..core.models import EngineContext
from ..core.registry import register


@register
class VolumeConfirmationEngine(BaseEngine):
    """12. Is there real participation behind the move?"""

    engine_id = 12
    name = "Volume Confirmation Engine"
    min_history = 20

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ad, ix = ctx.asset_data, ctx.indicators
        warnings = []
        rvol = ix.rel_volume
        rel_score = clamp(rvol * 50)

        # Delivery % (stocks) or OI change (F&O) as participation refinements.
        delivery = ad.x("delivery_pct")
        oi_change = ad.x("change_in_oi")

        if rvol >= 2.0:
            status = "strong"
        elif rvol >= 1.2:
            status = "normal"
        elif rvol >= 0.7:
            status = "weak"
            warnings.append(self.warn("below-average volume"))
        elif rvol >= 0.3:
            status = "abnormal"
        else:
            status = "suspicious"
            warnings.append(self.warn("suspiciously low volume"))

        if delivery is not None and delivery > 60:
            participation = "institutional"
        elif ad.x("block_deal") or (oi_change and abs(oi_change) > 0):
            participation = "institutional"
        elif rvol > 2.5 and (delivery is None or delivery < 35):
            participation = "event-driven"
        elif rvol < 0.6:
            participation = "low participation"
        else:
            participation = "retail-heavy"

        if status in ("strong", "normal"):
            tag = "confirmed"
        elif status == "weak":
            tag = "partially confirmed"
        elif status == "abnormal":
            tag = "unconfirmed"
        else:
            tag = "rejected"

        outputs = {
            "volume_confirmation_status": status,
            "relative_volume_score": round(rel_score, 1),
            "relative_volume_multiple": round(rvol, 2),
            "participation_quality": participation,
            "supports": {"breakout": rvol >= 1.3, "pullback": rvol < 1.0,
                          "reversal": rvol >= 2.0, "continuation": rvol >= 1.2},
            "final_volume_validation": tag,
        }
        return {"outputs": outputs, "score": round(rel_score, 1),
                "decision": tag, "warnings": warnings}
