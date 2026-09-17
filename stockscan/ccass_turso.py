"""直連 Turso 讀 CCASS `api_stock_cache`（P6b PART 2——繞開 Render）。

Render free plan 冷啟動係慢嘅根因；warm 完之後數據齊喺 Turso，STOCKSCAN
可以直接讀。呢個模組只做 SELECT，唔寫；憑證由 `load_secrets_env()`
（repo `_secrets/.env`，gitignored）載入，已設環境變數一定贏。
"""
from __future__ import annotations

import json
import os
from typing import Any

from stockscan.io_utils import load_secrets_env

BATCH_SIZE = 150


def _client():
    try:
        import libsql_client
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("libsql-client 未安裝（pip install libsql-client）") from exc
    load_secrets_env()
    url = os.environ["TURSO_DATABASE_URL"].strip()
    token = os.environ["TURSO_AUTH_TOKEN"].strip()
    if not url or not token:
        raise RuntimeError("TURSO_DATABASE_URL／TURSO_AUTH_TOKEN 未設定（正印：repo _secrets/.env）")
    if url.lower().startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    return libsql_client.create_client_sync(url, auth_token=token)


def fetch_stock_payloads(codes: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """讀 `stock:{code}:light:v1` payload。codes=None 讀全表。回傳 {code5: payload}。"""
    out: dict[str, dict[str, Any]] = {}
    with _client() as client:
        if codes is None:
            keys = [tuple(r)[0] for r in
                    client.execute("SELECT cache_key FROM api_stock_cache ORDER BY cache_key").rows]
        else:
            keys = [f"stock:{c.zfill(5)}:light:v1" for c in codes]
            placeholders = ",".join("?" * len(keys))
            keys = [tuple(r)[0] for r in client.execute(
                f"SELECT cache_key FROM api_stock_cache WHERE cache_key IN ({placeholders})",
                list(keys)).rows]
        for i in range(0, len(keys), BATCH_SIZE):
            chunk = keys[i:i + BATCH_SIZE]
            placeholders = ",".join("?" * len(chunk))
            rs = client.execute(
                f"SELECT cache_key, payload_json FROM api_stock_cache "
                f"WHERE cache_key IN ({placeholders})", list(chunk))
            for row in rs.rows:
                cache_key, payload_json = tuple(row)
                code = str(cache_key).split(":")[1]
                try:
                    payload = json.loads(str(payload_json))
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    out[code] = payload
    return out


def concentration_series(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """由 payload 抽 concentration 歷史（由新到舊），只留分析用欄位。

    SUSPECT_DENOMINATOR／exclude_from_analysis 照帶，唔准靜靜剔除——
    分母有可疑嘅百分比要由下游自己決定點處理。
    """
    records = ((payload.get("concentration") or {}).get("records")) or []
    out = []
    for r in records:
        try:
            out.append({
                "date": str(r.get("Date") or ""),
                "top5_pct": r.get("Top 5 %"),
                "top10_pct": r.get("Top 10 %"),
                "suspect_denominator": bool(r.get("SUSPECT_DENOMINATOR")),
                "exclude_from_analysis": bool(r.get("exclude_from_analysis")),
            })
        except AttributeError:
            continue
    return out
