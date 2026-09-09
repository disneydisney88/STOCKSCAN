"""RTSS Telegram Web 純文字 alert parser。"""
from __future__ import annotations

import re
from typing import Any

from stockscan.io_utils import parse_cn_number

_CODE_RE = re.compile(r"\bHK\.?\s*(\d{1,5})\b", re.I)
_NAME_RE = re.compile(r"(?:📈\s*)?(.+?)\s*\(\s*HK\.?\s*\d{1,5}\s*\)", re.I)
_COUNT_RE = re.compile(r"當日第\s*(\d+)\s*次(?:\s*\(([^)]*)\))?")
_LEVEL_RE = re.compile(r"[+-]?\d+(?:\.\d+)?%\s*[→➜\-]\s*[+-]?\d+(?:\.\d+)?%")


def _field_number(text: str, label: str) -> float | None:
    match = re.search(rf"{re.escape(label)}\s*[:：]\s*([^\n\r]+)", text, re.I)
    return parse_cn_number(match.group(1).strip()) if match else None


def parse_alert(text: str) -> dict[str, Any]:
    """Parse one RTSS alert, retaining raw text and never raising on bad input."""
    raw = str(text or "").strip()
    code_match = _CODE_RE.search(raw)
    name_match = _NAME_RE.search(raw)
    count_match = _COUNT_RE.search(raw)
    pct_match = re.search(r"升幅\s*[:：]\s*([+-]?\d+(?:\.\d+)?)\s*%", raw)
    price_match = re.search(r"最新價\s*[:：]\s*([+-]?\d+(?:\.\d+)?)", raw)
    time_match = re.search(r"(?:^|\n)\s*(?:🕐\s*)?(\d{1,2}:\d{2}:\d{2})\s*(?:$|\n)", raw)
    if not time_match:
        time_match = re.search(r"\b(\d{1,2}:\d{2}:\d{2})\b", raw)

    result: dict[str, Any] = {
        "msg_type": "SURGE" if "急升異動" in raw else "UNKNOWN",
        "code5": code_match.group(1).zfill(5) if code_match else "",
        "name": name_match.group(1).strip() if name_match else "",
        "mcap": _field_number(raw, "市值"),
        "turnover": _field_number(raw, "成交額"),
        "chg_pct": float(pct_match.group(1)) if pct_match else None,
        "last_price": float(price_match.group(1)) if price_match else None,
        "time": time_match.group(1) if time_match else "",
        "count_today": int(count_match.group(1)) if count_match else None,
        "level_range": (_LEVEL_RE.search(count_match.group(2)).group(0)
                        if count_match and count_match.group(2) and _LEVEL_RE.search(count_match.group(2))
                        else ""),
        "raw_text": raw,
    }
    required = ("code5", "name", "mcap", "turnover", "chg_pct", "last_price", "time")
    result["parse_failed"] = int(any(result[key] in ("", None) for key in required))
    return result
