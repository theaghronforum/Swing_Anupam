"""Importing this package registers every engine (1-30) in the registry.

Each engine lives in its own module, named `eNN_<slug>.py`, ordered to match
the 1->30 structure from the specification. The Pipeline runs them in ascending
engine_id, so the Gatekeeper (30) sees every upstream result.
"""
# Engine 1 is a reference/template implementation — swap in your own if needed.
from . import e01_suitability               # 1  Swing Trader Suitability
from . import e02_multi_asset_access        # 2  Multi-Asset Swing Access
from . import e03_capital_allocation        # 3  Capital Allocation & Risk Budget
from . import e04_market_regime             # 4  Swing Market Regime
from . import e05_trend_strength            # 5  Trend Strength Detection
from . import e06_price_structure           # 6  Price Structure Intelligence
from . import e07_support_resistance        # 7  Support & Resistance Mapping
from . import e08_breakout_validation       # 8  Breakout Validation
from . import e09_pullback_quality          # 9  Pullback Quality
from . import e10_momentum_continuation     # 10 Momentum Continuation
from . import e11_reversal_probability      # 11 Reversal Probability
from . import e12_volume_confirmation       # 12 Volume Confirmation
from . import e13_smart_money               # 13 Smart Money Accumulation
from . import e14_sector_index_alignment    # 14 Sector & Index Alignment
from . import e15_cross_asset_correlation   # 15 Cross-Asset Correlation
from . import e16_stocks_selection          # 16 Stocks Swing Selection
from . import e17_index_direction           # 17 Index Swing Direction
from . import e18_commodity_cycle           # 18 Commodity Cycle Intelligence
from . import e19_forex_macro               # 19 Forex Macro Swing
from . import e20_fno_confirmation          # 20 F&O Confirmation
from . import e21_volatility_expansion      # 21 Volatility Expansion
from . import e22_event_news_risk           # 22 Event & News Risk
from . import e23_global_impact             # 23 Global Market Impact
from . import e24_entry_timing              # 24 Entry Timing
from . import e25_stop_loss                 # 25 Stop-Loss Placement
from . import e26_target_projection         # 26 Target Projection
from . import e27_trailing_exit             # 27 Trailing Exit
from . import e28_holding_period            # 28 Position Holding Period
from . import e29_rebalancing               # 29 Swing Trade Rebalancing
from . import e30_gatekeeper                # 30 Final Strategy & Execution Gatekeeper

__all__ = [f"e{n:02d}" for n in range(1, 31)]
