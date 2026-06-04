"""Engine 15: Cross-Asset Correlation Engine."""
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
class CrossAssetCorrelationEngine(BaseEngine):
    """15. Relationships between the instrument and index/USD/commodities."""

    engine_id = 15
    name = "Cross-Asset Correlation Engine"
    min_history = 40

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ad, ix = ctx.asset_data, ctx.indicators
        warnings = []
        base = ad.daily["close"]
        corr_map: Dict[str, float] = {}

        peers = {
            "index": ad.x("benchmark_index"),
            "usd": ad.x("dxy_series") or ad.x("usdinr_series"),
            "crude": ad.x("crude_series"),
            "gold": ad.x("gold_series"),
            "yields": ad.x("yields_series"),
        }
        for name, series in peers.items():
            if isinstance(series, pd.DataFrame):
                series = series["close"]
            if isinstance(series, pd.Series) and len(series) > 30:
                a, b = _aligned_returns(base, series)
                if len(a) > 10:
                    corr_map[name] = round(float(np.corrcoef(a, b)[0, 1]), 2)

        risk_on = ad.x("vix")
        env = "risk-off" if (risk_on and risk_on > 20) else "risk-on"

        # Conflict: strongly negative correlation with a peer that is trending against us.
        conflict = any(abs(c) > 0.6 for c in corr_map.values())
        alert = ("negative" if any(c < -0.5 for c in corr_map.values()) else
                 "positive" if any(c > 0.5 for c in corr_map.values()) else "broken")

        diversification = clamp(100 - np.mean([abs(c) for c in corr_map.values()]) * 100) \
            if corr_map else 60.0
        confirmation = clamp(diversification * 0.6 + (40 if not conflict else 10))
        if conflict:
            warnings.append(self.warn("high cross-asset correlation / conflict"))

        outputs = {
            "correlation_map": corr_map,
            "risk_environment": env,
            "correlation_alert": alert,
            "conflict_warning": bool(conflict),
            "cross_asset_confirmation_score": round(confirmation, 1),
            "diversification_warning": diversification < 40,
        }
        return {"outputs": outputs, "score": round(confirmation, 1),
                "decision": env, "warnings": warnings}
