"""Longbridge (LongPort) OpenAPI 封裝：
- 憑證讀取次序：st.secrets（Streamlit 內）→ .env → 環境變數
- 分批（QUOTE_BATCH）＋限流指數退避（1,2,4,8s，最多 5 次重試）
- 每個錯誤落 logs/，唔准 silent pass
"""
from __future__ import annotations

import os
import time
from datetime import date, datetime, timedelta
from typing import Callable, TypeVar

from config import QUOTE_BATCH
from stockscan.io_utils import log_error

REQUIRED_KEYS = ("LONGPORT_APP_KEY", "LONGPORT_APP_SECRET", "LONGPORT_ACCESS_TOKEN")

T = TypeVar("T")


class MissingCredentialsError(RuntimeError):
    """憑證欠齊——要 KL 建立 .env／設 Secrets，唔好靜靜跳過。"""


def ensure_credentials() -> None:
    """依規格書 H4 次序設定環境變數：st.secrets → .env → 環境變數。"""
    try:  # 1) Streamlit secrets（本機無 streamlit runtime 會即 exception）
        import streamlit as st

        secrets = st.secrets
        if all(k in secrets for k in REQUIRED_KEYS):
            for k in REQUIRED_KEYS:
                os.environ[k] = str(secrets[k])
            return
    except Exception:
        pass
    # 2) repo 根目錄 .env（python-dotenv 唔會覆蓋已存在嘅環境變數）
    from dotenv import load_dotenv

    load_dotenv()


def get_config():
    ensure_credentials()
    missing = [k for k in REQUIRED_KEYS if not os.environ.get(k)]
    if missing:
        raise MissingCredentialsError(
            f"缺 Longbridge 憑證：{missing}。"
            "請喺 repo 根目錄建立 .env（照 .env.example 三個 LONGPORT_ 變數），"
            "或喺 Streamlit Cloud Secrets／GitHub Actions Secrets 設定。"
        )
    from longport.openapi import Config

    return Config.from_apikey(
        app_key=os.environ["LONGPORT_APP_KEY"],
        app_secret=os.environ["LONGPORT_APP_SECRET"],
        access_token=os.environ["LONGPORT_ACCESS_TOKEN"],
        enable_print_quote_packages=False,
    )


_BACKOFF_S = (1, 2, 4, 8, 8)  # 5 次重試之間嘅等待


class LB:
    """QuoteContext 薄封裝。ctx 建立會開 WebSocket，一個 process 一個就好。"""

    def __init__(self) -> None:
        self._ctx = None

    @property
    def ctx(self):
        if self._ctx is None:
            from longport.openapi import QuoteContext

            self._ctx = QuoteContext(get_config())
        return self._ctx

    def _retry(self, scope: str, fn: Callable[[], T]) -> T:
        last: Exception | None = None
        for attempt in range(1 + len(_BACKOFF_S)):
            if attempt:
                time.sleep(_BACKOFF_S[min(attempt - 1, len(_BACKOFF_S) - 1)])
            try:
                return fn()
            except Exception as e:  # noqa: BLE001——SDK 會丟多種 exception，統一記錄
                last = e
                log_error(scope, f"attempt {attempt + 1}: {e!r}")
        raise last  # type: ignore[misc]

    def _chunks(self, symbols: list[str]):
        for i in range(0, len(symbols), QUOTE_BATCH):
            yield symbols[i : i + QUOTE_BATCH]

    def quote_batch(self, symbols: list[str]) -> dict:
        """即市 quote，分批。回傳 {symbol: SecurityQuote}。"""
        out: dict = {}
        for chunk in self._chunks(symbols):
            rows = self._retry(f"quote[{len(chunk)}]", lambda c=chunk: self.ctx.quote(c))
            for q in rows:
                out[q.symbol] = q
        return out

    def static_info_batch(self, symbols: list[str]) -> dict:
        """靜態資料，分批。回傳 {symbol: SecurityStaticInfo}。"""
        out: dict = {}
        for chunk in self._chunks(symbols):
            rows = self._retry(
                f"static_info[{len(chunk)}]", lambda c=chunk: self.ctx.static_info(c)
            )
            for s in rows:
                out[s.symbol] = s
        return out

    def candles_today(self, symbol: str, n: int = 11) -> list:
        """日 K 最近 n 支（含今日即市 bar）——訊號 A「今日」跑法。"""
        from longport.openapi import AdjustType, Period

        return self._retry(
            f"candlesticks[{symbol}]",
            lambda: self.ctx.candlesticks(symbol, Period.Day, n, AdjustType.NoAdjust),
        )

    def candles_by_date(self, symbol: str, end: date, n: int = 11) -> list:
        """取 end（含）之前最近 n 支日 K——訊號 A「過去日子」跑法。"""
        from longport.openapi import AdjustType, Period

        start = end - timedelta(days=60)
        rows = self._retry(
            f"history_candles[{symbol}]",
            lambda: self.ctx.history_candlesticks_by_date(
                symbol, Period.Day, AdjustType.NoAdjust, start=start, end=end
            ),
        )
        return list(rows[-n:])

    def trading_days(self, start: date, end: date) -> list[date]:
        from longport.openapi import Market

        res = self._retry(
            "trading_days",
            lambda: self.ctx.trading_days(Market.HK, start, end),
        )
        return sorted(d for d in res.trading_days)
