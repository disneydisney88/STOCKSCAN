# STOCKSCAN｜zcode 8 小時 MVP 任務規格書（v2）

**v2 改動（2026-09-07 晚）**：加入 `universe_full_20260907.csv`（第 1 節 3b、第 2 節、H1、第 8 節）；H1 加除牌交叉檢查同 `--source full` 開關。其餘不變。

**日期**：2026-09-07　**執行者**：zcode（非 Codex）　**驗收人**：KL
**Repo**：https://github.com/disneydisney88/STOCKSCAN（目前空 repo，無 branch）
**Streamlit**：stockscan-dveokumsofy2vnundqfcg7.streamlit.app（已預留 domain）
**Google Drive 交收夾**：folder ID `1nRXamKWGED37CMltfC2NzFcV22JxnuHj`

> 本工具只供學術研究及風險分析，不構成投資建議。任何輸出必須附此聲明。

---

## 0. 一段話講清楚要砌乜

複製「倍升RtSS」頻道兩種訊號嘅骨架，全部用 Longbridge OpenAPI 公開數據自行計算：

| 訊號 | 定義（本 repo 嘅口徑，寫死喺 `config.py`） | 產出 |
|---|---|---|
| **A. 收市爆量榜** | 市值 <10 億 且 今日成交額 >50 萬 且 今日成交額 ÷ 前 10 個交易日成交額均值 ≥10×（前 10 日**不含**今日） | 每日一個 CSV，8 欄照 RTSS |
| **B. 即市急升異動** | 市值 <3 億（可調）且 即時成交額 ≥50 萬 且 即時升幅 ≥+20%；之後每多升 20pt 再發一次，記「當日第 N 次 (舊級→新級)」 | 逐條 alert 寫入 CSV；Streamlit 有「即掃一次」掣 |

**8 小時目標**：A 完整、B 半成品（手動觸發可用）、GitHub Actions 每日自動跑 A、Streamlit 可開、HANDOVER.md 齊。**唔做**：Telegram 推送、Turso、長開 worker、CCASS 串接。

---

## 1. 開工前 KL 要準備（zcode 開始前 15 分鐘）

| # | 項目 | 放邊 |
|---|---|---|
| 1 | Longbridge OpenAPI：`LONGPORT_APP_KEY`、`LONGPORT_APP_SECRET`、`LONGPORT_ACCESS_TOKEN`（open.longbridge.com → 開發者 → 建立應用；**記低 token 到期日**） | 本機 `.env`（**唔可以 commit**） |
| 2 | Longbridge App 內確認已開港股即時報價（LV1 已夠） | — |
| 3 | 股票宇宙種子檔 `universe_seed_20260831.csv`（1,564 隻，全部市值 ≤9.9 億，utf-8-sig） | 放入 repo `data/universe_seed_20260831.csv` |
| 3b | 全港股本證券名單 `universe_full_20260907.csv`（2,868 隻：主板 2,561 + GEM 307，已剔窩輪／牛熊／債券／ETF；欄位 `code5, symbol_lb, name, board, is_reit, in_seed_20260831`） | 放入 repo `data/universe_full_20260907.csv`——**今晚只放，唔用**，留畀下手 |
| 4 | GitHub 已登入、有 push 權限 | — |
| 5 | Streamlit Cloud 已連 GitHub（截圖已見） | — |

zcode 第一個動作係讀本文件，然後建立 `HANDOVER.md`（見第 7 節）。

---

## 2. Repo 目錄結構（必須跟）

```
STOCKSCAN/
├── streamlit_app.py            # Streamlit 入口（Streamlit Cloud 要求呢個名喺 root）
├── requirements.txt            # longport, streamlit, pandas, python-dotenv, pytz
├── .gitignore                  # .env, state/*.json, __pycache__
├── .env.example                # 三個 LONGPORT_ 變數名，值留空
├── README.md
├── HANDOVER.md                 # 交接文件，每個 checkpoint 更新
├── config.py                   # 全部門檻、路徑、時區（唯一改參數嘅地方）
├── stockscan/
│   ├── __init__.py
│   ├── lb_client.py            # Longbridge QuoteContext 封裝、分批、rate-limit 退避
│   ├── universe.py             # 讀種子 CSV → 標準化代號 → 補 static_info 股數
│   ├── scan_eod.py             # 訊號 A：收市爆量榜
│   ├── scan_intraday.py        # 訊號 B：即市急升 + 當日第 N 次狀態機
│   ├── calendar_hk.py          # trading_days 封裝
│   └── io_utils.py             # CSV 讀寫、時間戳、統一欄位
├── scripts/
│   ├── run_eod.py              # CLI：python scripts/run_eod.py --date 2026-09-07
│   ├── run_intraday.py         # CLI：掃一次即市
│   └── probe_ratelimit.py      # 第一小時用：測 quote 批量上限同每秒次數
├── data/
│   ├── universe_seed_20260831.csv   # KL 提供（今晚用）
│   ├── universe_full_20260907.csv   # KL 提供（全港 2,868 隻，下手換入）
│   ├── universe.csv                 # universe.py 產出（含 total_shares / hk_shares）
│   ├── eod/                         # radar_eod_YYYYMMDD.csv
│   └── intraday/                    # alerts_YYYYMMDD.csv
├── state/
│   └── intraday_state_YYYYMMDD.json # 當日第 N 次狀態（gitignore）
├── tests/
│   ├── test_formulas.py             # 純函數測試：10MA、倍數、級距
│   └── fixtures/                    # 09-04 RTSS 榜 15 隻對照表（手打）
└── .github/workflows/
    └── eod_scan.yml                 # 每個交易日 16:35 HKT 跑 A，commit CSV
```

