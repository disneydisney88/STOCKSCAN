"""STOCKSCAN Streamlit 入口（Streamlit Cloud 要求 root 有呢個檔名）。
四個 tab，全部只讀 data/ 產物；唯一例外係 tab 2「掃一次」（本機用，Cloud 顯示唯讀 alerts）。
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
    DATA_DIR,
    EOD_DIR,
    INTRADAY_DIR,
    RTSS_FIXTURE_DATE,
    UNIVERSE_CSV,
)
from stockscan.io_utils import read_csv_if_exists, today_hkt  # noqa: E402

st.set_page_config(page_title="STOCKSCAN 倍升雷達", page_icon="📡", layout="wide")

RTSS_8_COLS = ["code5", "name", "close", "chg_pct",
               "turnover_day", "mcap_total", "ratio", "turnover_to_mcap"]


def eod_files() -> list[Path]:
    return sorted(EOD_DIR.glob("radar_eod_*.csv"), reverse=True)


def fmt_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in ("turnover_day", "mcap_total", "mcap_hk", "turnover_intraday", "mcap_now"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").map(
                lambda v: "" if pd.isna(v) else f"{v / 1e6:,.0f}M")
    return out


def data_asof(df: pd.DataFrame) -> str:
    if df.empty or "scan_time" not in df.columns:
        return "—"
    return str(df["scan_time"].dropna().max())[:16]


tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["📊 收市爆量榜（訊號A）", "⚡ 即市掃描（訊號B）", "🔬 對照 RTSS", "🗂 歷史面板", "📈 事件率",
     "🔎 個股研究"])

with tab1:
    files = [f for f in eod_files() if f.name not in {"radar_eod_panel.csv", "radar_eod_panel_full.csv"}]
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
                       "成交額／市值單位：百萬港元（M）。　數據截至：" + data_asof(df))
            st.table(fmt_df(df[RTSS_8_COLS]).style.hide(axis="index"))
            st.download_button("⬇️ 下載完整 CSV",
                               df.to_csv(index=False).encode("utf-8-sig"),
                               file_name=pick.name, mime="text/csv")

with tab2:
    st.caption("SURGE（急升）：市值 <10 億、即市成交 ≥50 萬、升幅 ≥+20%，每多 20pt 再發；"
               "VOLUME（爆量）：即市成交 ÷ ma10 ≥ 10x，每多 10x 再發。各計「當日第 N 次」。")
    left, right = st.columns([1, 2])
    with left:
        run_btn = st.button("⚡ 即掃一次（本機）", type="primary",
                            help="Streamlit Cloud 無快取時會即場拉 40 支日 K，較慢；alert 要 secrets")
    if run_btn:
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
                st.table(alerts.style.hide(axis="index"))
            else:
                st.info("呢一輪冇新 alert。以下係近門檻 top 20：")
                st.table(near.style.hide(axis="index"))
        except Exception as e:  # noqa: BLE001——缺 secrets 顯示提示而唔係 crash
            st.warning(
                "掃唔到：Longbridge 憑證欠齊或 API 出錯。詳情：\n\n"
                f"`{e}`\n\n"
                "Streamlit Cloud 請喺 App → Settings → Secrets 填（LONGBRIDGE_ 或 LONGPORT_ 前綴都得）：\n\n"
                "```toml\nLONGBRIDGE_APP_KEY = \"…\"\nLONGBRIDGE_APP_SECRET = \"…\"\n"
                "LONGBRIDGE_ACCESS_TOKEN = \"…\"\n```")
    alert_files = sorted(INTRADAY_DIR.glob("alerts_*.csv"), reverse=True)
    if alert_files:
        st.subheader(f"最近 alert（{alert_files[0].name}）——唯讀")
        adf = read_csv_if_exists(alert_files[0])
        if not adf.empty:
            st.caption("數據截至：" + str(adf["ts"].dropna().max()))
            st.table(adf.sort_values("ts", ascending=False).style.hide(axis="index"))
    else:
        st.info("未有 alerts_*.csv。本機跑 `python scripts/run_intraday.py --once`。")

    # ── P4 Z1b：時點快照 ──
    snap_files = sorted(INTRADAY_DIR.glob("snapshot_*.csv"), reverse=True)
    if snap_files:
        st.subheader("📷 時點快照（每日 10:30／11:30／13:30／15:30／16:00）")
        snap = snap_files[0]
        sdf = read_csv_if_exists(snap)
        if not sdf.empty:
            # 本日首次出現：呢張快照有、之前嘅快照冇 → ⭐ 排先
            earlier_codes = set()
            for f in snap_files[1:]:
                if f.name[9:17] == snap.name[9:17]:  # 同一日
                    prev = read_csv_if_exists(f)
                    if not prev.empty and "code5" in prev.columns:
                        earlier_codes |= set(prev["code5"].astype(str))
            sdf["code5"] = sdf["code5"].astype(str)
            sdf["首次出現"] = ~sdf["code5"].isin(earlier_codes)
            sdf = sdf.sort_values("首次出現", ascending=False).reset_index(drop=True)
            sdf["name"] = sdf.apply(
                lambda r: ("⭐ " + str(r["name"])) if r["首次出現"] else r["name"], axis=1)
            st.caption(f"{snap.name.replace('snapshot_', '').replace('.csv', '')}　"
                       f"ratio≥10 共 {len(sdf)} 隻（⭐＝本日首次出現）")
            st.dataframe(sdf, use_container_width=True, hide_index=True)
    else:
        st.caption("未有時點快照（daemon 會喺 10:30/11:30/13:30/15:30/16:00 自動寫）。")

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

with tab4:
    panel = read_csv_if_exists(EOD_DIR / "radar_eod_panel.csv")
    if panel.empty:
        st.info("未有面板。跑：`python scripts/backfill_eod.py --start 2026-08-10 --end 2026-09-07`")
    else:
        st.caption(f"面板 {len(panel)} 行、{panel['scan_date'].nunique()} 個交易日。"
                   "　數據截至：" + data_asof(panel))
        daily = panel.groupby("scan_date").size()
        st.bar_chart(daily, height=220)
        st.caption("每日上榜數（訊號 A 命中）")
        c1, c2 = st.columns([1, 2])
        with c1:
            top = panel["code5"].value_counts().head(15)
            st.table(pd.DataFrame({
                    "code5": top.index,
                    "上榜次數": top.values,
                    "名稱": [panel.loc[panel["code5"] == c, "name"].iloc[0] for c in top.index],
                }).style.hide(axis="index"))
        with c2:
            pick_code = st.selectbox("點一隻股睇佢所有上榜日", top.index,
                                     format_func=lambda c: f"{c} "
                                     f"{panel.loc[panel['code5'] == c, 'name'].iloc[0]}")
            rows = panel[panel["code5"] == pick_code].sort_values("scan_date")
            st.dataframe(fmt_df(rows[["scan_date", "close", "chg_pct", "turnover_day",
                                      "mcap_total", "ratio", "turnover_to_mcap"]]),
                         use_container_width=True, height=800, hide_index=True)

with tab5:
    report = DATA_DIR / "reports" / "go_timing_summary.csv"
    if not report.exists():
        st.info("未有事件率報表。跑：`python scripts/report_go_timing.py`")
    else:
        rdf = read_csv_if_exists(report)
        st.caption("只列數字；事件窗口由上榜日開始計算。")
        st.table(rdf.style.hide(axis="index"))

with tab6:
    # ── P4 Z3：個股研究頁——一頁睇晒一隻股喺所有庫嘅紀錄（研究用）──
    import sqlite3
    from datetime import datetime as _dt

    from stockscan import kline_cache
    from stockscan.events import events_after

    st.caption("輸入 5 位代號，聚合宇宙／面板／事件庫／券商射倉／RTSS 回放／CCASS／即市 alert。研究用，唔構成投資建議。")
    code_input = st.text_input("股票代號（5 位）", value="01825", max_chars=5).strip().zfill(5)

    uni_all = read_csv_if_exists(UNIVERSE_CSV)
    row_u = uni_all[uni_all["code5"] == code_input]
    if row_u.empty:
        st.warning(f"{code_input} 唔喺宇宙（檢查代號，或者佢唔喺 universe.csv）。")
    else:
        u = row_u.iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("名稱", str(u.get("name_hk") or u.get("name_seed", ""))[:10])
        ts_total = pd.to_numeric(u.get("total_shares"), errors="coerce")
        c2.metric("總股數", f"{ts_total / 1e6:,.0f}M" if pd.notna(ts_total) else "—")
        c3.metric("in_seed(08-31)", str(u.get("in_seed", "—")))
        c4.metric("REIT", str(u.get("is_reit", "—")))

        # 1) 價格＋上榜日（13 個月快取）
        kdf = kline_cache.load(code_input)
        panel_full = read_csv_if_exists(EOD_DIR / "radar_eod_panel_full.csv")
        if panel_full.empty:
            panel_full = read_csv_if_exists(EOD_DIR / "radar_eod_panel.csv")
        hit_days = set()
        if not panel_full.empty:
            hits = panel_full[panel_full["code5"] == code_input]
            hit_days = set(hits["scan_date"]) if "scan_date" in hits.columns else set()
        if kdf is None or kdf.empty:
            st.info("快取無價格紀錄。")
        else:
            kdf = kdf.copy()
            kdf["上榜"] = kdf["date"].isin(hit_days)
            kdf["date_dt"] = pd.to_datetime(kdf["date"])
            chart = kdf.set_index("date_dt")[["close"]]
            st.line_chart(chart, height=200)
            n_hit = int(kdf["上榜"].sum())
            st.caption(f"快取 {len(kdf)} 支（{kdf['date'].iloc[0]}→{kdf['date'].iloc[-1]}）；"
                       f"面板上榜 {n_hit} 日"
                       + (f"：{', '.join(sorted(hit_days))}" if hit_days else ""))

        # 2) 事件（最近 24 個月）
        st.subheader("📅 事件（24 個月內）")
        try:
            evs = events_after(code_input, (today_hkt() - pd.Timedelta(days=730).to_pytimedelta()), 730)
        except Exception as e:  # noqa: BLE001
            evs = []
            st.caption(f"事件庫讀取失敗：{e!r}")
        if evs:
            st.dataframe(pd.DataFrame(evs)[
                ["event_type", "announce_date", "key_date_1", "ratio", "status"]
            ], use_container_width=True, hide_index=True)
        else:
            st.write("無紀錄")

        # 3) 券商射倉：面板上榜日 ±5 日
        st.subheader("🏛 券商射倉（上榜日 ±5 日）")
        shots = read_csv_if_exists(DATA_DIR / "broker_shots.csv")
        shown_shots = False
        if not shots.empty and hit_days and "code5" in shots.columns:
            sc = shots[shots["code5"] == code_input].copy()
            if not sc.empty and "date" in sc.columns:
                sc["date_dt"] = pd.to_datetime(sc["date"], errors="coerce")
                near_rows = sc[sc["date_dt"].apply(
                    lambda x: any(abs((x - pd.Timestamp(h)).days) <= 5 for h in hit_days))]
                if not near_rows.empty:
                    st.dataframe(near_rows.drop(columns=["date_dt"]),
                                 use_container_width=True, hide_index=True)
                    shown_shots = True
        if not shown_shots:
            st.write("無紀錄")

        # 4) RTSS 歷史回放（M6）
        st.subheader("🔁 RTSS 歷史回放（522 條研究）")
        nf = read_csv_if_exists(DATA_DIR / "reports" / "n_count_forward.csv")
        if nf.empty or "code5" not in nf.columns:
            st.write("無紀錄")
        else:
            nr = nf[nf["code5"].astype(str).str.zfill(5) == code_input]
            if nr.empty:
                st.write("無紀錄")
            else:
                st.caption(f"出現 {len(nr)} 次（n_max_est 為歷史估算）")
                st.dataframe(nr, use_container_width=True, hide_index=True)

        # 5) CCASS（M7）
        st.subheader("🏦 CCASS 集中度和主要變動")
        cc_dir = DATA_DIR / "ccass" / code_input
        cc_files = sorted(cc_dir.glob("*.json")) if cc_dir.exists() else []
        if not cc_files:
            st.write("無紀錄（上游 Render API 修復後，跑 `python scripts/run_ccass.py` 會生成）")
        else:
            for f in cc_files[-3:]:
                st.caption(f"📄 {f.name}")
                st.json(json.loads(f.read_text(encoding="utf-8")))

        # 6) 即市 alert（今日）
        st.subheader("⚡ 即市 alert（所有日子）")
        hit_alerts = []
        for af in sorted(INTRADAY_DIR.glob("alerts_*.csv"), reverse=True)[:5]:
            adf = read_csv_if_exists(af)
            if not adf.empty and "code5" in adf.columns:
                m = adf[adf["code5"].astype(str).str.zfill(5) == code_input]
                if not m.empty:
                    hit_alerts.append(m)
        if hit_alerts:
            st.dataframe(pd.concat(hit_alerts, ignore_index=True),
                         use_container_width=True, hide_index=True)
        else:
            st.write("無紀錄")

if UNIVERSE_CSV.exists():
    uni = read_csv_if_exists(UNIVERSE_CSV)
    st.sidebar.metric("宇宙（掃描中）", int((uni["in_scan"] == 1).sum()))
    st.sidebar.metric("宇宙（總數）", len(uni))

st.sidebar.caption(DISCLAIMER)
st.caption("—" * 40)
st.caption(DISCLAIMER)
