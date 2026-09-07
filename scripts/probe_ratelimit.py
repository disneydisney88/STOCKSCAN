#!/usr/bin/env python
"""probe_ratelimit.py——H0 用：實測 quote 批量上限同耗時，結果寫 logs/probe_*.json。

等 .env 放好先跑：python scripts/probe_ratelimit.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import LOGS_DIR, QUOTE_BATCH
from stockscan.io_utils import ensure_dirs, now_hkt
from stockscan.lb_client import LB, MissingCredentialsError

# 測試樣本：大價股＋細價股混合，確保全部有報價
PROBE_20 = [
    "700.HK", "5.HK", "941.HK", "1299.HK", "388.HK", "9988.HK", "3690.HK", "1810.HK",
    "3988.HK", "3.HK", "1.HK", "2.HK", "6.HK", "11.HK", "16.HK", "27.HK",
    "66.HK", "883.HK", "857.HK", "1088.HK",
]


def timed(fn, label: str, results: dict) -> bool:
    t0 = time.perf_counter()
    try:
        n = len(fn())
        dt = time.perf_counter() - t0
        results[label] = {"n": n, "seconds": round(dt, 2),
                          "per_symbol_ms": round(dt * 1000 / max(n, 1), 2)}
        print(f"[probe] {label}: n={n}　{dt:.2f}s（{dt * 1000 / max(n, 1):.1f} ms/隻）")
        return True
    except Exception as e:  # noqa: BLE001
        results[label] = {"error": repr(e)}
        print(f"[probe] {label}: 錯誤 {e!r}")
        return False


def main() -> int:
    ensure_dirs()
    try:
        lb = LB()
    except MissingCredentialsError as e:
        print(f"[probe] {e}", file=sys.stderr)
        return 2

    res: dict = {"time": now_hkt().isoformat(), "quote_batch_config": QUOTE_BATCH}

    # 1) 20 隻基準
    if not timed(lambda: list(lb.ctx.quote(PROBE_20)), "quote_20", res):
        print("[probe] 20 隻都失敗——檢查 token／報價權限。結果：", json.dumps(res, ensure_ascii=False))
        (LOGS_DIR / f"probe_{now_hkt():%Y%m%d_%H%M}.json").write_text(
            json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        return 1

    # 2) 大批量：100 / 300 / 500 隻一批（用真實宇宙代號湊數；唔夠就用 20 隻循環）
    import pandas as pd
    from config import UNIVERSE_CSV

    pool = PROBE_20
    if UNIVERSE_CSV.exists():
        uni = pd.read_csv(UNIVERSE_CSV, dtype=str, encoding="utf-8-sig")
        pool = uni["symbol_lb"].dropna().tolist()
    for size in (100, 300, 500):
        batch = (pool * (size // len(pool) + 1))[:size] if len(pool) < size else pool[:size]
        # 重複代號會被 API 拒？保險起見去重——宇宙唔夠大就照用現有
        batch = list(dict.fromkeys(batch))
        timed(lambda b=batch: list(lb.ctx.quote(b)), f"quote_{len(batch)}", res)

    # 3) 逐隻日 K 抽樣 20 隻，估訊號 A 全宇宙耗時
    t0 = time.perf_counter()
    ok = 0
    for sym in PROBE_20:
        try:
            lb.candles_today(sym, 11)
            ok += 1
        except Exception as e:  # noqa: BLE001
            res.setdefault("candle_errors", []).append(f"{sym}: {e!r}")
        time.sleep(0.15)  # 輕微節流
    dt = time.perf_counter() - t0
    res["candle_20"] = {"ok": ok, "seconds": round(dt, 2)}
    print(f"[probe] candlesticks 20 隻：成功 {ok}，{dt:.1f}s（含 0.15s 節流）")
    if ok:
        est = dt / ok * 1564
        res["candle_full_universe_est_s"] = round(est)
        print(f"[probe] 估計 1,564 隻日 K 耗時 ≈ {est / 60:.1f} 分鐘（單線程）")

    out = LOGS_DIR / f"probe_{now_hkt():%Y%m%d_%H%M}.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[probe] 已寫 {out}\n[probe] 免責聲明：本工具只供學術研究及風險分析，不構成投資建議。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
