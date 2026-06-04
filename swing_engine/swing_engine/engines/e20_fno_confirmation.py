"""Engine 20: F&O Confirmation Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.enums import Asset
from ..core.indicators import clamp, slope
from ..core.models import EngineContext
from ..core.registry import register


@register
class FnoConfirmationEngine(BaseEngine):
    """20. Uses derivatives data to confirm or reject the swing signal."""

    engine_id = 20
    name = "F&O Confirmation Engine"
    min_history = 20

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ad, ix = ctx.asset_data, ctx.indicators
        warnings = []
        oi = ad.x("oi")
        d_oi = ad.x("change_in_oi", 0.0)
        pcr = ad.x("pcr")
        iv = ad.x("iv")
        iv_pct = ad.x("iv_percentile")
        max_pain = ad.x("max_pain")
        fut = ad.x("futures_price", ix.last_close)
        price_up = ix.last_close > ix.ema20

        # Futures bias from price + OI.
        if price_up and d_oi > 0:
            fut_bias = "long buildup"
        elif not price_up and d_oi > 0:
            fut_bias = "short buildup"
        elif not price_up and d_oi < 0:
            fut_bias = "long unwinding"
        elif price_up and d_oi < 0:
            fut_bias = "short covering"
        else:
            fut_bias = "neutral"

        # Options bias from PCR.
        if pcr is None:
            opt_bias = "neutral"
        elif pcr > 1.3:
            opt_bias = "bullish (high put writing)"
        elif pcr < 0.7:
            opt_bias = "bearish (high call writing)"
        else:
            opt_bias = "neutral"

        score = clamp(50 +
                      (20 if fut_bias in ("long buildup", "short covering") else -20 if fut_bias in ("short buildup", "long unwinding") else 0) +
                      (15 if opt_bias.startswith("bullish") else -15 if opt_bias.startswith("bearish") else 0) +
                      (-10 if (iv_pct and iv_pct > 80) else 5))

        if iv_pct and iv_pct > 80:
            warnings.append(self.warn("IV in high percentile — premium expensive"))

        if score >= 62:
            structure = "futures trade" if ctx.user.can_trade(Asset.FNO) else "cash trade"
            status = "confirmed"
        elif score >= 50:
            structure = "call strategy" if price_up else "put strategy"
            status = "partially confirmed"
        elif iv_pct and iv_pct > 70:
            structure = "spread"
            status = "hedge suggested"
        else:
            structure = "avoid"
            status = "rejected"

        outputs = {
            "derivative_confirmation_status": status,
            "futures_bias": fut_bias,
            "options_bias": opt_bias,
            "pcr": pcr,
            "iv": iv,
            "iv_percentile": iv_pct,
            "max_pain": max_pain,
            "recommended_fno_structure": structure,
            "confirmation_score": round(score, 1),
            "execution_permission": status in ("confirmed", "partially confirmed"),
        }
        return {"outputs": outputs, "score": round(score, 1),
                "decision": status, "warnings": warnings}
