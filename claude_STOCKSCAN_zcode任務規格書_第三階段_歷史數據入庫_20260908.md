# STOCKSCAN｜zcode 第三階段任務規格書：歷史數據入庫與自動化研究

**日期**：2026-09-08　**前提**：第二階段 P1–P6 完成，HANDOVER 已更新
**性質**：長時間「磨」嘅工作，無硬時限；每完成一個模組 commit + 更新 HANDOVER，可以隨時停
**目標**：把 Project 入面靠人手／Codex 一次性跑過嘅研究數據，全部變成 repo 內可重跑嘅表，令三個常駐指標每日自動更新

> 只供學術研究及風險分析，不構成投資建議。

---

## 0. KL 要先放嘅原始檔（放 `data/raw/`，全部唔准改動原檔）

| 檔 | 來源 | 數量 |
|---|---|---|
| `配股事件20260831.csv` 等 10 個事件 CSV | Claude Project | 配股 500、供股 200、全購 200、可換股債券 202、合股 60、拆股 60、轉主板 83、半新股 488、殼股價值分析 1,564、配售代理大數據 203 |
| `券商射倉*.xlsx` × 7 | Claude Project | 2024-11 → 2026-08 |
| `L型研究*.xlsx` × 3 | Claude Project | 完整結果總表、F 版、I 版 |
| Codex P0 價格庫 | Drive 財技夾（folder `1DMWeePqFs6BkmvdOyX6kwNcj5phnTcGR`），KL 搵返檔名 | 608,413 stock-day，2025-06 起 |
| RTSS alert 解析結果（522 條）+ Telegram 訊息日誌（11,122 條） | `RTSS_Detailed_Final.xlsx`，Drive 同一夾 | — |

已知格式坑（來自之前研究，必須遵守）：
- 所有 CSV 要 `encoding="utf-8-sig"`；代號格式係 `00623.hk`，統一轉 `code5`
- 事件 CSV 嘅日期格式各異（`2026/07/08`、`08-31`、有啲係中文），寫一個 `parse_date()` 集中處理，解析失敗記 `date_parse_failed=1` 唔准 drop
- 券商射倉 7 個 xlsx 欄位未必一致，先各自 `head` 對照再合併
- 價格庫日期曾出現「靜默損毀」問題（Codex 第二輪修過），入庫前抽 20 隻對 Longbridge 快取核對收市價

---

## 1. 模組次序（按價值）

### M1　事件庫 `data/events.db`（SQLite）
1. `scripts/build_events_db.py`：讀 10 個 CSV → 一張長表 `events`：
   `event_type, code5, name, announce_date, key_date_1, key_date_2, price_1, price_2, ratio, agent, status, raw_json`
   - `event_type` ∈ {PLACING, RIGHTS, GO, CB, CONSOLIDATION, SPLIT, TRANSFER_MB, IPO, SHELL_VALUE, PLACING_AGENT}
   - 原始行整行塞入 `raw_json`，方便之後追欄
2. 建索引 `(code5, announce_date)`、`(event_type, announce_date)`
3. `stockscan/events.py`：`events_after(code5, date, days)` → 回傳 N 日內事件列表
4. 統計寫 HANDOVER：每類事件數、日期解析成功率、最早／最新日期

✅ 驗收：`events_after("00653", "2026-07-03", 180)` 回傳 30 合 1 合股（08-12 公佈）

### M2　價格庫入本地快取
1. 把 Codex P0 價格庫轉成同 P1 一樣嘅 `data/cache/daily/{code5}.csv` 格式，同 Longbridge 快取合併（Longbridge 優先，覆蓋重疊日）
2. 核對：隨機 20 隻 × 5 日，收市價同 Longbridge 差異 >1% 者列出
3. 結果：每隻股一條 2025-06 → 今嘅連續日線

✅ 驗收：`data/cache/daily/` ≥1,500 檔；核對表寫 HANDOVER

