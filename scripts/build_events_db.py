"""Build data/events.db from the immutable event CSVs in data/raw/."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_DIR

RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "events.db"

TYPE_BY_FILE = {
    "配股事件": "PLACING",
    "供股事件": "RIGHTS",
    "全購事件": "GO",
    "可換股債券事件": "CB",
    "合股事件": "CONSOLIDATION",
    "拆股事件": "SPLIT",
    "轉主板事件": "TRANSFER_MB",
    "半新股事件": "IPO",
    "殼股價值分析": "SHELL_VALUE",
    "配售代理大數據": "PLACING_AGENT",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_type TEXT NOT NULL,
    code5 TEXT NOT NULL,
    name TEXT,
    announce_date TEXT,
    key_date_1 TEXT,
    key_date_2 TEXT,
    price_1 REAL,
    price_2 REAL,
    ratio TEXT,
    agent TEXT,
    status TEXT,
    raw_json TEXT NOT NULL,
    date_parse_failed INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_events_code_date
    ON events(code5, announce_date);
CREATE INDEX IF NOT EXISTS idx_events_type_date
    ON events(event_type, announce_date);
"""


def parse_date(value) -> tuple[str | None, int]:
    """Parse the known spreadsheet date variants without dropping failures."""
    if value is None or pd.isna(value):
        return None, 1
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.date().isoformat() if hasattr(value, "date") else value.isoformat(), 0
    text = str(value).strip().replace("／", "/").replace("－", "-")
    if not text or text in {"-", "—", "未公佈", "N/A", "nan"}:
        return None, 1
    text = re.sub(r"[年月]", "/", text.replace("日", ""))
    text = re.sub(r"[.。]", "/", text)
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y",
                "%m/%d/%Y", "%m-%d-%Y", "%Y/%m", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat(), 0
        except ValueError:
            continue
    try:
        parsed = pd.to_datetime(text, dayfirst=True, errors="raise")
        return parsed.date().isoformat(), 0
    except (TypeError, ValueError):
        return None, 1


def clean_code(value) -> str:
    text = "" if value is None or pd.isna(value) else str(value).strip()
    match = re.search(r"(\d{1,5})(?:\.hk)?$", text, flags=re.I)
    return match.group(1).zfill(5) if match else ""


def first_number(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group()) if match else None


def pick(row: dict, *names: str):
    for name in names:
        if name in row and pd.notna(row[name]) and str(row[name]).strip() not in {"", "-", "—"}:
            return row[name]
    return None


def transform_row(event_type: str, row: dict) -> tuple:
    code = clean_code(pick(row, "代號", "編號", "股票編號", "股票"))
    name = pick(row, "名稱", "公司名稱", "公司名稱（資料內共識）")
    announce = pick(row, "公佈日", "公佈日期", "上市日", "日期", "整理用日期時間")
    key1 = pick(row, "除權日", "生效日期", "完成配售日期", "開始接納", "批准日", "上市半年")
    key2 = pick(row, "供股權開始", "最後接納", "轉板日", "上市一年", "派送日")
    price1 = pick(row, "供股價 /溢價(折讓)", "要約價 /溢價(折讓)", "換股價 / 現價", "配股價 / 溢價(折讓)", "招股價")
    price2 = pick(row, "現價 /溢價(折讓)", "現價 / 溢價(折讓)", "現價", "現價 / 溢價(折讓) ")
    ratio = pick(row, "比例", "新股比例")
    agent = pick(row, "配售代理", "包銷商", "保薦人", "新主")
    status = pick(row, "狀態", "公佈結果", "招股結果")
    announce_date, failed = parse_date(announce)
    key_date_1, _ = parse_date(key1)
    key_date_2, _ = parse_date(key2)
    raw = {str(k): (None if pd.isna(v) else v) for k, v in row.items()}
    return (event_type, code, None if pd.isna(name) else str(name), announce_date,
            key_date_1, key_date_2, first_number(price1), first_number(price2),
            None if ratio is None else str(ratio), None if agent is None else str(agent),
            None if status is None else str(status), json.dumps(raw, ensure_ascii=False, default=str), failed)


def source_files(raw_dir: Path = RAW_DIR) -> list[tuple[Path, str]]:
    out = []
    for path in sorted(raw_dir.glob("*.csv")):
        event_type = next((typ for marker, typ in TYPE_BY_FILE.items() if marker in path.stem), None)
        if event_type:
            out.append((path, event_type))
    return out


def build(raw_dir: Path = RAW_DIR, db_path: Path = DB_PATH) -> dict:
    rows: list[tuple] = []
    for path, event_type in source_files(raw_dir):
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=object)
        rows.extend(transform_row(event_type, row.to_dict()) for _, row in df.iterrows())
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as con:
        con.executescript("DROP TABLE IF EXISTS events;" + SCHEMA)
        con.executemany(
            "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        con.commit()
        stats = {
            "rows": len(rows),
            "files": len(source_files(raw_dir)),
            "by_type": dict(con.execute("SELECT event_type, COUNT(*) FROM events GROUP BY event_type")),
            "date_parse_success": int(con.execute("SELECT COUNT(*) FROM events WHERE date_parse_failed=0").fetchone()[0]),
            "date_parse_failed": int(con.execute("SELECT COUNT(*) FROM events WHERE date_parse_failed=1").fetchone()[0]),
            "earliest": con.execute("SELECT MIN(announce_date) FROM events WHERE announce_date IS NOT NULL").fetchone()[0],
            "latest": con.execute("SELECT MAX(announce_date) FROM events WHERE announce_date IS NOT NULL").fetchone()[0],
        }
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args()
    result = build(args.raw_dir, args.db)
    print(json.dumps(result, ensure_ascii=False, indent=2))
