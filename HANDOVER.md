# STOCKSCAN HANDOVER（交俾下一手：Claude / Codex / KL）

更新時間（HKT）：2026-09-08 08:30
執行者：zcode（第一、二階段）　交接對象：Claude（第三階段）／KL
工作夾＝單一真相來源＝交收位：**`G:\我的雲端硬碟\STOCKSCAN`**（Google Drive 同步）
Repo：https://github.com/disneydisney88/STOCKSCAN（`main`，全部已 push）
Streamlit：https://stockscan-emwmwndwrop2emavfyatme.streamlit.app（四 tab）
本機環境：Python 3.13（Windows Store 版）、套件 `longbridge==4.5.0`、Git Bash shell

> 本工具只供學術研究及風險分析，不構成投資建議。

---

## 0. 一分鐘睇晒（TL;DR）

- 兩個訊號都**已經生產級**：訊號 A 對 RTSS 09-04 **命中 15/15、零多零漏**（種子宇宙同 2,858 全宇宙都一樣）；訊號 B SURGE+VOLUME 實測正常。
- 宇宙已轉用 `universe_full_20260907.csv`（**2,868 隻，掃描 2,858**）。
- 20 日回填面板已做（`data/eod/radar_eod_panel.csv`，278 行）。
- 快取架構行緊：`data/cache/daily/{code5}.csv`（2,854 檔 × 40 支日 K）。
- **未做**：Actions 未試跑（等 KL 撳一次 Run workflow）、Streamlit tab2 未試（等 Cloud Secrets）、Telegram 真發（KL 話擺低）、第三階段（等 `data/raw/`）。
- **三大陷阱**（新代碼必讀 §5）：① API timestamp 係 UTC（會早一日）② 歷史K線端點 100 標的硬配額 ③ `.env` 唔准入 repo／Drive。

---

## 1. PATH 對照表（全部絕對路徑）

