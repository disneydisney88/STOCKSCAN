# CODEX 任務規格書｜STOCKSCAN T 部分：RTSS Telegram Web 文字抓取（CDP）

**日期**：2026-09-09　**執行者**：Codex（本機 Windows，因為要連本機 Chrome）
**工作夾**：`G:\我的雲端硬碟\STOCKSCAN`　**Repo**：disneydisney88/STOCKSCAN `main`
**開工前必讀**：`HANDOVER.md` §5 陷阱；`pytest -q` 全綠先動手

> 只供學術研究及風險分析，不構成投資建議。

---

## 0. 目標一句話

用 Chrome remote debugging（port 9222）連 KL 已登入嘅 Telegram Web，**只抓 RTSS 頻道嘅文字 alert**（唔抓圖），解析入 CSV，再同 STOCKSCAN 自己嘅 alert 逐日對照。唔用 Telethon、唔用 Telegram API、唔借電話——純讀已 render 嘅 DOM，同 KL 自己碌螢幕無分別，谷主查唔到，唔 mark read、唔加 view count。

---

## 1. 前提（KL 每次跑前確認）

- Chrome 已用呢句開住（KL 已在做）：
  ```
  & "C:\Program Files\Google\Chrome\Application\chrome.exe" `
    --remote-debugging-port=9222 `
    --user-data-dir="C:\TGWebProfile" `
    "https://web.telegram.org/k/#-2795969450"
  ```
- `Invoke-RestMethod http://127.0.0.1:9222/json/version` 見到 `webSocketDebuggerUrl` = port 通
- RTSS 頻道（id `-2795969450`）已開喺畫面

---

## 2. 要抓嘅兩種訊息（都係文字）

**A. 急升異動（逐條）**
```
🔥 3億以下急升異動 [當日第1次]
📈 煜榮集團 (HK.01536)
💰 市值: 2.55億
📊 成交額: 590.25萬
📶 升幅: +23.08%
🕒 最新價: 0.560
🕐 15:XX:XX
相關範疇：港股細市值急升監控
```
解析欄位：`msg_type=SURGE`, `code5`, `name`, `mcap`, `turnover`, `chg_pct`, `last_price`, `time`, `count_today`（第 N 次）, `level_range`（如有 41%→61%）

**B. 大市值成交股（表格截圖嗰種）**——**跳過**。呢種係圖入面嘅表，DOM 攞唔到文字，唔做。只抓純文字 alert。

---

## 3. 工作

### T1　CDP 連接 + 抓文字
`scripts/fetch_rtss_cdp.py`：
- Playwright `connect_over_cdp("http://127.0.0.1:9222")`（`pip install playwright`，唔使 `playwright install`，因為連現有 Chrome 唔係開新）
- 揀到 RTSS 頻道嗰個 page/tab
- 向上捲動載入當日訊息（捲到見到「今日」以外日期就停）
- 只讀訊息文字節點（`.message` text），**唔截圖、唔抓 media**
- **唔准 mark read**：只讀 DOM，唔好撳入訊息、唔好觸發已讀
- 抽唔到嘅訊息記 log，唔好 crash

### T2　Parser
`stockscan/rtss_parser.py::parse_alert(text)`：
- 用 regex 抽 code5（`HK.XXXXX` → 5 位）、市值（億/萬 → 港元數值）、成交額、升幅、最新價、時間、第 N 次
- 市值單位換算：`X.XX億` → X.XX×1e8；`XXX.XX萬` → ×1e4
- 解析失敗保留原文 `raw_text`，標 `parse_failed=1`
- 加 pytest：用真樣本（煜榮 01536 嗰條）測到齊欄位

### T3　輸出
- `data/rtss/rtss_alerts_YYYYMMDD.csv`（逐條，欄位見 §2A）
- 同一條 alert（同 code、同 time）唔好重複寫；跑多次要 upsert

### T4　同 STOCKSCAN 對照
`scripts/compare_rtss_daily.py`：
- 當日 `rtss_alerts_YYYYMMDD.csv` vs STOCKSCAN `data/intraday/alerts_YYYYMMDD.csv`
- 按 code5 分三組：`both`（兩邊都有）、`rtss_only`（佢有我哋冇）、`stockscan_only`（我哋有佢冇）
- 輸出 `data/reports/rtss_daily_diff_YYYYMMDD.csv`
- `rtss_only` 嗰批要記低點解漏（市值超 3 億？成交唔夠？我哋 daemon 冇開？）——只記數字同可能原因，唔落結論

### T5　Backfill KL 手動檔
- KL 用 TGWebExporter 抓咗 8-29 至今嘅檔（喺 `C:\TGWebExporter` 或 KL 指定路徑）
- 寫 `scripts/import_rtss_backfill.py` 讀嗰啲檔，用同一個 parser 入 `data/rtss/`
- 驗證 parser 喺歷史檔一樣 work

### T6　Streamlit tab 9「RTSS 對照」
- 揀日期 → 顯示三組（both / rtss_only / stockscan_only）數目同名單
- 逐日 diff 趨勢

---

## 4. 規矩
- 只讀 DOM，唔干擾 KL 正常用 Telegram（唔撳、唔已讀、唔截圖）
- Telegram Web DOM 改版會令 selector 壞——parser 同 selector 要容錯，抽唔到記 log 大聲講，唔好靜靜 pass
- 唔准 commit 任何 session／cookie／個人訊息內容以外嘅嘢；`data/rtss/` 入 gitignore（因為係第三方頻道內容，唔好公開 push）——**改為只 commit 解析後嘅 diff 統計，原始 alert CSV 留本機**
- 每個模組獨立 commit + HANDOVER §15

## 5. 驗收
| # | 項目 | 條件 |
|---|---|---|
| T1 | CDP 連接 | 連到現有 Chrome，讀到當日 RTSS 文字 |
| T2 | Parser | 煜榮 01536 樣本欄位齊；pytest 綠 |
| T3 | 輸出 | `rtss_alerts_YYYYMMDD.csv` 有當日 alert |
| T4 | 對照 | `rtss_daily_diff` 三組數目 |
| T5 | Backfill | 8-29 至今歷史檔入到庫 |
| T6 | tab 9 | 開到，顯示 diff |

## 6. 之後
每晚自動跑（Windows 排程，同 intraday_daemon 一齊）；儲夠 20 日 RTSS vs STOCKSCAN diff，量化兩者差異，做 RTSS 有效性研究更新。

## 7. 補充執行規則（KL 2026-09-09）

1. `data/rtss/` 只加入 `.gitignore`，唔 push；原始 RTSS 文字照留喺 Drive 工作夾，唔另做交收。
2. `scripts/fetch_rtss_cdp.py` 支援 `--backfill --from YYYY-MM-DD --to YYYY-MM-DD`，可捲到指定日期範圍一次過補抓；Telegram 訊息唔會消失。
3. 所有「當日」及「檔名日期」一律用 `today_hkt()`，唔准用 GMT 機器時間（對應 HANDOVER §5.6/5.10）。

*只供學術研究及風險分析，不構成投資建議。*
