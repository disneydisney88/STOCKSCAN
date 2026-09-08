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
import time
from datetime import date
from pathlib import Path

import pandas as pd

from config import CACHE_DIR
from stockscan.io_utils import HKT, lb_to_code5, log_error

_CACHE_COLUMNS = ["date", "open", "high", "low", "close", "volume", "turnover"]
_lock = threading.Lock()
_MEMO: dict[str, pd.DataFrame] = {}  # code5 → df（Drive FS 讀細檔慢，每 process 只讀一次）


def cache_path(code5: str) -> Path:
    return CACHE_DIR / "daily" / f"{code5}.csv"


class CacheReadError(RuntimeError):
    """快取檔存在但讀唔到（Drive FS 抽風／檔案損壞）。

    P4 教訓（09-08 14:07 零 VOLUME 事件）：以前讀失敗靜靜回 None，
    呼叫方當「冇數據」——VOLUME 全數無聲跳過。而家改為重試之後上拋，
    由呼叫方計數並大聲警告。"""


def load(code5: str) -> pd.DataFrame | None:
    """讀快取。檔案唔存在 → None（正常）；存在但讀唔到 → 重試 3 次後 raise CacheReadError。"""
    if code5 in _MEMO:
        return _MEMO[code5]
    p = cache_path(code5)
    if not p.exists():
        return None
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            df = pd.read_csv(p, dtype={"date": str})
            df = df if len(df) else None
            if df is not None:
                _MEMO[code5] = df
            return df
        except OSError as e:
            # Drive FS 瞬時故障——等一等重試（唔同於檔案損壞）
            last_err = e
            time.sleep(0.4 * (attempt + 1))
        except Exception as e:  # noqa: BLE001——真·檔案損壞，即場記低
            log_error("cache.load", f"{code5}: {e!r}")
            raise CacheReadError(f"{code5}: {e!r}") from e
    raise CacheReadError(f"{code5}: 讀取重試 3 次都失敗：{last_err!r}")


def last_bar_date(code5: str) -> date | None:
    """快取尾支日 K 嘅日期（HKT）；冇快取回 None。讀取失敗會上拋 CacheReadError。"""
    df = load(code5)
    if df is None or df.empty:
        return None
    return date.fromisoformat(df["date"].iloc[-1])


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
        _MEMO[code5] = df
    return df


def window_upto(df: pd.DataFrame, end: date, n: int) -> pd.DataFrame:
    """快取入面 end（含）之前最近 n 支。"""
    sub = df[df["date"] <= end.isoformat()]
    return sub.tail(n)


def fetch_window(lb, symbol: str, n: int = 40) -> list:
    """即市K線端點拉最近 n 支日 K（收市後＝已確認）。"""
    return lb.candles_today(symbol, n)
