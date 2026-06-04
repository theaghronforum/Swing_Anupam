"""Engine 2: Multi-Asset Swing Access Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.enums import Asset, EligibilityTag, RiskUtilisation, SegmentAccess
from ..core.models import EngineContext
from ..core.registry import register


@register
class MultiAssetAccessEngine(BaseEngine):
    """2. Decides whether *this* instrument/segment is available and how good
    the opportunity currently is."""

    engine_id = 2
    name = "Multi-Asset Swing Access Engine"
    min_history = 20

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ad, u, ix = ctx.asset_data, ctx.user, ctx.indicators
        warnings = []

        # Liquidity filter from traded value (price * volume).
        adv = ad.daily["volume"].tail(20).mean() if "volume" in ad.daily else 0.0
        traded_value = adv * ix.last_close
        liquid = traded_value >= ctx.config.get("min_traded_value", 0.0) or adv > 0

        permitted = u.can_trade(ad.asset)
        price_band_frozen = bool(ad.x("price_band_frozen", False))
        corp_action = bool(ad.x("corp_action_pending", False))

        # Segment access status.
        if not permitted:
            access = SegmentAccess.BLOCKED
        elif price_band_frozen:
            access = SegmentAccess.WATCH_ONLY
            warnings.append(self.warn("price band frozen"))
        elif not liquid:
            access = SegmentAccess.RESTRICTED
            warnings.append(self.warn("thin liquidity"))
        else:
            access = SegmentAccess.ENABLED

        # Opportunity-quality access score (0..100).
        liq_score = min(40.0, (traded_value / ctx.config.get("liquidity_ref", 1e7)) * 40) if traded_value else 10.0
        vol_score = 30.0 if 1.0 <= ix.atr_pct <= 6.0 else 15.0          # tradable volatility
        trend_score = min(30.0, abs(ix.ema20_slope) * 10)
        access_score = round(min(100.0, liq_score + vol_score + trend_score), 1)

        # Eligibility tag.
        if access == SegmentAccess.BLOCKED:
            tag = EligibilityTag.AVOID
        elif corp_action or access == SegmentAccess.WATCH_ONLY:
            tag = EligibilityTag.WAIT
        elif access == SegmentAccess.RESTRICTED:
            tag = EligibilityTag.MONITOR
        else:
            tag = EligibilityTag.TRADABLE if access_score >= 50 else EligibilityTag.MONITOR

        # Segment ranking hint (single-asset view; portfolio layer aggregates).
        ranking = {ad.asset.value: access_score}

        outputs = {
            "tradable_universe": [ad.symbol] if access == SegmentAccess.ENABLED else [],
            "segment_access": access.value,
            "best_segment_ranking": ranking,
            "eligibility_tag": tag.value,
            "access_score": access_score,
            "recommended_focus": ad.asset.value if tag == EligibilityTag.TRADABLE else "none",
        }
        return {
            "outputs": outputs,
            "score": access_score,
            "decision": tag.value,
            "warnings": warnings,
        }
