# CODEX 任務規格書｜STOCKSCAN 第三階段接手（歷史數據入庫與自動化研究）

**日期**：2026-09-08　**執行者**：Codex CLI（Windows / PowerShell）　**前手**：zcode（第一、二階段）　**驗收**：KL + Claude
**工作夾（單一真相來源）**：`G:\我的雲端硬碟\STOCKSCAN`
**Repo**：https://github.com/disneydisney88/STOCKSCAN（`main`）
**Streamlit**：https://stockscan-emwmwndwrop2emavfyatme.streamlit.app

> 只供學術研究及風險分析，不構成投資建議。所有輸出附此聲明。

---

## 0. 開工前必讀（Codex 第一個動作，順序不可調）

1. `HANDOVER.md`（repo 根目錄）——**特別係 §5 十個陷阱**，全部實測中過伏
2. `config.py`——所有門檻，唯一改參數嘅地方
3. `stockscan/kline_cache.py`、`stockscan/scan_eod.py`——你會重用嘅兩個模組
4. 本文件第 3 節（模組 M1–M7）
5. 跑 `pytest -q` 確認 49 綠，先動手

**現況一句話**：訊號 A（收市爆量榜）對 RTSS 09-04 命中 15/15；訊號 B 可用；宇宙 2,858 隻；日線快取 40 支；Actions 已備未跑；Telegram 代碼齊未真發。第三階段唔改動呢啲，只**加**歷史數據同報表。

---

## 1. 環境同規矩（Codex 專用）

| 項目 | 值 |
|---|---|
| Shell | PowerShell（唔係 bash；路徑用 `G:\...`；`&&` 改 `;`） |
| Python | 3.13（Windows Store 版）；`longbridge==4.5.0`（**唔好裝 `longport`**） |
| 憑證 | `C:\Users\klcho\.stockscan\.env`（`LONGBRIDGE_APP_KEY/SECRET/ACCESS_TOKEN`）；`lb_client.py` 自動讀，**唔准 cat／print／commit／寫入 log** |
| 時區 | 所有「今日」用 `stockscan.io_utils.today_hkt()`；呢部機時鐘係 GMT |
| API 時間戳 | UTC，日 K `.date()` 會早一日——用 `kline_cache` 已修嘅路徑，新代碼要 `.astimezone(HKT)` |
| 歷史 K 線 | `history_candlesticks_*` 有 **100 標的硬配額**（error 301607）——**第三階段完全唔用 Longbridge 拉歷史**，只用價格庫 |
| Drive 同步夾 | 大量細檔讀寫慢；唔好兩部機同時 git；`.git` 壞咗就 reclone |
| Commit 節奏 | 每個模組一個 commit + push + 更新 HANDOVER §11「第三階段進度」 |
| 原始檔 | `data/raw/` 內全部唔准改；清理後另存 |
| 推算欄位 | 名字帶 `_est` 或旗標（`mcap_unreliable`），唔准扮真數 |
| 報表 | 只列數字，唔落結論——結論留畀 KL 同 Claude |
| MCP | 如 Codex 有 Longbridge MCP，只可即場核對數字，唔准入代碼 |

---

## 2. 原始檔（KL 放 `data/raw/`；Codex 開工前先檢查齊唔齊，缺嘅記 HANDOVER 唔好等）

| 檔 | 來源 / Drive file ID | 用途 |
|---|---|---|
| `hk_prices_master.csv`（44 MB，至 2026-08-05） | Drive 研究夾 `15Hm3ePAahrIBei7jZB-RDigB_1dxt8W3`，file `1QbYuRWaS0z3Bz-AmfozlR9hgMnsSrFyF` | M2 價格庫主體 |
| `hk_prices_delta_20260805_20260902.csv`（4.3 MB） | 同夾，file `1zz33iv6LT-CWi3_F2Q0cXdoDo2Z1d2QJ` | M2 補 08-05→09-02 |
| `price_library_exclusions.csv` | 同夾，file `1FD884i2iQkMTSR2tEUPq3Q6Bjtl8mKsu` | M2 已知剔除名單 |
| `MANIFEST.md` | 同夾，file `11Ql9V2J3cAqQDLl9wy_o1PYDeWx51T9S` | 價格庫欄位定義同已知問題——**M2 前必讀** |
| `shares_outstanding_panel_X0.csv` | 同夾，file `1n77yEZ5AcfNA5ctiin6blwzmH4kFnyMT` | M3 歷史股數（比 static_info 現值準） |
| `RTSS_Detailed_Final.xlsx`（10 MB） | file `1KQN_6oFYW00_WLwYEHixRb5pQeY1GUaq` | M3 對照、M6 回放 |
| 10 個事件 CSV（`配股事件20260831.csv` 等） | Claude Project | M1 |
| 7 個 `券商射倉*.xlsx` | Claude Project | M5 |
| 3 個 `L型研究*.xlsx` | Claude Project | M1 GO ground truth |

已知格式坑：
- 所有 CSV `encoding="utf-8-sig"`；代號 `00623.hk` → `code5`
- 事件 CSV 日期格式各異（`2026/07/08`、`08-31`、中文），集中一個 `parse_date()`，失敗記 `date_parse_failed=1` 唔准 drop
- 券商射倉 7 個 xlsx 欄位未必一致，先各自 `head` 對照
- 價格庫日期曾「靜默損毀」（Codex 第二輪修過）——入庫前抽 20 隻對 Longbridge 40 支快取核對收市價

