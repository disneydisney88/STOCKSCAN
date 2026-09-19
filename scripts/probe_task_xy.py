#!/usr/bin/env python
"""任務XY 探測器（規格書 2026-09-13）：Y0 CCASS 三隻 + X′ 股本試點 30 隻。

規格紅線：冷啟動唔算失敗（指數退避）；Y0 答四條問題後停；X′ 試點報告後停，
全量（X1′/Y1）等 KL 確認。直接 HTTP，唔經 MCP，並發 3。Token 唔准 print。
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from stockscan.io_utils import load_secrets_env  # noqa: E402

OUT = Path(r"G:\我的雲端硬碟\RTSS\codex")
OUT.mkdir(parents=True, exist_ok=True)


def api_get(path: str, params: dict, key: str, base: str,
            timeout: int = 150, retries: int = 4):
    """GET with query-param key auth + exponential backoff（冷啟動唔算失敗）。"""
    query = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items())
    url = f"{base}{path}?key={urllib.request.quote(key)}&{query}"
    delay = 5.0
    last = None
    for attempt in range(1, retries + 1):
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8")), time.monotonic() - t0, attempt
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code in (404, 401):
                raise RuntimeError(f"{last}（唔係冷啟動，唔重試）") from e
        except Exception as e:  # noqa: BLE001——冷啟動 RemoteDisconnected/timeout 都要退避重試
            last = f"{type(e).__name__}: {str(e)[:80]}"
        print(f"    attempt {attempt} 失敗（{last}），退避 {delay:.0f}s", flush=True)
        time.sleep(delay)
        delay *= 2
    raise RuntimeError(f"重試 {retries} 次都失敗：{last}")


def main() -> int:
    load_secrets_env()
    base = os.environ["CCASS_API_URL"].rstrip("/")
    key = os.environ["CCASS_API_KEY"]
    print(f"base={base}（key 已載入，唔 print）", flush=True)

    # 叫醒
    print("[wake] /health ...", flush=True)
    try:
        h, secs, _ = api_get("/health", {}, key, base, timeout=180, retries=5)
        print(f"[wake] OK {secs:.1f}s status={h.get('status', h.get('db_backend', '?'))}", flush=True)
    except Exception as e:
        print(f"[wake] FAIL: {e}", flush=True)
        return 2

    results = {}

    # ── Y0：三隻 CCASS 探測（規格 4.2 四條問題）──
    print("\n[Y0] get_ccass_stock_data 02048 / 01825 / 08059", flush=True)
    y0 = {}
    for code in ("02048", "01825", "08059"):
        try:
            p, secs, att = api_get("/api/stock", {"code": code, "holdings_limit": 100,
                                                  "changes_limit": 100,
                                                  "concentration_limit": 100}, key, base)
            conc = p.get("concentration") or {}
            recs = conc.get("records") or []
            dates = sorted(str(r.get("Date") or "") for r in recs if r.get("Date"))
            holdings = p.get("holdings") or []
            hdates = sorted({str(h.get("Date") or h.get("date") or "") for h in holdings} - {""})
            y0[code] = {
                "seconds": round(secs, 1), "attempts": att,
                "concentration_records": len(recs),
                "conc_date_min": dates[0] if dates else "", "conc_date_max": dates[-1] if dates else "",
                "holdings_rows": len(holdings),
                "holdings_dates": hdates[:2] + (["..."] if len(hdates) > 2 else []) + hdates[-1:],
                "big_changes_rows": len(p.get("big_changes") or []),
                "errors": p.get("errors"),
            }
            print(f"  {code}: {secs:.1f}s conc={len(recs)} ({dates[0]}→{dates[-1]}) "
                  f"holdings={len(holdings)}@{hdates[-1] if hdates else '-'} "
                  f"bigchanges={len(p.get('big_changes') or [])}", flush=True)
        except Exception as e:
            y0[code] = {"error": str(e)}
            print(f"  {code}: FAIL {e}", flush=True)
    results["y0"] = y0

    # ── X0′：股本試點 30 隻（規格 3.2）──
    pilot = ["01218", "08059", "01069",  # 三個錨點必在
             "00075", "00207", "00393", "01393", "01592", "01792", "01825",
             "02048", "02371", "02535", "03018", "03301", "03417", "04099",
             "06083", "06099", "06696", "08059", "08072", "08162", "08293",
             "08368", "08439", "08483", "09543", "09978", "09998"]
    seen = set()
    pilot = [c for c in pilot if not (c in seen or seen.add(c))][:30]
    gem = [c for c in pilot if c.startswith("8")]
    print(f"\n[X0'] 試點 {len(pilot)} 隻（GEM {len(gem)} 隻）", flush=True)

    def fetch_capital(code: str):
        p, secs, att = api_get("/api/stock/capital",
                               {"code": code, "changes_limit": 200, "buybacks_limit": 20},
                               key, base)
        return code, p, secs, att

    rows, times, truncated, no_data = [], [], 0, 0
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(fetch_capital, c) for c in pilot]
        for fut in as_completed(futs):
            try:
                code, p, secs, att = fut.result()
            except Exception as e:
                rows.append({"code": "?", "error": str(e)})
                print(f"  FAIL {str(e)[:80]}", flush=True)
                continue
            times.append(secs)
            summary = p.get("capital_summary") or {}
            changes = p.get("capital_changes") or p.get("changes") or []
            if summary.get("truncated"):
                truncated += 1
            if not changes:
                no_data += 1
            for ch in changes:
                rows.append({"code": code, "announce_date": ch.get("announce_date", ""),
                             "change_date": ch.get("change_date", ""),
                             "shares_approx": ch.get("shares_approx", ""),
                             "shares_million": ch.get("shares_million", ""),
                             "reason": ch.get("reason", ""),
                             "reason_tags": ";".join(ch.get("reason_tags") or []),
                             "truncated": bool(summary.get("truncated"))})
            latest = summary.get("latest_share_capital") or {}
            print(f"  {code}: {secs:.1f}s changes={len(changes)} "
                  f"latest={latest.get('shares_approx')}@{latest.get('as_of')} "
                  f"truncated={summary.get('truncated')}", flush=True)
    results["x0"] = {
        "pilot_size": len(pilot), "rows": len(rows), "truncated": truncated,
        "no_data": no_data,
        "avg_seconds": round(sum(times) / len(times), 1) if times else None,
        "full_2036_estimate_min": round(sum(times) / max(1, len(times)) * 2036 / 3 / 60, 0)
        if times else None,
    }
    stamp = f"{datetime.now(timezone.utc):%Y%m%d_%H%M}"
    (OUT / f"taskXY_probe_{stamp}.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / f"share_capital_changes_pilot_{stamp}.csv").write_text(
        "code,announce_date,change_date,shares_approx,shares_million,reason,reason_tags,truncated\n"
        + "\n".join(",".join(str(r.get(k, "")) for k in
                             ("code", "announce_date", "change_date", "shares_approx",
                              "shares_million", "reason", "reason_tags", "truncated"))
                    for r in rows if "error" not in r), encoding="utf-8-sig")
    print(f"\n[out] {OUT}\taskXY_probe_{stamp}.json + share_capital_changes_pilot_{stamp}.csv",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
