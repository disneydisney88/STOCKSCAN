"""Broker shot history queries."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from config import DATA_DIR

BROKER_SHOTS_PATH = DATA_DIR / "broker_shots.csv"


def shots_around(code5: str, day: str | date, days: int = 5,
                 path: Path = BROKER_SHOTS_PATH) -> list[dict]:
    start = date.fromisoformat(day) if isinstance(day, str) else day
    df = pd.read_csv(path, dtype={"code5": str}, encoding="utf-8-sig") if path.exists() else pd.DataFrame()
    if df.empty:
        return []
    dates = pd.to_datetime(df["date"], errors="coerce").dt.date
    mask = (df["code5"].eq(str(code5).zfill(5))
            & dates.between(start - timedelta(days=days), start + timedelta(days=days)))
    return df.loc[mask].to_dict("records")
