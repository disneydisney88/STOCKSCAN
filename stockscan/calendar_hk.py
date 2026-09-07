"""港交所交易日曆封裝：trading_days / last_trading_day / prev_n_trading_days / 交易時段判斷。"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from config import TZ
from stockscan.lb_client import LB
from stockscan.io_utils import HKT

# 港股持續交易時段（供訊號 B off_hours 旗用）
SESSIONS = ((time(9, 30), time(12, 0)), (time(13, 0), time(16, 0)))
# 訊號 B 掃描時段（P3：下午掃到 16:10 收埋尾水）
SCAN_SESSIONS = ((time(9, 30), time(12, 0)), (time(13, 0), time(16, 10)))


def trading_days(lb: LB, start: date, end: date) -> list[date]:
    return lb.trading_days(start, end)


def last_trading_day(lb: LB, asof: date, inclusive: bool = True) -> date:
    """asof（含或不含）之前最近嘅交易日。"""
    days = trading_days(lb, asof - timedelta(days=30), asof)
    if not inclusive and days and days[-1] == asof:
        days = days[:-1]
    if not days:
        raise ValueError(f"搵唔到 {asof} 之前嘅交易日")
    return days[-1]


def prev_n_trading_days(lb: LB, asof: date, n: int, include_asof: bool = True) -> list[date]:
    """asof 前面 n 個交易日（include_asof=True 時含 asof 自身如果係交易日）。"""
    days = trading_days(lb, asof - timedelta(days=90), asof)
    if not include_asof and days and days[-1] == asof:
        days = days[:-1]
    return days[-n:]


def is_trading_day(lb: LB, d: date) -> bool:
    return d in trading_days(lb, d - timedelta(days=10), d)


def in_continuous_session(now: datetime | None = None) -> bool:
    """而家係咪港股持續交易時段（星期一至五 + 時段內；假日判斷交畀 scan 呼叫方用日曆）。"""
    now = now or datetime.now(HKT)
    if now.weekday() >= 5:
        return False
    t = now.time()
    return any(lo <= t < hi for lo, hi in SESSIONS)


def in_scan_session(now: datetime | None = None) -> bool:
    """而家係咪訊號 B 應該掃描嘅時段（SCAN_SESSIONS：09:30–12:00、13:00–16:10）。"""
    now = now or datetime.now(HKT)
    if now.weekday() >= 5:
        return False
    t = now.time()
    return any(lo <= t < hi for lo, hi in SCAN_SESSIONS)
