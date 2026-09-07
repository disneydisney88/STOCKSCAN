"""P4：Telegram 推送（Bot API，用 requests，唔裝額外套件）。

憑證（同一個 .env）：TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID
所有 send_* 缺憑證／失敗都只 log 唔炸——推送永遠唔可以搞冧掃描本身。
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from stockscan.io_utils import ensure_dirs, log_error

_base = "https://api.telegram.org/bot{token}/{method}"


def _creds() -> tuple[str, str] | None:
    import os

    from stockscan.lb_client import ensure_credentials

    ensure_credentials()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    return (token, chat) if token and chat else None


def send_text(msg: str) -> bool:
    """純文字。憑證欠齊回 False（caller 決定點處理）。"""
    creds = _creds()
    if not creds:
        return False
    import requests

    try:
        r = requests.post(
            _base.format(token=creds[0], method="sendMessage"),
            json={"chat_id": creds[1], "text": msg, "disable_web_page_preview": True},
            timeout=15,
        )
        return r.ok
    except Exception as e:  # noqa: BLE001
        log_error("notify", f"send_text: {e!r}")
        return False


def _fmt_m(v) -> str:
    try:
        return f"{float(v) / 1e6:.1f}M"
    except (TypeError, ValueError):
        return "-"


def _fmt_yi(v) -> str:
    try:
        return f"{float(v) / 1e8:.2f}億"
    except (TypeError, ValueError):
        return "-"


def eod_message(df: pd.DataFrame, scan_date: date) -> str:
    """EOD 榜訊息（照 RTSS 表頭，等寬對齊）。"""
    head = (
        f"📊 STOCKSCAN 收市爆量榜 {scan_date:%Y-%m-%d}（{len(df)} 隻）\n"
        "條件：市值<10億 & 成交>50萬 & 今日/10MA≥10x\n"
        "代號  名稱      現價  升跌    成交額  市值   倍數  成交/市值"
    )
    lines = []
    for _, r in df.iterrows():
        lines.append(
            f"{r['code5']} {str(r['name'])[:6]:<6} "
            f"{r['close']:>5} {r['chg_pct']:>+6.1f}% "
            f"{_fmt_m(r['turnover_day']):>6} {_fmt_yi(r['mcap_total']):>6} "
            f"{r['ratio']:>5.1f}x {r['turnover_to_mcap']:>4.1f}%"
        )
    return head + "\n" + "\n".join(lines) + "\n只供學術研究，不構成投資建議"


def send_eod_table(df: pd.DataFrame, scan_date: date, dry_run: bool = False) -> bool:
    msg = eod_message(df, scan_date)
    print(msg)
    if dry_run:
        print("[notify] dry-run——唔發送。")
        return False
    return send_text(msg)


def intraday_message(row: dict) -> str:
    """即市 alert（照 RTSS 格式）。row 係 alerts CSV 一行（dict-like）。"""
    icon = "🔥" if row.get("alert_type") == "SURGE" else "💥"
    typ = "急升異動" if row.get("alert_type") == "SURGE" else "即市爆量"
    lvl = f"[當日第{row['count_today']}次 ({row['level_from']}%→{row['level_to']}%)]"
    ratio = row.get("ratio_intraday", "")
    ratio_txt = f"  🧮 倍數: {ratio}x" if ratio not in ("", None) else ""
    return (
        f"{icon} {typ} {lvl}\n"
        f"📈 {row['name']} (HK.{row['code5']})\n"
        f"💰 市值: {_fmt_yi(row.get('mcap_now'))}  💹 成交額: {_fmt_m(row.get('turnover_intraday'))}{ratio_txt}\n"
        f"📊 升幅: +{row['chg_pct']}%  最新價: {row['last_done']}  🕒 {row['ts'].split(' ')[1]}"
    )


def send_intraday_alert(row: dict, dry_run: bool = False) -> bool:
    msg = intraday_message(row)
    print(msg)
    if dry_run:
        print("[notify] dry-run——唔發送。")
        return False
    return send_text(msg)
