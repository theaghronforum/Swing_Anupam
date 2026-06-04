"""Engine 6: Price Structure Intelligence Engine."""
from __future__ import annotations

from typing import Any, Dict

from ..core.base_engine import BaseEngine
from ..core.indicators import clamp, fibonacci_levels, swing_points
from ..core.models import EngineContext
from ..core.registry import register


@register
class PriceStructureEngine(BaseEngine):
    """6. Reads swing structure: HH/HL, LH/LL, range, compression, expansion."""

    engine_id = 6
    name = "Price Structure Intelligence Engine"
    min_history = 30

    def evaluate(self, ctx: EngineContext) -> Dict[str, Any]:
        df, ix = ctx.asset_data.daily, ctx.indicators
        warnings = []
        highs, lows = swing_points(df)

        hh = len(highs) >= 2 and highs[-1][1] > highs[-2][1]
        hl = len(lows) >= 2 and lows[-1][1] > lows[-2][1]
        lh = len(highs) >= 2 and highs[-1][1] < highs[-2][1]
        ll = len(lows) >= 2 and lows[-1][1] < lows[-2][1]

        compressing = ix.bb_width and ix.bb_width < ctx.config.get("compression_bw", 6.0)
        expanding = ix.bb_width and ix.bb_width > ctx.config.get("expansion_bw", 16.0)

        if hh and hl:
            structure = "higher-high higher-low"
            decision = "bullish structure"
        elif lh and ll:
            structure = "lower-high lower-low"
            decision = "bearish structure"
        elif compressing:
            structure = "compression"
            decision = "neutral structure"
        elif expanding:
            structure = "expansion"
            decision = "unstable structure"
        else:
            structure = "range"
            decision = "neutral structure"

        # Break of structure / change of character.
        bos = (hh and ix.last_close > ix.swing_high) or (ll and ix.last_close < ix.swing_low)
        choch = (lh and hl) or (hh and ll)  # conflicting pivots
        if choch:
            warnings.append(self.warn("change of character detected"))

        # Cleanliness: fewer, well-separated pivots == cleaner.
        n_piv = len(highs) + len(lows)
        quality = clamp(100 - abs(n_piv - 8) * 6)

        outputs = {
            "structure_label": structure,
            "swing_high": round(ix.swing_high, 4),
            "swing_low": round(ix.swing_low, 4),
            "structure_quality_score": round(quality, 1),
            "break_of_structure": bool(bos),
            "change_of_character": bool(choch),
            "final_structure_decision": decision,
        }
        return {"outputs": outputs, "score": round(quality, 1),
                "decision": decision, "warnings": warnings}
