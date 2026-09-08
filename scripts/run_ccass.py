"""Fetch CCASS data for one EOD panel day and update T+2 columns."""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_DIR, EOD_DIR
from stockscan.ccass import date_alignment, fetch_stock, health, save_stock
from stockscan.io_utils import log_error, write_csv


def run(day: str, limit: int | None = None, health_wait: int = 60) -> dict:
    panel_path = EOD_DIR / "radar_eod_panel_full.csv"
    panel = pd.read_csv(panel_path, dtype={"scan_date": str, "code5": str}, encoding="utf-8-sig")
    day_df = panel[panel["scan_date"].eq(day)].copy()
    codes = sorted(day_df["code5"].dropna().astype(str).str.zfill(5).unique())
    if limit:
        codes = codes[:limit]
    health()
    if health_wait:
        time.sleep(health_wait)
    success = 0
    for i, code in enumerate(codes, 1):
        try:
            alignment = date_alignment(day)
            payload = fetch_stock(code)
            save_stock(code, day, {"alignment": alignment, "stock": payload})
            success += 1
            print(f"[ccass] {i}/{len(codes)} {code} ok")
        except Exception as exc:  # noqa: BLE001
            log_error("ccass.fetch", f"{code} {day}: {type(exc).__name__}: {exc}")
            print(f"[ccass] {i}/{len(codes)} {code} failed ({type(exc).__name__})")
    # Read saved wrappers and align their numeric fields into the panel.
    values = {}
    for code in codes:
        path = DATA_DIR / "ccass" / code / f"{day}.json"
        if path.exists():
            import json
            obj = json.loads(path.read_text(encoding="utf-8"))
            values[code] = (obj.get("ccass_top5_pct_t2"), obj.get("ccass_top10_pct_t2"))
    panel["ccass_top5_pct_t2"] = panel["code5"].map(lambda c: values.get(str(c).zfill(5), (None, None))[0])
    panel["ccass_top10_pct_t2"] = panel["code5"].map(lambda c: values.get(str(c).zfill(5), (None, None))[1])
    write_csv(panel, panel_path)
    write_csv(panel, EOD_DIR / "radar_eod_panel.csv")
    return {"day": day, "requested": len(codes), "success": success, "failed": len(codes) - success}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD; defaults to latest panel date")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--health-wait", type=int, default=60)
    args = ap.parse_args()
    if args.date is None:
        p = pd.read_csv(EOD_DIR / "radar_eod_panel_full.csv", usecols=["scan_date"], dtype=str)
        args.date = p["scan_date"].max()
    print(run(args.date, args.limit, args.health_wait))