| 嘢 | 路徑 |
|---|---|
| 工作夾（repo root） | `G:\我的雲端硬碟\STOCKSCAN` |
| 入口：訊號 A | `G:\我的雲端硬碟\STOCKSCAN\scripts\run_eod.py` |
| 入口：訊號 B | `G:\我的雲端硬碟\STOCKSCAN\scripts\run_intraday.py` |
| 入口：回填面板 | `G:\我的雲端硬碟\STOCKSCAN\scripts\backfill_eod.py` |
| 入口：RTSS 對照 | `G:\我的雲端硬碟\STOCKSCAN\scripts\compare_rtss.py` |
| 入口：API 限額實測 | `G:\我的雲端硬碟\STOCKSCAN\scripts\probe_ratelimit.py` |
| 排程範例（未註冊） | `G:\我的雲端硬碟\STOCKSCAN\scripts\schedule_intraday.ps1` |
| 核心套件 | `G:\我的雲端硬碟\STOCKSCAN\stockscan\`（lb_client / universe / scan_eod / scan_intraday / kline_cache / calendar_hk / notify / io_utils） |
| 所有門檻 | `G:\我的雲端硬碟\STOCKSCAN\config.py`（唯一改參數嘅地方） |
| **本機憑證** | `C:\Users\klcho\.stockscan\.env`（LONGBRIDGE_APP_KEY／APP_SECRET／ACCESS_TOKEN） |
| KL 原始金鑰檔 | `G:\我的雲端硬碟\STOCKSCAN\LONGBRIDGE_APP.ENV`（已 .gitignore，**唔准 commit**） |
| 宇宙 | `data/universe.csv`（生成物，2,868 行）；種子 `data/universe_seed_20260831.csv`；全宇宙 `data/universe_full_20260907.csv` |
| 日線快取 | `data/cache/daily/{code5}.csv`（date,open,high,low,close,volume,turnover；**唔入 git**） |
| EOD 產出 | `data/eod/radar_eod_YYYYMMDD.csv`＋`radar_eod_panel.csv`＋`compare_rtss_20260904.json` |
| 即市產出 | `data/intraday/alerts_YYYYMMDD.csv`；狀態 `state/intraday_state_YYYYMMDD.json` |
| Log | `logs/`（errors_*.log、run_stats.csv、intraday_stats.csv、probe_*.json；gitignore） |
| RTSS fixture | `tests/fixtures/rtss_20260904.csv`（15 隻） |
| 測試 | `tests/test_formulas.py`（49 項，`pytest -q` 全綠） |
| Actions | `.github/workflows/eod_scan.yml`（cron 35 8 * * 1-5 UTC＝HKT 16:35＋workflow_dispatch；`--notify`） |
| 第三階段規格 | `G:\我的雲端硬碟\STOCKSCAN\claude_STOCKSCAN_zcode任務規格書_第三階段_歷史數據入庫_20260908.md` |
| 原始檔落點（第三階段） | `data/raw/`（KL 未放） |

---

## 2. 而家去到邊（第一階段 H0–H6＋第二階段 P1–P6 全部 ✅）

| 模組 | 狀態 | 實測數字 |
|---|---|---|
| H0 地基 | ✅ | longbridge SDK 4.5.0；`.cn` 接入點（呢部機快 4 倍） |
| H1 宇宙 | ✅ | **2,868 總數／2,858 掃描（剔 10 REIT）／static 2,857 成功**；`3408.HK` 無 static（槓桿產品，正常），`static_missing=1` 照保留 |
| H2 訊號 A | ✅ | **09-04 vs RTSS：15/15，extra=[]，missing=[]**（種子宇宙同 full 宇宙都一樣）；09-07 命中 11 |
| H3 訊號 B | ✅ | SURGE+VOLUME 雙觸發；10 億門檻；實測 21 條 alert（off_hours=1）；VOLUME 嗰 11 隻同 A 榜完全重疊 |
| H4/H5 部署 | ✅/⚠ | Streamlit 四 tab 已部署（KL 搞掂）；**Actions 未試跑**（workflow 已備好，雙 Secret 名兼容） |
| H6 測試 | ✅ | pytest 49 綠 |
| P1 快取 | ✅ | 40 支窗；重跑 09-07 全程 <2 分鐘；`--codes`／`--workers`／`--cache-only`／run_stats |
| P2 面板 | ✅ | 21 交易日（08-10→09-07），**278 行**；每日命中中位 13／min 6／max 23；上榜王 06182 乙德 4 次；市值<3 億佔 51.8% |
| P3 訊號 B 升級 | ✅ | 見 H3；`schedule_intraday.ps1` 只寫檔未註冊 |
| P4 Telegram | ⏸ 擺低 | 代碼齊＋dry-run 已驗；真發等 KL（3 分鐘教學喺 README） |
| P5 Streamlit | ✅ | 四 tab＋「數據截至」時間戳；tab2 本機掃一次／Cloud 唯讀 alerts |
| P6 交接 | ✅ | 本檔 |

## 3. TO DO（跟優先；「未 DO」詳細理由喺 §4）

1. **KL 撳一次 Actions**：GitHub repo → Actions → `eod_scan` → Run workflow（main）。
   會：2,858 隻全掃（首次幫新符號拉 ~130 支快取，約 10–15 分鐘）→ 寫 `radar_eod_20260908.csv` → commit 返嚟。
   ⚠ Actions runner 喺美國，SDK 自動會行 `.com` 接入點，正常。
2. **KL 貼 Streamlit Secrets**（App → Settings → Secrets，TOML，值抄 `LONGBRIDGE_APP.ENV`）→ tab2「即掃一次」。
   第一次掃會即場拉快取，**7–10 分鐘冇反應係正常**（Cloud 免費版唔好催）。
3. **第三階段**（等 KL 放 `data/raw/`，10 個事件 CSV＋7 個券商射倉 xlsx＋3 個 L 型研究＋Codex P0 價格庫＋RTSS 522 alert）→ 跟第三階段規格書 M1→M7 順序做。
4. 觀察 3–5 個交易日：A 榜 vs RTSS 逐日對數（`scripts/compare_rtss.py --all`，有新 fixture 就加落 `tests/fixtures/`）。
5. 之後先諗：Render 長開 worker、Turso、門檻微調。

## 4. 未 DO（做唔到／未做嘅，同埋點解）

| 未做 | 點解 | 開工條件 |
|---|---|---|
| Actions 實跑 | 我無 GitHub API token 觸發 workflow_dispatch（KL 禁咗用 git credential；`gh` 未登入） | KL 撳一次 Run workflow 就完 |
| Streamlit tab2 實試 | 等 Cloud Secrets | KL 貼三個值 |
| Telegram 真發 | KL 明言「唔搞住」 | KL 俾 token（README 教學） |
| 第三階段 M1–M7 | KL 指示等 `data/raw/` 放好先開 | KL 放檔＋話開工 |
| `universe_full` 之後嘅 `has_domestic_shares` | full 檔冇「內資股(佔比)」欄，轉 full 後個旗全 0 | 想保留：拿 `in_seed_20260831=1` join 返種子檔個旗（細工程） |
| 停牌股重複拉數 | 尾支舊過 scan_date 嘅股每次 run 都會重拉（~130 隻，2 分鐘），因為佢哋永遠冇當日 bar | 可以喺 ensure_cache 加「重拉過一次都仲舊就跳過」邏輯（非必要） |
| 動態市值宇宙 | 規格 §8：每日用即市價 × total_shares 重算邊啲入 10 億／3 億 | 現行做法已經係「static total_shares × 即市價」，效果等價；真正嘅「每日重算宇宙成員」係第三階段後嘅嘢 |

## 5. 留意（陷阱——新代碼前必讀，全部實測中過伏）

1. **UTC 時間戳**：官方文檔明寫所有 API timestamp 係 UTC。日 K timestamp 係 HKT 零晨，
   直接 `.date()` 會**早一日**——第一晚 09-04 全空榜（0/15）就係咁嚟。
   `kline_cache.merge_save` 已 `.astimezone(HKT)`，有回歸測試。任何掂 timestamp 嘅新代碼都要轉 HKT。
2. **歷史K線配額**：`history_candlesticks_*` 有 **100 標的／期** 硬配額（error 301607
   `requested:100/limit:100`）。大規模拉數一律用**即市K線端點** `ctx.candlesticks(symbol, count)`
   （獨立配額，收市後回最近 N 支已確認日 K）。`scan_eod.ensure_cache` 見 301607 會早退用快取頂住。
3. **NaN total_shares**：`3408.HK` 呢類冇 static_info 嘅，`total_shares=NaN`——
   `not NaN` 係 False，`if not ts_total` 擋唔住，`round(NaN)` 會炸。`scan_eod`／`scan_intraday`
   都已補 `pd.isna` guard；新代碼記住呢個 pattern。
4. **憑證規矩**：唔准 cat／print／commit 任何 token。repo 內唔准有 `.env`（正印位置
   `%USERPROFILE%\.stockscan\.env`）。`LONGBRIDGE_APP.ENV` 同 `*.env` 已 gitignore。
   Log 入面都唔准有 token。
5. **憑證讀取次序**：st.secrets → repo `.env`（如存在）→ `%USERPROFILE%\.stockscan\.env` →
   環境變數。`LONGBRIDGE_*`／`LONGPORT_*` 兩個前綴都認（GitHub Secrets 兩個名都兼容，workflow 已寫 `||` fallback）。
6. **時區**：所有「今日」用 HKT（`stockscan.io_utils.today_hkt()`），唔好用機器本地時間
   （呢部機係 GMT，曾經搞到 alert 寫錯日子）。
7. **Drive 同步注意**：工作夾喺 Drive 入面——(a) 大量細檔讀寫慢，`kline_cache` 有 in-memory
   memo（每 process 讀一次）；(b) `.git` 由 Drive 同步有少量風險，如果 git 壞咗，reclone 就返生（所有嘢都推咗上去）；(c) 唔好喺兩部機同時開住個 repo 做 git 操作。
8. **SDK**：用 `longbridge`（4.5.0），唔好用舊 `longport` 包（預設端點已死）。
   4.x API：`Config.from_apikey(...)`（冇 `from_env`）；批量 quote/static 上限 500。
9. **門檻只准改 `config.py`**，改完寫 HANDOVER。對照失手唔准夾數——先記錄差異再查口徑。
10. **呢单機嘅時鐘係 GMT**；「今日」錯一日就會寫錯檔名——一律 `today_hkt()`。

## 6. 點樣重跑（三行＋測試）

```bash
cd "G:\我的雲端硬碟\STOCKSCAN"
python scripts/run_eod.py                      # 今日 EOD（首次 ~10 分鐘拉快取，之後秒級）
python scripts/run_eod.py --date 2026-09-04    # 對照 RTSS（自動出 compare JSON）
python scripts/run_intraday.py --loop 60       # 即市常駐（交易日 09:30–12:00／13:00–16:10 HKT）
python scripts/backfill_eod.py --start 2026-08-10 --end 2026-09-07   # 回填＋面板
pytest -q                                      # 49 tests 全綠
```

## 7. RTSS 09-04 對照（詳細）

- **15/15 命中、0 多、0 漏**（種子宇宙 1,557 同 full 宇宙 2,858 各跑一次，結果一樣）。
- 手動核對：01393 恒鼎實業收市 0.028、成交 5.55M、前 10 日均 197,320 → **28.1x**，同 RTSS 一致
  ——確認「前 10 個交易日均值唔含今日」口徑正確。
- 邊緣個案照捕：01094 承輝國際 -11.76%（29.7x）、00201 華大酒店 -6.06%——RTSS 唔篩升跌，我哋都唔篩。
- 門檻 ≥10/15：**超額完成**。

## 8. 面板摘要（P2：08-10→09-07，21 個交易日，full 宇宙 278 行）

- 每日上榜：中位 **13**／最少 **6**／最多 **23**
- 上榜王：06182 乙德投資控股 4 次；02048 易居企業控股／01792 CMON／00254 國家聯合資源 3 次
- 市值 <3 億佔 **51.8%**
- 檔：`data/eod/radar_eod_panel.csv`（多一欄 `scan_date`）

## 9. Secrets 放邊（只寫位置）

- 本機：`C:\Users\klcho\.stockscan\.env` ✅（KL 已放，zcode 驗證過讀到）
- GitHub Actions：repo Secrets ✅（KL 已放；`LONGPORT_*` 或 `LONGBRIDGE_*` 名都得）
- Streamlit Cloud：App → Settings → Secrets ⏳（等 KL；TOML 格式見 kl 問過嗰個框）

## 10. git 一覽（今晚五個 commit）

`cd14aca` 骨架 → `564267a` polish → `a60b40e` SDK 轉 longbridge → `e7520c1` P1 快取＋P3 升級＋兩日 radar → `03e1434` P2 面板＋P4/P5/P6 → `a2d9617` workflow 雙 Secret 名 → 最新：NaN guard＋full 宇宙重掃＋本檔。

## 11. 第三階段進度（Codex，2026-09-08）

- **M1 ✅ 事件庫**：`data/events.db` 已由 `data/raw/` 內 10 個事件 CSV 建立；共 **3,560** 行。
- 各類數量：CB 202、CONSOLIDATION 60、GO 200、IPO 488、PLACING 500、PLACING_AGENT 203、RIGHTS 200、SHELL_VALUE 1,564、SPLIT 60、TRANSFER_MB 83。
- 公佈日期解析：成功 **3,333/3,560（93.62%）**；失敗 **227** 行保留，`date_parse_failed=1`，原始行保存在 `raw_json`；可解析日期範圍 **1954-09-15 → 2026-08-28**。
- 新增 `scripts/build_events_db.py`、`stockscan/events.py`；`events_after(code5, date, days)` 已支援 `.hk` 代號及日期窗口。指定驗收查詢 `events_after("00653", "2026-07-03", 180)` 可回傳 00653 合股紀錄。
- **M2 ✅ 價格庫**：`scripts/import_price_library.py` 已匯入 master + delta 共 **648,194** 行，產生／更新 **2,872** 個 `data/cache/daily/{code5}.csv`；日期範圍 **2025-05-02 → 2026-09-02**，每檔包含 `source`（`lb`／`lib`），重疊日 Longbridge 優先。
- M2 固定 seed 核對：**20 隻 × 5 日 = 100 行**，收市價差絕對值 >1%：**0**；結果見 `data/reports/price_library_validation.csv`，統計見 `data/reports/price_library_import_stats.json`。
- **M3 ⏳ 下一步**：13 個月 EOD 面板回填；券商射倉目前只有 4 個，M5 按指示先用現有 4 個。
- **M3 ✅ EOD 面板**：`scripts/backfill_eod.py --start 2025-06-26 --end 2026-09-07` 純快取完成 **296** 個交易日、**4,036** 行；輸出 `data/eod/radar_eod_panel_full.csv`（同時更新 legacy `radar_eod_panel.csv`）。使用 X0 月度股數；缺股數或有合股／拆股／配股／供股事件的行標 `mcap_unreliable=1`，目前 **4,006/4,036** 行被標記。每日命中數：中位 **13**、最少 **3**、最多 **36**。
- RTSS `每日摘要` 對照已按月輸出 `data/reports/rtss_monthly_compare.csv`，共 **16** 個月，欄位含 ours／rtss／hits／extra／missing／hit_rate；只記錄數字，不作結論。
- **M4 ⏳ 下一步**：GO 報時及基準組報表；券商射倉目前只有 4 個，M5 按指示先用現有 4 個。
- **M4 ✅ GO 報時**：`scripts/report_go_timing.py` 已按 panel 每個（code5，scan_date）計 60／120／180 日後 GO／合股／配股／供股旗標；輸出 `data/reports/go_timing_20260907.csv`（**6,996** 行）及 `go_timing_summary.csv`（24 行）。基準組按每日抽樣最多 10 隻、成交額 ≥1M、市值 <10 億且排除當日上榜股，共 **2,960** 個觀察。
- M4 分層數字（180 日）：signal GO **109/4,036**、baseline GO **63/2,960**；signal 合股 **82/4,036**、baseline 合股 **80/2,960**；signal 配股 **430/4,036**、baseline 配股 **551/2,960**；signal 供股 **99/4,036**、baseline 供股 **129/2,960**。只記數字，不作結論。
- Actions 已加 EOD 後執行 `report_go_timing.py`，並將 `data/reports` 一併提交。
- **M5 ⏳ 下一步**：用現有 4 個券商射倉檔入庫；舊 3 個檔案待日後補充。
- **M5 ✅ 券商射倉**：`scripts/import_broker_shots.py` 已解析現有 **4** 個 workbook（舊 3 個未提供），合併 `data/broker_shots.csv` 共 **86,853** 條；日期 **2025-11-03 → 2026-08-05**。新增 `stockscan/broker.py::shots_around(code5, date, days)`。
- 原始欄位只提供券商名稱及百分比變動，故 `shares_change` 保留空值；`pct_change`、`direction` 按正／負／零解析。panel `radar_eod_panel_full.csv` 已加入 `has_broker_shot`，命中 **1,115** 行（±5 日）。匯入統計見 `data/reports/broker_import_stats.json`。
- **M6 ⏳ 下一步**：RTSS 歷史 alert 回放及 t+5／t+10／t+20 報酬。
- **M6 ✅ 訊號 B 歷史回放**：`scripts/replay_signal_b.py` 從 `Parsed_Alerts` 取 `small_cap_surge` **522** 條；本地 cache 命中 **492** 條，缺當日 bar **30** 條。輸出 `data/reports/n_count_forward.csv`（522 行）及 `n_count_forward_summary.csv`（12 個 n_max_est 分層），含 t+5／t+10／t+20 收市對收市中位回報及勝率。
- M6 分層摘要數字見 `n_count_forward_summary.csv`；欄位使用 `n_max_est`，只作歷史估算，不代表實際當日 alert。
- **M7 ⏸ 停止**：`CCASS_API_URL` 及 `CCASS_API_KEY` 尚未提供；未建立 CCASS client、未發 API request、未寫入任何 key。待 credentials 提供後再開始 M7。

*本規格書及所有產出只供學術研究及風險分析，不構成投資建議。*
