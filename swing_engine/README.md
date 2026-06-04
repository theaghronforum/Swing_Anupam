# Swing Trading Engine (Engines 2–30)

Production-grade, asset-aware decision stack implementing **all 30 engines (1–30)**
from your spec, for **Stocks, F&O, Index, Forex Pairs and Commodities** — each
engine in its own module.

Every engine consumes a shared context and emits a standardised, JSON-serialisable
`EngineResult` whose `outputs` map **one-to-one** onto the bullets in your
"Engine Outputs" document.

## Install & run
```bash
pip install -r requirements.txt
PYTHONPATH=. python examples/run_demo.py        # runs all engines on synthetic data
```
Or install as a package: `pip install -e .` (add a `pyproject.toml`) and `import swing_engine`.

## Architecture
Each engine lives in **its own module** under `engines/`, named `eNN_<slug>.py`,
ordered to match the 1→30 structure of your spec.
```
swing_engine/
  core/
    enums.py         # all output vocabularies (status/label enums)
    indicators.py    # EMA/RSI/MACD/ADX/ATR/Bollinger/swings/fib/rel-volume (pandas)
    models.py        # AssetData, UserProfile, IndicatorBundle, EngineContext, EngineResult
    base_engine.py   # BaseEngine: timing, error capture, degraded-mode, grading helpers
    registry.py      # @register decorator + Pipeline orchestrator
  engines/
    e01_suitability.py            e16_stocks_selection.py
    e02_multi_asset_access.py     e17_index_direction.py
    e03_capital_allocation.py     e18_commodity_cycle.py
    e04_market_regime.py          e19_forex_macro.py
    e05_trend_strength.py         e20_fno_confirmation.py
    e06_price_structure.py        e21_volatility_expansion.py
    e07_support_resistance.py     e22_event_news_risk.py
    e08_breakout_validation.py    e23_global_impact.py
    e09_pullback_quality.py       e24_entry_timing.py
    e10_momentum_continuation.py  e25_stop_loss.py
    e11_reversal_probability.py   e26_target_projection.py
    e12_volume_confirmation.py    e27_trailing_exit.py
    e13_smart_money.py            e28_holding_period.py
    e14_sector_index_alignment.py e29_rebalancing.py
    e15_cross_asset_correlation.py e30_gatekeeper.py
    __init__.py      # imports all 30 in order -> they self-register
examples/run_demo.py
```
Engine 1 here is a complete reference implementation so the full 1→30 pipeline
runs; swap in your existing suitability logic by editing `e01_suitability.py`
(its input `UserProfile` and output keys already match the spec).

## The data contract
Since you already fetch the data, you only assemble two objects.

`AssetData` — one instrument:
- `daily`, `weekly`, `intraday`: OHLCV `DataFrame`s (`open,high,low,close,volume`, ascending `DatetimeIndex`).
- `extras`: a dict carrying every asset-specific field your spec lists. Engines read what they need and **degrade gracefully** when a key is absent. Common keys:
  - **F&O**: `oi`, `change_in_oi`, `pcr`, `iv`, `iv_percentile`, `max_pain`, `futures_price`, `days_to_expiry`
  - **Index**: `vix`, `breadth` (`{advances,declines,new_highs,new_lows}`), `benchmark_index`, `sector_index`
  - **Forex**: `rate_differential`, `dxy`, `dxy_slope`, `central_bank_event`, `event_type`
  - **Commodity**: `dxy`, `inventory_trend`, `cot_commercial`, `weather_risk`, `geopolitical_risk`
  - **Common**: `fii_dii`, `delivery_pct`, `block_deal`, `events` (`[{type,in_days,impact}]`), `global_cues`, `corp_action_pending`

`UserProfile` — capital, risk %, permissions, open positions (drives engines 2, 3, 29, 30).

