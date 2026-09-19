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

st.markdown(
    """
    <style>
    .block-container { max-width: 1600px; padding-top: 1.5rem; padding-bottom: 2rem; }
    [data-testid="stMetric"] { border: 1px solid rgba(128,128,128,.22); border-radius: .75rem; padding: .65rem .8rem; }
    [data-testid="stMetricValue"] { font-size: 1.35rem; }
    button[kind="primary"] { border-radius: .6rem; }
    [data-testid="stTabs"] button { font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown("## 📡 STOCKSCAN 倍升雷達")
st.caption(f"港股價量監控・RTSS 對照・研究面板　｜　今日 HKT：{today_hkt():%Y-%m-%d}")
st.divider()

st.sidebar.title("📡 STOCKSCAN")
st.sidebar.caption("港股價量監控儀表板")
st.sidebar.divider()
st.sidebar.subheader("快速導覽")
st.sidebar.markdown(
    "**收市榜**：睇訊號 A 排行\n\n"
    "**即市掃描**：睇訊號 B 同時點快照\n\n"
    "**個股研究**：輸入 5 位代號查完整紀錄"
)
st.sidebar.caption(f"資料日曆以 HKT 計算：{today_hkt():%Y-%m-%d}")

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


tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11, tab12 = st.tabs(
    ["📊 收市爆量榜（訊號A）", "⚡ 即市掃描（訊號B）", "🔬 對照 RTSS", "🗂 歷史面板", "📈 事件率",
     "🔎 個股研究", "9️⃣ RTSS 對照", "🐤 春江鴨", "🧩 L 型候選", "📕 追蹤簿", "🧭 GO 預示器",
     "🧮 集中度歷史"])

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
            c1, c2, c3 = st.columns(3)
            c1.metric("上榜股票", len(df))
            ratios = pd.to_numeric(df.get("ratio"), errors="coerce")
            c2.metric("最高成交倍數", f"{ratios.max():,.1f}x" if ratios.notna().any() else "—")
            c3.metric("數據截至", data_asof(df))
            st.caption(f"共 {len(df)} 隻，按市值由細到大（RTSS 口徑）。"
                       "成交額／市值單位：百萬港元（M）。　數據截至：" + data_asof(df))
            st.table(fmt_df(df[RTSS_8_COLS]).style.hide(axis="index"))
            st.download_button("⬇️ 下載完整 CSV",
                               df.to_csv(index=False).encode("utf-8-sig"),
                               file_name=pick.name, mime="text/csv")

with tab2:
    with st.expander("ℹ️ 掃描規則（按需要展開）"):
        st.markdown("SURGE（急升）：市值 <10 億、即市成交 ≥50 萬、升幅 ≥+20%，每多 20pt 再發。\n\n"
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
    # A2.3：優先讀 Turso（雲 Cron＋本機 daemon 嘅單一真相），讀唔到 fallback 本機 CSV
    adf = None
    try:
        from stockscan import turso_state

        if turso_state.configured():
            adf = turso_state.recent_alerts(days=3, limit=500)
            if adf is not None and not adf.empty:
                st.subheader("最近 alert——來源：Turso（雲＋本機，最近 3 日）")
                st.caption("數據截至：" + str(adf["ts"].dropna().max()))
                st.table(adf.style.hide(axis="index"))
    except Exception as e:  # noqa: BLE001——Turso 抽風 fallback 本機
        st.caption(f"Turso 讀取失敗，改用本機 CSV（{e!r}）")
    alert_files = sorted(INTRADAY_DIR.glob("alerts_*.csv"), reverse=True)
    if adf is None or adf.empty:
        if alert_files:
            st.subheader(f"最近 alert（{alert_files[0].name}）——唯讀（本機 CSV fallback）")
            adf = read_csv_if_exists(alert_files[0])
            if not adf.empty:
                st.caption("數據截至：" + str(adf["ts"].dropna().max()))
                st.table(adf.sort_values("ts", ascending=False).style.hide(axis="index"))
        else:
            st.info("未有 alerts。本機跑 `python scripts/run_intraday.py --once`，"
                    "或者 Render Cron 起好之後自動有。")

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
            st.dataframe(sdf, use_container_width=True, height=800, hide_index=True)
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
            ], use_container_width=True, height=800, hide_index=True)
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
                                 use_container_width=True, height=800, hide_index=True)
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
                st.dataframe(nr, use_container_width=True, height=800, hide_index=True)

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
                         use_container_width=True, height=800, hide_index=True)
        else:
            st.write("無紀錄")

with tab7:
    st.caption("逐日 RTSS 純文字 alert 對照 STOCKSCAN 即市 alert；原始 RTSS 文字不會上載或顯示。")
    diff_files = sorted((DATA_DIR / "reports").glob("rtss_daily_diff_*.csv"), reverse=True)
    if not diff_files:
        st.info("未有逐日 diff。先跑 `python scripts/compare_rtss_daily.py --date YYYY-MM-DD`。")
    else:
        diff_dates = {f: f.stem.replace("rtss_daily_diff_", "") for f in diff_files}
        pick_diff = st.selectbox("揀日期", diff_files, format_func=lambda f: diff_dates[f])
        ddf = read_csv_if_exists(pick_diff)
        counts = ddf["group"].value_counts() if not ddf.empty and "group" in ddf.columns else pd.Series(dtype=int)
        c1, c2, c3 = st.columns(3)
        c1.metric("兩邊都有", int(counts.get("both", 0)))
        c2.metric("RTSS 有／我哋冇", int(counts.get("rtss_only", 0)))
        c3.metric("我哋有／RTSS 冇", int(counts.get("stockscan_only", 0)))
        if not ddf.empty:
            trend_rows = []
            for f in diff_files:
                t = read_csv_if_exists(f)
                vc = t["group"].value_counts() if not t.empty and "group" in t.columns else pd.Series(dtype=int)
                trend_rows.append({
                    "date": diff_dates[f],
                    "both": int(vc.get("both", 0)),
                    "rtss_only": int(vc.get("rtss_only", 0)),
                    "stockscan_only": int(vc.get("stockscan_only", 0)),
                })
            st.subheader("逐日 diff 趨勢")
            trend = pd.DataFrame(trend_rows).sort_values("date").set_index("date")
            st.line_chart(trend, height=220)
            for group, title in (("both", "兩邊都有"), ("rtss_only", "RTSS 有／我哋冇"),
                                 ("stockscan_only", "我哋有／RTSS 冇")):
                st.subheader(title)
                part = ddf[ddf["group"] == group]
                st.dataframe(part, use_container_width=True, height=800, hide_index=True)
        else:
            st.info("呢日未有可對照資料。")

with tab8:
    st.caption("春江鴨＝爆量上榜 ＋ 貨源異動證據（上榜日 ±5 日有券商射倉；CCASS Top10 待 M7 上游通後自動補）。只列旗標，唔構成投資建議。")
    duck_files = sorted((DATA_DIR / "reports").glob("spring_duck_*.csv"), reverse=True)
    if not duck_files:
        st.info("未有報表。跑：`python scripts/spring_duck.py`")
    else:
        ddf = read_csv_if_exists(duck_files[0])
        flagged = ddf[ddf["spring_duck_flag"] == 1] if not ddf.empty else ddf
        st.caption(f"{duck_files[0].name}　flag=1 共 {len(flagged)}/{len(ddf)} 行")
        if not flagged.empty:
            pick_day = st.selectbox("揀日期", sorted(flagged["scan_date"].unique(), reverse=True),
                                    key="duck_day")
            st.dataframe(flagged[flagged["scan_date"] == pick_day],
                         use_container_width=True, height=800, hide_index=True)

with tab9:
    st.caption("L 型候選＝過去 180 日有 GO／換主，之後未見配股供股（等表演）。只列旗標，唔構成投資建議。")
    l_files = sorted((DATA_DIR / "reports").glob("l_shape_candidates_*.csv"), reverse=True)
    if not l_files:
        st.info("未有報表。跑：`python scripts/l_shape.py`")
    else:
        ldf = read_csv_if_exists(l_files[0])
        if ldf.empty:
            st.write("無紀錄")
        else:
            stage = st.selectbox("篩 stage", ["全部", "GO_等表演", "GO_已配供"], key="l_stage")
            show = ldf if stage == "全部" else ldf[ldf["l_shape_stage"] == stage]
            st.caption(f"{l_files[0].name}　{len(show)}/{len(ldf)} 隻")
            st.dataframe(show, use_container_width=True, height=800, hide_index=True)

with tab10:
    # ── P6 追蹤簿：上榜嗰刻起追 t+5/10/20/60（規格書 §5）──
    st.caption("追蹤簿：每股由上榜嗰刻起追 t+5/10/20/60 價格變化（收市對收市，M2 快取）。"
               "entry_intraday 暫用同日收市做代理（eod_proxy）；合股／拆股跳空窗口嘅 ret 已標 _est=1。"
               "只列數字，不構成投資建議。")
    tf = read_csv_if_exists(DATA_DIR / "reports" / "tracking_first.csv")
    te = read_csv_if_exists(DATA_DIR / "reports" / "tracking_each.csv")
    tsum = read_csv_if_exists(DATA_DIR / "reports" / "tracking_summary.csv")
    if tf.empty or te.empty:
        st.info("未有追蹤簿。跑：`python scripts/build_tracking.py`")
    else:
        book_pick = st.selectbox(
            "揀簿", ["簿A・首次入冊（每股一筆）", "簿B・每次入冊（每上榜日一筆）"], key="trk_book")
        book_key = "first" if book_pick.startswith("簿A") else "each"
        df = tf if book_key == "first" else te
        grp_pick = st.selectbox(
            "揀組", ["全部", "有財技（上榜後180日內 GO/供股/配股/合股/CB）", "冇財技"], key="trk_grp")
        if grp_pick.startswith("有"):
            show = df[df["has_capital_action"] == 1]
        elif grp_pick.startswith("冇"):
            show = df[df["has_capital_action"] == 0]
        else:
            show = df

        # 摘要卡：兩組 t20 中位對比（只計非 _est）
        if not tsum.empty:
            s20 = tsum[(tsum["book"] == book_key) & (tsum["horizon"] == "t20")]
            med = {r["group"]: r["median_ret_pct"] for _, r in s20.iterrows()}
            n = {r["group"]: r["n_clean"] for _, r in s20.iterrows()}

            def _fmt(v):
                return f"{float(v):+.2f}%" if v not in ("", None) and str(v) != "nan" else "—"
            c1, c2, c3 = st.columns(3)
            c1.metric("t20 中位・有財技", _fmt(med.get("with_ca")),
                      f"n={n.get('with_ca', 0)}（非_est）")
            c2.metric("t20 中位・冇財技", _fmt(med.get("without_ca")),
                      f"n={n.get('without_ca', 0)}（非_est）")
            c3.metric("t20 中位・全部", _fmt(med.get("all")),
                      f"n={n.get('all', 0)}（非_est）")
            st.caption("中位數只計 ret_t20 非 _est 行；_est 行數見 tracking_summary.csv n_est 欄。")

        st.subheader(f"明細（{len(show)} 行）")
        st.dataframe(show, use_container_width=True, height=520, hide_index=True)

        # 個股 drill-down：所有上榜日 + 價格路徑
        st.subheader("個股 drill-down")
        from stockscan import kline_cache
        codes = sorted(show["code5"].astype(str).unique())
        if codes:
            pick = st.selectbox(
                "揀股", codes,
                format_func=lambda c: f"{c} {df.loc[df['code5'] == c, 'name'].iloc[0]}",
                key="trk_code")
            rows = te[te["code5"] == pick].sort_values("scan_date")
            st.caption(f"{pick} 共上榜 {len(rows)} 次（簿B 逐筆）")
            st.dataframe(rows, use_container_width=True, height=420, hide_index=True)
            kdf = kline_cache.load(pick)
            if kdf is not None and not kdf.empty:
                kdf = kdf.copy()
                kdf["date_dt"] = pd.to_datetime(kdf["date"])
                chart = kdf.set_index("date_dt")[["close"]]
                st.line_chart(chart, height=260)
                entry_pts = kdf[kdf["date"].isin(set(rows["scan_date"]))]
                if not entry_pts.empty:
                    st.scatter_chart(entry_pts.set_index("date_dt")[["close"]], height=260)
                st.caption(f"快取價格路徑 {kdf['date'].iloc[0]}→{kdf['date'].iloc[-1]}；"
                           f"散點＝上榜日收市（entry_close）")

        # L 型版本子區
        st.subheader("L 型版本對比（季度）")
        ldiff = read_csv_if_exists(DATA_DIR / "reports" / "l_shape_version_diff.csv")
        if not ldiff.empty:
            st.caption("新入／畢業（開始配股表演）／跌出——只列名單變化。")
            st.dataframe(ldiff, use_container_width=True, height=300, hide_index=True)
        for qcsv in sorted((DATA_DIR / "reports").glob("l_shape_20*_Q*.csv")):
            with st.expander(f"📄 {qcsv.name}"):
                st.dataframe(read_csv_if_exists(qcsv), use_container_width=True, height=300,
                             hide_index=True)

with tab11:
    st.caption("GO/供股預示器只展示事前特徵與歷史關聯；不構成投資建議。小樣本會標記 insufficient_sample。")
    gp = read_csv_if_exists(DATA_DIR / "reports" / "go_predictors.csv")
    rp = read_csv_if_exists(DATA_DIR / "reports" / "rights_predictors.csv")
    gf = read_csv_if_exists(DATA_DIR / "reports" / "go_features.csv")
    if gp.empty or gf.empty:
        st.info("未有 GO 報表。先跑：`python scripts/build_go_predictors.py`")
    else:
        left, right = st.columns(2)
        with left:
            st.subheader("GO predictors")
            st.dataframe(gp, use_container_width=True, hide_index=True)
        with right:
            st.subheader("Rights predictors")
            st.dataframe(rp, use_container_width=True, hide_index=True)
        st.subheader("事前篩選（flag-only）")
        feature = st.selectbox("特徵", [c for c in FEATURES if c in gf.columns] if "FEATURES" in globals() else ["appearance_seq", "recurrence", "prior_go_365d"])
        if feature in gf.columns:
            vals = sorted(gf[feature].dropna().astype(str).unique())
            chosen = st.multiselect("值", vals, default=vals[:1])
            current = gf[gf["scan_date"] == gf["scan_date"].max()] if "scan_date" in gf else gf
            if chosen:
                current = current[current[feature].astype(str).isin(chosen)]
            st.dataframe(current, use_container_width=True, hide_index=True)

with tab12:
    # ── P6c 集中度歷史：三源合併（dump of-issued / Turso cache 近窗 / holdings_daily）
    # ＋ adjusted_concentration（剔除結算所/非流通塊）──
    st.caption("逐日 CCASS Top10%：三個源各自標明（Webb dump of-issued＝2025H2 主力、"
               "warm cache 近 15 個結算日、holdings_daily of-CCASS 僅參考）。"
               "CCASS 為 T-2 結算日數據；只列數字，不構成投資建議。")
    code12 = st.text_input("股票代號（5 位）", value="01825", max_chars=5,
                           key="conc_code").strip().zfill(5)

    feat12 = read_csv_if_exists(DATA_DIR / "reports" / "ccass_concentration_features.csv")
    row12 = feat12[feat12["code5"] == code12] if not feat12.empty else pd.DataFrame()

    from stockscan.ccass_turso import concentration_series, fetch_stock_payloads
    try:
        payloads = fetch_stock_payloads([code12])
        series = concentration_series(payloads.get(code12) or [])
    except Exception as e:  # noqa: BLE001——Turso 讀唔到唔好炸成個 tab
        series = []
        st.warning(f"Turso 讀取失敗：{e!r}")

    chart_rows = []
    for r in series:  # warm cache 源（近窗，webb 原始口徑）
        if r["date"] and r["top10_pct"] not in (None, ""):
            chart_rows.append({"date": r["date"], "Top10%（warm cache）":
                               float(r["top10_pct"])})
    if not row12.empty:
        for _, r in row12.iterrows():  # dump 源（2025H2，of-issued）
            if str(r.get("dump_asof_date") or "") and str(r.get("dump_top10_pct_of_issued_raw") or ""):
                chart_rows.append({"date": str(r["dump_asof_date"]),
                                   "Top10%（dump of-issued）":
                                   float(r["dump_top10_pct_of_issued_raw"])})
        for _, r in row12.iterrows():  # holdings_daily 參考源
            if str(r.get("hd_asof_date") or "") and str(r.get("hd_top10_pct_of_ccass") or ""):
                chart_rows.append({"date": str(r["hd_asof_date"]),
                                   "Top10%（holdings_daily of-CCASS）":
                                   float(r["hd_top10_pct_of_ccass"])})
    if chart_rows:
        cdf = pd.DataFrame(chart_rows).drop_duplicates(["date"], keep="first")
        for src_col in ("Top10%（warm cache）", "Top10%（dump of-issued）",
                        "Top10%（holdings_daily of-CCASS）"):
            if src_col in cdf:
                cdf[src_col] = pd.to_numeric(cdf[src_col], errors="coerce")
        cdf = cdf.groupby("date", as_index=True).max().sort_index()
        st.line_chart(cdf, height=300)
        st.caption(f"{len(cdf)} 個有數據日子；三條線口徑唔同，唔可以直接互相比。")
    else:
        st.info(f"{code12} 暫時三個源都冇集中度紀錄（未 warm／dump 冇呢隻）。")

    if not row12.empty:
        show_cols = [c for c in ("scan_date", "dump_asof_date", "dump_top10_pct_of_issued",
                                 "dump_concentration_rising", "dump_corp_action_in_window",
                                 "ccass_top10_pct", "hd_top10_pct_of_ccass")
                     if c in row12.columns]
        st.subheader("追蹤簿上榜日嘅 as-of 值（T-2 交易日對齊）")
        st.dataframe(row12[show_cols], use_container_width=True, height=280, hide_index=True)

    # 財技事件旗（上榜研究必睇嘅背景）
    import sqlite3
    with sqlite3.connect(DATA_DIR / "events.db") as econ:
        evs = pd.read_sql_query(
            "SELECT event_type, announce_date, key_date_1, status FROM events "
            "WHERE code5 = ? AND announce_date >= '2025-01-01' "
            "ORDER BY announce_date DESC LIMIT 20",
            econ, params=(code12,))
    if not evs.empty:
        st.subheader("財技事件（2025 起）")
        st.dataframe(evs, use_container_width=True, height=240, hide_index=True)

    # ⑦ adjusted_concentration（剔除結算所／非流通塊）——需要持股明細
    st.subheader("調整後集中度（adjusted concentration）")
    holdings_rows = (payloads.get(code12) or {}).get("holdings") or []
    if holdings_rows:
        from stockscan.adjusted_concentration import compute_concentration
        holdings = [{"pid": str(h.get("participant_id") or h.get("ID") or h.get("pid") or ""),
                     "name": str(h.get("participant_name") or h.get("Name") or ""),
                     "shares": int(h.get("holding") or h.get("shares") or 0)}
                    for h in holdings_rows if (h.get("holding") or h.get("shares"))]
        if holdings:
            m12 = compute_concentration(holdings)
            st.caption("剔除規則未設定（exclude_ids 空）＝raw 指標；A 字頭參與者語義要自己核實先填。")
            st.json({k: m12[k] for k in ("ccass_total_shares", "adj_top5_pct", "adj_top10_pct",
                                         "adj_hhi", "participant_count", "flags")
                     if k in m12})
        else:
            st.info("有 holdings 明細但解析唔到持股欄位。")
    else:
        st.info("warm cache（hybrid_light）冇 Holdings 明細——adjusted 版要等 dump `holdings` 表"
                "重抽（17GB dump 重新提供後）或 Render holdings 修復。fail-loud 唔拼湊。")

if UNIVERSE_CSV.exists():
    uni = read_csv_if_exists(UNIVERSE_CSV)
    st.sidebar.metric("宇宙（掃描中）", int((uni["in_scan"] == 1).sum()))
    st.sidebar.metric("宇宙（總數）", len(uni))

st.sidebar.divider()
st.sidebar.caption("提示：先揀上方 tab，再用日期／代號篩選；表格可橫向拖動。")

st.sidebar.caption(DISCLAIMER)
st.caption("—" * 40)
st.caption(DISCLAIMER)
