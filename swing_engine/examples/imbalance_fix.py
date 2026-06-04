"""Fix the class-imbalance / misleading-accuracy problem, end to end.

The trouble: the default label (target hit before stop, ~26% positive) is
imbalanced, so raw accuracy is meaningless and a 0.5 decision threshold is wrong.

This script fixes it three ways and shows the difference:
  1. LABEL BALANCE   - offers balanced labels (~50% positive) so accuracy means
                       something again, and prints every candidate's positive rate.
  2. CLASS WEIGHTING - trains with class_weight='balanced'.
  3. THRESHOLD TUNING- picks the decision threshold on a validation split
                       (maximising balanced accuracy AND realised return), instead
                       of blindly using 0.5.
Then it reports the full honest metric suite at 0.5 vs the tuned threshold.

Usage:
    PYTHONPATH=. python examples/imbalance_fix.py raw_data
    PYTHONPATH=. python examples/imbalance_fix.py raw_data --label dir5
    PYTHONPATH=. python examples/imbalance_fix.py raw_data --label balanced --rebuild
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

from swing_engine import Asset
from swing_engine.data import RawDataRepository, LoaderConfig, build_dataset

LEAK_PREFIXES = ("fwd_ret_", "mfe_", "mae_")
LEAK_EXACT = {"stop_hit", "target_hit", "holding_outcome", "days_to_exit",
              "label_bin", "asset"}


def candidate_labels(ds: pd.DataFrame) -> dict:
    """Return several label options; 'balanced' is forced to ~50% positive."""
    return {
        "barrier2to1": ds["label_bin"].astype(float),            # original, imbalanced
        "dir5": (ds["fwd_ret_5"] > 0).astype(float),             # ~balanced
        "dir10": (ds["fwd_ret_10"] > 0).astype(float),           # ~balanced
        "balanced": (ds["fwd_ret_10"] > ds["fwd_ret_10"].median()).astype(float),  # exactly 50%
    }


def features(ds):
    return [c for c in ds.columns
            if not c.startswith(LEAK_PREFIXES) and c not in LEAK_EXACT]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default="raw_data")
    ap.add_argument("--label", default="dir5",
                    choices=["barrier2to1", "dir5", "dir10", "balanced"])
    ap.add_argument("--stride", type=int, default=5)
    ap.add_argument("--symbols", type=int, default=60)
    ap.add_argument("--warmup", type=int, default=210)
    ap.add_argument("--cache", default="train_cache.parquet")
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()

    # ---- data ----------------------------------------------------------- #
    if os.path.exists(args.cache) and not args.rebuild:
        print(f"Loading cached dataset: {args.cache}")
        ds = pd.read_parquet(args.cache)
    else:
        print("Building dataset (cached afterwards)...")
        repo = RawDataRepository(LoaderConfig(root=args.root,
                                              benchmark_index_symbol="NIFTY50"))
        ds = build_dataset(repo,
                           assets=[Asset.STOCK, Asset.FNO, Asset.INDEX,
                                   Asset.FOREX, Asset.COMMODITY],
                           symbols_per_asset=args.symbols, stride=args.stride,
                           warmup=args.warmup, horizons=(3, 5, 10, 15),
                           stop_atr_mult=1.5, target_atr_mult=3.0)
        if ds.empty:
            print("No rows built — run diagnose.py."); return
        ds.to_parquet(args.cache)
        print(f"Cached -> {args.cache}")

    # ---- 1) show the imbalance across candidate labels ------------------ #
    cands = candidate_labels(ds)
    print("\n[1] LABEL BALANCE — positive rate of each candidate:")
    for name, y in cands.items():
        print(f"    {name:12s} positive-rate {float(y.mean()):.3f}  "
              f"(naive-accuracy floor {max(y.mean(),1-y.mean()):.3f})")
    print(f"    -> using '{args.label}'. Balanced labels make accuracy meaningful again.")

    y = cands[args.label]
    cols = features(ds)
    X = ds[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    fwd = pd.to_numeric(ds["fwd_ret_10"], errors="coerce").fillna(0.0)  # for EV tuning

    # time-ordered split: 60% train / 20% val (tune threshold) / 20% test
    order = ds.index.get_level_values("date").argsort()
    X, y, fwd = X.iloc[order], y.iloc[order], fwd.iloc[order]
    n = len(X); a, b = int(n * 0.6), int(n * 0.8)
    Xtr, ytr = X.iloc[:a], y.iloc[:a]
    Xval, yval, fval = X.iloc[a:b], y.iloc[a:b], fwd.iloc[a:b]
    Xte, yte, fte = X.iloc[b:], y.iloc[b:], fwd.iloc[b:]

    # ---- 2) train with class weighting ---------------------------------- #
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import (roc_auc_score, average_precision_score,
                                 balanced_accuracy_score, accuracy_score,
                                 precision_score, recall_score, f1_score,
                                 confusion_matrix)
    model = HistGradientBoostingClassifier(max_iter=400, max_depth=4,
                                           learning_rate=0.05, l2_regularization=1.0,
                                           class_weight="balanced", random_state=0)
    model.fit(Xtr, ytr)
    pval = model.predict_proba(Xval)[:, 1]
    pte = model.predict_proba(Xte)[:, 1]

    # ---- 3) tune the decision threshold on validation ------------------- #
    grid = np.linspace(0.30, 0.80, 51)
    best_bal, thr_bal = -1, 0.5
    best_ev, thr_ev, ev_trades = -1e9, 0.5, 0
    for t in grid:
        pred = (pval >= t).astype(int)
        bal = balanced_accuracy_score(yval, pred)
        if bal > best_bal:
            best_bal, thr_bal = bal, t
        sel = pval >= t                       # bars we'd trade
        if sel.sum() >= max(20, 0.05 * len(pval)):
            ev = fval[sel].mean()             # realised mean fwd return of trades taken
            if ev > best_ev:
                best_ev, thr_ev, ev_trades = ev, t, int(sel.sum())
    print(f"\n[2] TRAINING with class_weight='balanced'.")
    print(f"[3] THRESHOLD TUNING on validation:")
    print(f"    best balanced-accuracy threshold : {thr_bal:.2f}")
    print(f"    best expected-return threshold   : {thr_ev:.2f} "
          f"(mean fwd-10 {best_ev:+.2f}% on {ev_trades} trades)")

    # ---- report: default 0.5 vs tuned ----------------------------------- #
    def report(tag, thr):
        pred = (pte >= thr).astype(int)
        base = max(float(yte.mean()), 1 - float(yte.mean()))
        print(f"\n   --- {tag} (threshold {thr:.2f}) ---")
        print(f"   accuracy          : {accuracy_score(yte,pred):.3f}  (naive floor {base:.3f})")
        print(f"   balanced accuracy : {balanced_accuracy_score(yte,pred):.3f}  <-- the honest one")
        print(f"   precision / recall: {precision_score(yte,pred,zero_division=0):.3f}"
              f" / {recall_score(yte,pred,zero_division=0):.3f}")
        print(f"   F1                : {f1_score(yte,pred,zero_division=0):.3f}")
        cm = confusion_matrix(yte, pred)
        print(f"   confusion matrix  : [[TN {cm[0,0]} FP {cm[0,1]}] [FN {cm[1,0]} TP {cm[1,1]}]]")
        sel = pte >= thr
        if sel.sum():
            print(f"   trades taken      : {int(sel.sum())}  | win-rate {float(yte[sel].mean()):.3f}"
                  f"  | mean fwd-10 {float(fte[sel].mean()):+.2f}%")

    print("\n[RESULTS on untouched test set]")
    print(f"   ROC-AUC           : {roc_auc_score(yte, pte):.3f}   (threshold-independent)")
    print(f"   PR-AUC            : {average_precision_score(yte, pte):.3f}   (baseline {float(yte.mean()):.3f})")
    report("DEFAULT 0.5 (the misleading one)", 0.50)
    report("TUNED for balanced accuracy", thr_bal)
    report("TUNED for return (trade only high-confidence)", thr_ev)

    print("\nTAKEAWAY:")
    print("  * On a balanced label, accuracy is meaningful again (floor ~0.50).")
    print("  * Use balanced-accuracy / AUC as the headline, never raw accuracy.")
    print("  * The return-tuned threshold trades fewer bars but at a higher win-rate")
    print("    and positive mean forward return — that is the real objective.")


if __name__ == "__main__":
    main()
