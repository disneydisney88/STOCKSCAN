# STOCKSCAN HANDOVER

更新時間（HKT）：2026-09-08 02:05
執行者：zcode　交接對象：下一位（Codex / Claude / KL）
工作夾（單一真相來源）：`G:\我的雲端硬碟\STOCKSCAN`（= Google Drive 同步，全部交收就喺呢度）
Repo：https://github.com/disneydisney88/STOCKSCAN（branch `main`）
Streamlit：https://stockscan-emwmwndwrop2emavfyatme.streamlit.app（四個 tab）

> 本工具只供學術研究及風險分析，不構成投資建議。

## 1. 而家去到邊（第一階段 H0–H6 ＋ 第二階段 P1–P6）

| Checkpoint | 狀態 | 備註 |
|---|---|---|
| H0 地基 | ✅ | config／lb_client（longbridge SDK 4.5.0）／probe；首次 push 完成 |
| H1 宇宙 | ✅ | 1,562 隻（剔 2 個 `_depre` 重複）；掃描宇宙 1,557；static 成功率 **100%**；內資股 21 隻 |
| H2 收市榜 | ✅ | **09-04 對照 RTSS 命中 15/15（100%），零多零漏**；09-07 命中 11 |
| H3 即市 | ✅ | SURGE＋VOLUME 雙觸發實測 21 條 alert（off_hours=1）；VOLUME 嗰 11 隻同 A 榜完全重疊 |
| H4 Streamlit | ✅ | KL 自己部署咗（stockscan-emwmwndwrop2emavfyatme）；本地加埋 tab4 |
| H5 部署 | ✅(半) | Actions workflow 已上（加咗 --notify）；GitHub Secrets 未貼 → 未試手動觸發 |
| H6 測試交接 | ✅ | pytest **49 項全綠**；README／HANDOVER 齊 |
| P1 EOD 提速 | ✅ | 日線快取 `data/cache/daily/{code5}.csv`（1,557 檔 × 40 支）；重跑 09-07 全程 **3 分鐘內**（實際 cached 日子秒級）；`--codes`／`--workers`／`--cache-only`／run_stats 全有 |
| P2 面板 | ✅ | 21 個交易日（08-10→09-07）逐日 CSV＋`radar_eod_panel.csv` 266 行；摘要見 §9 |
| P3 訊號B | ✅ | 門檻放寬 10 億；SURGE/VOLUME 各自第 N 次；掃描時段 09:30–12:00／13:00–16:10；`schedule_intraday.ps1` 只寫檔未註冊 |
| P4 Telegram | ✅(半) | notify.py＋`--notify`／`--dry-run`＋workflow；dry-run 格式已驗；**真發等 KL 放 TELEGRAM_ 兩個變數** |
| P5 Streamlit | ✅ | 四 tab：A 榜／B 即市（本機掃一次＋唯讀 alerts）／RTSS 對照／歷史面板（每日命中圖＋上榜王＋逐股翻查）；每個 tab 有「數據截至」 |
| P6 交接 | ✅ | 本檔＋README；push 完成（commit 見 git log） |

## 2. 實測限額（probe＋兩晚實戰）

- quote 每批 500 無問題（probe 實測 500 級別全過；QUOTA 無事）；**quote 延遲 warmup 後 ~3ms/隻**。
- 即市K線端點（`ctx.candlesticks`）：1,557 隻 × 40 支一次過拉晒，2 線程 6.6 分鐘，0 限流。
- **歷史K線端點（history_candlesticks_*）：硬配額 100 隻標的／期**（error 301607
  `requested:100/limit:100`）。第一晚 4 線程拉 09-04 嗰輪燒晒 100 個名額後全面跪。
  **教訓：大規模拉數用即市K線端點（收市後回最近 N 支已確認日 K），歷史端點慳住用。**
