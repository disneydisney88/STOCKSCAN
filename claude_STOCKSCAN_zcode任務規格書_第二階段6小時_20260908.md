# STOCKSCAN｜zcode 第二階段 6 小時任務規格書

**日期**：2026-09-08 凌晨　**前提**：第一階段 H0–H6 已完成（38 tests 綠、Streamlit 已部署、EOD 09-04 掃描跑緊）
**Repo 本機路徑**：`G:\我的雲端硬碟\STOCKSCAN`（zcode 已定為單一真相來源）
**本階段目標**：把 A 由「跑得到」變「跑得快 + 有歷史面板」；把 B 由半成品變可用；加 Telegram 推送。

> 只供學術研究及風險分析，不構成投資建議。

---

## 0. 開工前先做（15 分鐘，唔計入 6 小時）

1. 等 09-04 掃描完成 → 即跑 `--date 2026-09-07` → 兩個 CSV commit + push → Streamlit Rerun → 確認 tab 1 有表。
2. **對照結果寫入 HANDOVER §4**：09-04 命中 x/15、多咗邊啲、漏咗邊啲、原因。呢個數字係全晚最重要嘅一個。
3. **安全**：repo 而家喺 Google Drive 同步夾，即係 `.env` 會被同步上雲端。改為：
   - `.env` 搬去 `%USERPROFILE%\.stockscan\.env`
   - `lb_client.py` 讀取次序：`st.secrets` → repo `.env`（如存在）→ `%USERPROFILE%\.stockscan\.env` → 環境變數
   - repo 內留 `.env.example`，刪走真 `.env`
   - `logs/` 同 `state/` 亦唔應該同步：加入 `.gitignore` 已有，但 Drive 照樣同步——可接受，但 log 內唔准有 token。

---

## 1. 六小時分段

### P1　0:00–1:00　EOD 提速（唔提速，之後回填 20 日要跑幾個鐘）
現況：1,557 隻逐隻 `candles(11)`，有 429 退避，一輪要 30 分鐘以上。

1. 建本地日線快取 `data/cache/daily/{code5}.csv`（欄：date, open, high, low, close, volume, turnover）。
2. `scan_eod.py` 改為：先讀快取 → 只補缺嘅日子（通常每日 1 支）→ 寫返快取 → 計算。首次仍要全拉，之後每日 <5 分鐘。
3. 加 `--workers N` 有限並發（預設 2；probe 結果話得就 3），每個 worker 之間固定間隔，尊重限流。
4. 加 `--codes 1393,8483` 參數，方便單隻 debug。
5. 記錄每次 run 嘅耗時、API 次數、429 次數落 `logs/run_stats.csv`。

✅ 驗收：重跑 `--date 2026-09-07`（快取已有）<5 分鐘；結果同未快取版本逐行相同。

### P2　1:00–2:30　回填 20 個交易日面板
1. `scripts/backfill_eod.py --start 2026-08-10 --end 2026-09-07`：逐日跑 A，輸出 `data/eod/radar_eod_YYYYMMDD.csv`。
2. 合併為 `data/eod/radar_eod_panel.csv`（多一欄 `scan_date`）。
3. 統計寫入 HANDOVER §9「面板摘要」：
   - 每日上榜數（中位／最少／最多）
   - 上榜次數最多頭 10 隻
   - 市值 <3 億佔比
4. 如 Project 之前有 RTSS 同期截圖數據（KL 提供），留 `tests/fixtures/rtss_YYYYMMDD.csv` 格式，`scripts/compare_rtss.py` 可批量對照。今晚只做 09-04 一日，其他留接口。

✅ 驗收：20 個 CSV + panel 存在；HANDOVER 有摘要表。

### P3　2:30–3:45　訊號 B 升級為可用版
改動（全部喺 `config.py`）：
```python
MCAP_CAP_INTRA  = 10e8    # 由 3 億放寬到 10 億（補返 RTSS 兩榜各自漏嘅股）
INTRA_FIRST_PCT = 20.0
INTRA_STEP_PCT  = 20.0
INTRA_TURNOVER_MIN = 5e5
INTRA_POLL_SEC  = 60
```
1. `scan_intraday.py` 加第二個觸發條件「即市爆量」：`turnover_intraday ÷ ma10 ≥ 10`（ma10 由 P1 快取取）——即係 A 嘅邏輯搬到即市。兩種 alert 用 `alert_type` 欄分開：`SURGE`（急升）／`VOLUME`（爆量）。同一隻股兩種可以各自計「當日第 N 次」。
2. `scripts/run_intraday.py --loop 60`：
   - 用 `calendar_hk.py` 判斷交易日；只喺 09:30–12:00、13:00–16:10 HKT 掃；其餘時間 sleep
   - 每輪先用「昨日收市市值 <10 億」預篩（約 1,550 隻，3–4 個 quote 批次）
   - 每輪耗時、alert 數寫 `logs/intraday_stats.csv`
   - Ctrl-C 安全退出，state 已落盤
3. 提供 Windows 工作排程器範例 `scripts/schedule_intraday.ps1`（09:25 HKT 啟動，16:15 結束），**只寫檔，唔幫 KL 註冊**。
4. `state/intraday_state_YYYYMMDD.json` 加 `first_seen_price`、`first_seen_turnover`，方便之後研究「第 1 次 alert 當刻 vs 收市」。

