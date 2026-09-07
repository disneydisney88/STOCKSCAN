"""日線快取層（P1）：data/cache/daily/{code5}.csv，一支檔一隻股。

設計（2026-09-08 深夜決定，原因記 HANDOVER §2）：
- Longbridge「歷史K線」端點有 100 隻標的／期硬配額（error 301607 requested:100/limit:100），
  大規模回填唔可能用佢。
- 「即市K線」端點（ctx.candlesticks，即 probe 入面嗰個）係獨立配額，收市後回傳最近 N 支
  已確認日 K（尾支＝最後交易日）。一次過拉 count=40 條窗，就夠計訊號 A 任何一日
  （ scan 日 + 前 10 交易日），仲夠做 08-10 起嘅 20 日回填。
- 快取以日期為 key merge，永不重複拉已有嘅日子。
"""
from __future__ import annotations

import threading
from datetime import date
from pathlib import Path

import pandas as pd

from config import CACHE_DIR
from stockscan.io_utils import HKT, lb_to_code5, log_error

_CACHE_COLUMNS = ["date", "open", "high", "low", "close", "volume", "turnover"]
_lock = threading.Lock()


def cache_path(code5: str) -> Path:
    return CACHE_DIR / "daily" / f"{code5}.csv"


def load(code5: str) -> pd.DataFrame | None:
    p = cache_path(code5)
    if not p.exists():
        return None
    try:
        df = pd.read_csv(p, dtype={"date": str})
        return df if len(df) else None
    except Exception as e:  # noqa: BLE001——快取檔壞咗就當冇，重新拉
        log_error("cache.load", f"{code5}: {e!r}")
        return None


def merge_save(code5: str, rows: list) -> pd.DataFrame:
    """SDK Candlestick rows → merge 入快取（以 date 為 key，後寫覆前寫）。

    ⚠ 官方文檔：所有 timestamp 係 UTC。日 K 嘅 timestamp 係 HKT 零晨，
    直接 .date() 會早一日（301607 慘案＋09-04 全空榜嘅根因）。必須先轉 HKT。"""
    new = pd.DataFrame([
        {
            "date": b.timestamp.astimezone(HKT).date().isoformat(),
            "open": float(b.open), "high": float(b.high),
            "low": float(b.low), "close": float(b.close),
            "volume": int(b.volume), "turnover": float(b.turnover),
        }
        for b in rows
    ])
    with _lock:
        old = load(code5)
        df = pd.concat([old, new], ignore_index=True) if old is not None else new
        df = (df.drop_duplicates(subset="date", keep="last")
                .sort_values("date").reset_index(drop=True))
        p = cache_path(code5)
        p.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(p, index=False)
    return df


def window_upto(df: pd.DataFrame, end: date, n: int) -> pd.DataFrame:
    """快取入面 end（含）之前最近 n 支。"""
    sub = df[df["date"] <= end.isoformat()]
    return sub.tail(n)


def fetch_window(lb, symbol: str, n: int = 40) -> list:
    """即市K線端點拉最近 n 支日 K（收市後＝已確認）。"""
    return lb.candles_today(symbol, n)
