"""Load the `raw_data/` tree into `AssetData` objects the engines consume.

Expected layout (your structure)::

    raw_data/
      ohlcv/        -> Asset.STOCK   (cash equities OHLCV)
      fo/           -> Asset.FNO     (futures OHLCV + OI/IV/PCR/... columns)
      index/        -> Asset.INDEX   (index OHLCV + VIX/breadth columns)
      forex/        -> Asset.FOREX   (pair OHLCV + DXY/rate-diff columns)
      commodities/  -> Asset.COMMODITY (contract OHLCV + inventory/DXY columns)

Each folder may contain EITHER:
  * one file per symbol  (RELIANCE.csv, TCS.csv, ...), symbol = file stem, OR
  * one combined file with a `symbol` column (auto-detected).

File format is auto-detected from the extension (.csv/.parquet/.feather/.pq).
Column names are matched case-insensitively through alias tables, so you do not
need to rename anything. Anything the loader recognises as an asset-specific
field (oi, pcr, iv, vix, dxy, ...) is routed into `AssetData.extras`:
the latest value under e.g. `extras["pcr"]` and the full column under
`extras["pcr_series"]`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

from ..core.enums import Asset
from ..core.models import AssetData

logger = logging.getLogger("swing_engine.data")

# --------------------------------------------------------------------------- #
# Column alias tables (all lower-cased before matching)
# --------------------------------------------------------------------------- #
_DATE_ALIASES = ["date", "timestamp", "datetime", "time", "trade_date", "dt"]
_OHLCV_ALIASES = {
    "open": ["open", "o", "open_price", "op"],
    "high": ["high", "h", "high_price"],
    "low": ["low", "l", "low_price"],
    "close": ["close", "c", "close_price", "last", "ltp", "settle", "settlement"],
    "volume": ["volume", "vol", "v", "qty", "traded_qty", "contracts"],
}
_SYMBOL_ALIASES = ["symbol", "ticker", "scrip", "instrument", "name", "tradingsymbol"]

# canonical extra key -> possible source column names
_EXTRA_ALIASES: Dict[str, List[str]] = {
    "oi": ["oi", "open_interest", "openinterest"],
    "change_in_oi": ["change_in_oi", "oi_change", "chg_in_oi", "doi"],
    "pcr": ["pcr", "put_call_ratio", "pcr_oi"],
    "iv": ["iv", "implied_volatility", "atm_iv"],
    "iv_percentile": ["iv_percentile", "ivp", "iv_rank", "ivr"],
    "max_pain": ["max_pain", "maxpain"],
    "futures_price": ["futures_price", "fut_close", "fut_price", "future_close"],
    "days_to_expiry": ["days_to_expiry", "dte", "days_to_exp"],
    "basis": ["basis", "premium", "fut_premium"],
    "rollover_pct": ["rollover_pct", "rollover", "roll_pct"],
    "vix": ["vix", "india_vix", "indiavix"],
    "dxy": ["dxy", "dollar_index", "usdx"],
    "delivery_pct": ["delivery_pct", "deliv_pct", "delivery_percentage", "del_pct"],
    "rate_differential": ["rate_differential", "rate_diff", "yield_diff"],
    "inventory_trend": ["inventory_trend", "inventory", "stocks_change"],
    "cot_commercial": ["cot_commercial", "commercial_net", "cot_net"],
    "fii_net": ["fii_net", "fii", "fii_flow"],
    "dii_net": ["dii_net", "dii", "dii_flow"],
}

_DEFAULT_FOLDER_MAP = {
    "ohlcv": Asset.STOCK,
    "fo": Asset.FNO,
    "index": Asset.INDEX,
    "forex": Asset.FOREX,
    "commodities": Asset.COMMODITY,
}

_READERS = {
    ".csv": lambda p: pd.read_csv(p),
    ".txt": lambda p: pd.read_csv(p),
    ".parquet": lambda p: pd.read_parquet(p),
    ".pq": lambda p: pd.read_parquet(p),
    ".feather": lambda p: pd.read_feather(p),
}


@dataclass
class LoaderConfig:
    root: str = "raw_data"
    folder_map: Dict[str, Asset] = field(default_factory=lambda: dict(_DEFAULT_FOLDER_MAP))
    # Optional symbol used to enrich every instrument with a benchmark index.
    benchmark_index_symbol: Optional[str] = None
    benchmark_from_folder: str = "index"
    weekly_rule: str = "W"


def _read_table(path: Path) -> pd.DataFrame:
    reader = _READERS.get(path.suffix.lower())
    if reader is None:
        raise ValueError(f"Unsupported file type: {path.name}")
    return reader(path)


def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def _first_match(cols: Iterable[str], aliases: Iterable[str]) -> Optional[str]:
    cols = set(cols)
    for a in aliases:
        if a in cols:
            return a
    return None


def _to_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise to a DatetimeIndexed OHLCV frame; keep recognised extras.

    Handles two common layouts:
      * clean single-header files (Date, Open, High, Low, Close, Volume, ...)
      * yfinance multi-row-header CSVs, where the first header cell is 'Price'
        and the next two rows hold the Ticker name and a blank 'Date' row. Those
        junk rows are dropped automatically because they don't parse as dates.
    """
    df = _norm_cols(df)

    # 1) locate the date column
    date_col = _first_match(df.columns, _DATE_ALIASES)
    if date_col is None and "price" in df.columns:
        # yfinance signature: the date column is labelled 'Price'
        date_col = "price"
    if date_col is None and len(df.columns):
        # last resort: use the first column if most of it parses as dates
        first = df.columns[0]
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed_ratio = pd.to_datetime(df[first], errors="coerce").notna().mean()
        if parsed_ratio > 0.5:
            date_col = first

    # 2) rename OHLCV columns to canonical names
    rename = {}
    for canon, aliases in _OHLCV_ALIASES.items():
        src = _first_match(df.columns, aliases)
        if src:
            rename[src] = canon
    df = df.rename(columns=rename)
    if date_col in rename:
        date_col = rename[date_col]

    # 3) set datetime index; rows whose date won't parse (Ticker/Date junk
    #    rows from yfinance) become NaT and are dropped
    if date_col and date_col in df.columns:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.dropna(subset=[date_col]).set_index(date_col).sort_index()
    df.index.name = "date"

    # 4) map recognised extra columns to canonical names (keep them on the frame)
    for canon, aliases in _EXTRA_ALIASES.items():
        src = _first_match(df.columns, aliases)
        if src and src != canon:
            df = df.rename(columns={src: canon})

    # 5) coerce price/volume columns to numbers safely (stray strings -> NaN)
    for c in ("open", "high", "low", "close", "volume"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "volume" not in df.columns:
        df["volume"] = 0.0

    core = [c for c in ("open", "high", "low", "close") if c in df.columns]
    if core:
        df = df.dropna(subset=core)        # drop ticker/junk rows (non-numeric)

    # 6) if the file had no usable date column (e.g. some commodity exports),
    #    synthesise a business-day index so downstream resample/labels work.
    if not isinstance(df.index, pd.DatetimeIndex):
        df = df.reset_index(drop=True)
        df.index = pd.date_range(end=pd.Timestamp.today().normalize(),
                                 periods=len(df), freq="B")
        df.index.name = "date"

    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def _extras_from_frame(df: pd.DataFrame) -> dict:
    """Pull asset-specific fields out of an OHLCV+extras frame."""
    extras: dict = {}
    for canon in _EXTRA_ALIASES:
        if canon in df.columns:
            series = pd.to_numeric(df[canon], errors="coerce").dropna()
            if not series.empty:
                extras[canon] = float(series.iloc[-1])     # latest scalar
                extras[f"{canon}_series"] = series          # full history
    return extras


class RawDataRepository:
    """Reads the raw_data tree and produces `AssetData` objects."""

    def __init__(self, config: LoaderConfig | None = None, **kwargs):
        self.cfg = config or LoaderConfig(**kwargs)
        self.root = Path(self.cfg.root)
        if not self.root.exists():
            raise FileNotFoundError(f"raw_data root not found: {self.root}")
        self._cache: Dict[str, Dict[str, pd.DataFrame]] = {}

    # ---- discovery ------------------------------------------------------- #
    def _folder_for(self, asset: Asset) -> Path:
        for folder, a in self.cfg.folder_map.items():
            if a == asset:
                return self.root / folder
        raise KeyError(f"No folder mapped to {asset}")

    def _index_folder(self, folder: Path) -> Dict[str, pd.DataFrame]:
        """Return {symbol: ohlcv_frame} for a folder.

        If the asset folder contains timeframe subfolders (daily/ hourly/
        weekly/ oi/ master/), only the daily OHLCV is used. Otherwise the folder
        is read directly. Handles one-file-per-symbol and combined files.
        """
        key = str(folder)
        if key in self._cache:
            return self._cache[key]

        # Prefer a 'daily' subfolder wherever it sits (e.g. fo/ohlcv/daily);
        # never mix timeframes. Fall back to the folder itself.
        daily_dir = next((d for d in folder.rglob("daily") if d.is_dir()), None)
        read_dir = daily_dir or folder
        frames: Dict[str, pd.DataFrame] = {}
        files = [p for p in sorted(read_dir.glob("*"))
                 if p.is_file() and p.suffix.lower() in _READERS]
        for p in files:
            raw = _norm_cols(_read_table(p))
            sym_col = _first_match(raw.columns, _SYMBOL_ALIASES)
            # A clean per-file symbol column (single value, e.g. 'COPPER') is a
            # naming hint, not a combined file. Treat as combined only when it
            # genuinely holds several different symbols.
            real_syms = (raw[sym_col].dropna().astype(str).str.strip()
                         .replace("", pd.NA).dropna().unique() if sym_col else [])
            if sym_col and len(real_syms) > 1:
                for sym, g in raw.groupby(sym_col):
                    if str(sym).strip():
                        frames[str(sym).upper()] = _to_ohlcv(g.drop(columns=[sym_col]))
            else:
                # prefer the symbol column value if it's clean, else the filename
                sym = (str(real_syms[0]) if len(real_syms) == 1 else p.stem).upper()
                frames[sym] = _to_ohlcv(raw)
        self._cache[key] = frames
        logger.info("Indexed %d symbols in %s", len(frames), read_dir)
        return frames

    def list_symbols(self, asset: Asset) -> List[str]:
        return sorted(self._index_folder(self._folder_for(asset)))

    # ---- loading --------------------------------------------------------- #
    def load(self, asset: Asset, symbol: str,
             extra_attrs: Optional[dict] = None) -> AssetData:
        frames = self._index_folder(self._folder_for(asset))
        symbol = symbol.upper()
        if symbol not in frames:
            raise KeyError(f"{symbol} not found under {asset.value}")
        daily = frames[symbol]
        extras = _extras_from_frame(daily)
        # Trim extras columns off the OHLCV frame so indicators stay clean.
        ohlcv = daily[[c for c in ("open", "high", "low", "close", "volume")
                       if c in daily.columns]].apply(pd.to_numeric, errors="coerce")
        ohlcv = ohlcv.dropna(subset=[c for c in ("open", "high", "low", "close")
                                     if c in ohlcv.columns])
        weekly = ohlcv.resample(self.cfg.weekly_rule).agg(
            {"open": "first", "high": "max", "low": "min",
             "close": "last", "volume": "sum"}).dropna()

        # Optional benchmark enrichment.
        if self.cfg.benchmark_index_symbol:
            try:
                bidx = self._index_folder(self.root / self.cfg.benchmark_from_folder)
                bsym = self.cfg.benchmark_index_symbol.upper()
                if bsym in bidx:
                    extras["benchmark_index"] = bidx[bsym][["close"]].astype(float)
                    extras.setdefault("vix", float(bidx[bsym].get("vix", pd.Series([0])).iloc[-1])
                                      if "vix" in bidx[bsym] else extras.get("vix"))
            except (FileNotFoundError, KeyError):
                pass

        if extra_attrs:
            extras.update(extra_attrs)

        return AssetData(asset=asset, symbol=symbol, daily=ohlcv,
                         weekly=weekly, extras=extras)

    def load_all(self, asset: Asset, limit: Optional[int] = None) -> Iterable[AssetData]:
        syms = self.list_symbols(asset)
        if limit:
            syms = syms[:limit]
        for s in syms:
            try:
                yield self.load(asset, s)
            except Exception as exc:  # skip bad files, keep going
                logger.warning("Skipping %s/%s: %s", asset.value, s, exc)

    def load_everything(self, limit_per_asset: Optional[int] = None
                        ) -> Dict[Asset, List[AssetData]]:
        out: Dict[Asset, List[AssetData]] = {}
        for asset in self.cfg.folder_map.values():
            try:
                out[asset] = list(self.load_all(asset, limit=limit_per_asset))
            except (FileNotFoundError, KeyError):
                out[asset] = []
        return out
