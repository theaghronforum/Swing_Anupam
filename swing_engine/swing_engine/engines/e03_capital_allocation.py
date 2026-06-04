"""Engine 3: Capital Allocation & Risk Budget Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.enums import Asset, EligibilityTag, RiskUtilisation, SegmentAccess
from ..core.models import EngineContext
from ..core.registry import register


@register
class CapitalAllocationEngine(BaseEngine):
    """3. Sizes the position and enforces per-trade / portfolio risk budgets."""

    engine_id = 3
    name = "Capital Allocation & Risk Budget Engine"
    min_history = 14

    # Notional weight per segment used as a starting allocation template.
    SEGMENT_WEIGHTS = {
        Asset.STOCK: 0.40,
        Asset.INDEX: 0.20,
        Asset.FNO: 0.15,
        Asset.FOREX: 0.10,
        Asset.COMMODITY: 0.15,
    }

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ad, u, ix = ctx.asset_data, ctx.user, ctx.indicators
        warnings = []
        capital = max(u.capital, 1.0)

        # Per-trade risk in currency.
        per_trade_risk = capital * (u.risk_per_trade_pct / 100.0)
        portfolio_risk_limit = capital * (u.max_portfolio_risk_pct / 100.0)
        max_exposure = capital * (u.max_exposure_pct / 100.0)

        # Stop distance: prefer Engine 25 if already run, else ATR-based default.
        sl_distance = ctx.out(25, "stop_distance")
        if not sl_distance:
            sl_distance = max(ix.atr14 * ctx.config.get("atr_stop_mult", 1.5), ix.last_close * 0.005)

        # Position size so that (qty * sl_distance) ~= per_trade_risk.
        qty = int(per_trade_risk // sl_distance) if sl_distance > 0 else 0
        notional = qty * ix.last_close

        # Current open risk already deployed.
        open_risk = sum(p.get("risk_amount", 0.0) for p in u.open_positions)
        remaining_budget = max(0.0, portfolio_risk_limit - open_risk)
        if per_trade_risk > remaining_budget:
            warnings.append(self.warn("trade risk exceeds remaining portfolio budget"))
            qty = int(remaining_budget // sl_distance) if sl_distance > 0 else 0
            notional = qty * ix.last_close

        # Risk utilisation status.
        util = (open_risk + per_trade_risk) / portfolio_risk_limit if portfolio_risk_limit else 1.0
        if util <= 0.5:
            status = RiskUtilisation.SAFE
        elif util <= 0.8:
            status = RiskUtilisation.MODERATE
        elif util <= 1.0:
            status = RiskUtilisation.STRETCHED
        else:
            status = RiskUtilisation.OVEREXPOSED
            warnings.append(self.warn("portfolio overexposed", ))

        allocation = {a.value: round(capital * w, 2) for a, w in self.SEGMENT_WEIGHTS.items()}

        outputs = {
            "allocation_by_segment": allocation,
            "per_trade_risk": round(per_trade_risk, 2),
            "portfolio_risk_limit": round(portfolio_risk_limit, 2),
            "max_exposure_limit": round(max_exposure, 2),
            "position_size_qty": qty,
            "position_notional": round(notional, 2),
            "stop_distance_used": round(sl_distance, 4),
            "risk_utilisation": status.value,
            "risk_budget_remaining": round(max(0.0, remaining_budget - per_trade_risk), 2),
        }
        score = round(max(0.0, 100.0 * (1 - util)), 1)
        return {
            "outputs": outputs,
            "score": score,
            "decision": status.value,
            "warnings": warnings,
        }