Branch：**`main`**（唔好用 master；Streamlit 部署頁要改 branch = main）。

---

## 3. 資料口徑（寫入 `config.py`，唔准散落各處）

```python
TZ = "Asia/Hong_Kong"
MCAP_CAP_EOD   = 10e8      # 訊號 A 市值上限（港元）
MCAP_CAP_INTRA = 3e8       # 訊號 B 市值上限
TURNOVER_MIN   = 5e5       # 成交額下限 50 萬
MA_DAYS        = 10        # 前 10 個交易日，不含今日
RATIO_MIN      = 10.0      # 今日/10MA
INTRA_FIRST_PCT = 20.0     # 第一次 alert 升幅門檻
INTRA_STEP_PCT  = 20.0     # 每級 20pt
QUOTE_BATCH     = 500      # 每次 quote 最多 500 隻（probe 後可改）
```

**市值分母規則（必須記錄）**：
- `mcap_total = last_price × total_shares`（static_info）
- `mcap_hk    = last_price × hk_shares`（如有）
- 篩選用 `mcap_total`；CSV 兩個都輸出；**種子 CSV 嘅「市值」欄只作首日對照，唔用嚟篩**。
- 有內資股（種子 CSV「內資股(佔比)」≠ `-`）嘅股票加一欄 `has_domestic_shares=1`，之後研究要分開睇。

**代號格式**：種子檔 `00623.hk` → Longbridge `623.HK`（去前導零、大寫 HK）。CSV 輸出時保留 5 位 `00623` 一欄，方便同 Project 其他檔 join。

**成交額口徑**：訊號 A 用 `candlesticks` 日線 `turnover`（全日）；訊號 B 用 `quote.turnover`（即時累計）。兩者欄名分別叫 `turnover_day` / `turnover_intraday`，唔可以混。

**前 10 日均值**：`history_candlesticks_by_offset` 或 `candlesticks(Period.Day, count=11)`，取最後 11 支，剔除最後一支（今日）後平均；不足 10 支則 `ma10_days_available` 記實際支數，比率仍計但加旗 `ma_short=1`。

---

## 4. 八小時分段工作表（每段末必須更新 HANDOVER.md）

### H0　0:00–0:40　地基
1. `git init`、建 `main`、建目錄樹、`.gitignore`、`.env.example`、`requirements.txt`。
2. `lb_client.py`：讀 `.env` → `Config.from_env()` → `QuoteContext`；封裝 `quote_batch(symbols)`、`static_info_batch(symbols)`、`candles(symbol, n)`；統一 try/except，遇 429/限流 sleep 指數退避（1,2,4,8s，最多 5 次）。
3. `scripts/probe_ratelimit.py`：對 700.HK 等 20 隻試 quote；再試 100/300/500 隻一批；記錄每批耗時同錯誤。**結果寫入 HANDOVER.md §實測限額**，並據此改 `QUOTE_BATCH`。
4. 首次 push 到 GitHub `main`。

✅ Checkpoint H0：`python -c "from stockscan.lb_client import *"` 無錯；probe 有數字。

### H1　0:40–1:40　股票宇宙
1. `universe.py`：讀種子 CSV（`encoding="utf-8-sig"`），標準化代號，去重（種子有 2 個重複代號）。
   - 種子入面 5 隻已唔喺 HKEX 現名單（02900、02901、02903、02912、08577，似已除牌）：用 `universe_full` 嘅 `code5` 做交叉，唔喺名單嘅標 `delisted_suspect=1` 並剔出掃描。
   - `universe.py` 要留一個 `--source full` 開關，可以改讀 `universe_full_20260907.csv`（今晚唔開，但寫好接口）。