### M3　13 個月 EOD 面板回填（取代 OCR）
1. `scripts/backfill_eod.py --start 2025-06-26 --end 2026-09-07`（用 M2 快取，零 API）
2. 市值分母問題：歷史股數用 Longbridge `static_info` 現值近似，凡期內有合股／拆股／大額配股（M1 可查）嘅股票標 `mcap_unreliable=1`
3. 輸出 `data/eod/radar_eod_panel_full.csv`
4. 對照：同 `RTSS_Detailed_Final.xlsx` 入面 OCR 細升榜逐日比——命中率、我哋多、我哋漏，按月統計

✅ 驗收：panel 有 ~280 個交易日；對照按月表寫 HANDOVER

### M4　常駐指標一：GO 報時
1. `scripts/report_go_timing.py`：panel 每隻股每個上榜日，用 M1 查之後 60/120/180 日內有冇 GO／合股／配股／供股公佈
2. 基準：同日隨機抽 10 隻非上榜、成交 ≥1M 嘅細價股（用 M2 快取）
3. 輸出 `data/reports/go_timing_YYYYMMDD.csv` + Streamlit tab 5「事件率」
4. 每日 Actions 跑完 EOD 後自動更新

✅ 驗收：全購 180 日率同之前研究（3.5% vs 0.5%，7.1×）同一數量級；如差好遠先查 M1 日期解析

### M5　券商射倉入庫
1. 合併 7 個 xlsx → `data/broker_shots.csv`：`date, code5, broker_id, broker_name, shares_change, pct_change, direction`
2. `stockscan/broker.py`：`shots_around(code5, date, ±days)`
3. 面板 join：上榜日 ±5 日有冇射倉紀錄，加欄 `has_broker_shot`

✅ 驗收：隨機抽 10 條對返原 xlsx

### M6　訊號 B 歷史回放
1. 用 RTSS 522 條 alert 嘅（code5, date）對，喺 M2 快取取當日 high／close／turnover
2. 反推「如果我哋當日跑 B（10 億上限、20pt 級距），最高會去到第幾次」`n_max_est = floor(max_pct/20)`
3. 加前瞻回報 t+5／t+10／t+20（收市對收市，用 M2）
4. 輸出 `data/reports/n_count_forward.csv`，按 n_max_est 分層列中位／勝率

✅ 驗收：報表存在；HANDOVER 記低分層結果（唔准落結論，只記數字）

### M7　CCASS 自動抓取
1. `stockscan/ccass.py`：call 自家 CCASS API（endpoint 同 key 放 `.env`：`CCASS_API_URL`、`CCASS_API_KEY`）
2. 每日 EOD 跑完，對當日上榜股逐隻抓 Concentration + Big Changes，存 `data/ccass/{code5}/{date}.json`
3. Render 冷啟動：第一個 call 前先打一次 health，等 60 秒
4. 面板加欄 `ccass_top5_pct`、`ccass_top10_pct`（T+2 對齊，欄名寫明 `_t2`）

✅ 驗收：一日上榜股全部有 JSON；失敗有 log 唔 silent

---

## 2. 規矩

- 每個模組獨立 script，獨立 commit；一個做唔完唔影響其他
- 原始檔唔准改；所有清理後嘅表另存
- 所有推算欄位（`mcap_unreliable`、`n_count_est`）名字要帶 `_est` 或旗標，唔准扮真數
- 對照差異先記錄再判斷；報表只列數字，結論留畀 KL 同 Claude
- token 規矩同前

## 3. 驗收總表

| 模組 | 產出 | HANDOVER 要記 |
|---|---|---|
| M1 | events.db | 每類數、日期解析率 |
| M2 | cache/daily 全期 | 20 隻核對表 |
| M3 | panel_full | 按月對照表 |
| M4 | go_timing 報表 + tab5 | 180 日全購率 |
| M5 | broker_shots.csv | 抽查 10 條 |
| M6 | n_count_forward.csv | 分層表 |
| M7 | ccass/ JSON | 成功率 |

## 4. 之後（第四階段候選）
- 長開 worker 上雲；alert 入 Turso；宇宙換 universe_full；兩星期同 RTSS 頻道逐日對照；串入 Round 4 morning brief

*只供學術研究及風險分析，不構成投資建議。*
