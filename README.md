# STOCKSCAN｜倍升訊號掃描器

用 Longbridge OpenAPI 公開數據自行計算「倍升RtSS」頻道兩種訊號嘅骨架：

| 訊號 | 口徑（寫死喺 `config.py`） | 產出 |
|---|---|---|
| **A. 收市爆量榜** | 市值 <10 億 且 成交額 >50 萬 且 成交額 ÷ 前 10 個交易日均值 ≥10×（唔含今日） | `data/eod/radar_eod_YYYYMMDD.csv`，按市值由細到大 |
| **B. 即市急升異動** | 市值 <3 億 且 即市成交額 ≥50 萬 且 升幅 ≥+20%；每多升 20pt 再發，記「當日第 N 次」 | `data/intraday/alerts_YYYYMMDD.csv` 逐條 |

> **免責聲明**：本工具只供學術研究及風險分析，不構成投資建議。

## 點裝

```bash
pip install -r requirements.txt
cp .env.example .env        # 填入三個 LONGPORT_ 變數（open.longbridge.com → 開發者）
```

## 點跑

```bash
python -m stockscan.universe              # 建宇宙 data/universe.csv（一次性，之後 Actions 會補）
python scripts/run_eod.py                 # 訊號 A：今日（首次會拉 40 支日 K 入快取）
python scripts/run_eod.py --date 2026-09-04   # 訊號 A：過去日子＋自動對照 RTSS
python scripts/run_eod.py --codes 1393,8483   # 只掃某幾隻（debug）
python scripts/run_eod.py --notify --dry-run  # 印 Telegram 訊息唔發送
python scripts/run_intraday.py --once     # 訊號 B：掃一次
python scripts/run_intraday.py --loop 60  # 訊號 B：交易日 09:30–12:00／13:00–16:10 HKT 每 60 秒循環
python scripts/backfill_eod.py --start 2026-08-10 --end 2026-09-07  # 回填＋面板（零 API）
python scripts/compare_rtss.py --all      # 對照所有 RTSS fixture
python scripts/probe_ratelimit.py         # 實測 API 限額（結果寫 logs/）
streamlit run streamlit_app.py            # 網頁版
pytest -q                                 # 測試
```

## 即市監察點開（常駐）

- 手動（推薦先試）：`python scripts/run_intraday.py --loop 60`，交易日 09:30–12:00／13:00–16:10
  HKT 自動掃，午休／收市自動瞓，Ctrl-C 隨時走（狀態已落盤）。
- Windows 開機自動：`scripts/schedule_intraday.ps1`（登記 09:25 每日啟動；**要你自己行一次**，
  檔內有寫登記同移除命令）。

## Telegram 點設定（3 分鐘）

1. Telegram 搵 **@BotFather** → `/newbot` → 攞 token
2. 開私人 group／channel，加 bot 做 admin
3. 向 bot 發一句嘢，開 `https://api.telegram.org/bot<token>/getUpdates` 抄 `chat.id`
4. 兩個值加去 `C:\Users\<你>\.stockscan\.env`：`TELEGRAM_BOT_TOKEN=…`、`TELEGRAM_CHAT_ID=…`
5. 試：`python scripts/run_eod.py --date 2026-09-07 --notify --dry-run`（唔發），
   無問題就 `--notify`（真發）。GitHub Actions 想發就喺 repo Secrets 加同一對變數。

## 點改門檻

全部喺 [`config.py`](config.py)：`MCAP_CAP_EOD`（10 億）、`MCAP_CAP_INTRA`（10 億，P3 放寬）、
`TURNOVER_MIN`（50 萬）、`MA_DAYS`（10）、`RATIO_MIN`（10×）、`INTRA_FIRST_PCT`／`INTRA_STEP_PCT`
（20pt）、`INTRA_VOL_FIRST`／`INTRA_VOL_STEP`（10x）、`INTRA_POLL_SEC`（60）、
`QUOTE_BATCH`（500）、`CANDLE_WORKERS`（2）。改完喺 `HANDOVER.md` 記低原因。

## 數據口徑

- **時區**：所有「今日」用 `Asia/Hong_Kong`。
- **市值**：`last/close × total_shares`（static_info 口徑）；篩選用 `mcap_total`，
  有 H 股／內資股另出 `mcap_hk`、`has_domestic_shares` 旗。
- **成交額**：訊號 A 用日 K `turnover`（全日）；訊號 B 用 `quote.turnover`（即市累計）。
- **代號**：輸出保留 5 位 `00623` 一欄（`code5`），Longbridge 格式 `623.HK`。
- **前 10 日均值**：日 K 取 11 支、剔最後一支（今日）後平均；不足 10 支照計，
  `ma10_days_available` 記實際支數、`ma_short=1`。
- 種子檔「市值」欄只作首日對照，唔用嚟篩。
- **快取**（P1）：`data/cache/daily/{code5}.csv`（不入 git，Drive 同步）。官方 API 所有
  timestamp 係 UTC——日 K 日期必須轉 HKT 先取（`kline_cache.merge_save` 已處理，
  有回歸測試看門）。歷史K線端點有 100 標的／期硬配額（301607），大規模拉數用即市
  K 線端點（收市後回傳最近 N 支已確認日 K）。

## 自動化

- GitHub Actions：`.github/workflows/eod_scan.yml`，交易日 HKT 16:35 自動跑訊號 A
  （`--notify`）並 commit CSV（repo Secrets：三個 Longbridge 變數＋兩個 TELEGRAM_ 變數，
  唔設 TELEGRAM_ 就只掃唔推）。
- Streamlit Community Cloud：連 `main` branch、main file = `streamlit_app.py`；
  Secrets 填三個 Longbridge 變數（`LONGBRIDGE_*` 或 `LONGPORT_*` 前綴都得）。

## 接手

睇 [`HANDOVER.md`](HANDOVER.md)——checkpoint 狀態、probe 實測、RTSS 對照結果、下手清單。
