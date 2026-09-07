# STOCKSCAN HANDOVER

更新時間（HKT）：2026-09-07 23:20
執行者：zcode　交接對象：下一位（Codex / Claude / KL）

> 本工具只供學術研究及風險分析，不構成投資建議。

## 1. 而家去到邊

| Checkpoint | 狀態 (✅/⚠/❌) | 備註 |
|---|---|---|
| H0 地基 | ✅(半) | 目錄樹／config／lb_client 寫好；**首次 push main 完成（commit cd14aca）**；probe 未跑（等 .env） |
| H1 宇宙 | ⚠ | universe.py＋`--source full` 開關寫好、pytest 過、`_depre` 去重處理好；**universe.csv 未生成（等 .env）** |
| H2 收市榜 | ⚠ | scan_eod.py＋RTSS fixture（15 隻）寫好；**09-04／09-07 掃描未跑（等 .env）** |
| H3 即市 | ⚠ | scan_intraday.py（狀態機＋off_hours）寫好；**未實測（等 .env）** |
| H4 Streamlit | ⚠(半) | 三 tab 寫好；**本機起機冒煙測試過（HTTP 200＋bare-mode 無錯）**；未部署 Cloud |
| H5 部署 | ⚠ | workflow eod_scan.yml 已 push；**待 KL 貼 GitHub/Streamlit Secrets＋手動觸發** |
| H6 測試交接 | ✅ | pytest 38 項全綠；README、HANDOVER 齊 |

**卡關一件事：KL 未放 `.env`（三個 LONGPORT_ 變數）入 repo 根目錄。**
放好之後照第 7 節三行命令跑：universe → eod 09-04 → eod 今日 → probe，再更新本檔狀態。

## 2. 實測限額（probe 結果）

- quote 每批最多：**未測**（config 暫定 QUOTE_BATCH=500，SDK 上限待 probe 確認）
- 每秒次數：**未測**（lb_client 已有 1,2,4,8s×5 次指數退避）
- 全宇宙一輪耗時：**未測**（日 K 無批量 API，用 4 線程；probe 會出估計值）
- 跑法：`python scripts/probe_ratelimit.py`，結果寫 `logs/probe_*.json`

## 3. 數據口徑決定（同 config.py 一致）

- 時區一律 `Asia/Hong_Kong`；「今日」唔用機器本地時間。
- `mcap_total = close × total_shares`（static_info）；篩選用 mcap_total；`mcap_hk = close × hk_shares` 另出。
- 訊號 A 成交額＝日 K `turnover`（欄名 `turnover_day`）；訊號 B＝`quote.turnover`（`turnover_intraday`），兩者唔混。
- 前 10 日均值：日 K 取 11 支剔今日；不足 10 支照計，`ma10_days_available` 記實數＋`ma_short=1`（規格書 §3 有提 ma_short，已加入輸出欄）。
- `turnover_to_mcap` 以 **百分比** 輸出（例如 5.23 = 5.23%）。
- 種子檔「市值」欄只作對照（`seed_mcap`），唔用嚟篩。
- 代號：種子 `00623.hk` → Longbridge `623.HK`；輸出 `code5=00623`。
- 種子去重：`02667.hk_depre`／`03301.hk_depre` 同正常行重複，剔 `_depre` 行（1,564 → 1,562）。
- 除牌交叉：`universe_full_20260907.csv` **今晚缺席**；用 config 硬編 5 隻
  （02900/02901/02903/02912/08577）標 `delisted_suspect=1`。full 檔放好後重跑 universe 會自動改用 code5 交叉。
- 訊號 B 預篩：`min(prev_close, last_done) × total_shares < 3 億`（一輪 quote 過晒，唔會走漏）；
  最終篩 `mcap_now = last_done × total_shares < 3 億`。
- 訊號 B 非交易時段 alert 加 `off_hours=1`（判斷：HKT 09:30–12:00／13:00–16:00 之外）。

## 4. 對照 RTSS 09-04 結果

- 命中：**未跑（等 .env）**——fixture 已手打 `tests/fixtures/rtss_20260904.csv`（15 隻：
  01393,08483,01663,03997,00328,02322,01094,03789,08375,01587,00756,02170,00529,00201,02167）
- 我哋多咗：待填
- 我哋漏咗：待填
- 跑 `python scripts/run_eod.py --date 2026-09-04` 會自動對照並寫 `data/eod/compare_rtss_20260904.json`

## 5. 已知 bug / 未完成

- `.env`／`universe_full_20260907.csv` 未放（KL 負責）→ probe、universe.csv、兩個 EOD CSV、即市實測全部未跑。
- Streamlit Cloud 部署＋GitHub Actions 手動觸發未做（等 repo 有內容＋Secrets）。
- Telegram 推送、Turso、長開 worker、CCASS：今晚唔做（規格書 §8）。

## 6. 下手要做（按優先）

1. KL 放 `.env` 入 repo 根目錄（唔好 commit），跑第 7 節三行命令＋probe，更新本檔 §1/§2/§4。
2. KL 放 `data/universe_full_20260907.csv`，重跑 `python -m stockscan.universe`（自動改用 code5 除牌交叉）。
3. Streamlit Cloud 部署：branch=main、main file=streamlit_app.py、貼三個 Secrets。
4. GitHub repo Secrets 貼三個 `LONGPORT_`，Actions 手動 trigger 一次 `eod_scan`。
5. 下手換 `--source full` 宇宙（2,868 隻）＋動態市值篩（規格書 §8）。
6. 兩星期逐日同 RTSS 對數，先考慮微調門檻。

## 7. 點樣本機重跑（三行命令）

```bash
python -m stockscan.universe
python scripts/run_eod.py --date 2026-09-04 && python scripts/run_eod.py
python scripts/run_intraday.py
```

（前提：repo 根目錄有 `.env`。測試：`pytest -q`。）

## 8. Secrets 放邊（只寫位置，唔寫值）

- 本機：repo 根目錄 `.env`（已 gitignore，唔准 commit）
- Streamlit Cloud：App → Settings → Secrets（TOML：三個 LONGPORT_ 變數）
- GitHub Actions：repo → Settings → Secrets and variables → Actions（三個 LONGPORT_）
