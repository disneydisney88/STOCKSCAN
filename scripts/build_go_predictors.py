"""Build the as-of GO/rights feature and predictor reports.

This is deliberately a local, deterministic report builder.  It never looks
past the listing date when constructing a feature; forward outcomes already
materialised in tracking_each.csv are used only as labels.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "data" / "reports"

FEATURES = [
    "mcap", "turnover_to_mcap", "ratio", "prior_go_365d",
    "prior_change_of_control", "prior_placing_180d", "prior_rights_180d",
    "prior_consolidation_180d", "has_broker_shot", "appearance_seq",
    "recurrence", "board",
]


def _asof_features(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["scan_date"] = pd.to_datetime(d["scan_date"], errors="coerce").dt.date
    d = d.sort_values(["code5", "scan_date"]).reset_index(drop=True)
    d["code5"] = d["code5"].astype(str).str.zfill(5)
    # Only fields available in the tracking book are used; absent upstream
    # feeds remain explicitly null rather than being guessed.
    for c in ("mcap", "turnover_to_mcap", "ratio", "board"):
        if c not in d:
            d[c] = np.nan
    if "has_broker_shot" not in d:
        d["has_broker_shot"] = 0
    d["has_broker_shot"] = pd.to_numeric(d["has_broker_shot"], errors="coerce").fillna(0).astype(int)
    d["appearance_seq"] = pd.to_numeric(d["appearance_seq"], errors="coerce")
    d["recurrence"] = (d["appearance_seq"].fillna(1) > 1).astype(int)
    # Build historical flags from completed prior tracking rows only.  An
    # action is prior when its listing date + first_action_days is <= now.
    for name, action in (("go", "GO"), ("rights", "RIGHTS"),
                         ("placing", "PLACING"), ("consolidation", "CONSOLIDATION")):
        d[f"prior_{name}_365d"] = 0 if name == "go" else d.get(f"prior_{name}_180d", 0)
    for i, row in d.iterrows():
        prior = d[(d.code5 == row.code5) & (d.scan_date < row.scan_date)]
        if prior.empty:
            continue
        delta = (pd.Timestamp(row.scan_date) - pd.to_datetime(prior.scan_date)).dt.days
        action_days = pd.to_numeric(prior.first_action_days, errors="coerce").fillna(99999).clip(-1, 3650)
        action_date = pd.to_datetime(prior.scan_date) + pd.to_timedelta(action_days, unit="D")
        eligible = prior[action_date.dt.date <= row.scan_date]
        d.at[i, "prior_go_365d"] = int(((eligible.first_action_type == "GO") & (delta.loc[eligible.index] <= 365)).any())
        for nm, typ in (("placing", "PLACING"), ("rights", "RIGHTS"), ("consolidation", "CONSOLIDATION")):
            d.at[i, f"prior_{nm}_180d"] = int(((eligible.first_action_type == typ) & (delta.loc[eligible.index] <= 180)).any())
        d.at[i, "prior_change_of_control"] = int((eligible.first_action_type.astype(str).str.contains("CONTROL", case=False)).any())
    d["feature_cutoff"] = d["scan_date"].astype(str)
    d["led_to_go_180d"] = pd.to_numeric(d.get("fu_go", 0), errors="coerce").fillna(0).astype(int)
    d["led_to_rights_180d"] = pd.to_numeric(d.get("fu_rights", 0), errors="coerce").fillna(0).astype(int)
    return d


def _groups(s: pd.Series, feature: str) -> pd.Series:
    if feature in {"mcap", "turnover_to_mcap", "ratio"}:
        x = pd.to_numeric(s, errors="coerce")
        return pd.cut(x, [-np.inf, 0, 1, 5, 10, 50, np.inf], labels=["<=0", "0-1", "1-5", "5-10", "10-50", ">=50"]).astype(object).where(x.notna(), "unknown")
    if feature == "appearance_seq":
        x = pd.to_numeric(s, errors="coerce").fillna(0)
        return pd.cut(x, [-1, 1, 2, 4, np.inf], labels=["1", "2", "3-4", ">=5"]).astype(str)
    return s.fillna("unknown").astype(str)


def _predictors(d: pd.DataFrame, label: str) -> pd.DataFrame:
    baseline = float(d[label].mean()) if len(d) else 0.0
    rows = []
    for f in FEATURES:
        g = _groups(d[f], f)
        for group, part in d.assign(_group=g).groupby("_group", dropna=False):
            n = len(part); rate = float(part[label].mean()) if n else 0.0
            rows.append({"feature": f, "group": str(group), "n": n,
                         "outcome": label, "go_rate": round(rate, 6),
                         "baseline": round(baseline, 6),
                         "lift": round(rate / baseline, 6) if baseline else None,
                         "sample_note": "insufficient_sample" if n < 20 else ""})
    return pd.DataFrame(rows)


def build(input_path: Path = REPORTS / "tracking_each.csv") -> tuple[Path, Path, Path]:
    raw = pd.read_csv(input_path)
    d = _asof_features(raw)
    go_path = REPORTS / "go_features.csv"; rights_features = REPORTS / "rights_features.csv"
    d.to_csv(go_path, index=False, encoding="utf-8-sig")
    d.to_csv(rights_features, index=False, encoding="utf-8-sig")
    go_pred = REPORTS / "go_predictors.csv"; rights_pred = REPORTS / "rights_predictors.csv"
    _predictors(d, "led_to_go_180d").to_csv(go_pred, index=False, encoding="utf-8-sig")
    _predictors(d, "led_to_rights_180d").to_csv(rights_pred, index=False, encoding="utf-8-sig")
    print(f"[go] rows={len(d)} baseline_go={d.led_to_go_180d.mean():.4f} baseline_rights={d.led_to_rights_180d.mean():.4f}")
    return go_path, go_pred, rights_pred


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--input", type=Path, default=REPORTS / "tracking_each.csv")
    args = ap.parse_args(); build(args.input)
