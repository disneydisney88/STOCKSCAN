"""股票宇宙：讀種子 CSV → 標準化代號 → 去重 → 除牌交叉 → static_info 補總股數。

用法（CLI）：
    python -m stockscan.universe                # 讀種子 universe_seed_20260831.csv（今晚用）
    python -m stockscan.universe --source full  # 讀 universe_full_20260907.csv（2,868 隻，下手先開）
輸出 data/universe.csv，統計印 stdout。
"""
from __future__ import annotations

import argparse

import pandas as pd

from config import (
    DELISTED_SUSPECT_SEED,
    FULL_CSV,
    SEED_CSV,
    UNIVERSE_CSV,
)
from stockscan.io_utils import (
    ensure_dirs,
    lb_to_code5,
    log_error,
    parse_cn_number,
    seed_code_to_lb,
    write_csv,
)

OUT_COLUMNS = [
    "code5", "symbol_lb", "name_seed", "name_hk", "industry",
    "board", "lot_size", "total_shares", "hk_shares",
    "has_domestic_shares", "delisted_suspect", "static_missing", "in_scan",
]


def _full_codeset() -> set[str] | None:
    """universe_full code5 集合；檔案缺席回 None（今晚應該係 None）。"""
    if FULL_CSV.exists():
        df = pd.read_csv(FULL_CSV, dtype=str, encoding="utf-8-sig")
        return set(df["code5"].str.zfill(5))
    return None


def load_seed(path=SEED_CSV) -> pd.DataFrame:
    """種子檔 → 標準化 DataFrame（去重、代號轉換、內資股旗）。"""
    raw = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    raw.columns = [c.strip() for c in raw.columns]
    df = pd.DataFrame()
    df["code_raw"] = raw["編號"].str.strip()
    df["code5"] = df["code_raw"].map(lambda c: lb_to_code5(seed_code_to_lb(c)))
    df["symbol_lb"] = df["code_raw"].map(seed_code_to_lb)
    df["name_seed"] = raw["名稱"].str.strip()
    df["industry"] = raw.get("行業", "").fillna("").str.strip() if "行業" in raw.columns else ""
    # 種子「市值」只作首日對照，唔用嚟篩
    df["seed_mcap"] = raw["市值"].map(parse_cn_number) if "市值" in raw.columns else None
    if "內資股(佔比)" in raw.columns:
        dom = raw["內資股(佔比)"].astype(str).str.strip()
        df["has_domestic_shares"] = (~dom.isin({"-", "", "nan"})).astype(int)
    else:
        df["has_domestic_shares"] = 0
    n_before = len(df)
    # _depre（deprecated）行同正常行重複——優先保留正常行（spec：種子有 2 個重複代號）
    df["_depre"] = df["code_raw"].str.contains("_depre", case=False).astype(int)
    df = (df.sort_values("_depre")
            .drop_duplicates(subset="code5", keep="first")
            .drop(columns="_depre")
            .reset_index(drop=True))
    if len(df) < n_before:
        print(f"[universe] 種子去重：{n_before} → {len(df)}（剔 {n_before - len(df)} 個重複代號）")
    return df


def load_full(path=FULL_CSV) -> pd.DataFrame:
    """全港名單（--source full 用，今晚唔開）。欄位：code5, symbol_lb, name, board, is_reit, in_seed_20260831"""
    raw = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    df = pd.DataFrame()
    df["code5"] = raw["code5"].str.zfill(5)
    df["symbol_lb"] = raw["symbol_lb"]
    df["name_seed"] = raw["name"]
    df["industry"] = ""
    df["seed_mcap"] = None
    df["has_domestic_shares"] = 0
    df["is_reit"] = raw.get("is_reit", "0").fillna("0").astype(int)
    return df


def mark_delisted(df: pd.DataFrame) -> pd.DataFrame:
    """用 universe_full code5 交叉；full 檔缺席就用 config 硬編清單。"""
    codes = _full_codeset()
    if codes is not None:
        df["delisted_suspect"] = (~df["code5"].isin(codes)).astype(int)
        src = "universe_full code5 交叉"
    else:
        df["delisted_suspect"] = df["code5"].isin(DELISTED_SUSPECT_SEED).astype(int)
        src = "config 硬編清單（universe_full 缺席）"
    n = int(df["delisted_suspect"].sum())
    print(f"[universe] delisted_suspect=1 共 {n} 隻（判斷來源：{src}）")
    return df


