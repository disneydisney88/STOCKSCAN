#!/usr/bin/env python
"""P6c 將 港股研究站 dt_events 12 類財技事件（3,013 單，2026-09-19 抓取）入 events.db。

來源：`C:\\data\\HKSTOCKDB\\dropin\\dt_events\\dt_events_all_20260919.csv`
（正規化欄位 code/cat/name/ann_date/ex_date/status/price/premium_pct/ratio/source_file）。

映射：cat → event_type（general_offer→GO、convertible_bond→CB、stock_consolidation→
CONSOLIDATION、stock_split→SPLIT、rights_issue→RIGHTS、placing→PLACING、
switchboard→TRANSFER_MB、privatization→PRIVATIZATION、bonus_share→BONUS、
halfnew→HALFNEW、ipo→IPO）。

去重：同 (code5, event_type, announce_date) 已存在就 skip。
回購（share_repurchase）唔入 events——佢係每日動作唔係一次性事件，另開
`repurchase_daily` 表（獨立 schema，含年初至今佔股本%）。

紀律：試點 30 行→報告→全量；數字對不上如實報告。
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SRC = Path(r"C:\data\HKSTOCKDB\dropin\dt_events\dt_events_all_20260919.csv")
RP_CSV = Path(r"C:\data\HKSTOCKDB\dropin\dt_events\dt_share_repurchase_20260919.csv")
DB = ROOT / "data" / "events.db"

CAT_MAP = {
    "全購": "GO", "可換股債券": "CB",
    "合股": "CONSOLIDATION", "拆股": "SPLIT",
    "供股": "RIGHTS", "配股": "PLACING",
    "轉主板": "TRANSFER_MB", "私有化": "PRIVATIZATION",
    "送紅股": "BONUS", "半新股": "HALFNEW", "IPO": "IPO",
}


def main() -> int:
    all_df = pd.read_csv(SRC, dtype=str, encoding="utf-8-sig")
    all_df["code5"] = all_df["code"].astype(str).str.zfill(5)
    all_df["event_type"] = all_df["cat"].map(CAT_MAP)
    unmapped = all_df[all_df["event_type"].isna()]
    if len(unmapped):
        print(f"⚠ 未映射類別 {len(unmapped)} 行：{unmapped['cat'].unique()}（跳過）")
    all_df = all_df[all_df["event_type"].notna()]

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    existing = {
        (r["code5"], r["event_type"], r["announce_date"])
        for r in con.execute(
            "SELECT code5, event_type, announce_date FROM events "
            "WHERE announce_date IS NOT NULL AND announce_date != ''")
    }

    # ── 試點 30 行 ──
    pilot = all_df.head(30)
    p_new = p_dup = 0
    for r in pilot.itertuples(index=False):
        key = (r.code5, r.event_type, str(r.ann_date))
        if key in existing:
            p_dup += 1
        else:
            p_new += 1
    print(f"[試點 30 行] 新 {p_new}／重複 {p_dup}", flush=True)

    # ── 全量 ──
    ins_sql = ("INSERT INTO events(event_type, code5, name, announce_date, key_date_1, "
               "price_1, ratio, status, raw_json, date_parse_failed) "
               "VALUES(?,?,?,?,?,?,?,?,?,?)")
    new_n = dup_n = bad_date = 0
    per_type: dict[str, int] = {}
    for r in all_df.itertuples(index=False):
        ann = str(r.ann_date) if pd.notna(r.ann_date) else ""
        key = (r.code5, r.event_type, ann)
        if key in existing:
            dup_n += 1
            continue
        # 半新股／IPO 係純名單（無日期）——照 M1 慣例照入，標 date_parse_failed=1 留底
        date_ok = bool(ann) and len(ann) == 10
        if not date_ok:
            ann = ""
            bad_date += 1
        existing.add(key)
        raw = json.dumps({"cat": r.cat, "premium_pct": r.premium_pct,
                          "source_file": r.source_file,
                          "note": "no_date_name_list" if not date_ok else ""},
                         ensure_ascii=False)
        con.execute(ins_sql, (r.event_type, r.code5,
                              str(r.name) if pd.notna(r.name) else "",
                              ann,
                              str(r.ex_date) if pd.notna(r.ex_date) else "",
                              str(r.price) if pd.notna(r.price) else "",
                              str(r.ratio) if pd.notna(r.ratio) else "",
                              str(r.status) if pd.notna(r.status) else "",
                              raw, int(not date_ok)))
        new_n += 1
        per_type[r.event_type] = per_type.get(r.event_type, 0) + 1
    con.commit()

    total = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    vmax = con.execute("SELECT MAX(announce_date) FROM events").fetchone()[0]
    print(f"[全量] 新增 {new_n} 單／重複 skip {dup_n}／壞日期跳過 {bad_date}")
    print(f"[全量] 按類：{dict(sorted(per_type.items()))}")
    print(f"[events.db] 總行數 {total}（前 3,560）｜max announce_date {vmax}")

    # ── 回購另開表 ──
    rp = pd.read_csv(RP_CSV, dtype=str, encoding="utf-8-sig")
    con.execute("""CREATE TABLE IF NOT EXISTS repurchase_daily(
        code5 TEXT NOT NULL, name TEXT, repurchase_date TEXT NOT NULL,
        shares INTEGER, amount_hkd REAL, high_price REAL, low_price REAL,
        close_price REAL, ytd_shares INTEGER, ytd_pct_of_issued REAL,
        source TEXT, PRIMARY KEY(code5, repurchase_date, shares))""")
    before = con.execute("SELECT COUNT(*) FROM repurchase_daily").fetchone()[0]
    ins_rp = ("INSERT OR IGNORE INTO repurchase_daily VALUES(?,?,?,?,?,?,?,?,?,?,?)")

    def _num(s):
        s = str(s or "").replace("HKD", "").replace(",", "").strip()
        try:
            return float(s)
        except ValueError:
            return None

    rp_n = 0
    for vals in rp.values.tolist():  # 欄序：代號0 名稱1 回購日期2 股數3 金額4 高5 低6 現價7 年初至今股數8 佔比9
        code_raw, name, d = vals[0], vals[1], str(vals[2] or "")
        d = "-".join(reversed(d.split("/"))) if "/" in d else d
        if len(d) == 8:
            d = f"20{d[6:]}-{d[3:5]}-{d[:2]}"
        con.execute(ins_rp, (norm(code_raw), str(name or ""), d,
                             int(_num(vals[3]) or 0), _num(vals[4]), _num(vals[5]),
                             _num(vals[6]), _num(vals[7]), int(_num(vals[8]) or 0),
                             _num(vals[9]), "dt_share_repurchase_20260919"))
        rp_n += 1
    con.commit()
    after = con.execute("SELECT COUNT(*) FROM repurchase_daily").fetchone()[0]
    print(f"[repurchase_daily] 讀 {rp_n} 行，入庫後表共 {after} 行（前 {before}；"
          f"PK code+date+shares 去重）")
    con.close()
    print("免責聲明：本工具只供學術研究及風險分析，不構成投資建議。")
    return 0


def norm(code) -> str:
    digits = "".join(ch for ch in str(code or "") if ch.isdigit())
    return digits.zfill(5) if digits else ""


if __name__ == "__main__":
    raise SystemExit(main())
