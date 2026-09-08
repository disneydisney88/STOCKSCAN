#!/usr/bin/env python
"""P4 Z1：訊號 B 常駐守護进程（本機自動化，唔使雲）。

用法：python scripts/intraday_daemon.py            （前景跑，Ctrl-C 離開）
功能：
- 包住 scan_once 循環：交易日 09:30–12:00／13:00–16:10 HKT 每 60 秒一輪
- 崩潰自動重啟（每日最多 5 次，間隔 60 秒；超過就退出交俾排程器聽日再嚟）
- 非交易日／非掃描時段：分段瞓，唔會報錯
- stdout/stderr 轉檔 logs/intraday_YYYYMMDD.log（保留 30 日）
- 時點快照：10:30／11:30／13:30／15:30／16:00 HKT 各寫一張
  data/intraday/snapshot_YYYYMMDD_HHMM.csv（全部 ratio ≥10 嘅股，
  欄位照訊號 A 八欄 + first_seen_today）
- 每日 16:15 HKT 收市後寫 data/intraday/summary_YYYYMMDD.csv
  （每隻股當日最高 level、alert 總數、首次 alert 時間、首次 alert 價 vs 收市價）
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import INTRADAY_DIR, INTRA_POLL_SEC, LOGS_DIR, DISCLAIMER
from stockscan.calendar_hk import in_scan_session
from stockscan.io_utils import (
    HKT,
    append_csv,
    lb_to_code5,
    load_state,
    log_error,
    now_hkt,
    today_hkt,
)
from stockscan.lb_client import LB
from stockscan.scan_intraday import calc_ratio_intraday, ma10_from_cache, scan_once

SNAPSHOT_TIMES = ((10, 30), (11, 30), (13, 30), (15, 30), (16, 0))
SUMMARY_TIME = (16, 15)
MAX_CRASHES_PER_DAY = 5
LOG_KEEP_DAYS = 30

_snapshot_done: set[str] = set()
_summary_done: set[str] = set()
_last_round: dict | None = None  # 上一輪 scan meta（內含 pool，供快照用）


# ── log 轉檔 ──

def rotate_log() -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"intraday_{today_hkt():%Y%m%d}.log"
    sys.stdout = open(log_path, "a", buffering=1, encoding="utf-8")
    sys.stderr = sys.stdout
    # 清理 30 日前
    cutoff = (now_hkt() - timedelta(days=LOG_KEEP_DAYS)).date()
    for p in LOGS_DIR.glob("intraday_*.log"):
        try:
            if datetime.strptime(p.stem.replace("intraday_", ""), "%Y%m%d").date() < cutoff:
                p.unlink(missing_ok=True)
        except ValueError:
            continue
    return log_path


# ── 時點快照 ──

def maybe_snapshot(d: date) -> None:
    """round 之後檢查：有冇快照時點啱啱過咗而未寫。"""
    global _last_round
    if _last_round is None or not _last_round.get("_pool"):
        return
    now = now_hkt()
    if now.date() != d:
        return
    for hh, mm in SNAPSHOT_TIMES:
        key = f"{d:%Y%m%d}_{hh:02d}{mm:02d}"
        if key in _snapshot_done:
            continue
        due = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if now >= due:
            _write_snapshot(d, key, hh, mm)
            _snapshot_done.add(key)


def _write_snapshot(d: date, key: str, hh: int, mm: int) -> None:
    """全部即市 ratio ≥10 嘅股 → snapshot CSV（欄位照訊號 A 八欄 + first_seen_today）。"""
    from stockscan.scan_intraday import INTRA_VOL_FIRST, calc_ratio_intraday, ma10_from_cache
    from stockscan import kline_cache

    pool = _last_round.get("_pool", {})
    shares = _last_round.get("_shares", {})
    names = _last_round.get("_names", {})
    state = load_state(d)
    rows = []
    for sym, p in pool.items():
        ts_total = shares.get(sym)
        if not ts_total or ts_total != ts_total or ts_total <= 0:
            continue
        try:
            ma10 = ma10_from_cache(lb_to_code5(sym), d)
        except Exception:  # noqa: BLE001——讀唔到就跳過呢隻
            continue
        ratio = calc_ratio_intraday(p["turnover"], ma10)
        if ratio is None or ratio < INTRA_VOL_FIRST:
            continue
        first = (state.get(sym, {}).get("first_seen_ts") or "")[11:16]
        mcap = p["last_done"] * ts_total
        rows.append({
            "code5": lb_to_code5(sym),
            "name": names.get(sym, sym),
            "close": p["last_done"],
            "chg_pct": round(p["chg_pct"], 2),
            "turnover_day": round(p["turnover"]),
            "mcap_total": round(mcap),
            "ratio": round(ratio, 2),
            "turnover_to_mcap": round(p["turnover"] / mcap * 100, 2) if mcap else "",
            "first_seen_today": first,
        })
    df = pd.DataFrame(rows).sort_values("mcap_total").reset_index(drop=True)
    path = INTRADAY_DIR / f"snapshot_{key}.csv"
    INTRADAY_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"[snapshot] {hh:02d}:{mm:02d}　ratio≥10 共 {len(df)} 隻 → {path}")


# ── 收市 summary ──

def maybe_summary(d: date) -> None:
    global _last_round
    now = now_hkt()
    key = f"{d:%Y%m%d}"
    if key in _summary_done or now.date() != d:
        return
    if (now.hour, now.minute) < SUMMARY_TIME:
        return
    alerts_path = INTRADAY_DIR / f"alerts_{d:%Y%m%d}.csv"
    alerts = pd.read_csv(alerts_path, encoding="utf-8-sig") if alerts_path.exists() \
        else pd.DataFrame()
    pool = (_last_round or {}).get("_pool", {})
    names = (_last_round or {}).get("_names", {})
    rows = []
    if not alerts.empty:
        for code5, g in alerts.groupby("code5"):
            g = g.sort_values("ts")
            first = g.iloc[0]
            close = None
            sym = first.get("symbol")
            if sym in pool:
                close = pool[sym]["last_done"]
            first_px = float(first.get("last_done") or 0)
            rows.append({
                "code5": code5,
                "name": first.get("name"),
                "max_level": int(pd.to_numeric(g["level_to"]).max()),
                "alert_count": len(g),
                "first_alert_ts": first.get("ts"),
                "first_alert_price": first_px,
                "close_price": close,
                "first_vs_close_pct": round((close / first_px - 1) * 100, 2)
                if close and first_px else "",
            })
    df = pd.DataFrame(rows).sort_values("max_level", ascending=False) if rows else pd.DataFrame()
    path = INTRADAY_DIR / f"summary_{d:%Y%m%d}.csv"
    INTRADAY_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    _summary_done.add(key)
    print(f"[summary] {d}　{len(df)} 隻有 alert → {path}")


# ── 主循環 ──

def is_trading_day(lb, d: date) -> bool:
    try:
        from stockscan.calendar_hk import trading_days
        return d in trading_days(lb, d - timedelta(days=14), d)
    except Exception as e:  # noqa: BLE001——日曆失手就用星期幾頂住
        log_error("daemon.calendar", repr(e))
        return d.weekday() < 5


def main() -> int:
    lb = LB()
    rotate_log()
    crashes = 0
    crash_day = today_hkt()
    print(f"[daemon] 啟動 {now_hkt():%Y-%m-%d %H:%M:%S} HKT　"
          f"（每輪 {INTRA_POLL_SEC}s；快照時點 {SNAPSHOT_TIMES}；summary {SUMMARY_TIME}）")

    while True:
        try:
            d = today_hkt()
            if d != crash_day:  # 跨日：重置 crash 計數＋轉 log
                crashes, crash_day = 0, d
                rotate_log()
            if not is_trading_day(lb, d) or not in_scan_session():
                now = now_hkt()
                print(f"[daemon] {now:%H:%M} 非掃描時段，{INTRA_POLL_SEC}s 後再檢查。")
                time.sleep(INTRA_POLL_SEC)
                continue

            global _last_round
            alerts, near, meta = scan_once(lb, d)
            _last_round = meta
            print(f"[daemon] {meta['scan_time']}　quoted={meta['quoted']} pool={meta['pool']} "
                  f"alert={meta['alerts']} ma10_err={meta.get('ma10_errors', 0)} "
                  f"off_hours={meta['off_hours']} {meta['elapsed_s']}s")
            if not alerts.empty:
                print(alerts.to_string(index=False))
            maybe_snapshot(d)
            maybe_summary(d)
            time.sleep(INTRA_POLL_SEC)

        except KeyboardInterrupt:
            print("[daemon] Ctrl-C 離開。")
            return 0
        except Exception as e:  # noqa: BLE001——崩潰重啟
            crashes += 1
            log_error("daemon", f"第 {crashes} 次崩潰：{e!r}\n{traceback.format_exc()}")
            print(f"[daemon] 崩潰 {crashes}/{MAX_CRASHES_PER_DAY}，60 秒後重啟掃描循環。")
            if crashes >= MAX_CRASHES_PER_DAY:
                print("[daemon] 今日崩潰次數用晒——退出（排程器聽日再嚟）。")
                return 1
            time.sleep(60)


if __name__ == "__main__":
    raise SystemExit(main())
