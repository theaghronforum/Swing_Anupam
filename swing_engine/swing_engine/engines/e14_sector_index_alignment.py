"""Engine 14: Sector & Index Alignment Engine."""
from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd

from ..core.base_engine import BaseEngine
from ..core.indicators import clamp, slope
from ..core.models import EngineContext
from ..core.registry import register


def _aligned_returns(a: pd.Series, b: pd.Series, n: int = 60):
    a = a.pct_change().dropna().tail(n)
    b = b.pct_change().dropna().tail(n)
    idx = a.index.intersection(b.index)
    return a.loc[idx], b.loc[idx]


@register
class SectorIndexAlignmentEngine(BaseEngine):
    """14. Does the trade align with its sector and the index?"""

    engine_id = 14
    name = "Sector & Index Alignment Engine"
    min_history = 30

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ad, ix = ctx.asset_data, ctx.indicators
        warnings = []
        sector = ad.x("sector_index")     # DataFrame with close
        index = ad.x("benchmark_index")   # DataFrame with close

        sec_dir = "neutral"
        rs_vs_index = 50.0
        align_score = 50.0

        stock_ret = (ad.daily["close"].iloc[-1] / ad.daily["close"].iloc[-21] - 1) \
            if len(ad.daily) > 21 else 0.0

        if isinstance(sector, pd.DataFrame) and len(sector) > 21:
            sec_slope = slope(sector["close"], 10)
            sec_dir = "up" if sec_slope > 0.05 else "down" if sec_slope < -0.05 else "neutral"
        if isinstance(index, pd.DataFrame) and len(index) > 21:
            idx_ret = index["close"].iloc[-1] / index["close"].iloc[-21] - 1
            rs_vs_index = clamp(50 + (stock_ret - idx_ret) * 500)
            align = (stock_ret > 0) == (idx_ret > 0)
            align_score = clamp((rs_vs_index * 0.6) + (30 if align else -10))

        breadth = ad.x("breadth", {})     # {"advances":..,"declines":..,"new_highs":..}
        adv, dec = breadth.get("advances", 0), breadth.get("declines", 0)
        if adv + dec > 0:
            ratio = adv / (adv + dec)
            breadth_out = ("broad participation" if ratio > 0.6 else
                           "weak breadth" if ratio < 0.4 else "narrow participation")
        else:
            breadth_out = "narrow participation"

        leadership = ("leading" if rs_vs_index > 65 else "lagging" if rs_vs_index < 40
                      else "rotating")
        if rs_vs_index > 85:
            leadership = "overheated"
            warnings.append(self.warn("relative strength overheated"))

        if align_score > 65 and sec_dir != "down":
            final = "aligned trade"
        elif align_score > 50:
            final = "partial alignment"
        elif align_score < 35:
            final = "contradictory setup"
            warnings.append(self.warn("trade fights the index"))
        else:
            final = "avoid"

        outputs = {
            "sector_direction": sec_dir,
            "index_alignment_score": round(align_score, 1),
            "market_breadth": breadth_out,
            "sector_leadership": leadership,
            "stock_vs_index_strength": round(rs_vs_index, 1),
            "final_alignment_output": final,
        }
        return {"outputs": outputs, "score": round(align_score, 1),
                "decision": final, "warnings": warnings}