- 全宇宙一輪 quote（訊號 B）：~10 秒。
- 301607 出現時 `scan_eod.ensure_cache` 會早退用現有快取頂住，唔會燒 retry。

## 3. 數據口徑決定（同 config.py 一致）

- 時區一律 HKT。**⚠ 官方 API 所有 timestamp 係 UTC**——日 K timestamp 係 HKT 零晨，
  直接 `.date()` 會早一日（第一晚 0/15 全空榜根因）。`kline_cache.merge_save` 已轉 HKT，
  有回歸測試。**任何新代碼掂 timestamp 都要記住呢條。**
- `mcap_total = close × total_shares`（static_info）；篩選用 mcap_total；`mcap_hk` 另出。
- 訊號 A 成交額＝日 K `turnover`；訊號 B＝`quote.turnover`（即市累計）。
- 前 10 日均值：快取取 scan 日前 10 支；不足 10 支照計（`ma10_days_available`＋`ma_short=1`）。
- `turnover_to_mcap` 以百分比輸出。
- 代號：種子 `00623.hk` → `623.HK`；輸出 `code5=00623`。`02667.hk_depre`／`03301.hk_depre` 剔除。
- 除牌交叉：`universe_full_20260907.csv` 仍未放；暫用 config 硬編 5 隻。
- 訊號 B 預篩 `min(prev_close, last_done) × total_shares < 10 億`；最終篩 `mcap_now < 10 億`。
- 快取 `data/cache/daily/` **唔入 git**（1,557 細檔，Drive 已同步；Actions 每日全量重拉即市窗無損失）。
- `.env` 正印位置 `%USERPROFILE%\.stockscan\.env`（P0 安全：唔好俾 Drive 同步上雲）；
  讀取次序 st.secrets → repo .env（如存在）→ user profile → 環境變數；
  `LONGBRIDGE_*`／`LONGPORT_*` 兩個前綴都認。repo 內真 .env 已刪。

## 4. 對照 RTSS 09-04 結果

- **命中 15/15（100%）；多 0；漏 0。** 詳情 `data/eod/compare_rtss_20260904.json`。
- 手動核對樣本：01393 恒鼎實業——收市 0.028、成交 5.55M、ma10=197,320 → **28.1x**，
  同 RTSS 圖完全一致（呢個數確認埋「前 10 日均值唔含今日」嘅口徑係啱）。
- 邊緣個案都有：01094 承輝國際 -11.76% 跌住爆量 29.7x、00201 華大酒店 -6.06%——RTSS 榜唔篩升跌，
  我哋口徑一樣。
- 規格書 H2 門檻「命中 ≥10/15」：**超額完成**。
- P1 驗收「重跑結果同未快取版本逐行相同」：09-04 由快取重算仍係 15 隻同一批 ✓。

## 5. 已知 bug / 未完成

- GitHub Actions 未實跑過（等 KL 貼 Secrets：三個 Longbridge＋兩個 TELEGRAM_，唔設 TELEGRAM_ 會照跑只係唔推）。
- Streamlit Cloud tab2「掃一次」未試（要 Cloud Secrets；無快取時會即場拉 40 支日 K，慢過本機）。
- Telegram 真發未試（等 KL 放 `TELEGRAM_BOT_TOKEN`／`TELEGRAM_CHAT_ID` 入 `%USERPROFILE%\.stockscan\.env`）。
- `universe_full_20260907.csv`（2,868 隻）仍未放 `data/`；除牌交叉暫用硬編 5 隻。
- 快取 memo（in-memory）process 內不過期——長開 loop 每日第一次跑前重啟 process 就新鮮。
- 回填面後市值用今日 static_info 股數近似；期內有合股／拆股／大配股嘅股未標 `mcap_unreliable`（第三階段 M3 處理）。

## 6. 下手要做（按優先）