2. 分批 `static_info` 補 `name_hk`、`total_shares`、`hk_shares`、`lot_size`、`board`；失敗嘅記 `static_missing=1` 唔好 drop。
3. 輸出 `data/universe.csv`；統計：總數、static 成功率、有內資股數。
4. `calendar_hk.py`：`trading_days(Market.HK, start, end)`；提供 `last_trading_day(asof)`、`prev_n_trading_days(asof, n)`。

✅ Checkpoint H1：`universe.csv` ≥1,500 行，static 成功率 ≥95%。

### H2　1:40–3:10　訊號 A 收市榜（核心）
1. `scan_eod.py::run(date)`：
   - universe → 分批 `candles(symbol, 11)`（如 `--date` 係過去日子，用 by_date 版本取 date 前 11 支）
   - 計 `turnover_day`、`ma10`、`ratio`、`mcap_total`、`turnover_to_mcap`
   - 篩三條件 → 按市值由細到大排（照 RTSS）
2. 輸出 `data/eod/radar_eod_YYYYMMDD.csv`，欄位：
   `code5, symbol, name, close, chg_pct, turnover_day, mcap_total, mcap_hk, ma10, ratio, turnover_to_mcap, ma10_days_available, has_domestic_shares, scan_time`
3. **驗收對照**：用 `--date 2026-09-04` 跑（RTSS 09-06 23:06 嗰張圖係 09-04 數據），對照 `tests/fixtures/rtss_20260904.csv`（下表，zcode 手打入 fixture）。記錄：命中幾多／我哋多咗邊啲／漏咗邊啲／差異原因（市值分母？成交額口徑？）。
4. 再跑 `--date 2026-09-07`（今日）。

RTSS 09-04 榜（15 隻）：
`01393,08483,01663,03997,00328,02322,01094,03789,08375,01587,00756,02170,00529,00201,02167`

✅ Checkpoint H2：兩個 CSV 存在；對照表命中率寫入 HANDOVER.md。**命中 ≥10/15 先算過關；<10 要先查分母，唔好改門檻夾數。**

### H3　3:10–4:10　訊號 B 即市掃描（半成品可接受）
1. `scan_intraday.py::scan_once()`：
   - universe 篩 `mcap_total < MCAP_CAP_INTRA`（用昨日收市價預篩，減少 quote 數）
   - `quote_batch` → `chg_pct = (last_done/prev_close − 1)×100`、`turnover_intraday`、即時 `mcap`
   - 讀 `state/intraday_state_YYYYMMDD.json`：`{symbol: {"level": 40, "count": 2, "last_alert": "11:40:28"}}`
   - 級距 = `floor(chg_pct / 20) × 20`；若 `chg_pct ≥ 20` 且（無紀錄 或 級距 > 已記級距）→ 出 alert，`count += 1`，記 `"level_from→level_to"`
   - alert 追加寫 `data/intraday/alerts_YYYYMMDD.csv`：
     `ts, code5, symbol, name, count_today, level_from, level_to, chg_pct, last_done, turnover_intraday, mcap_now`
2. `scripts/run_intraday.py`：跑一次即出；加 `--loop 60` 選項（每 60 秒循環，本機用，Streamlit 唔用）。
3. 非交易時段跑：照計，但 alert 加 `off_hours=1`。

✅ Checkpoint H3：本機跑一次有輸出（就算今晚係收市後，用 prev_close 對 last_done 一樣會有數）。

### H4　4:10–5:40　Streamlit
`streamlit_app.py` 三個 tab，全部只讀 `data/`，唔喺 Streamlit 內跑重掃（免 Cloud timeout）：
1. **收市爆量榜**：日期選擇 → 讀 `radar_eod_*.csv` → 表格 8 欄 + 下載掣。
2. **即市掃描**：一個「掃一次」掣 → 呼叫 `scan_once()`（讀 `st.secrets` 取 Longbridge key）→ 顯示 alert 表；如 `st.secrets` 缺 key，顯示提示而唔係 crash。
3. **對照 RTSS**：顯示 09-04 對照結果（命中／多／漏）。
頁尾固定顯示免責聲明。

Secrets（Streamlit Cloud → Advanced settings → Secrets，TOML）：
```toml
LONGPORT_APP_KEY = ""
LONGPORT_APP_SECRET = ""
LONGPORT_ACCESS_TOKEN = ""
```
`lb_client.py` 讀取次序：`st.secrets`（如喺 Streamlit 內）→ `.env` → 環境變數。

✅ Checkpoint H4：`streamlit run streamlit_app.py` 本機開到三個 tab。

### H5　5:40–6:40　自動化 + 部署
1. `.github/workflows/eod_scan.yml`：
   - `schedule: cron "35 8 * * 1-5"`（UTC 08:35 = HKT 16:35；Actions cron 會遲 5–15 分鐘，可接受）
   - `workflow_dispatch` 手動掣
   - steps：checkout → python 3.11 → pip install → `python scripts/run_eod.py` → `git commit data/eod/*.csv` → push
   - secrets 用 GitHub repo Secrets（三個 LONGPORT_）