✅ 驗收：本機 `--loop 60 --once`（單輪）跑到；假日／收市後執行時正確 sleep 而非報錯；pytest 新增級距同 alert_type 測試。

### P4　3:45–4:45　Telegram 推送
KL 要準備（見第 2 節）：`TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`，放同一個 `.env`。

1. `stockscan/notify.py`：`send_text(msg)`、`send_eod_table(df, date)`、`send_intraday_alert(row)`；用 `requests` 直接打 Bot API，唔裝額外套件。
2. EOD 訊息格式（照 RTSS 表頭，等寬對齊）：
```
📊 STOCKSCAN 收市爆量榜 2026-09-07（15 隻）
條件：市值<10億 & 成交>50萬 & 今日/10MA≥10x
代號  名稱      現價  升跌    成交額  市值   倍數  成交/市值
01393 恒鼎實業  0.03 +27.3%  5.6M   1.29億 28.1x 4.3%
...
只供學術研究，不構成投資建議
```
3. 即市 alert 格式（照 RTSS）：
```
🔥 急升異動 [當日第2次 (40%→60%)]
📈 名稱 (HK.01393)
💰 市值: 1.29億  💹 成交額: 5.6M
📊 升幅: +62.3%  最新價: 0.031  🕒 11:59:59
```
4. `--notify` 開關，預設關；`--dry-run` 印出訊息唔發送。
5. `.github/workflows/eod_scan.yml` 加 `--notify`（secrets 加兩個 TELEGRAM_）。

✅ 驗收：`python scripts/run_eod.py --date 2026-09-07 --notify --dry-run` 印出正確格式；如 KL 已放 token，真發一次。

### P5　4:45–5:30　Streamlit 加歷史面板
1. Tab 4「歷史面板」：讀 `radar_eod_panel.csv`
   - 每日上榜數折線
   - 股票上榜次數排行（可揀日期範圍）
   - 點一隻股 → 顯示佢喺面板出現嘅所有日子同當日數據
2. Tab 2 即市：顯示 `data/intraday/alerts_*.csv`（Cloud 版只讀，唔跑掃描）；本機版先有「掃一次」掣。
3. 每個 tab 加「數據截至」時間戳。

✅ 驗收：Cloud 版四個 tab 開到；tab 4 有圖。

### P6　5:30–6:00　交接
1. HANDOVER.md 更新：§1 加 P1–P6 狀態；§2 更新耗時（快取前後）；§4 對照結果；§9 面板摘要；§6 下手要做重排。
2. README 加「即市監察點開」「Telegram 點設定」兩節。
3. `pytest` 全綠；push；Drive 同步確認。

---

## 2. KL 要準備嘅（P4 之前）

Telegram bot（3 分鐘）：
1. Telegram 搵 **@BotFather** → `/newbot` → 改名（例如 `stockscan_kl_bot`）→ 攞 token
2. 開一個私人 channel 或 group，把 bot 加入做 admin
3. 攞 chat_id：向 bot 發一句嘢，然後開 `https://api.telegram.org/bot<token>/getUpdates` 睇 `chat.id`（channel 係負數，例如 `-1001234567890`）
4. 兩個值放落 `%USERPROFILE%\.stockscan\.env`：
```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

---

## 3. 規矩（延續第一階段）

- 門檻只喺 `config.py` 改，每次改寫入 HANDOVER。
- 對照失手唔准夾數。
- 唔准 cat / print / commit 任何 token；log 入面唔准出現 token。
- MCP 只可用嚟即場核對數字，程式碼一律用 `longbridge` SDK。
- 每段完結 commit + push + 更新 HANDOVER。
- 429 退避唔准縮短；寧願慢。

---

## 4. 驗收（KL 起身睇）

| # | 項目 | 通過條件 |
|---|---|---|
| 1 | 09-04 對照 | HANDOVER §4 有命中率同差異原因 |
| 2 | 快取 | 重跑 09-07 <5 分鐘 |
| 3 | 面板 | 20 日 CSV + panel + HANDOVER §9 摘要 |
| 4 | B | `--loop 60 --once` 本機跑到；alert_type 分 SURGE/VOLUME |
| 5 | Telegram | dry-run 格式正確（真發視乎 KL 有冇放 token） |
| 6 | Streamlit | 四 tab；tab 4 有圖 |
| 7 | 安全 | repo 內無 `.env`；`.env` 喺 `%USERPROFILE%\.stockscan\` |
| 8 | pytest | 全綠 |

---

## 5. 下手（第三階段）候選

1. 長開 worker 搬上雲（Render background worker），唔靠本機 PC 開機。
2. alert 寫入 Turso；同 CCASS API、公告串接，入 Round 4 morning brief 五訊號。
3. 宇宙由種子換成 `universe_full_20260907.csv`，每日動態算市值。
4. 用兩星期真實 alert 對照 RTSS Telegram 頻道，量化「我哋多咗／漏咗」。
5. 「當日第 N 次」前瞻預測力檢驗（第一階段研究遺留最高價值假設）。

*只供學術研究及風險分析，不構成投資建議。*
