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

PANEL = ROOT / "data" / "eod" / "radar_eod_panel_full.csv"


def _asof_features(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["scan_date"] = pd.to_datetime(d["scan_date"], errors="coerce").dt.date
    d = d.sort_values(["code5", "scan_date"]).reset_index(drop=True)
    d["code5"] = d["code5"].astype(str).str.zfill(5)
    # The tracking book does not carry the three numeric scan features.  Join
    # the as-of EOD panel on the same code/date; this is not the CCASS pipe.
    if PANEL.exists():
        panel = pd.read_csv(PANEL, usecols=["scan_date", "code5", "mcap_total",
                                             "ratio", "turnover_to_mcap",
                                             "has_broker_shot"])
        panel["scan_date"] = pd.to_datetime(panel["scan_date"], errors="coerce").dt.date
        panel["code5"] = panel["code5"].astype(str).str.zfill(5)
        panel = panel.drop_duplicates(["code5", "scan_date"])
        panel = panel.rename(columns={"has_broker_shot": "_panel_has_broker_shot"})
        d = d.drop(columns=[c for c in ("mcap", "ratio", "turnover_to_mcap") if c in d])
        d = d.merge(panel, on=["code5", "scan_date"], how="left")
        d = d.rename(columns={"mcap_total": "mcap"})
        if "has_broker_shot" in d:
            d["has_broker_shot"] = d["has_broker_shot"].fillna(
                d["_panel_has_broker_shot"])
            d = d.drop(columns="_panel_has_broker_shot")
        else:
            d = d.rename(columns={"_panel_has_broker_shot": "has_broker_shot"})
    # Absent upstream feeds remain explicitly null rather than being guessed.
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
        if name != "go" and f"prior_{name}_180d" not in d:
            d[f"prior_{name}_180d"] = 0
    if "prior_change_of_control" not in d:
        d["prior_change_of_control"] = 0
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
    d["led_to_go_180d"] = pd.to_numeric(
        d["fu_go"] if "fu_go" in d else pd.Series(0, index=d.index), errors="coerce"
    ).fillna(0).astype(int)
    # A missing t60 close is an unknown outcome, not a negative return.
    t60 = pd.to_numeric(d["ret_t60"] if "ret_t60" in d else pd.Series(index=d.index, dtype="float64"), errors="coerce")
    d["led_to_perform"] = (t60 > 0).where(t60.notna())
    d["led_to_rights_180d"] = pd.to_numeric(
        d["fu_rights"] if "fu_rights" in d else pd.Series(0, index=d.index), errors="coerce"
    ).fillna(0).astype(int)
    return d


def _groups(s: pd.Series, feature: str) -> pd.Series:
    if feature == "mcap":
        x = pd.to_numeric(s, errors="coerce")
        return pd.cut(x, [-np.inf, 1e8, 3e8, 1e9, np.inf],
                      labels=["<1億", "1-3億", "3-10億", ">=10億"]).astype(object).where(x.notna(), "unknown")
    if feature == "ratio":
        x = pd.to_numeric(s, errors="coerce")
        return pd.cut(x, [-np.inf, 20, 50, np.inf],
                      labels=["<20x", "20-50x", ">50x"]).astype(object).where(x.notna(), "unknown")
    if feature == "turnover_to_mcap":
        x = pd.to_numeric(s, errors="coerce")
        return pd.cut(x, [-np.inf, 1, 5, np.inf],
                      labels=["<1%", "1-5%", ">5%"]).astype(object).where(x.notna(), "unknown")
    if feature == "appearance_seq":
        x = pd.to_numeric(s, errors="coerce").fillna(0)
        return pd.cut(x, [-1, 1, 2, 4, np.inf], labels=["1", "2", "3-4", ">=5"]).astype(str)
    return s.fillna("unknown").astype(str)


def _predictors(d: pd.DataFrame, label: str) -> pd.DataFrame:
    valid = d[d[label].notna()].copy()
    baseline = float(valid[label].mean()) if len(valid) else 0.0
    rows = []
    for f in FEATURES:
        g = _groups(valid[f], f)
        for group, part in valid.assign(_group=g).groupby("_group", dropna=False):
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
    go_re = _predictors(d, "led_to_go_180d")
    go_perf = _predictors(d, "led_to_perform")
    # Keep the Streamlit-facing filename, with both outcomes in one report;
    # also publish separate files for downstream review and handover.
    go_re.to_csv(REPORTS / "go_predictors_led_to_go.csv", index=False, encoding="utf-8-sig")
    go_perf.to_csv(REPORTS / "go_predictors_led_to_perform.csv", index=False, encoding="utf-8-sig")
    pd.concat([go_re, go_perf], ignore_index=True).to_csv(go_pred, index=False, encoding="utf-8-sig")
    _predictors(d, "led_to_rights_180d").to_csv(rights_pred, index=False, encoding="utf-8-sig")
    print(f"[go] rows={len(d)} baseline_go={d.led_to_go_180d.mean():.4f} "
          f"baseline_perform={d.led_to_perform.mean():.4f} "
          f"known_perform={d.led_to_perform.notna().sum()} "
          f"baseline_rights={d.led_to_rights_180d.mean():.4f}")
    return go_path, go_pred, rights_pred


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--input", type=Path, default=REPORTS / "tracking_each.csv")
    args = ap.parse_args(); build(args.input)
