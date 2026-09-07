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
python scripts/run_eod.py                 # 訊號 A：今日
python scripts/run_eod.py --date 2026-09-04   # 訊號 A：過去日子＋自動對照 RTSS
python scripts/run_intraday.py            # 訊號 B：掃一次
python scripts/run_intraday.py --loop 60  # 訊號 B：每 60 秒循環（本機用）
python scripts/probe_ratelimit.py         # 實測 API 限額（結果寫 logs/）
streamlit run streamlit_app.py            # 網頁版
pytest -q                                 # 測試
```

## 點改門檻

全部喺 [`config.py`](config.py)：`MCAP_CAP_EOD`（10 億）、`MCAP_CAP_INTRA`（3 億）、
`TURNOVER_MIN`（50 萬）、`MA_DAYS`（10）、`RATIO_MIN`（10×）、`INTRA_STEP_PCT`（20pt）、
`QUOTE_BATCH`（500，probe 後可調）。改完喺 `HANDOVER.md` 記低原因。

## 數據口徑

- **時區**：所有「今日」用 `Asia/Hong_Kong`。
- **市值**：`last/close × total_shares`（static_info 口徑）；篩選用 `mcap_total`，
  有 H 股／內資股另出 `mcap_hk`、`has_domestic_shares` 旗。
- **成交額**：訊號 A 用日 K `turnover`（全日）；訊號 B 用 `quote.turnover`（即市累計）。
- **代號**：輸出保留 5 位 `00623` 一欄（`code5`），Longbridge 格式 `623.HK`。
- **前 10 日均值**：日 K 取 11 支、剔最後一支（今日）後平均；不足 10 支照計，
  `ma10_days_available` 記實際支數、`ma_short=1`。
- 種子檔「市值」欄只作首日對照，唔用嚟篩。

## 自動化

- GitHub Actions：`.github/workflows/eod_scan.yml`，交易日 HKT 16:35 自動跑訊號 A 並 commit CSV
  （需喺 repo Secrets 設三個 `LONGPORT_` 變數）。
- Streamlit Community Cloud：連 `main` branch、main file = `streamlit_app.py`；
  Secrets 同上三個變數（TOML 格式）。

## 接手

睇 [`HANDOVER.md`](HANDOVER.md)——checkpoint 狀態、probe 實測、RTSS 對照結果、下手清單。
