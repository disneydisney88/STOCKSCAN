# STOCKSCAN｜zcode 第四階段夜間長工任務規格書（4–6 小時）

**日期**：2026-09-08 晚　**執行者**：zcode　**前手**：Codex（第三階段 M1–M7 + 四項小修）
**工作夾**：`G:\我的雲端硬碟\STOCKSCAN`　**Repo**：disneydisney88/STOCKSCAN `main`
**開工前必讀**：`HANDOVER.md`（§5 陷阱、§11 第三階段進度）→ `config.py` → `pytest -q` 全綠先動手

> 只供學術研究及風險分析，不構成投資建議。

---

## 0. 而家去到邊（一段話）

訊號 A 收市榜對 RTSS 15/15，Actions 每日 16:35 HKT 自動跑（09-08 係第一次真跑，開工前先睇 Actions 頁有冇成功，失敗就 Z0 先修）。訊號 B 即市可用但要人手撳掣。13 個月面板、事件庫、券商射倉、事件率 tab 全部落地。M7 CCASS 代碼齊但上游 Render 服務 `/api/stock` 斷線。今晚目標：**令訊號 B 自動跑、修返 CCASS 上游、加個股研究頁**。

---

## 1. 任務（按優先；每項獨立 commit + push + HANDOVER §12）

### Z0　0:00–0:20　檢查 Actions 首次真跑
- GitHub Actions `eod_scan` 09-08 16:35 HKT 嗰次：成功 → `data/eod/radar_eod_20260908.csv` 應已 commit，Streamlit tab 1 日期選單有 09-08
- 失敗 → 讀 log 修，手動 `workflow_dispatch` 一次補返 09-08
- 順便核對：09-08 榜同 RTSS 09-08 收市榜（KL 如有截圖會放 `tests/fixtures/rtss_20260908.csv`；冇就跳過）

### Z1　0:20–1:30　訊號 B 本機自動化（唔使雲、唔使錢）
目標：KL 部機開住就自動掃，唔使撳掣。
1. `scripts/intraday_daemon.py`：包住 `run_intraday.py --loop 60`
   - 崩潰自動重啟（最多 5 次／日，間隔 60 秒）
   - 非交易日／非交易時段 sleep 到下一個開市
   - log 轉檔：`logs/intraday_YYYYMMDD.log`，保留 30 日
   - 每日 16:15 HKT 收市後寫 `data/intraday/summary_YYYYMMDD.csv`：每隻股當日最高 level、alert 總數、首次 alert 時間、首次 alert 價 vs 收市價
2. **註冊 Windows 工作排程器**（今次真係註冊，唔係淨寫檔）：
   - 任務名 `STOCKSCAN_intraday`，觸發：每日 09:20 HKT（留意部機時鐘係 GMT，排程用本機時間要換算，或者 daemon 自己用 HKT 判斷）
   - 動作：`python G:\我的雲端硬碟\STOCKSCAN\scripts\intraday_daemon.py`
   - 「即使使用者未登入亦執行」唔使勾（要密碼）；勾「喚醒電腦」
   - 用 `schtasks /query /tn STOCKSCAN_intraday` 驗證已註冊
3. 復牌／長停牌假訊號：`chg_pct` 計算前查快取最後一支 K 嘅日期，距今 >5 個交易日 → 標 `resumption_suspect=1`，alert 照出但另一欄標記（同合股 guard 並行，02738 嗰單要查清楚係合股定復牌，寫 HANDOVER）

✅ 驗收：`schtasks` 見到任務；手動跑 daemon 30 秒後 Ctrl-C 正常退出；summary 格式有樣本

### Z2　1:30–3:00　修 CCASS 上游（另一個 repo）
Repo 本機位置：`C:\Users\klcho\webbsite-ccass-tool-github`（HANDOVER 有提；冇就 `git clone disneydisney88/webbsite-ccass-tool`）
1. 先診斷：Render → Logs（zcode 開唔到就叫 KL 貼），確認係 worker timeout 定 OOM
2. 修法（按次序試）：
   - `Procfile`／`render.yaml`：`gunicorn --timeout 300 --workers 1 --threads 2`
   - `/api/stock` 改 **cache-first**：先查 Turso 有冇今日快照，有就即回；冇先即時抓，抓完寫 Turso
   - 抓取加 `?light=1` 選項：只抓 Concentration + Big Changes 兩頁（STOCKSCAN 只需要呢兩樣），唔抓全部 holdings
