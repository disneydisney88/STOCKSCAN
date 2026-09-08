"""Refresh the retained HK equity universe without deleting historical rows."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

from config import FULL_CSV
from stockscan.io_utils import lb_to_code5, write_csv
from stockscan.lb_client import LB


def _value(obj, *names):
    for name in names:
        value = getattr(obj, name, None)
        if value not in (None, ""):
            return value
    return ""


def refresh(path: Path = FULL_CSV, asof: date | None = None, lb=None) -> dict:
    """Merge Longbridge's live list into ``universe_full``.

    Existing rows absent from the live list are retained and marked
    ``delisted=1``. New rows are appended with ``listed_date`` when the API
    exposes it; no row is silently removed.
    """
    current = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    for col, default in (("listed_date", ""), ("delisted", "0")):
        if col not in current.columns:
            current[col] = default
    client = lb or LB()
    securities = client.security_list()
    live: dict[str, object] = {}
    for security in securities:
        symbol = str(_value(security, "symbol", "security"))
        if not symbol:
            continue
        live[lb_to_code5(symbol)] = security

    current["code5"] = current["code5"].astype(str).str.zfill(5)
    current_codes = set(current["code5"])
    current["delisted"] = (~current["code5"].isin(live)).astype(int).astype(str)
    additions = []
    for code5, security in sorted(live.items()):
        if code5 in current_codes:
            continue
        symbol = str(_value(security, "symbol"))
        listed = _value(security, "listed_date", "list_date", "listing_date")
        additions.append({
            "code5": code5,
            "symbol_lb": symbol,
            "name": str(_value(security, "name", "name_hk", "name_cn")),
            "board": str(_value(security, "board")),
            "is_reit": "0",
            "in_seed_20260831": "0",
            "listed_date": str(listed),
            "delisted": "0",
        })
    if additions:
        current = pd.concat([current, pd.DataFrame(additions)], ignore_index=True, sort=False)
    current = current.drop_duplicates("code5", keep="first").sort_values("code5")
    write_csv(current, path)
    result = {
        "asof": (asof or date.today()).isoformat(),
        "live": len(live),
        "existing": len(current_codes),
        "added": len(additions),
        "delisted_marked": int((current["delisted"] == "1").sum()),
        "path": str(path),
    }
    print(result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=FULL_CSV)
    args = parser.parse_args()
    refresh(args.path)
