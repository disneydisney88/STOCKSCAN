#!/usr/bin/env python
"""逐日對照 RTSS 純文字 alerts 與 STOCKSCAN intraday alerts。"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stockscan.io_utils import today_hkt, write_csv

RTSS_DIR = Path("data/rtss")
INTRADAY_DIR = Path("data/intraday")
REPORT_DIR = Path("data/reports")
OUT_COLUMNS = [
    "group", "code5", "name", "rtss_count", "stockscan_count",
    "rtss_types", "stockscan_types", "possible_reason",
]


def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype={"code5": str}, encoding="utf-8-sig")


def _normalise(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    out["code5"] = out["code5"].astype(str).str.extract(r"(\d{1,5})", expand=False).str.zfill(5)
    return out[out["code5"].notna()]


def _reasons(rtss: pd.DataFrame) -> str:
    reasons: list[str] = []
    if not rtss.empty and "mcap" in rtss:
        mcap = pd.to_numeric(rtss["mcap"], errors="coerce")
        if mcap.ge(3e8).any():
            reasons.append("mcap_over_3e8")
    if not rtss.empty and "turnover" in rtss:
        turnover = pd.to_numeric(rtss["turnover"], errors="coerce")
        if turnover.lt(5e5).any():
            reasons.append("turnover_below_500k")
    if not reasons:
        reasons.append("daemon_or_definition_difference")
    return ";".join(reasons)


def compare_day(day: date, rtss_path: Path | None = None, stockscan_path: Path | None = None,
                out_path: Path | None = None) -> Path:
    rtss = _normalise(_read(rtss_path or RTSS_DIR / f"rtss_alerts_{day:%Y%m%d}.csv"))
    ours = _normalise(_read(stockscan_path or INTRADAY_DIR / f"alerts_{day:%Y%m%d}.csv"))
    rtss_codes = set(rtss["code5"]) if not rtss.empty else set()
    ours_codes = set(ours["code5"]) if not ours.empty else set()
    rows: list[dict] = []
    for code in sorted(rtss_codes | ours_codes):
        r = rtss[rtss["code5"] == code]
        o = ours[ours["code5"] == code]
        if code in rtss_codes and code in ours_codes:
            group = "both"
        elif code in rtss_codes:
            group = "rtss_only"
        else:
            group = "stockscan_only"
        rows.append({
            "group": group,
            "code5": code,
            "name": (r["name"].iloc[0] if not r.empty and "name" in r else
                     o["name"].iloc[0] if not o.empty and "name" in o else ""),
            "rtss_count": len(r),
            "stockscan_count": len(o),
            "rtss_types": ";".join(sorted(r.get("msg_type", pd.Series(dtype=str)).dropna().astype(str).unique())),
            "stockscan_types": ";".join(sorted(o.get("alert_type", pd.Series(dtype=str)).dropna().astype(str).unique())),
            "possible_reason": _reasons(r) if group == "rtss_only" else "",
        })
    result = pd.DataFrame(rows, columns=OUT_COLUMNS)
    out_path = out_path or REPORT_DIR / f"rtss_daily_diff_{day:%Y%m%d}.csv"
    write_csv(result, out_path)
    counts = result["group"].value_counts().to_dict() if not result.empty else {}
    print(f"[rtss-compare] {day:%Y%m%d}: {counts} -> {out_path}")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD；預設 today_hkt()")
    args = ap.parse_args()
    day = date.fromisoformat(args.date) if args.date else today_hkt()
    compare_day(day)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
