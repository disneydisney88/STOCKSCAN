"""訊號 B：即市急升異動＋「當日第 N 次」狀態機（門檻全部喺 config.py）。

條件：mcap_now < MCAP_CAP_INTRA　且　turnover_intraday ≥ TURNOVER_MIN
　　且　chg_pct ≥ INTRA_FIRST_PCT；之後每多升 INTRA_STEP_PCT 再發一次。
級距 = floor(chg_pct / STEP) × STEP；記「level_from→level_to」同 count_today。
預篩用 min(prev_close, last_done) × total_shares（一輪 quote 過晒，慳 static 呼叫）。
"""
from __future__ import annotations

import math
from datetime import date

import pandas as pd

from config import (
    INTRA_FIRST_PCT,
    INTRA_STEP_PCT,
    MCAP_CAP_INTRA,
    TURNOVER_MIN,
    UNIVERSE_CSV,
)
from stockscan.calendar_hk import in_continuous_session
from stockscan.io_utils import (
    append_csv,
    ensure_dirs,
    lb_to_code5,
    load_state,
    now_hkt,
    read_csv_if_exists,
    save_state,
    ts_hkt,
)

ALERT_COLUMNS = [
    "ts", "code5", "symbol", "name", "count_today",
    "level_from", "level_to", "chg_pct", "last_done",
    "turnover_intraday", "mcap_now", "off_hours",
]


def level_of(chg_pct: float, step: float = INTRA_STEP_PCT) -> int:
    """升幅級距：floor(chg/step)×step；負數或零回 0。"""
    if chg_pct <= 0:
        return 0
    return int(math.floor(chg_pct / step)) * int(step)


def decide_alert(rec: dict | None, chg_pct: float,
                 first: float = INTRA_FIRST_PCT, step: float = INTRA_STEP_PCT) -> tuple[bool, int, int]:
    """狀態機：無紀錄且 chg≥first → 出；有紀錄且新級距 > 已記級距 → 出。
    回傳 (要唔要 alert, level_from, level_to)。"""
    if chg_pct < first:
        return False, 0, 0
    new_level = level_of(chg_pct, step)
    if rec is None:
        return True, 0, new_level
    if new_level > int(rec.get("level", 0)):
        return True, int(rec.get("level", 0)), new_level
    return False, 0, 0


def _load_universe() -> pd.DataFrame:
    uni = read_csv_if_exists(UNIVERSE_CSV)
    if uni.empty:
        raise SystemExit("data/universe.csv 唔存在——先跑 `python -m stockscan.universe`。")
    uni = uni[uni["in_scan"] == 1].copy()
    uni["total_shares"] = pd.to_numeric(uni["total_shares"], errors="coerce")
    return uni


def scan_once(lb, scan_date: date | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """掃一次即市。回傳 (alerts_df, 近門檻榜 near_df, meta)。alert 追加寫 CSV＋更新狀態檔。"""
    ensure_dirs()
    uni = _load_universe()
    shares = dict(zip(uni["symbol_lb"], uni["total_shares"]))
    names = dict(zip(uni["symbol_lb"], uni["name_hk"].fillna(uni["name_seed"])))
    symbols = uni["symbol_lb"].tolist()

    quotes = lb.quote_batch(symbols)
    pool: dict = {}
    for sym, q in quotes.items():
        ts_total = shares.get(sym)
        prev = float(q.prev_close or 0)
        last = float(q.last_done or 0)
        if not prev or not last or not ts_total or ts_total <= 0:
            continue
        # 預篩：min(prev,last)×shares < cap——唔會走漏任何可能合資格嘅
        if min(prev, last) * ts_total >= MCAP_CAP_INTRA:
            continue
        pool[sym] = {
            "prev_close": prev, "last_done": last,
            "turnover": float(q.turnover or 0),
            "chg_pct": (last / prev - 1) * 100,
            "mcap_now": last * ts_total,
        }

    state = load_state(scan_date or now_hkt().date())
    off_hours = 0 if in_continuous_session() else 1
    alerts: list[dict] = []
    for sym, p in sorted(pool.items(), key=lambda kv: -kv[1]["chg_pct"]):
        fire, lv_from, lv_to = decide_alert(state.get(sym), p["chg_pct"])
        if not fire:
            continue
        count = int(state.get(sym, {}).get("count", 0)) + 1
        t = now_hkt()
        alerts.append({
            "ts": t.strftime("%Y-%m-%d %H:%M:%S"),
            "code5": lb_to_code5(sym),
            "symbol": sym,
            "name": names.get(sym, sym),
            "count_today": count,
            "level_from": lv_from,
            "level_to": lv_to,
            "chg_pct": round(p["chg_pct"], 2),
            "last_done": p["last_done"],
            "turnover_intraday": round(p["turnover"]),
            "mcap_now": round(p["mcap_now"]),
            "off_hours": off_hours,
        })
        state[sym] = {
            "level": lv_to, "count": count,
            "last_alert": t.strftime("%H:%M:%S"),
        }

    if alerts:
        d = scan_date or now_hkt().date()
        append_csv(pd.DataFrame(alerts, columns=ALERT_COLUMNS),
                   _alerts_path(d))
        save_state(scan_date or now_hkt().date(), state)

    near = pd.DataFrame([
        {"code5": lb_to_code5(s), "name": names.get(s, s),
         "chg_pct": round(p["chg_pct"], 2), "last_done": p["last_done"],
         "turnover_intraday": round(p["turnover"]), "mcap_now": round(p["mcap_now"])}
        for s, p in pool.items()
    ]).sort_values("chg_pct", ascending=False).head(20).reset_index(drop=True)

    meta = {
        "quoted": len(quotes), "pool": len(pool),
        "alerts": len(alerts), "off_hours": off_hours,
        "scan_time": ts_hkt(),
    }
    return pd.DataFrame(alerts, columns=ALERT_COLUMNS), near, meta


def _alerts_path(d: date):
    from config import INTRADAY_DIR

    return INTRADAY_DIR / f"alerts_{d:%Y%m%d}.csv"
