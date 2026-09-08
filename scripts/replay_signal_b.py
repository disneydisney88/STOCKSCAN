"""Replay RTSS small-cap-surge alerts against the local daily cache."""
from __future__ import annotations

import argparse
import math
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_DIR
from stockscan.io_utils import write_csv


def code5(value) -> str:
    match = re.search(r"(\d{1,5})", str(value))
    return match.group(1).zfill(5) if match else ""


def forward_return(closes: pd.Series, idx: int, n: int) -> float | None:
    target = idx + n
    if idx < 0 or target >= len(closes) or pd.isna(closes.iloc[idx]) or pd.isna(closes.iloc[target]):
        return None
    return round((float(closes.iloc[target]) / float(closes.iloc[idx]) - 1) * 100, 4)


def build(source: Path = DATA_DIR / "raw" / "RTSS_Detailed_Final.xlsx",
          cache_dir: Path = DATA_DIR / "cache" / "daily") -> pd.DataFrame:
    alerts = pd.read_excel(source, sheet_name="Parsed_Alerts")
    alerts = alerts[alerts["category"].eq("small_cap_surge")].copy()
    alerts["code5"] = alerts["ticker"].map(code5)
    alerts["date"] = pd.to_datetime(alerts["date_hk"], errors="coerce").dt.date.astype("string")
    alerts = alerts[alerts["code5"].ne("") & alerts["date"].notna()].copy()
    cache = {}
    rows = []
    for _, alert in alerts.iterrows():
        code, day = alert["code5"], alert["date"]
        if code not in cache:
            path = cache_dir / f"{code}.csv"
            cache[code] = pd.read_csv(path, dtype={"date": str}) if path.exists() else pd.DataFrame()
        bars = cache[code]
        if not bars.empty and "date" in bars.columns:
            bars = bars.sort_values("date").reset_index(drop=True)
        else:
            bars = pd.DataFrame()
        idxs = bars.index[bars["date"].eq(day)].tolist() if not bars.empty else []
        row = {"code5": code, "date": day, "source_change_pct": alert.get("change_pct")}
        if not idxs:
            row.update({"high": None, "prev_close": None, "max_pct": None, "n_max_est": None,
                        "t5_return_pct": None, "t10_return_pct": None, "t20_return_pct": None})
        else:
            idx = idxs[-1]
            high = float(bars.iloc[idx]["high"])
            prev = float(bars.iloc[idx - 1]["close"]) if idx > 0 else None
            max_pct = (high / prev - 1) * 100 if prev and prev > 0 else None
            row.update({"high": high, "prev_close": prev,
                        "max_pct": round(max_pct, 4) if max_pct is not None else None,
                        "n_max_est": math.floor(max_pct / 20) if max_pct is not None and max_pct > 0 else 0,
                        "t5_return_pct": forward_return(bars["close"], idx, 5),
                        "t10_return_pct": forward_return(bars["close"], idx, 10),
                        "t20_return_pct": forward_return(bars["close"], idx, 20)})
        rows.append(row)
    return pd.DataFrame(rows)


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for n, group in df.groupby("n_max_est", dropna=False):
        row = {"n_max_est": n, "alerts": len(group)}
        for horizon in (5, 10, 20):
            vals = pd.to_numeric(group[f"t{horizon}_return_pct"], errors="coerce").dropna()
            row[f"t{horizon}_median_return_pct"] = round(float(vals.median()), 4) if len(vals) else None
            row[f"t{horizon}_win_rate"] = round(float((vals > 0).mean()), 4) if len(vals) else None
            row[f"t{horizon}_n"] = len(vals)
        rows.append(row)
    return pd.DataFrame(rows).sort_values("n_max_est")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, default=DATA_DIR / "raw" / "RTSS_Detailed_Final.xlsx")
    ap.add_argument("--cache-dir", type=Path, default=DATA_DIR / "cache" / "daily")
    ap.add_argument("--out-dir", type=Path, default=DATA_DIR / "reports")
    args = ap.parse_args()
    df = build(args.source, args.cache_dir)
    summary = summarize(df)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(df, args.out_dir / "n_count_forward.csv")
    write_csv(summary, args.out_dir / "n_count_forward_summary.csv")
    print(f"[replay_b] alerts={len(df)} matched_cache={df['high'].notna().sum()} summary_rows={len(summary)}")
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
