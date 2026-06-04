"""End-to-end demo: build synthetic data for each asset class and run the full
30-engine pipeline, printing the Gatekeeper trade card.

Run:  python examples/run_demo.py
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from swing_engine import Asset, AssetData, Pipeline, UserProfile


def synth_ohlcv(days: int = 400, start: float = 100.0, drift: float = 0.0008,
                vol: float = 0.015, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, days)
    close = start * np.exp(np.cumsum(rets))
    high = close * (1 + np.abs(rng.normal(0, vol / 2, days)))
    low = close * (1 - np.abs(rng.normal(0, vol / 2, days)))
    open_ = np.concatenate([[start], close[:-1]])
    volume = rng.integers(5_000, 50_000, days).astype(float)
    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=days, freq="B")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def weekly(df: pd.DataFrame) -> pd.DataFrame:
    return df.resample("W").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()


def main() -> None:
    user = UserProfile(
        user_id="u-1001",
        capital=1_000_000,
        cash_balance=600_000,
        risk_per_trade_pct=1.0,
        max_portfolio_risk_pct=6.0,
        experience_years=4,
        risk_appetite="balanced",
        permissions={"STOCK": True, "INDEX": True, "FNO": True,
                     "FOREX": True, "COMMODITY": True},
        open_positions=[
            {"symbol": "INFY", "sector": "IT", "trend_score": 62, "risk_amount": 8000},
            {"symbol": "TCS", "sector": "IT", "trend_score": 35, "risk_amount": 7000},
        ],
    )

    daily = synth_ohlcv(drift=0.0012)        # mild uptrend
    bench = synth_ohlcv(drift=0.0007, seed=3)

    cases = {
        Asset.STOCK: AssetData(
            asset=Asset.STOCK, symbol="RELIANCE", daily=daily, weekly=weekly(daily),
            extras={
                "delivery_pct": 64, "benchmark_index": bench,
                "sector_index": synth_ohlcv(drift=0.0009, seed=5),
                "breadth": {"advances": 1200, "declines": 700},
                "fii_dii": {"fii_net": 450, "dii_net": 200},
                "earnings_in_days": 18,
                "events": [{"type": "earnings", "in_days": 18, "impact": "binary"}],
                "global_cues": {"us_futures": 0.4, "asia": 0.2, "gift_nifty": 0.3, "vix": 14},
                "vix": 14,
            },
        ),
        Asset.FNO: AssetData(
            asset=Asset.FNO, symbol="RELIANCE-FUT", daily=daily, weekly=weekly(daily),
            extras={
                "oi": 5_000_000, "change_in_oi": 250_000, "pcr": 1.25, "iv": 22,
                "iv_percentile": 48, "max_pain": float(daily["close"].iloc[-1]),
                "futures_price": float(daily["close"].iloc[-1]) * 1.002,
                "days_to_expiry": 12, "benchmark_index": bench,
                "events": [], "vix": 14,
            },
        ),
        Asset.INDEX: AssetData(
            asset=Asset.INDEX, symbol="NIFTY50", daily=bench, weekly=weekly(bench),
            extras={"vix": 13, "breadth": {"advances": 32, "declines": 18},
                    "benchmark_index": bench,
                    "global_cues": {"us_futures": 0.5, "asia": 0.1, "gift_nifty": 0.4, "vix": 13}},
        ),
        Asset.FOREX: AssetData(
            asset=Asset.FOREX, symbol="USDINR", daily=synth_ohlcv(start=83, vol=0.004, seed=11),
            extras={"rate_differential": 1.5, "dxy_slope": 0.05, "dxy": 104,
                    "central_bank_event": None, "event_type": "none"},
        ),
        Asset.COMMODITY: AssetData(
            asset=Asset.COMMODITY, symbol="GOLD",
            daily=synth_ohlcv(start=2000, drift=0.0006, vol=0.01, seed=21),
            extras={"dxy": 104, "inventory_trend": -1, "cot_commercial": 1200,
                    "weather_risk": False, "geopolitical_risk": False},
        ),
    }

    pipe = Pipeline()
    for asset, ad in cases.items():
        card = pipe.run_trade_card(ad, user)
        print("=" * 72)
        print(f"{asset.value:10s} {ad.symbol}")
        print("-" * 72)
        print("final_action :", card["final_action"])
        print("trade_card   :", json.dumps(card["trade_card"], indent=2, default=str))
        # Show a couple of engine decisions for context.
        for eid in (1, 4, 5, 8, 30):
            r = card["all_results"][eid]
            print(f"  E{eid:02d} {r['engine_name']:42s} -> {r['decision']:20s} "
                  f"(score {r['score']})")
    print("=" * 72)
    print(f"Engines registered: {sorted(__import__('swing_engine').registered_engines())}")


if __name__ == "__main__":
    main()