## Run it
```python
from swing_engine import Pipeline, AssetData, UserProfile, Asset

pipe = Pipeline()                          # all engines 2–30, in order
results = pipe.run(asset_data, user)       # dict[engine_id -> EngineResult]
card    = pipe.run_trade_card(asset_data, user)   # final Gatekeeper trade card

# Run a subset (e.g. only the technical core):
Pipeline(engine_ids=[5, 6, 7, 8, 26]).run(asset_data, user)
```

## How engines chain
The `Pipeline` runs engines in ascending id and feeds every later engine the
accumulated `upstream` results. So Engine 30 (Gatekeeper) reads trend, regime,
breakout, volume, alignment, F&O, target-RR, entry and global scores to produce a
single weighted confidence, apply **hard blockers** (no permission / overexposed /
extreme event / zero size), and emit the final trade card + `execute|monitor|protect|avoid`.

## Plugging in trained models
The engines are rule-based but ML-ready. Each `evaluate()` computes interpretable
features then scores them — replace the scoring block with a model call:
```python
score = self.model.predict_proba(features)[0, 1] * 100   # drop-in
```
Train using the labels your spec defines (forward 3/5/10/15-day return, MAE/MFE,
stop-hit, target-hit). Keep raw / adjusted / indicator / feature / label layers
separate, exactly as your Implementation Notes require.

## Training from your `raw_data/` tree
Your folder layout maps directly onto the five asset classes:
```
raw_data/ohlcv       -> Asset.STOCK         raw_data/forex       -> Asset.FOREX
raw_data/fo          -> Asset.FNO           raw_data/commodities -> Asset.COMMODITY
raw_data/index       -> Asset.INDEX
```
The `swing_engine.data` package reads it and builds model-ready training data:

```python
from swing_engine import Asset
from swing_engine.data import RawDataRepository, LoaderConfig, build_dataset, feature_label_split

repo = RawDataRepository(LoaderConfig(root="raw_data", benchmark_index_symbol="NIFTY50"))
repo.list_symbols(Asset.STOCK)          # discovery
ad = repo.load(Asset.FNO, "RELIANCE-FUT")   # -> AssetData (OI/PCR/IV routed to extras)

ds = build_dataset(repo, assets=[Asset.STOCK], stride=1, warmup=210,
                   horizons=(3,5,10,15), stop_atr_mult=1.5, target_atr_mult=3.0)
X, y, cols = feature_label_split(ds, label="label_bin")   # ready for sklearn/xgboost
```

- **Loader** (`data/loaders.py`): auto-detects CSV / Parquet / Feather; matches
  column names case-insensitively via alias tables (so you needn't rename
  anything); handles both one-file-per-symbol and one-combined-file-with-`symbol`
  layouts; routes recognised fields (oi, change_in_oi, pcr, iv, max_pain, vix,
  dxy, delivery_pct, rate_differential, inventory, fii/dii, ...) into
  `AssetData.extras` (latest scalar + full `_series`).
- **Labels** (`data/labels.py`): your spec's outcomes — forward 3/5/10/15-day
  return, MFE, MAE, stop-hit, target-hit, holding-period outcome — computed only
  from data *after* each bar (no leakage). `label_bin` = target-hit-before-stop.
- **Dataset** (`data/dataset.py`): walks history as-of each bar, runs the
  technical engines, and turns their scores + numeric outputs into a feature row,
  joined to the labels. Features are **scale-free by default** (scores, ratios,
  %s, probabilities, flags) so models generalise across symbols and price regimes;
  absolute price levels are dropped.

See `examples/train_demo.py` for the full load -> build -> train -> save flow.
Tune the column alias tables in `loaders.py` if your headers differ from the defaults.

## Notes
- No look-ahead in any indicator; safe for both back-test and live inference.
- One bad asset never crashes a run — errors are captured per-engine in `EngineResult.error`.
- All labels come from `core/enums.py`, so downstream UI/RMS never sees free-form strings.
- `min_history` per engine guards against thin data (raises → recorded as degraded).