3. push → Render 自動 deploy → 用 01393 測 `/api/stock?light=1`
4. 成功後返 STOCKSCAN 跑 `python scripts/run_ccass.py --date 2026-09-08`，睇 `data/ccass/` 有冇 JSON

✅ 驗收：01393 一個 request <60 秒回 200；09-08 榜 ≥80% 有 JSON。**如果 2 小時內修唔好，停低寫清楚診斷，唔好死磨。**

### Z3　3:00–4:30　Streamlit tab 6「個股研究頁」
輸入 code5 → 一頁睇晒呢隻股喺所有庫嘅紀錄（研究用，唔係炒股用）：
1. 基本：名、市值、股數、`in_seed`、`is_reit`
2. 面板：13 個月每次上榜日（M3），折線圖：收市價 + 上榜日標記
3. 事件（M1）：時間軸列出配股／供股／GO／合股／拆股／CB，最近 24 個月
4. 券商射倉（M5）：上榜日 ±5 日嘅射倉紀錄
5. RTSS 歷史（M6）：呢隻股喺 RTSS 522 條 alert 出現過幾次、n_max_est
6. CCASS（M7）：如有 JSON 就顯示 Top 5／Top 10 走勢
7. 即市（B）：今日 alert 紀錄
每個區塊冇數據就寫「無紀錄」，唔好留空。

✅ 驗收：輸入 01825、00254、08368 三隻，每個區塊有嘢或寫「無紀錄」

### Z4　4:30–5:00　數據質量審計（只記錄，唔改數）
1. `mcap_unreliable=1` 佔面板幾多行；按月分佈
2. 面板 `mcap_total` vs 種子檔「市值」（08-31）對 1,557 隻：差 >30% 嘅列表 + 原因猜測（合股／配股／內資股）
3. 訊號 B 今日 alert 入面 `corp_action_suspect` 同 `resumption_suspect` 各幾條
4. 寫 HANDOVER §13「數據質量」

### Z5　5:00–5:30　收尾
1. 3 個舊券商射倉 xlsx：KL 如已放 `data/raw/`，跑 M5 補入；未放就記低
2. Telegram：KL 如已放 `TELEGRAM_BOT_TOKEN`／`CHAT_ID`，`--notify` 真發一次 EOD 表；未放就跳過
3. HANDOVER §12 第四階段狀態表、§6 下手要做重排；README 加「daemon 點開點停」
4. `pytest -q` 全綠；push

---

## 2. 規矩（同前，重點三條）
- 唔准 cat／print／commit token；`.env` 只喺 `%USERPROFILE%\.stockscan\`
- 門檻只喺 `config.py` 改；改咗寫 HANDOVER
- 修 CCASS repo 時**唔准改 STOCKSCAN 嘅 client 接口**，兩邊獨立 commit

## 3. KL 明早睇（驗收）

| # | 項目 | 通過條件 |
|---|---|---|
| 1 | Actions 09-08 | tab 1 有 09-08 |
| 2 | 排程 | `schtasks` 見 `STOCKSCAN_intraday`；09-09 開市後 tab 2 自動有 alert |
| 3 | CCASS | 01393 回 200，或 HANDOVER 有清楚診斷 |
| 4 | tab 6 | 三隻測試股開到 |
| 5 | 審計 | HANDOVER §13 有數 |
| 6 | pytest | 全綠 |

## 4. 之後（第五階段候選）
Render 長開 worker（唔靠本機）；alert 入 Turso；RTSS Telegram 頻道自動抓取逐日對照（要 Telegram API id/hash）；「當日第 N 次」前瞻檢驗（要累積 ≥20 個交易日自家即市數據）；串入 Round 4 morning brief。

*只供學術研究及風險分析，不構成投資建議。*
