"""Full evaluation of BOTH the rule-based pipeline and the trained ML model.

It runs all 30 engines as-of each historical bar (no look-ahead), captures every
engine's score plus the Gatekeeper's verdict, attaches forward outcomes, and
reports:

  PART A  Per-engine signal   - single-feature AUC for each engine: which of the
                                30 engines actually predict the outcome.
  PART B  Rule-based pipeline  - accuracy / precision / win-rate of the
                                Gatekeeper's 'execute' calls vs just trading
                                everything (the honest "how good is my pipeline").
  PART C  ML model             - accuracy, balanced accuracy, precision, recall,
                                F1, ROC-AUC, confusion matrix, time-series CV AUC,
                                and per-asset AUC.

Usage:
    PYTHONPATH=. python examples/evaluate.py raw_data
    PYTHONPATH=. python examples/evaluate.py raw_data --label target --stride 10 --symbols 20
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

from swing_engine import Asset, Pipeline, UserProfile
from swing_engine.data import RawDataRepository, LoaderConfig
from swing_engine.data.labels import make_labels
from swing_engine.data.dataset import _slice_asset


def build_eval_frame(repo, assets, symbols_per_asset, stride, warmup,
                     stop_atr_mult, target_atr_mult):
    """Run the FULL 30-engine pipeline as-of each bar; capture scores + verdict."""
    user = UserProfile(user_id="eval", capital=5_000_000,
                       risk_per_trade_pct=1.0, max_portfolio_risk_pct=10.0,
                       experience_years=10, stop_loss_discipline=0.8,
                       permissions={a.value: True for a in Asset})
    pipe = Pipeline()  # all 30 engines
    rows = []
    for asset in assets:
        for ad in repo.load_all(asset, limit=symbols_per_asset):
            labels = make_labels(ad.daily, stop_atr_mult=stop_atr_mult,
                                 target_atr_mult=target_atr_mult)
            if labels.empty:
                continue
            valid = set(labels.index)
            for pos in range(warmup, len(ad.daily), max(1, stride)):
                date = ad.daily.index[pos]
                if date not in valid:
                    continue
                sliced = _slice_asset(ad, date)
                if len(sliced.daily) < warmup:
                    continue
                try:
                    res = pipe.run(sliced, user)
                except Exception:
                    continue
                row = {"symbol": ad.symbol, "asset": asset.value, "date": date}
                for eid, r in res.items():
                    row[f"e{eid:02d}_score"] = r.score
                gate = res.get(30)
                if gate:
                    row["gate_conf"] = gate.score
                    row["gate_action"] = gate.outputs.get("final_action")
                    row["gate_status"] = gate.outputs.get("final_trade_approval_status")
                lab = labels.loc[date]
                row["label_bin"] = float(lab["target_hit"] == 1)
                row["updays5"] = float(lab["fwd_ret_5"] > 0)
                rows.append(row)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default="raw_data")
    ap.add_argument("--label", default="label_bin", choices=["label_bin", "updays5"])
    ap.add_argument("--stride", type=int, default=10,
                    help="bar step (higher = faster, fewer rows)")
    ap.add_argument("--symbols", type=int, default=25,
                    help="max symbols per asset (keeps runtime sane)")
    ap.add_argument("--warmup", type=int, default=210)
    ap.add_argument("--cache", default="eval_cache.parquet")
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()

    if os.path.exists(args.cache) and not args.rebuild:
        print(f"Loading cached eval frame: {args.cache}")
        df = pd.read_parquet(args.cache)
    else:
        print("Running full 30-engine pipeline over history (slow; cached after)...")
        repo = RawDataRepository(LoaderConfig(root=args.root,
                                              benchmark_index_symbol="NIFTY50"))
        df = build_eval_frame(
            repo,
            assets=[Asset.STOCK, Asset.FNO, Asset.INDEX, Asset.FOREX, Asset.COMMODITY],
            symbols_per_asset=args.symbols, stride=args.stride, warmup=args.warmup,
            stop_atr_mult=1.5, target_atr_mult=3.0)
        if df.empty:
            print("No rows — check the loader/diagnostic.")
            return
        df.to_parquet(args.cache)
        print(f"Cached -> {args.cache}")

    y = df[args.label].astype(int)
    base = float(y.mean())
    print("\n" + "=" * 64)
    print(f"EVALUATION  |  rows={len(df)}  symbols={df['symbol'].nunique()}  "
          f"label='{args.label}'  positive-rate={base:.3f}")
    print("=" * 64)

    from sklearn.metrics import (roc_auc_score, accuracy_score,
                                 balanced_accuracy_score, precision_score,
                                 recall_score, f1_score, confusion_matrix)

    # ---- PART A: per-engine single-feature signal ----------------------- #
    print("\nPART A — per-engine predictive power (single-feature AUC)")
    print("  (0.50 = no signal; |AUC-0.50| = strength; 'inv' = inversely predictive)")
    eng_cols = sorted(c for c in df.columns if c.endswith("_score") and c != "gate_conf")
    scored = []
    for c in eng_cols:
        s = pd.to_numeric(df[c], errors="coerce").fillna(df[c].median())
        if s.nunique() < 2 or y.nunique() < 2:
            continue
        auc = roc_auc_score(y, s)
        scored.append((c, auc, abs(auc - 0.5)))
    for c, auc, strength in sorted(scored, key=lambda t: -t[2])[:12]:
        tag = "inv" if auc < 0.5 else "   "
        print(f"   {c:14s} AUC {auc:.3f}  {tag}  strength {strength:.3f}")

    # ---- PART B: rule-based pipeline accuracy --------------------------- #
    print("\nPART B — rule-based pipeline (Gatekeeper) accuracy")
    if "gate_action" in df.columns:
        exec_mask = df["gate_action"].astype(str).eq("execute")
        n_exec = int(exec_mask.sum())
        if n_exec:
            win_exec = float(y[exec_mask].mean())
            print(f"   Gatekeeper said EXECUTE on {n_exec}/{len(df)} bars "
                  f"({n_exec/len(df):.1%})")
            print(f"   win-rate of EXECUTE calls : {win_exec:.3f}")
            print(f"   win-rate if you traded all: {base:.3f}  (base)")
            print(f"   -> lift from the pipeline : {win_exec/max(base,1e-9):.2f}x")
        else:
            print("   Gatekeeper issued no EXECUTE calls in this sample.")
        # treat execute as the positive prediction
        pred = exec_mask.astype(int)
        print(f"   accuracy : {accuracy_score(y, pred):.3f}  "
              f"precision : {precision_score(y, pred, zero_division=0):.3f}  "
              f"recall : {recall_score(y, pred, zero_division=0):.3f}")
    if "gate_conf" in df.columns and df['gate_conf'].nunique() > 1:
        print(f"   Gatekeeper confidence AUC : "
              f"{roc_auc_score(y, df['gate_conf']):.3f}  "
              f"(does higher confidence => more winners?)")
        q75 = df["gate_conf"].quantile(0.75)
        hi = df["gate_conf"] >= q75
        if hi.sum() > 10:
            print(f"   top-quartile confidence win-rate : {float(y[hi].mean()):.3f} "
                  f"(vs base {base:.3f}, lift {y[hi].mean()/max(base,1e-9):.2f}x) "
                  f"— grade signals by confidence even without an EXECUTE verdict")

    # ---- PART C: trained ML model --------------------------------------- #
    print("\nPART C — trained ML model on engine features")
    feat_cols = [c for c in eng_cols if c != "e30_score"]   # exclude composite
    X = df[feat_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    order = df["date"].argsort()
    Xo, yo = X.iloc[order], y.iloc[order]

    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.model_selection import TimeSeriesSplit
    pw = (1 - base) / max(base, 1e-6)

    aucs = []
    tscv = TimeSeriesSplit(n_splits=5)
    for tr, te in tscv.split(Xo):
        if yo.iloc[te].nunique() < 2:
            continue
        m = HistGradientBoostingClassifier(max_iter=300, max_depth=4,
                                           learning_rate=0.05, class_weight="balanced",
                                           random_state=0)
        m.fit(Xo.iloc[tr], yo.iloc[tr])
        aucs.append(roc_auc_score(yo.iloc[te], m.predict_proba(Xo.iloc[te])[:, 1]))

    # final holdout (last 20%) for the full metric set
    cut = int(len(Xo) * 0.8)
    model = HistGradientBoostingClassifier(max_iter=300, max_depth=4,
                                           learning_rate=0.05, class_weight="balanced",
                                           random_state=0).fit(Xo.iloc[:cut], yo.iloc[:cut])
    p = model.predict_proba(Xo.iloc[cut:])[:, 1]
    yte = yo.iloc[cut:]
    pred = (p >= 0.5).astype(int)
    print(f"   time-series CV AUC : {np.mean(aucs):.3f} +/- {np.std(aucs):.3f}")
    if yte.nunique() > 1:
        print(f"   holdout ROC-AUC    : {roc_auc_score(yte, p):.3f}")
    print(f"   accuracy           : {accuracy_score(yte, pred):.3f}  "
          f"(baseline {max(base,1-base):.3f})")
    print(f"   balanced accuracy  : {balanced_accuracy_score(yte, pred):.3f}")
    print(f"   precision / recall : {precision_score(yte, pred, zero_division=0):.3f}"
          f" / {recall_score(yte, pred, zero_division=0):.3f}")
    print(f"   F1                 : {f1_score(yte, pred, zero_division=0):.3f}")
    cm = confusion_matrix(yte, pred)
    print(f"   confusion matrix   : [[TN {cm[0,0]} FP {cm[0,1]}] "
          f"[FN {cm[1,0]} TP {cm[1,1]}]]")

    # per-asset AUC
    print("   per-asset holdout AUC:")
    test_assets = df.iloc[order].iloc[cut:]["asset"].values
    for a in sorted(set(test_assets)):
        m2 = test_assets == a
        ya = yte.values[m2]
        if len(ya) > 20 and len(set(ya)) > 1:
            print(f"      {a:10s} AUC {roc_auc_score(ya, p[m2]):.3f}  (n={m2.sum()})")

    print("\n" + "=" * 64)
    print("READ-OUT: AUC is the headline metric (0.50=random). Pipeline lift>1 and")
    print("model AUC>0.55 mean a real, tradeable edge once risk sizing is applied.")
    print("=" * 64)


if __name__ == "__main__":
    main()
