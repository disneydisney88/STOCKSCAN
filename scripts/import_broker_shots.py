"""Normalize the available broker-shot workbooks into data/broker_shots.csv."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_DIR
from stockscan.io_utils import write_csv

RAW_DIR = DATA_DIR / "raw"
OUT_PATH = DATA_DIR / "broker_shots.csv"
COLS = ["date", "code5", "broker_id", "broker_name", "shares_change", "pct_change", "direction"]


def code5(value) -> str:
    match = re.search(r"(\d{1,5})", str(value))
    return match.group(1).zfill(5) if match else ""


def number(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group()) if match else None


def broker_parts(value) -> list[tuple[str, float | None]]:
    if value is None or pd.isna(value):
        return []
    out = []
    for part in re.split(r"\n|；|;", str(value)):
        part = part.strip()
        if not part or part in {"-", "—"}:
            continue
        parts = re.split(r"\s*[:：]\s*", part, maxsplit=1)
        name = parts[0]
        change = parts[1] if len(parts) > 1 else None
        if change is None:
            name, change = part, None
        name = name.strip()
        if name:
            out.append((name, number(change)))
    return out


def broker_id(name: str) -> str:
    return hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def parse_workbook(path: Path) -> list[dict]:
    raw = pd.read_excel(path, header=None, dtype=object)
    header = next((i for i, row in raw.iterrows() if "編號" in row.astype(str).tolist()), None)
    if header is None:
        return []
    cols = raw.iloc[header].tolist()
    rows = []
    current = {"code5": "", "name": None, "date": None}
    for _, row in raw.iloc[header + 2:].iterrows():
        code = code5(row.iloc[0])
        if code:
            current = {"code5": code, "name": row.iloc[1], "date": row.iloc[8]}
        if not current["code5"]:
            continue
        shot_date = pd.to_datetime(current["date"], errors="coerce")
        if pd.isna(shot_date):
            continue
        for name, pct in broker_parts(row.iloc[9]):
            sign = 1 if pct is None or pct > 0 else -1 if pct < 0 else 0
            rows.append({
                "date": shot_date.date().isoformat(), "code5": current["code5"],
                "broker_id": broker_id(name), "broker_name": name,
                "shares_change": None, "pct_change": pct,
                "direction": "in" if sign > 0 else "out" if sign < 0 else "flat",
            })
    return rows


def add_panel_flag(panel_path: Path) -> int:
    if not panel_path.exists() or not OUT_PATH.exists():
        return 0
    panel = pd.read_csv(panel_path, dtype={"scan_date": str, "code5": str}, encoding="utf-8-sig")
    shots = pd.read_csv(OUT_PATH, dtype={"code5": str}, encoding="utf-8-sig")
    shots["date"] = pd.to_datetime(shots["date"], errors="coerce")
    panel["_date"] = pd.to_datetime(panel["scan_date"], errors="coerce")
    keys = shots[["code5", "date"]].drop_duplicates()
    panel["has_broker_shot"] = 0
    for code, group in keys.groupby("code5"):
        idx = panel.index[panel["code5"].eq(code)]
        if len(idx):
            dates = group["date"].dropna().tolist()
            panel.loc[idx, "has_broker_shot"] = panel.loc[idx, "_date"].map(
                lambda d: int(any(abs((d - x).days) <= 5 for x in dates)))
    panel.drop(columns="_date", inplace=True)
    panel.to_csv(panel_path, index=False, encoding="utf-8-sig")
    return int(panel["has_broker_shot"].sum())


def build(raw_dir: Path = RAW_DIR, out_path: Path = OUT_PATH) -> dict:
    files = sorted(raw_dir.glob("券商射倉*.xlsx"))
    rows = [row for path in files for row in parse_workbook(path)]
    df = pd.DataFrame(rows, columns=COLS).drop_duplicates()
    df = df.sort_values(["date", "code5", "broker_name"]).reset_index(drop=True)
    write_csv(df, out_path)
    flagged = add_panel_flag(DATA_DIR / "eod" / "radar_eod_panel_full.csv")
    add_panel_flag(DATA_DIR / "eod" / "radar_eod_panel.csv")
    result = {"files": len(files), "rows": len(df), "date_min": df["date"].min() if len(df) else None,
              "date_max": df["date"].max() if len(df) else None, "panel_has_broker_shot": flagged}
    (DATA_DIR / "reports").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "reports" / "broker_import_stats.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    args = ap.parse_args()
    print(json.dumps(build(args.raw_dir, args.out), ensure_ascii=False, indent=2))
