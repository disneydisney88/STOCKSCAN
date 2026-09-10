"""RTSS 本機一撳即用控制台。

呢個頁面只負責操作現有 RTSS scripts；抓取、parser、build、compare 仍由
scripts/fetch_rtss_cdp.py、build_rtss_alerts.py、compare_rtss_daily.py 及
import_rtss_backfill.py 執行。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from stockscan.io_utils import today_hkt


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RTSS_DIR = DATA_DIR / "rtss"
REPORT_DIR = DATA_DIR / "reports"
INTRADAY_DIR = DATA_DIR / "intraday"
DEFAULT_EXPORTER = Path(r"C:\TGWebExporter\RTSS_Output\rtss_messages.sqlite")
DEFAULT_DRIVE = Path(r"G:\我的雲端硬碟\RTSS\RTSS_TG")
DRIVE_FOLDER_ID = "1H0I2YUQn1_JRN1O3zBZUepm88YAarKpx"
CDP_VERSION_URL = "http://127.0.0.1:9222/json/version"
CDP_LIST_URL = "http://127.0.0.1:9222/json/list"

st.set_page_config(page_title="RTSS Console", page_icon="📡", layout="wide")
st.markdown(
    """
    <style>
    .block-container { max-width: 1450px; padding-top: 1.5rem; padding-bottom: 2rem; }
    [data-testid="stMetric"] { border: 1px solid rgba(128,128,128,.22); border-radius: .75rem; padding: .65rem .8rem; }
    [data-testid="stMetricValue"] { font-size: 1.35rem; }
    button[kind="primary"] { border-radius: .6rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _json_url(url: str) -> object | None:
    try:
        with urllib.request.urlopen(url, timeout=1.5) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None


def cdp_status() -> tuple[bool, str]:
    version = _json_url(CDP_VERSION_URL)
    if not isinstance(version, dict):
        return False, "Chrome CDP 未開啟"
    pages = _json_url(CDP_LIST_URL)
    if isinstance(pages, list):
        rtss = [p for p in pages if "web.telegram.org" in str(p.get("url", ""))]
        if rtss:
            return True, str(rtss[0].get("title") or "Telegram Web（RTSS）")
    return False, "CDP 已連接，但未搵到 Telegram Web RTSS tab"


def open_chrome() -> tuple[bool, str]:
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    chrome = next((p for p in candidates if p.exists()), None)
    if chrome is None:
        return False, "搵唔到 chrome.exe；請自行用 --remote-debugging-port=9222 開 Chrome。"
    try:
        subprocess.Popen(
            [str(chrome), "--remote-debugging-port=9222", r"--user-data-dir=C:\TGWebProfile",
             "https://web.telegram.org/"],
            cwd=str(ROOT),
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    except OSError as exc:
        return False, f"開 Chrome 失敗：{exc}"
    return True, "已要求 Chrome 開啟；請等幾秒再撳「重新檢查」。"


def run_script(label: str, args: list[str], output_box) -> tuple[bool, str]:
    command = [sys.executable, *args]
    output_box.write(f"▶ {label}\nCOMMAND: {' '.join(command)}")
    try:
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as exc:
        output_box.error(f"{label} 未能完成：{exc}")
        return False, str(exc)
    text = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
    if text:
        output_box.code(text[-6000:])
    if result.returncode:
        output_box.error(f"{label} 失敗（exit {result.returncode}）")
        return False, text
    return True, text


def run_pipeline(day: date, output_box, progress=None) -> bool:
    steps = [
        ("1/3 抓取 RTSS 文字", ["scripts/fetch_rtss_cdp.py", "--date", day.isoformat()]),
        ("2/3 build alert CSV", ["scripts/build_rtss_alerts.py", "--date", day.isoformat()]),
        ("3/3 compare STOCKSCAN", ["scripts/compare_rtss_daily.py", "--date", day.isoformat()]),
    ]
    for index, (label, args) in enumerate(steps, 1):
        if progress:
            progress.progress((index - 1) / len(steps), text=label)
        ok, _ = run_script(label, args, output_box)
        if not ok:
            if progress:
                progress.progress((index - 1) / len(steps), text=f"停止：{label}")
            return False
    if progress:
        progress.progress(1.0, text="完成")
    return True


def run_range(start: date, end: date, output_box, progress=None) -> bool:
    total = (end - start).days + 1
    commands = [
        ("1/3 補抓 RTSS 文字", ["scripts/fetch_rtss_cdp.py", "--backfill", "--from", start.isoformat(), "--to", end.isoformat()]),
        ("2/3 build alert CSV", ["scripts/build_rtss_alerts.py", "--backfill", "--from", start.isoformat(), "--to", end.isoformat()]),
    ]
    for index, (label, args) in enumerate(commands, 1):
        if progress:
            progress.progress((index - 1) / (total + 2), text=label)
        ok, _ = run_script(label, args, output_box)
        if not ok:
            return False
    for offset in range(total):
        day = start + timedelta(days=offset)
        label = f"3/3 對照 {day.isoformat()}（{offset + 1}/{total}）"
        ok, _ = run_script(label, ["scripts/compare_rtss_daily.py", "--date", day.isoformat()], output_box)
        if not ok:
            return False
        if progress:
            progress.progress((offset + 3) / (total + 2), text=label)
    if progress:
        progress.progress(1.0, text=f"完成：{total} 日")
    return True


def csv_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open(encoding="utf-8-sig") as handle:
            return max(0, sum(1 for _ in handle) - 1)
    except OSError:
        return 0


def show_summary(day: date) -> None:
    alerts = RTSS_DIR / f"rtss_alerts_{day:%Y%m%d}.csv"
    diff = REPORT_DIR / f"rtss_daily_diff_{day:%Y%m%d}.csv"
    frame = pd.read_csv(diff, dtype=str, encoding="utf-8-sig") if diff.exists() else pd.DataFrame()
    counts = frame["group"].value_counts() if "group" in frame else pd.Series(dtype=int)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("RTSS 抓到", csv_count(alerts))
    c2.metric("兩邊都有", int(counts.get("both", 0)))
    c3.metric("RTSS 有／我哋冇", int(counts.get("rtss_only", 0)))
    c4.metric("我哋有／RTSS 冇", int(counts.get("stockscan_only", 0)))
    st.caption(f"alerts：{alerts}　|　diff：{diff}")


def copy_to_drive(mode: str, day: date, destination: Path) -> tuple[list[Path], list[Path]]:
    if mode == "今日 diff CSV":
        files = [REPORT_DIR / f"rtss_daily_diff_{day:%Y%m%d}.csv"]
    elif mode == "指定日期 diff CSV":
        files = [REPORT_DIR / f"rtss_daily_diff_{day:%Y%m%d}.csv"]
    elif mode == "指定日期 alerts CSV":
        files = [RTSS_DIR / f"rtss_alerts_{day:%Y%m%d}.csv"]
    else:
        files = sorted(RTSS_DIR.glob("rtss_alerts_*.csv"))
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    skipped: list[Path] = []
    for source in (path for path in files if path.exists()):
        target = destination / source.name
        if target.exists():
            skipped.append(target)
            continue
        shutil.copy2(source, target)
        copied.append(target)
    return copied, skipped


def diff_dates() -> list[date]:
    result = []
    for path in sorted(REPORT_DIR.glob("rtss_daily_diff_*.csv"), reverse=True):
        try:
            result.append(date.fromisoformat(path.stem.removeprefix("rtss_daily_diff_")))
        except ValueError:
            continue
    return result


st.title("📡 RTSS Console")
st.caption(f"本機 RTSS 文字抓取控制台・所有日期以 HKT 計算：{today_hkt():%Y-%m-%d}")

connected, cdp_message = cdp_status()
status_col, action_col = st.columns([3, 1])
with status_col:
    if connected and "未搵到" not in cdp_message:
        st.success(f"🟢 {cdp_message}")
    elif connected:
        st.warning(f"🟡 {cdp_message}")
    else:
        st.error("🔴 Chrome CDP 未連接")
with action_col:
    if st.button("🔄 重新檢查", use_container_width=True):
        st.rerun()
    if not connected and st.button("🌐 開 RTSS Chrome", use_container_width=True):
        ok, message = open_chrome()
        (st.success if ok else st.error)(message)

st.divider()

today = today_hkt()
st.header("1. 抓今日（最常用）")
st.caption("一撳順序執行：fetch → build → compare。Chrome 必須開住 Telegram Web RTSS 頻道。")
if st.button("📥 抓今日 RTSS", type="primary", use_container_width=True, disabled=not connected):
    box = st.empty()
    progress = st.progress(0.0, text="準備中…")
    if run_pipeline(today, box, progress):
        st.success("今日流程完成")
        show_summary(today)
else:
    existing_today = RTSS_DIR / f"rtss_alerts_{today:%Y%m%d}.csv"
    if existing_today.exists():
        st.info("今日已有產物；如要更新，撳上面按鈕重抓。")

st.divider()
st.header("2. 指定日期／補抓範圍")
single_col, single_button = st.columns([2, 1])
with single_col:
    single_day = st.date_input("指定日期", value=today, key="single_day")
with single_button:
    st.write("")
    st.write("")
    single_run = st.button("📥 抓呢日", use_container_width=True)
if single_run:
    box = st.empty()
    progress = st.progress(0.0, text="準備中…")
    if run_pipeline(single_day, box, progress):
        st.success(f"{single_day} 完成")
        show_summary(single_day)

range_col1, range_col2, range_button = st.columns([1, 1, 1])
with range_col1:
    range_from = st.date_input("補抓起日", value=today - timedelta(days=7), key="range_from")
with range_col2:
    range_to = st.date_input("補抓終日", value=today, key="range_to")
with range_button:
    st.write("")
    st.write("")
    range_run = st.button("🗓️ 補抓範圍", use_container_width=True)
if range_run:
    if range_from > range_to:
        st.error("起日不可晚於終日。")
    else:
        box = st.empty()
        progress = st.progress(0.0, text="準備中…")
        if run_range(range_from, range_to, box, progress):
            st.success(f"已完成 {range_from} 至 {range_to}")
            st.caption("每日輸出條數：" + "、".join(
                f"{range_from + timedelta(days=i):%m-%d} {csv_count(RTSS_DIR / f'rtss_alerts_{range_from + timedelta(days=i):%Y%m%d}.csv')} 條"
                for i in range((range_to - range_from).days + 1)
            ))

st.divider()
st.header("3. 匯入 TGWebExporter 歷史檔")
st.caption("只讀 message_text；唔讀 media，唔會改動原始 SQLite／CSV。")
source = st.text_input("歷史檔路徑", value=str(DEFAULT_EXPORTER))
import_col1, import_col2, import_col3 = st.columns([1, 1, 1])
with import_col1:
    import_from = st.date_input("匯入起日", value=date(2025, 8, 29), key="import_from")
with import_col2:
    import_to = st.date_input("匯入終日", value=today, key="import_to")
with import_col3:
    st.write("")
    st.write("")
    import_run = st.button("📦 匯入歷史")
if import_run:
    if import_from > import_to:
        st.error("匯入起日不可晚於終日。")
    elif not Path(source).exists():
        st.error(f"搵唔到檔案：{source}")
    else:
        box = st.empty()
        ok, _ = run_script(
            "匯入 RTSS 歷史",
            ["scripts/import_rtss_backfill.py", "--source", source, "--from", import_from.isoformat(), "--to", import_to.isoformat()],
            box,
        )
        if ok:
            st.success("歷史匯入完成；產物仍留喺 gitignored data/rtss/。")

st.divider()
st.header("4. 送 Google Drive 交收夾")
drive_dates: list[date] = []
for path in REPORT_DIR.glob("rtss_daily_diff_*.csv"):
    try:
        drive_dates.append(datetime.strptime(path.stem.removeprefix("rtss_daily_diff_"), "%Y%m%d").date())
    except ValueError:
        continue
drive_dates = sorted(set(drive_dates), reverse=True)
drive_col1, drive_col2, drive_button = st.columns([1, 2, 1])
with drive_col1:
    drive_mode = st.selectbox("要送咩", ["今日 diff CSV", "指定日期 diff CSV",
                                           "指定日期 alerts CSV", "全部 rtss_alerts"])
with drive_col2:
    drive_path = st.text_input("固定交收夾", value=str(DEFAULT_DRIVE), disabled=True)
with drive_button:
    st.write("")
    st.write("")
    drive_run = st.button("☁️ 送去 Drive")
if drive_dates:
    drive_day = st.selectbox("指定交收日期", drive_dates, format_func=lambda d: d.isoformat(),
                             key="drive_day")
    st.caption("已有 diff：" + "、".join(d.isoformat() for d in drive_dates))
else:
    drive_day = single_day
    st.caption("目前未有 diff 產物；先完成抓取／匯入流程，再送去 Drive。")
if drive_run:
    try:
        copied, skipped = copy_to_drive(drive_mode, drive_day, Path(drive_path))
        if copied:
            st.success(f"已新增 {len(copied)} 檔到 {drive_path}")
        if skipped:
            st.info(f"已跳過 {len(skipped)} 個同名檔（唔覆蓋既有交收檔）")
        if not copied and not skipped:
            st.warning("未搵到符合條件嘅產物。")
    except OSError as exc:
        st.error(f"複製失敗：{exc}")

st.divider()
st.header("5. 歷史 diff")
available = diff_dates()
if not available:
    st.info("未有 diff report。先抓一日或補抓範圍。")
else:
    history_day = st.selectbox("選擇日期", available, format_func=lambda d: d.isoformat())
    history_path = REPORT_DIR / f"rtss_daily_diff_{history_day:%Y%m%d}.csv"
    history = pd.read_csv(history_path, dtype=str, encoding="utf-8-sig")
    groups = history["group"].value_counts() if "group" in history else pd.Series(dtype=int)
    c1, c2, c3 = st.columns(3)
    c1.metric("兩邊都有", int(groups.get("both", 0)))
    c2.metric("RTSS 有／我哋冇", int(groups.get("rtss_only", 0)))
    c3.metric("我哋有／RTSS 冇", int(groups.get("stockscan_only", 0)))
    if not history.empty:
        for group, title in (("both", "兩邊都有"), ("rtss_only", "RTSS 有／我哋冇"),
                             ("stockscan_only", "我哋有／RTSS 冇")):
            st.subheader(title)
            st.table(history[history["group"] == group].style.hide(axis="index"))
    trend_rows = []
    for d in available:
        path = REPORT_DIR / f"rtss_daily_diff_{d:%Y%m%d}.csv"
        frame = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
        vc = frame["group"].value_counts() if "group" in frame else pd.Series(dtype=int)
        trend_rows.append({"date": d.isoformat(), "rtss_only": int(vc.get("rtss_only", 0))})
    if trend_rows:
        st.subheader("RTSS-only 趨勢（我哋漏咗幾多隻）")
        st.line_chart(pd.DataFrame(trend_rows).sort_values("date").set_index("date"))

st.caption("只供學術研究及風險分析，不構成投資建議。")
