"""Measure forward corporate-event rates for EOD hits and a small baseline."""
from __future__ import annotations

import argparse
import random
import re
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_DIR
from stockscan.io_utils import write_csv

EVENT_TYPES = ("GO", "CONSOLIDATION", "PLACING", "RIGHTS")
WINDOWS = (60, 120, 180)


def code5(value) -> str:
    match = re.search(r"(\d{1,5})", str(value))
    return match.group(1).zfill(5) if match else ""


def load_events(db_path: Path) -> list[dict]:
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute(
            "SELECT event_type, code5, announce_date FROM events "
            "WHERE event_type IN ('GO','CONSOLIDATION','PLACING','RIGHTS') "
            "AND announce_date IS NOT NULL")]


def event_flags(events: list[dict], code: str, start: date) -> dict:
    out = {}
    for window in WINDOWS:
        end = start + timedelta(days=window)
        for typ in EVENT_TYPES:
            out[f"{typ.lower()}_{window}"] = int(any(
                e["code5"] == code and e["event_type"] == typ
                and start.isoformat() <= e["announce_date"] <= end.isoformat()
                for e in events))
    return out


def build_candidate_index(cache_dir: Path, universe: pd.DataFrame) -> dict[str, list[str]]:
    shares = dict(zip(universe["code5"], pd.to_numeric(universe["total_shares"], errors="coerce")))
    index: dict[str, list[str]] = {}
    for path in cache_dir.glob("*.csv"):
        code = path.stem
        try:
            d = pd.read_csv(path, dtype={"date": str})
            d["turnover"] = pd.to_numeric(d["turnover"], errors="coerce")
            d["close"] = pd.to_numeric(d["close"], errors="coerce")
            ts = shares.get(code)
            if pd.isna(ts) or ts <= 0:
                continue
            for _, row in d[(d["turnover"] >= 1e6) & (d["close"] * ts < 1e9)].iterrows():
                index.setdefault(row["date"], []).append(code)
        except (OSError, ValueError, KeyError):
            continue
    return index


def baseline_for_day(day: date, panel_codes: set[str], candidate_index: dict[str, list[str]],
                     rng: random.Random) -> list[str]:
    candidates = [code for code in candidate_index.get(day.isoformat(), []) if code not in panel_codes]
    return rng.sample(candidates, min(10, len(candidates)))


def build(panel_path: Path = DATA_DIR / "eod" / "radar_eod_panel_full.csv",
          db_path: Path = DATA_DIR / "events.db", seed: int = 20260908) -> pd.DataFrame:
    panel = pd.read_csv(panel_path, dtype={"scan_date": str, "code5": str})
    universe = pd.read_csv(DATA_DIR / "universe.csv", dtype={"code5": str})
    events = load_events(db_path)
    candidate_index = build_candidate_index(DATA_DIR / "cache" / "daily", universe)
    rng = random.Random(seed)
    rows = []
    for day_text, day_df in panel.groupby("scan_date", sort=True):
        day = date.fromisoformat(day_text)
        signal_codes = set(day_df["code5"].astype(str).str.zfill(5))
        observations = [("signal", c) for c in sorted(signal_codes)]
        observations += [("baseline", c) for c in baseline_for_day(
            day, signal_codes, candidate_index, rng)]
        for group, code in observations:
            rows.append({"group": group, "code5": code, "scan_date": day_text,
                         **event_flags(events, code, day)})
    return pd.DataFrame(rows)


def summarize(observations: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for group, df in observations.groupby("group"):
        for window in WINDOWS:
            for typ in EVENT_TYPES:
                col = f"{typ.lower()}_{window}"
                rows.append({"group": group, "window_days": window, "event_type": typ,
                             "observations": len(df), "events": int(df[col].sum()),
                             "rate": round(float(df[col].mean()), 6) if len(df) else None})
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", type=Path, default=DATA_DIR / "eod" / "radar_eod_panel_full.csv")
    ap.add_argument("--db", type=Path, default=DATA_DIR / "events.db")
    ap.add_argument("--out-dir", type=Path, default=DATA_DIR / "reports")
    args = ap.parse_args()
    observations = build(args.panel, args.db)
    summary = summarize(observations)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    asof = pd.to_datetime(observations["scan_date"]).max().strftime("%Y%m%d") if not observations.empty else date.today().strftime("%Y%m%d")
    write_csv(observations, args.out_dir / f"go_timing_{asof}.csv")
    write_csv(summary, args.out_dir / "go_timing_summary.csv")
    print(f"[go_timing] observations={len(observations)} summary_rows={len(summary)} asof={asof}")
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
