"""CSV 讀寫、代號轉換、時間戳、狀態檔、錯誤 log——純函數優先，方便 pytest。"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from config import DATA_DIR, EOD_DIR, INTRADAY_DIR, LOGS_DIR, STATE_DIR, TZ

HKT = ZoneInfo(TZ)


def now_hkt() -> datetime:
    return datetime.now(HKT)


def today_hkt() -> date:
    return now_hkt().date()


def ts_hkt() -> str:
    return now_hkt().strftime("%Y-%m-%d %H:%M:%S")


# ── 代號轉換 ──

def seed_code_to_lb(code: str) -> str:
    """種子檔格式 00623.hk → Longbridge 623.HK（去前導零、大寫；容忍 02667.hk_depre 呢類後綴）。"""
    s = str(code).strip().lower().split("_")[0]
    if s.endswith(".hk"):
        s = s[:-3]
    return f"{int(s)}.HK"


def lb_to_code5(symbol: str) -> str:
    """Longbridge 623.HK → 5 位代號 00623。"""
    return str(symbol).strip().upper().split(".")[0].zfill(5)


def parse_cn_number(text) -> float | None:
    """9.9億 → 9.9e8；6.8千萬 → 6.8e7；'-' → None。種子檔市值欄用。"""
    if text is None:
        return None
    s = str(text).strip().replace(",", "")
    if s in {"", "-", "—", "NA"}:
        return None
    mult = 1.0
    for suffix, m in (("兆", 1e12), ("億", 1e8), ("亿", 1e8), ("千萬", 1e7), ("千万", 1e7), ("萬", 1e4), ("万", 1e4)):
        if s.endswith(suffix):
            mult = m
            s = s[: -len(suffix)]
            break
    try:
        return float(s) * mult
    except ValueError:
        return None


# ── 目錄／log ──

def ensure_dirs() -> None:
    for d in (DATA_DIR, EOD_DIR, INTRADAY_DIR, STATE_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def log_error(scope: str, msg: str) -> None:
    """每個 API 錯誤都要落 log，唔准 silent pass。logs/ 已 gitignore。"""
    ensure_dirs()
    line = f"{ts_hkt()} [{scope}] {msg}"
    print(line, file=sys.stderr)
    with open(LOGS_DIR / f"errors_{now_hkt():%Y%m%d}.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ── CSV 讀寫（統一 utf-8-sig，方便 Excel 開）──

def write_csv(df: pd.DataFrame, path: Path) -> Path:
    ensure_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def append_csv(df: pd.DataFrame, path: Path) -> Path:
    """逐條 alert 追加；檔案唔存在就連 header 寫。"""
    ensure_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    header = not path.exists()
    df.to_csv(path, mode="a", index=False, header=header, encoding="utf-8-sig")
    return path


def read_csv_if_exists(path: Path) -> pd.DataFrame:
    if Path(path).exists():
        return pd.read_csv(path, dtype={"code5": str}, encoding="utf-8-sig")
    return pd.DataFrame()


# ── 訊號 B 當日狀態檔（state/intraday_state_YYYYMMDD.json）──

def state_path(d: date) -> Path:
    return STATE_DIR / f"intraday_state_{d:%Y%m%d}.json"


def load_state(d: date) -> dict:
    from stockscan import turso_state
    if turso_state.configured():
        return turso_state.load(d)
    p = state_path(d)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(d: date, state: dict) -> Path:
    from stockscan import turso_state
    if turso_state.configured():
        turso_state.save(d, state)
        return state_path(d)
    ensure_dirs()
    p = state_path(d)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    return p


def add_trading_days_buffer(d: date, calendar_days: int = 45) -> date:
    return d - timedelta(days=calendar_days)
