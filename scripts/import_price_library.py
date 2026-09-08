"""Import the P0 price library into the per-stock daily cache.

The existing Longbridge cache is authoritative on overlapping dates. Library
rows are retained for earlier history and tagged ``source=lib``.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CACHE_DIR, DATA_DIR

RAW_DIR = DATA_DIR / "raw"
DAILY_DIR = CACHE_DIR / "daily"
REPORT_DIR = DATA_DIR / "reports"
CACHE_COLUMNS = ["date", "open", "high", "low", "close", "volume", "turnover", "source"]


def code5(value) -> str:
    m = re.search(r"(\d{1,5})", str(value))
    return m.group(1).zfill(5) if m else ""


def load_library(raw_dir: Path) -> pd.DataFrame:
    parts = []
    for path in (raw_dir / "hk_prices_master.csv", raw_dir / "hk_prices_delta_20260805_20260902.csv"):
        if not path.exists():
            raise FileNotFoundError(path)
        df = pd.read_csv(path, encoding="utf-8-sig", dtype={"code": str, "date": str})
        df["code5"] = df["code"].map(code5)
        df["source"] = "lib"
        parts.append(df)
    out = pd.concat(parts, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date.astype("string")
    out = out[out["code5"].ne("") & out["date"].notna()].copy()
    out = out[["code5", *[c for c in CACHE_COLUMNS if c != "source"], "source"]]
    return out.drop_duplicates(["code5", "date"], keep="last")


def load_lb_cache(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=CACHE_COLUMNS)
    df = pd.read_csv(path, dtype={"date": str})
    for col in CACHE_COLUMNS:
        if col not in df:
            df[col] = "lb" if col == "source" else pd.NA
    if "source" not in df:
        df["source"] = "lb"
    else:
        df["source"] = df["source"].fillna("lb")
    return df[CACHE_COLUMNS]


def import_library(raw_dir: Path = RAW_DIR, daily_dir: Path = DAILY_DIR,
                   report_dir: Path = REPORT_DIR, seed: int = 20260908) -> dict:
    lib = load_library(raw_dir)
    library_by_code = {
        code: group.drop(columns="code5")
        for code, group in lib.groupby("code5", sort=False)
    }
    daily_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    codes = set(lib["code5"])
    codes.update(p.stem for p in daily_dir.glob("*.csv"))
    overlap_rows = []
    for code in sorted(codes):
        old = load_lb_cache(daily_dir / f"{code}.csv")
        new = library_by_code.get(code, pd.DataFrame(columns=CACHE_COLUMNS[:-1]))
        if new.empty:
            continue
        complete = False
        if len(old) and not new.empty and "lib" in set(old["source"]):
            complete = (old["date"].min() <= new["date"].min()
                        and old["date"].max() >= new["date"].max())
        if not complete:
            combined = new.copy() if old.empty else pd.concat([new, old], ignore_index=True)
            combined = combined.drop_duplicates("date", keep="last").sort_values("date")
            combined.to_csv(daily_dir / f"{code}.csv", index=False)
        if len(old):
            old_dates = set(old["date"].dropna())
            for _, row in new[new["date"].isin(old_dates)].iterrows():
                lb_row = old[old["date"] == row["date"]].iloc[-1]
                overlap_rows.append({
                    "code5": code, "date": row["date"],
                    "library_close": row["close"], "lb_close": lb_row["close"],
                    "pct_diff": (float(row["close"]) / float(lb_row["close"]) - 1) * 100
                    if float(lb_row["close"]) else None,
                })
    overlap = pd.DataFrame(overlap_rows)
    rng = random.Random(seed)
    sample_codes = rng.sample(sorted(set(overlap["code5"])) if not overlap.empty else [],
                              min(20, overlap["code5"].nunique() if not overlap.empty else 0))
    sample = overlap[overlap["code5"].isin(sample_codes)].groupby("code5", group_keys=False).head(5)
    sample.to_csv(report_dir / "price_library_validation.csv", index=False, encoding="utf-8-sig")
    result = {
        "library_rows": int(len(lib)),
        "cache_files": len(codes),
        "sample_codes": len(sample_codes),
        "sample_rows": int(len(sample)),
        "sample_over_1pct": int((sample["pct_diff"].abs() > 1).sum()) if not sample.empty else 0,
        "library_min_date": str(lib["date"].min()),
        "library_max_date": str(lib["date"].max()),
    }
    (report_dir / "price_library_import_stats.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    ap.add_argument("--daily-dir", type=Path, default=DAILY_DIR)
    ap.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    args = ap.parse_args()
    print(json.dumps(import_library(args.raw_dir, args.daily_dir, args.report_dir), ensure_ascii=False, indent=2))