1. **KL**：GitHub repo Secrets 貼三個 Longbridge 變數 → Actions 手動 trigger 一次 `eod_scan` 驗證。
2. **KL**：Streamlit Cloud App Secrets 貼三個 Longbridge 變數 → tab2 試「掃一次」。
3. **KL**：Telegram bot（README 有 3 分鐘教學）→ `--notify` 真發一次。
4. **KL**：放 `data/universe_full_20260907.csv` → 重跑 `python -m stockscan.universe`（自動改 code5 交叉）。
5. **第三階段（等 KL 放 `data/raw/` 先開）**：M1 事件庫 → M2 價格庫入快取 → M3 13 個月面板……規格書已喺 Drive 夾。
6. 觀察幾日 A 榜同 RTSS 逐日對數，再決定門檻微調。
7. Render 長開 worker（--loop 60）搬上雲，唔靠 PC 開機。

## 7. 點樣本機重跑

```bash
cd "G:\我的雲端硬碟\STOCKSCAN"
python scripts/run_eod.py                      # 今日（首次 ~7 分鐘拉快取，之後秒級）
python scripts/run_eod.py --date 2026-09-04    # 對照 RTSS
python scripts/run_intraday.py --loop 60       # 即市常駐（交易日 09:30-16:10 HKT）
python scripts/backfill_eod.py --start 2026-08-10 --end 2026-09-07   # 回填面板
pytest -q                                      # 49 tests
```

（前提：`%USERPROFILE%\.stockscan\.env` 有三個 Longbridge 變數。）

## 8. Secrets 放邊（只寫位置，唔寫值）

- 本機正印：`C:\Users\klcho\.stockscan\.env`（唔喺 repo，唔會上 Drive）
- Streamlit Cloud：App → Settings → Secrets（`LONGBRIDGE_*` 三個；TELEGRAM_ 兩個如要 tab2 推）
- GitHub Actions：repo → Settings → Secrets → Actions（三個 Longbridge＋兩個 TELEGRAM_）

## 9. 面板摘要（P2：2026-08-10 → 2026-09-07，21 個交易日，266 行）

- **每日上榜數**：中位 **12**／最少 **6**／最多 **21**
- **上榜次數最多頭 10**：
  1. 06182 乙德投資控股 4 次
  2. 02048 易居企業控股 3 次
  3. 01792 CMON 3 次
  4. 00254 國家聯合資源 3 次
  5. 08491 COOL LINK 2 次
  6. 02113 世紀集團國際 2 次
  7. 01265 天津津燃公用 2 次
  8. 00210 達芙妮國際 2 次
  9. 02536 百樂皇宮 2 次
  10. 08620 亞洲速運 2 次
- **市值 <3 億佔比**：52.3%
- 檔案：`data/eod/radar_eod_panel.csv`（欄 `scan_date` ＋ 15 欄標準輸出）；逐日 CSV 同夾。

## 10. 今晚改動一覽（第二階段）

- `stockscan/kline_cache.py`（新）：日線快取＋HKT 日期修復＋memo＋40 支窗
- `stockscan/scan_eod.py`：重寫做快取優先；`--cache-only`；301607 早退；run_stats
- `stockscan/scan_intraday.py`：SURGE＋VOLUME；級距 `level_of(value, first, step)`；
  狀態檔加 first_seen_price/turnover/ts
- `stockscan/notify.py`（新）：Telegram 三件套；dry-run
- `stockscan/lb_client.py`：憑證次序加 user profile；LONGBRIDGE_/LONGPORT_ 雙前綴
- `scripts/`：backfill_eod.py（新）、compare_rtss.py（新）、schedule_intraday.ps1（新）、
  run_eod/run_intraday 加參數
- `streamlit_app.py`：四 tab
- `.github/workflows/eod_scan.yml`：`--notify`＋TELEGRAM_ secrets
- 測試 38 → **49**（級距／雙觸發／UTC→HKT 疫苗／memo／15/15 回歸）

*本規格書及所有產出只供學術研究及風險分析，不構成投資建議。*
