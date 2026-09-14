"""RTSS board caption parsing and OCR support shared by O tools."""
from __future__ import annotations
import re

BOARD_TYPES = ("large_up", "large_down", "small_up", "small_down")

def classify_board_caption(text: str) -> str | None:
    s = re.sub(r"\s+", "", str(text or ""))
    if not re.search(r"價格(?:上升|下降)股票|价格(?:上升|下降)股票", s): return None
    direction = "up" if "上升" in s else "down"
    size = "large" if re.search(r"市值10[億亿]以上", s) else "small" if re.search(r"市值10[億亿]以下", s) else None
    return f"{size}_{direction}" if size else None

def extract_threshold_x(text: str) -> float | None:
    s = re.sub(r"\s+", "", str(text or ""))
    m = re.search(r"(?:成交額|成交额)[^\d]{0,20}(\d+(?:\.\d+)?)倍", s)
    return float(m.group(1)) if m else None
