"""RTSS Telegram Web 純文字 alert parser。"""
from __future__ import annotations

import re
from datetime import date
from hashlib import sha256
from typing import Any

from stockscan.io_utils import parse_cn_number

_CODE_RE = re.compile(r"\bHK\.?\s*(\d{1,5})\b", re.I)
_NAME_RE = re.compile(r"(?:📈\s*)?(.+?)\s*\(\s*HK\.?\s*\d{1,5}\s*\)", re.I)
_COUNT_RE = re.compile(r"當日第\s*(\d+)\s*次(?:\s*\(([^)]*)\))?")
_LEVEL_RE = re.compile(r"[+-]?\d+(?:\.\d+)?%\s*[→➜\-]\s*[+-]?\d+(?:\.\d+)?%")
_TIME_RE = re.compile(r"(?:^|\n)\s*(?:🕐|🕒)?\s*(\d{1,2}:\d{2}:\d{2})\s*(?:$|\n)")


def _field_number(text: str, label: str) -> tuple[float | None, str]:
    match = re.search(
        rf"{re.escape(label)}\s*[:：]\s*([+-]?\d[\d,]*(?:\.\d+)?\s*(?:兆|億|亿|千萬|千万|萬|万)?)",
        text,
        re.I,
    )
    raw = match.group(1).strip() if match else ""
    return (parse_cn_number(raw) if raw else None), raw


def parse_alert(text: str, message_date: date | str | None = None,
                msg_id: str | None = None) -> dict[str, Any]:
    """Parse one RTSS alert, retaining raw text and never raising on bad input."""
    raw = str(text or "").strip()
    code_match = _CODE_RE.search(raw)
    name_match = _NAME_RE.search(raw)
    count_match = _COUNT_RE.search(raw)
    pct_match = re.search(r"升幅\s*[:：]\s*([+-]?\d+(?:\.\d+)?)\s*%", raw)
    price_match = re.search(r"最新價\s*[:：]\s*([+-]?\d+(?:\.\d+)?)", raw)
    time_match = _TIME_RE.search(raw)
    if not time_match:
        time_match = re.search(r"\b(\d{1,2}:\d{2}:\d{2})\b", raw)

    mcap, mcap_raw = _field_number(raw, "市值")
    turnover, turnover_raw = _field_number(raw, "成交額")
    level_from = level_to = None
    if count_match and count_match.group(2):
        level_match = _LEVEL_RE.search(count_match.group(2))
        if level_match:
            values = re.findall(r"[+-]?\d+(?:\.\d+)?", level_match.group(0))
            level_from, level_to = (float(values[0]), float(values[1]))
    category_match = re.search(r"相關範疇\s*[:：]\s*(.+)", raw)
    msg_date = str(message_date or "")
    alert_ts = f"{msg_date} {time_match.group(1)}" if msg_date and time_match else ""
    generated_id = msg_id or sha256(f"{raw}\n{alert_ts}".encode("utf-8")).hexdigest()
    result: dict[str, Any] = {
        "msg_id": str(generated_id),
        "alert_ts": alert_ts,
        "date": msg_date,
        "time": time_match.group(1) if time_match else "",
        "code5": code_match.group(1).zfill(5) if code_match else "",
        "name": name_match.group(1).strip() if name_match else "",
        "msg_type": ("SURGE" if "急升異動" in raw else
                     "VOLUME" if "爆量" in raw else
                     "大市值" if "大市值" in raw else "UNKNOWN"),
        "count_today": int(count_match.group(1)) if count_match else None,
        "level_from": level_from,
        "level_to": level_to,
        "mcap": mcap,
        "mcap_raw": mcap_raw,
        "turnover": turnover,
        "turnover_raw": turnover_raw,
        "chg_pct": float(pct_match.group(1)) if pct_match else None,
        "last_price": float(price_match.group(1)) if price_match else None,
        "category": category_match.group(1).strip() if category_match else "",
        "raw_text": raw,
        # 舊欄位保留，方便舊測試／舊畫面讀取。
        "level_range": (_LEVEL_RE.search(count_match.group(2)).group(0)
                        if count_match and count_match.group(2) and _LEVEL_RE.search(count_match.group(2))
                        else ""),
    }
    required = ("code5", "name", "mcap", "turnover", "chg_pct", "last_price", "time")
    if msg_date:
        required = required + ("alert_ts",)
    result["parse_failed"] = int(any(result[key] in ("", None) for key in required))
    return result
