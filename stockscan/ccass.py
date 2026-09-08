"""Small client for the private CCASS research API."""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from config import DATA_DIR
from stockscan.io_utils import HKT, log_error


def _load_config() -> tuple[str, str]:
    load_dotenv(Path.home() / ".stockscan" / ".env")
    url, key = os.environ.get("CCASS_API_URL"), os.environ.get("CCASS_API_KEY")
    if not url or not key:
        raise RuntimeError("CCASS_API_URL／CCASS_API_KEY 未設定")
    return url.rstrip("/"), key


def request_json(path: str, params: dict | None = None, timeout: int = 40):
    base, key = _load_config()
    query = f"?{urlencode(params)}" if params else ""
    req = Request(base + path + query, headers={"X-API-Key": key, "Authorization": f"Bearer {key}"})
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def health() -> dict:
    return request_json("/health", timeout=10)


def fetch_stock(code5: str, timeout: int = 180, retries: int = 2, retry_delay: int = 30) -> dict:
    params = {
        "code": str(code5).zfill(5), "source_preference": "auto",
        "concentration_limit": 100, "big_changes_limit": 100, "changes_limit": 100,
    }
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return request_json("/api/stock", params, timeout=timeout)
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                raise
            log_error(
                "ccass.stock.retry",
                f"{params['code']} attempt {attempt + 1}/{retries + 1}: {type(exc).__name__}",
            )
            time.sleep(retry_delay)
    assert last_error is not None
    raise last_error


def date_alignment(event_date: str) -> dict:
    return request_json("/api/date-alignment", {"event_date": event_date, "basis": "settlement"})


def _number(value) -> float | None:
    if isinstance(value, (int, float)) and value == value:
        return float(value)
    if isinstance(value, str):
        m = re.search(r"[-+]?\d+(?:\.\d+)?", value.replace(",", ""))
        return float(m.group()) if m else None
    return None


def _find_rows(value, names: set[str]):
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower().replace("_", "") in {n.replace("_", "") for n in names} and isinstance(child, list):
                yield child
            yield from _find_rows(child, names)
    elif isinstance(value, list):
        for child in value:
            yield from _find_rows(child, names)


def top_concentration_pct(payload: dict) -> tuple[float | None, float | None]:
    """Sum the largest percentage values in the concentration rows."""
    rows = next(_find_rows(payload, {"concentration", "concentration_rows", "holdings"}), [])
    values = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key, value in row.items():
            if any(token in key.lower() for token in ("percentage", "share_pct", "holding_pct", "pct")):
                num = _number(value)
                if num is not None:
                    values.append(num if abs(num) > 1 else num * 100)
                    break
    values.sort(reverse=True)
    return (round(sum(values[:5]), 6) if values else None,
            round(sum(values[:10]), 6) if values else None)


def save_stock(code5: str, event_date: str, payload: dict, out_dir: Path = DATA_DIR / "ccass") -> Path:
    path = out_dir / str(code5).zfill(5) / f"{event_date}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    top5, top10 = top_concentration_pct(payload)
    wrapped = {"code5": str(code5).zfill(5), "event_date": event_date,
               "fetched_at_hkt": datetime.now(HKT).isoformat(),
               "ccass_top5_pct_t2": top5, "ccass_top10_pct_t2": top10,
               "payload": payload}
    path.write_text(json.dumps(wrapped, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