def enrich_static(df: pd.DataFrame, lb) -> pd.DataFrame:
    """分批 static_info 補 name_hk / total_shares / hk_shares / lot_size / board；失敗記 static_missing=1 唔好 drop。"""
    df = df.copy()
    for col in ("name_hk", "board", "lot_size", "total_shares", "hk_shares", "static_missing"):
        df[col] = pd.NA
    df["static_missing"] = 0
    symbols = df["symbol_lb"].tolist()
    info = lb.static_info_batch(symbols) if symbols else {}
    idx = df.set_index("symbol_lb").index
    missing = []
    for sym in symbols:
        s = info.get(sym)
        if s is None:
            missing.append(sym)
            continue
        j = df.index[df["symbol_lb"] == sym]
        if len(j) == 0:
            continue
        j = j[0]
        df.at[j, "name_hk"] = s.name_hk or s.name_cn or ""
        df.at[j, "board"] = str(getattr(s.board, "name", s.board))
        df.at[j, "lot_size"] = int(s.lot_size) if s.lot_size else pd.NA
        df.at[j, "total_shares"] = float(s.total_shares) if s.total_shares else pd.NA
        df.at[j, "hk_shares"] = float(s.hk_shares) if s.hk_shares else pd.NA
    df.loc[df["symbol_lb"].isin(missing), "static_missing"] = 1
    df.loc[df["static_missing"] == 1, "name_hk"] = df.loc[
        df["static_missing"] == 1, "name_seed"
    ]
    if missing:
        log_error("universe.static_info", f"static 缺失 {len(missing)} 隻：{missing[:20]}")
    return df


def build(source: str = "seed", lb=None) -> pd.DataFrame:
    if source == "seed":
        df = load_seed()
    elif source == "full":
        df = load_full()
    else:
        raise ValueError(f"未知 source：{source}")
    df = mark_delisted(df)

    if source == "seed":
        df["in_scan"] = 1 - df["delisted_suspect"]
    else:  # full 名單：REIT 預設剔除（規格書 §8 口徑）
        df["in_scan"] = 1 - df["is_reit"]

    if lb is not None:
        scan_syms = df.loc[df["in_scan"] == 1, "symbol_lb"].tolist()
        scan_df = enrich_static(df[df["in_scan"] == 1], lb)
        rest = df[df["in_scan"] != 1].copy()
        for col in OUT_COLUMNS:
            if col not in rest.columns:
                rest[col] = pd.NA
        df = pd.concat([scan_df, rest], ignore_index=True)
    else:
        for col in OUT_COLUMNS:
            if col not in df.columns:
                df[col] = pd.NA

    df["has_domestic_shares"] = df.get("has_domestic_shares", 0)
    df = df[OUT_COLUMNS].sort_values("code5").reset_index(drop=True)
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description="建立 data/universe.csv")
    ap.add_argument("--source", choices=["seed", "full"], default="seed",
                    help="seed=種子檔（今晚用）；full=全港名單（下手先開）")
    args = ap.parse_args()

    ensure_dirs()
    from stockscan.lb_client import LB

    lb = LB()
    df = build(source=args.source, lb=lb)
    write_csv(df, UNIVERSE_CSV)

    total = len(df)
    scan = df[df["in_scan"] == 1]
    ok = int((scan["static_missing"] == 0).sum())
    dom = int((df["has_domestic_shares"] == 1).sum())
    print(f"[universe] 總數 {total}；掃描宇宙 {len(scan)}；static 成功率 {ok}/{len(scan)}"
          f" = {ok / max(len(scan), 1):.1%}；內資股 {dom} 隻")
    print(f"[universe] 已寫 {UNIVERSE_CSV}")
    print("免責聲明：本工具只供學術研究及風險分析，不構成投資建議。")


if __name__ == "__main__":
    main()