---

## 3. 模組（按價值排序；獨立 commit；一個做唔完唔阻其他）

### M1　事件庫 `data/events.db`（SQLite）
- `scripts/build_events_db.py`：10 個 CSV → 長表 `events(event_type, code5, name, announce_date, key_date_1, key_date_2, price_1, price_2, ratio, agent, status, raw_json)`
- `event_type` ∈ {PLACING, RIGHTS, GO, CB, CONSOLIDATION, SPLIT, TRANSFER_MB, IPO, SHELL_VALUE, PLACING_AGENT}；原始行塞 `raw_json`
- 索引 `(code5, announce_date)`、`(event_type, announce_date)`
- `stockscan/events.py::events_after(code5, date, days)`
- HANDOVER 記：每類數、日期解析成功率、最早／最新日期
- ✅ `events_after("00653", "2026-07-03", 180)` 回傳 30 合 1 合股（08-12 公佈）

### M2　價格庫入本地快取
- `scripts/import_price_library.py`：master + delta → `data/cache/daily/{code5}.csv`（同 `kline_cache` 格式：date,open,high,low,close,volume,turnover）
- 合併規則：Longbridge 40 支優先，覆蓋重疊日；價格庫補更早
- 核對：隨機 20 隻 × 5 個重疊日，收市價差 >1% 列表寫 HANDOVER
- `kline_cache` 加 `source` 欄（`lb` / `lib`），方便追
- ✅ `data/cache/daily/` ≥1,500 檔，每隻 2025-06 → 今連續

### M3　13 個月 EOD 面板回填（取代 OCR）
- `scripts/backfill_eod.py --start 2025-06-26 --end 2026-09-07 --cache-only`（零 API）
- 市值分母：優先 `shares_outstanding_panel_X0.csv` 歷史股數；冇就用 static 現值並標 `mcap_unreliable=1`；期內有合股／拆股／大額配股（M1 查）亦標
- 輸出 `data/eod/radar_eod_panel_full.csv`
- 對照 `RTSS_Detailed_Final.xlsx` OCR 細升榜逐日：命中率、我哋多、我哋漏，**按月**寫 HANDOVER
- ✅ ~280 個交易日；按月對照表

### M4　常駐指標：GO 報時
- `scripts/report_go_timing.py`：panel 每個（code5, 上榜日）→ M1 查 60/120/180 日內 GO／合股／配股／供股
- 基準：同日隨機 10 隻非上榜、成交 ≥1M 細價股（M2 快取）
- 輸出 `data/reports/go_timing_YYYYMMDD.csv`；Streamlit 加 tab 5「事件率」；Actions EOD 後自動跑
- ✅ 180 日全購率同之前研究（3.5% vs 0.5%，約 7×）同數量級；差好遠先查 M1 日期

### M5　券商射倉入庫
- 7 個 xlsx → `data/broker_shots.csv(date, code5, broker_id, broker_name, shares_change, pct_change, direction)`
- `stockscan/broker.py::shots_around(code5, date, days)`
- panel 加欄 `has_broker_shot`（上榜日 ±5 日）
- ✅ 隨機 10 條對返原 xlsx

### M6　訊號 B 歷史回放
- RTSS 522 條 alert 嘅（code5, date）→ M2 快取取當日 high／close／turnover
- `n_max_est = floor((high/prev_close − 1)×100 / 20)`；前瞻 t+5／t+10／t+20 收市回報
- 輸出 `data/reports/n_count_forward.csv`，按 `n_max_est` 分層列中位／勝率
- ✅ 分層表寫 HANDOVER，唔落結論

### M7　CCASS 自動抓取
- `stockscan/ccass.py`：自家 CCASS API（`.env` 加 `CCASS_API_URL`、`CCASS_API_KEY`，KL 提供）
- EOD 跑完對當日上榜股抓 Concentration + Big Changes → `data/ccass/{code5}/{date}.json`
- Render 冷啟動：先 health，等 60 秒
- panel 加 `ccass_top5_pct_t2`、`ccass_top10_pct_t2`
- ✅ 一日上榜股全部有 JSON；失敗有 log

---

## 4. 驗收總表

| 模組 | 產出 | HANDOVER 要記 |
|---|---|---|
| M1 | `data/events.db` | 每類數、日期解析率 |
| M2 | `cache/daily` 全期 | 20 隻核對表 |
| M3 | `radar_eod_panel_full.csv` | 按月對照表 |
| M4 | go_timing 報表 + tab5 | 180 日全購率 vs 基準 |
| M5 | `broker_shots.csv` | 抽查 10 條 |
| M6 | `n_count_forward.csv` | 分層表 |
| M7 | `data/ccass/` | 成功率 |

每個模組完成：`pytest -q` 仍全綠（新模組加測試）→ commit → push → HANDOVER §11 更新。

## 5. KL 要做

1. 從 Drive 研究夾下載第 2 節五個檔 + Project 20 個檔，放 `data/raw/`
2. M7 前提供 CCASS API URL 同 key（放 `.env`）
3. 之前未做：Actions 撳一次 Run workflow；Streamlit Secrets；刪走 Drive 夾內 `LONGBRIDGE_APP.ENV`

## 6. 第四階段候選（唔做）
長開 worker 上雲；alert 入 Turso；兩星期同 RTSS 逐日對照；串入 Round 4 morning brief。

*只供學術研究及風險分析，不構成投資建議。*
