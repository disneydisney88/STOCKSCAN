"""STOCKSCAN Streamlit 入口（Streamlit Cloud 要求 root 有呢個檔名）。
三個 tab，全部只讀 data/ 產物；唯一例外係 tab 2「掃一次」（用 st.secrets 憑證）。
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (  # noqa: E402
    DISCLAIMER,
    EOD_DIR,
    INTRADAY_DIR,
    RTSS_FIXTURE_DATE,
    UNIVERSE_CSV,
)
from stockscan.io_utils import read_csv_if_exists  # noqa: E402

st.set_page_config(page_title="STOCKSCAN 倍升雷達", page_icon="📡", layout="wide")

RTSS_8_COLS = ["code5", "name", "close", "chg_pct",
               "turnover_day", "mcap_total", "ratio", "turnover_to_mcap"]


def eod_files() -> list[Path]:
    return sorted(EOD_DIR.glob("radar_eod_*.csv"), reverse=True)


def fmt_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in ("turnover_day", "mcap_total", "mcap_hk"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").map(
                lambda v: "" if pd.isna(v) else f"{v / 1e6:,.0f}M")
    return out


tab1, tab2, tab3 = st.tabs(["📊 收市爆量榜（訊號A）", "⚡ 即市掃描（訊號B）", "🔬 對照 RTSS"])

with tab1:
    files = eod_files()
    if not files:
        st.warning("未有 radar_eod_*.csv。先喺本機跑：`python scripts/run_eod.py`")
    else:
        labels = {f: f.name.replace("radar_eod_", "").replace(".csv", "") for f in files}
        pick = st.selectbox("揀日期", list(labels.keys()),
                            format_func=lambda f: labels[f])
        df = read_csv_if_exists(pick)
        if df.empty:
            st.info("呢個檔係空嘅（當日冇命中）。")
        else:
            st.caption(f"共 {len(df)} 隻，按市值由細到大（RTSS 口徑）。"
                       "成交額／市值單位：百萬港元（M）。")
            st.dataframe(fmt_df(df[RTSS_8_COLS]), use_container_width=True, hide_index=True)
            st.download_button("⬇️ 下載完整 CSV",
                               df.to_csv(index=False).encode("utf-8-sig"),
                               file_name=pick.name, mime="text/csv")

with tab2:
    st.caption("即時掃一次全宇宙：市值 <3 億、即市成交額 ≥50 萬、升幅 ≥+20%，"
               "每多升 20pt 再發一次（當日第 N 次）。alert 會追加寫入 data/intraday/。")
    if st.button("⚡ 即掃一次", type="primary"):
        try:
            from stockscan.lb_client import LB
            from stockscan.scan_intraday import scan_once

            with st.spinner("quote 全宇宙中……"):
                alerts, near, meta = scan_once(LB())
            st.success(f"掃描完成：quoted={meta['quoted']}　pool={meta['pool']}　"
                       f"新 alert={meta['alerts']}　off_hours={meta['off_hours']}　"
                       f"{meta['scan_time']}")
            if not alerts.empty:
                st.error("🚨 新 alert（級距「舊→新」）", icon="🚨")
                st.dataframe(alerts, use_container_width=True, hide_index=True)
            else:
                st.info("呢一輪冇新 alert。以下係近門檻 top 20：")
                st.dataframe(near, use_container_width=True, hide_index=True)
        except Exception as e:  # noqa: BLE001——缺 secrets 顯示提示而唔係 crash
            st.warning(
                "掃唔到：Longbridge 憑證欠齊或 API 出錯。詳情：\n\n"
                f"`{e}`\n\n"
                "Streamlit Cloud 請喺 App → Settings → Secrets 填三個變數：\n\n"
                "```toml\nLONGPORT_APP_KEY = \"…\"\nLONGPORT_APP_SECRET = \"…\"\n"
                "LONGPORT_ACCESS_TOKEN = \"…\"\n```")
    today_csv = INTRADAY_DIR / f"alerts_{date.today():%Y%m%d}.csv"
    if today_csv.exists():
        st.subheader("今日已發 alert")
        st.dataframe(read_csv_if_exists(today_csv), use_container_width=True, hide_index=True)

with tab3:
    st.caption(f"訊號 A 對照「倍升RtSS」{RTSS_FIXTURE_DATE} 榜（15 隻，手打 fixture）。"
               "命中 ≥10/15 為過關門檻。")
    cmp_path = EOD_DIR / f"compare_rtss_{RTSS_FIXTURE_DATE}.json"
    if cmp_path.exists():
        res = json.loads(cmp_path.read_text(encoding="utf-8"))
        c1, c2, c3 = st.columns(3)
        c1.metric("命中", f"{res['hit_count']}/{res['n_fixture']}")
        c2.metric("我哋多咗", len(res["extra"]))
        c3.metric("我哋漏咗", len(res["missing"]))
        st.write(f"**命中**：{', '.join(res['hits']) or '—'}")
        st.write(f"**漏咗**：{', '.join(res['missing']) or '—'}")
        st.write(f"**多咗**：{', '.join(res['extra']) or '—'}")
    else:
        st.info("未有對照結果。跑：`python scripts/run_eod.py --date 2026-09-04`")

if UNIVERSE_CSV.exists():
    uni = read_csv_if_exists(UNIVERSE_CSV)
    st.sidebar.metric("宇宙（掃描中）", int((uni["in_scan"] == 1).sum()))
    st.sidebar.metric("宇宙（總數）", len(uni))

st.sidebar.caption(DISCLAIMER)
st.caption("—" * 40)
st.caption(DISCLAIMER)