2. push `main`；喺 Streamlit 部署頁改 **Branch = main、Main file = streamlit_app.py**，貼 secrets，Deploy。
3. 手動 trigger 一次 workflow_dispatch，確認 commit 返嚟。

✅ Checkpoint H5：Streamlit URL 開到；Actions 手動跑成功一次。

### H6　6:40–7:30　測試、README、交接
1. `tests/test_formulas.py`：10MA（含不足 10 支）、ratio、級距函數、代號轉換，`pytest` 全綠。
2. README：一頁——點裝、點跑、點改門檻、數據口徑、免責。
3. **HANDOVER.md 最終版**（第 7 節格式）。
4. 產出交收包 → KL 上載 Drive（zcode 無 Drive 權限，由 KL 手動）：
   - `HANDOVER.md`
   - `data/eod/radar_eod_20260904.csv`、`radar_eod_20260907.csv`
   - `data/universe.csv`
   - probe 結果

### Buffer　7:30–8:00
優先修 H2 對照差異；有剩時間先做「Telegram 推送」stub（`notify.py`，只留 function 簽名同 TODO）。

---

## 5. 每小時都要守嘅規矩

- **唔准 commit `.env` 或任何 token**。push 前 `git diff --cached | grep -i token`。
- **門檻只喺 `config.py` 改**，改咗要喺 HANDOVER 記低點解。
- **對照失手唔准夾數**：先寫低差異，再判斷係口徑定 bug。
- 每個 API 錯誤要 log 落 `logs/`（gitignore），唔准 silent pass。
- 任何「今日」都用 HKT，唔好用機器本地時間。
- 每段完結必須：commit + push + 更新 HANDOVER.md 嘅 checkpoint 表。

---

## 6. 驗收標準（KL 明早檢查）

| # | 項目 | 通過條件 |
|---|---|---|
| 1 | GitHub `main` | 目錄結構照第 2 節；無 secrets |
| 2 | `data/eod/radar_eod_20260904.csv` | 存在，對照 RTSS 15 隻命中 ≥10，差異有解釋 |
| 3 | `data/eod/radar_eod_20260907.csv` | 存在 |
| 4 | Streamlit URL | 開到，tab 1 有表 |
| 5 | Actions | 手動跑過一次成功 |
| 6 | HANDOVER.md | 六個 checkpoint 全有狀態；「下手要做」清單 ≥5 項 |
| 7 | `pytest` | 全綠 |

半成品可接受嘅位：tab 2 即市掃描可以只係「本機跑到、Cloud 未試」；Actions cron 未等到自動觸發。

---

## 7. HANDOVER.md 格式（zcode 由 H0 開始維護）

```markdown
# STOCKSCAN HANDOVER
更新時間（HKT）：
執行者：zcode　交接對象：下一位（Codex / Claude / KL）

## 1. 而家去到邊
| Checkpoint | 狀態 (✅/⚠/❌) | 備註 |
| H0 地基 | | |
| H1 宇宙 | | |
| H2 收市榜 | | 命中 x/15 |
| H3 即市 | | |
| H4 Streamlit | | |
| H5 部署 | | |
| H6 測試交接 | | |

## 2. 實測限額（probe 結果）
- quote 每批最多：
- 每秒次數：
- 全宇宙一輪耗時：

## 3. 數據口徑決定（同 config.py 一致）
## 4. 對照 RTSS 09-04 結果
- 命中：
- 我哋多咗：（代號＋原因）
- 我哋漏咗：（代號＋原因）
## 5. 已知 bug / 未完成
## 6. 下手要做（按優先）
1. 
## 7. 點樣本機重跑（三行命令）
## 8. Secrets 放邊（只寫位置，唔寫值）
```

---

## 8. 下手（Codex／Claude）預計接手嘅事（今晚唔做）

1. **宇宙換成 `universe_full_20260907.csv`（2,868 隻）**：每日用 Longbridge 即日價 × `total_shares` 重算，動態決定邊啲 <10 億／<3 億，唔再依賴 08-31 靜態種子。REIT（`is_reit=1`）預設剔除。
2. Telegram bot 推送（訊號 A 每日一張表、訊號 B 逐條）。
3. 長開 worker 跑 `--loop 60`（Render background worker）。
4. alert 寫入 Turso，同 CCASS API、公告串接（Round 4 morning brief 五訊號之一）。
5. 市值分母同 X1 shares-outstanding panel 對齊。
6. 兩星期同 RTSS 逐日對數後，決定門檻是否微調。

---

*本規格書及所有產出只供學術研究及風險分析，不構成投資建議。*
