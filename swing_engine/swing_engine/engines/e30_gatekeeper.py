"""Engine 30: Final Strategy & Execution Gatekeeper Engine."""
from __future__ import annotations

from typing import Any, Dict, List

from ..core.base_engine import BaseEngine
from ..core.enums import ApprovalStatus, ExecutionPriority
from ..core.indicators import clamp
from ..core.models import EngineContext
from ..core.registry import register


@register
class GatekeeperEngine(BaseEngine):
    """30. Final approval layer; assembles the trade card from all engines."""

    engine_id = 30
    name = "Final Strategy & Execution Gatekeeper Engine"
    min_history = 20

    # Hard blockers — any of these forces rejection regardless of score.
    def _hard_blocks(self, ctx: EngineContext) -> List[str]:
        blocks = []
        if ctx.out(2, "segment_access") == "blocked":
            blocks.append("segment not permitted for user")
        if ctx.out(3, "risk_utilisation") == "overexposed":
            blocks.append("portfolio overexposed")
        if ctx.out(22, "event_risk_level") == "extreme":
            blocks.append("extreme event risk in window")
        if ctx.out(3, "position_size_qty", 0) <= 0:
            blocks.append("no risk budget for position")
        return blocks

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        u, ix = ctx.user, ctx.indicators
        warnings = []

        # Composite confidence from the key decision engines.
        weights = {
            5: 0.18,   # trend strength
            4: 0.10,   # regime strength
            8: 0.10,   # breakout quality
            12: 0.08,  # volume
            14: 0.10,  # alignment
            20: 0.12,  # F&O confirmation
            26: 0.12,  # target confidence (RR)
            24: 0.10,  # entry confidence
            23: 0.10,  # global impact
        }
        composite = 0.0
        for eid, w in weights.items():
            r = ctx.upstream.get(eid)
            composite += (r.score if r else 50.0) * w
        composite = clamp(composite)

        rr = ctx.out(26, "risk_reward_ratio", 0)
        reversal = ctx.out(11, "reversal_probability", 0)
        blocks = self._hard_blocks(ctx)

        if blocks:
            status = ApprovalStatus.REJECTED
            priority = ExecutionPriority.NO_TRADE
            final_action = "avoid"
            warnings.extend(self.warn(b) for b in blocks)
        elif ctx.out(4, "regime_label") in ("volatile", "reversal zone") or reversal > 60:
            status = ApprovalStatus.HEDGE_REQUIRED
            priority = ExecutionPriority.LOW
            final_action = "protect"
        elif composite >= 65 and rr >= 1.5:
            status = ApprovalStatus.APPROVED
            priority = ExecutionPriority.HIGH if composite >= 78 else ExecutionPriority.MEDIUM
            final_action = "execute"
        elif composite >= 52:
            status = ApprovalStatus.CONDITIONAL
            priority = ExecutionPriority.MEDIUM
            final_action = "monitor"
        else:
            status = ApprovalStatus.WAIT
            priority = ExecutionPriority.LOW
            final_action = "monitor"

        trade_card = {
            "asset": ctx.asset.value,
            "segment": ctx.asset.value,
            "symbol": ctx.asset_data.symbol,
            "signal": ctx.out(16, "signal") or ctx.out(19, "signal")
                      or ctx.out(17, "index_direction") or ctx.out(18, "directional_signal"),
            "entry": ctx.out(24, "entry_zone", {}).get("primary", ix.last_close),
            "stop_loss": ctx.out(25, "stop_loss_level"),
            "target_1": ctx.out(26, "target_1"),
            "target_2": ctx.out(26, "target_2"),
            "quantity": ctx.out(3, "position_size_qty", 0),
            "capital_at_risk": ctx.out(25, "capital_at_risk", 0),
            "risk_reward": rr,
            "confidence": round(composite, 1),
            "holding_period_days": ctx.out(28, "expected_holding_days", 7),
        }

        # Reason summary aggregates each engine's headline decision.
        reason = {
            eid: {"name": r.engine_name, "decision": r.decision, "score": round(r.score, 1)}
            for eid, r in sorted(ctx.upstream.items())
        }

        outputs = {
            "final_trade_approval_status": status.value,
            "trade_card": trade_card,
            "execution_priority": priority.value,
            "reason_summary": reason,
            "hard_blocks": blocks,
            "final_action": final_action,
        }
        return {"outputs": outputs, "score": round(composite, 1),
                "decision": status.value, "warnings": warnings}
