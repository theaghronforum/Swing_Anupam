"""Engine 4: Swing Market Regime Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.enums import Asset, Regime, StrategyTag, TrendDirection
from ..core.indicators import clamp
from ..core.models import EngineContext
from ..core.registry import register


@register
class MarketRegimeEngine(BaseEngine):
    """4. Trending / sideways / volatile / breakout / reversal classification."""

    engine_id = 4
    name = "Swing Market Regime Engine"
    min_history = 50

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        ad, ix = ctx.asset_data, ctx.indicators
        warnings = []

        adx = ix.adx
        trending = adx >= 25
        rising = ix.last_close > ix.ema50
        vix = ad.x("vix")
        high_vol = ix.atr_pct > ctx.config.get("high_vol_atr_pct", 4.0) or (vix and vix > 20)
        near_resistance = any(abs(ix.last_close - r) / ix.last_close < 0.01 for r in ix.resistance)

        if trending and rising:
            regime = Regime.BULLISH
        elif trending and not rising:
            regime = Regime.BEARISH
        elif high_vol:
            regime = Regime.VOLATILE
            warnings.append(self.warn("elevated volatility regime"))
        elif near_resistance and ix.rsi14 > 65:
            regime = Regime.REVERSAL
        elif adx < 18:
            regime = Regime.SIDEWAYS
        else:
            regime = Regime.BREAKOUT

        strength = clamp(adx * 2.2 + abs(ix.ema20_slope) * 5)

        strat = {
            Regime.BULLISH: StrategyTag.TREND_FOLLOWING,
            Regime.BEARISH: StrategyTag.TREND_FOLLOWING,
            Regime.SIDEWAYS: StrategyTag.PULLBACK,
            Regime.VOLATILE: StrategyTag.HEDGED,
            Regime.BREAKOUT: StrategyTag.BREAKOUT,
            Regime.REVERSAL: StrategyTag.AVOID,
        }[regime]

        if regime in (Regime.BULLISH, Regime.BREAKOUT):
            decision = "open swing trades"
        elif regime == Regime.VOLATILE:
            decision = "reduce size / hedge"
        elif regime == Regime.REVERSAL:
            decision = "avoid new longs"
        else:
            decision = "selective / wait"

        outputs = {
            "regime_label": regime.value,
            "regime_strength": round(strength, 1),
            "segment_condition": {ad.asset.value: regime.value},
            "strategy_tag": strat.value,
            "final_regime_decision": decision,
        }
        return {"outputs": outputs, "score": round(strength, 1),
                "decision": regime.value, "warnings": warnings}
