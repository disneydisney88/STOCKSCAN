# STOCKSCAN HANDOVER（交俾下一手：Claude / Codex / KL）

更新時間（HKT）：2026-09-09 06:42
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

11. **Actions rerun 陷阱**：只 rerun 最新 commit；workflow 已加 `git pull --rebase origin main`（F1）。

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
- **M7 ✅ 代碼完成／⏸ 暫停**：已從 `%USERPROFILE%\.stockscan\` 兩個原始檔抽出並寫入標準 `.env`（另加 `LONGBRIDGE_REGION=hk`），五個變數已用 `lb_client.ensure_credentials()` 驗證；原始 `LONGBRIDGE_APP.ENV` 及 `httpswebbsite-ccass-a.env` 已刪除。
- 新增 `stockscan/ccass.py`、`scripts/run_ccass.py`；API `/health` 回 **200**，`/api/date-alignment` 回 **200**。`/api/stock` 現改為每次 timeout **180 秒**，失敗退避重試 **2 次**、每次間隔 **30 秒**。
- 依規格先用 `01393` 單股試跑，3 次均因 `RemoteDisconnected` 失敗（成功 **0/1**），所以未啟動 09-07 全榜掃描，亦未生成成功 CCASS JSON。研判疑似 Render worker timeout／OOM；待 CCASS tool repo 修復後重跑 `python scripts/run_ccass.py`。失敗已透過 `log_error` 落 `logs/errors_YYYYMMDD.log`。
- M7 client 已支援 health、date alignment、Concentration／Big Changes payload 保存、`ccass_top5_pct_t2`／`ccass_top10_pct_t2` 欄位及逐股失敗記錄；Actions 加入只在 `CCASS_API_URL`／`CCASS_API_KEY` secrets 存在時執行的 gated step。待 API `/api/stock` 上游恢復後重跑 `python scripts/run_ccass.py`。

### 第四階段小修驗收表

#### M3：按月面板／RTSS 對照（P5 F2 重做——取代第四階段分母錯嘅版本）

方法：RTSS 側用 `RTSS_Detailed_Final.xlsx`「每日摘要」，按 (date, code5) 去重、
只留代表市值 <10 億（大市值榜唔係我哋口徑）、只對我哋面板有嘅交易日
（RTSS 假期／週末照出——5 月 22 條 missing 入面多數係呢類）。腳本：`scripts/compare_rtss.py --monthly`。

| 月份 | 我哋 (date,code5) | RTSS | 命中 | 額外 | 漏報 | 命中率 |
|---|---:|---:|---:|---:|---:|---:|
| 2026-04 | 252 | 64 | 64 | 188 | 0 | 1.0000 |
| 2026-05 | 307 | 271 | 249 | 58 | 22 | 0.9188 |
| 2026-06 | 226 | 241 | 200 | 26 | 41 | 0.8299 |
| 2026-07 | 255 | 206 | 188 | 67 | 18 | 0.9126 |

- 4 月 100%（RTSS 出嘅我哋全接住）、5 月 91.9%、7 月 91.3% 達標（>90%）；6 月 83%（41 條漏報，
  初步抽樣個別係 RTSS 列咗我哋當日 ratio 未夠 10／停牌股，未逐條歸因）。
- 我哋「額外」遠多過漏報（188/58/26/67）——RTSS 覆蓋窄（04 月只有 64 對），唔代表我哋錯。
- 舊表（第四階段）分母用咗未去重＋含大市值榜＋含非交易日嘅 RTSS 數（05 月 1,585 條），作廢。
- 明細：`data/reports/rtss_monthly_compare_v2.csv`。

#### M4：180 日事件率（P5 F3 重做——上榜組去重＋全體基準）

方法：上榜組按 code5 去重（08368 上榜 18 次＝1 個觀察，窗口由首次上榜日起計）；
基準兩版——`baseline_sample`＝原版每日抽 10 隻；`baseline_all`＝全體 <10 億、成交 ≥1M、
從未上榜（每隻一個觀察，首個合資格日）。快取窗口 ~40 支（約兩個月），解釋力有限。

| 組別 | 觀察 | GO 180d | CONSOLIDATION 180d | PLACING 180d | RIGHTS 180d |
|---|---:|---:|---:|---:|---:|
| signal（去重） | 1,226 | **40 (3.26%)** | 21 (1.71%) | 96 (7.83%) | 29 (2.37%) |
| baseline_sample | 2,960 | 55 (1.86%) | 82 (2.77%) | 537 (18.14%) | 141 (4.76%) |
| baseline_all（全體基準） | 147 | 5 (3.40%) | 0 (0.00%) | 6 (4.08%) | 2 (1.36%) |

- 對返舊研究「上榜 3.5% vs 非上榜 0.5%」：signal GO 3.26% 同 3.5% 同一量級 ✓；
  但 `baseline_all`（3.40%）**唔見到 GO alpha**——注意呢個基準限定「成交 ≥1M 活躍股」，
  同舊研究嘅「全體非上榜」（包含大量死股）唔同口徑；且快取只有 ~2 個月窗口，147 個觀察太少。
- 只記數字，不作結論；結論留 KL／Claude。明細：`data/reports/go_timing_20260907.csv`／`go_timing_summary.csv`。

#### M6：`n_max_est` 分層

| n_max_est | alerts | t+5 中位% | t+5 勝率 | t+10 中位% | t+10 勝率 | t+20 中位% | t+20 勝率 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 19 | 8.6758 | 0.7368 | -6.0606 | 0.1579 | 4.8485 | 0.5789 |
| 1 | 131 | -6.9106 | 0.2977 | -8.0460 | 0.2443 | -13.2993 | 0.2969 |
| 2 | 101 | -2.7027 | 0.4343 | 0.0000 | 0.4747 | -4.3011 | 0.3737 |
| 3 | 59 | -8.7500 | 0.3103 | -10.0000 | 0.2931 | -9.1866 | 0.3621 |
| 4 | 47 | -8.3333 | 0.4444 | -13.8889 | 0.3778 | -21.6418 | 0.2889 |
| 5 | 50 | -27.2727 | 0.0400 | -33.2253 | 0.0400 | -28.9256 | 0.0400 |
| 6 | 23 | 7.0423 | 0.5217 | -35.8025 | 0.2609 | -44.4444 | 0.2609 |
| 7 | 22 | -8.6022 | 0.2727 | 2.0408 | 0.5455 | 12.2449 | 0.5455 |
| 8 | 15 | 151.2195 | 0.5333 | 107.3170 | 0.6000 | 126.8293 | 0.6000 |
| 10 | 22 | -8.7719 | 0.3182 | -16.1404 | 0.3182 | -22.8070 | 0.3182 |
| 12 | 3 | 0.0000 | 0.0000 | -13.6674 | 0.0000 | -22.5513 | 0.0000 |
| missing | 30 | — | — | — | — | — | — |

- Actions 09-08 首跑結果：**origin 冇 `radar_eod_20260908.csv`**（zcode 無 Actions API 權限睇 log）；已由本機補跑 EOD 09-08 補返（見 §12 Z0）。

*本規格書及所有產出只供學術研究及風險分析，不構成投資建議。*

## 12. 第四階段夜工（zcode，2026-09-08 深夜）

| 任務 | 狀態 | 摘要 |
|---|---|---|
| Z0 Actions 首跑檢查 | ⚠ | origin 冇 09-08 radar；本地補跑補返（`radar_eod_20260908.csv`）；KL 話會自己睇 Actions log |
| Z0 VOLUME 零 alert 診斷 | ✅ | **代碼冇壞**（10a793c 係純重構）——根因係 Drive FS 讀快取失敗時 `kline_cache.load()` 靜靜回 None → ma10=None → VOLUME 無聲跳過（SURGE 唔使 cache 所以倖存）。修復：load 重試 3 次（OSError 類）→ 仍失敗 `raise CacheReadError`；`scan_once` 計 `ma10_errors`，>10% 池大聲警告。回歸測試：RTSS 11 隻實測數字合成快取 → 11/11 VOLUME 全開火；讀取持續失敗必上拋 |
| Z0 RTSS 即市對照 | ✅ | `tests/fixtures/rtss_intraday_20260908_1330.csv`（11 隻）vs 修復後掃描 `alerts_20260908.csv`：**命中 11/11**；我哋多 7 條 VOLUME（收市後 ratio 繼續累積，正常） |
| Z0 02738 判定 | ✅ | **合股唔係復牌**：快取 09-03→09-07 連續交易（0.039/0.041/0.043）無停牌間隙，09-08 上 0.4 ≈ 9.3x＝10合1 有效日；events DB 漏記呢單。新 `price_gap_suspect` guard（一日 ±4 倍跳而事件庫冇記錄）已捕捉，兩條 alert 旗標=1 照出 |
| Z1 daemon | ✅ | `scripts/intraday_daemon.py`：崩潰重啟（5 次/日）、時段外瞓、log 轉檔留 30 日、16:15 summary、時點快照 10:30/11:30/13:30/15:30/16:00。冒煙測試過（啟動/轉檔/判斷時段/乾淨退出）。**排程已真註冊**：`STOCKSCAN_intraday`（State=Ready，每日 01:20 GMT＝09:20 HKT，WakeToRun） |
| Z1b tab2 時點快照 | ✅ | 最新快照 ⭐ 標記本日首次出現（同日較早快照冇嘅 code） |
| Z2 CCASS 上游 | 🔶 | 診斷：`/health` 200（冷啟動 49s，服務生）；`/api/stock` 401（本機無 `CCASS_API_KEY`，唔係服務死）。已修 webbsite-ccass-tool 並 push（`50a1290`）：gunicorn `-w 1 --timeout 300`（取代裸 uvicorn）、auto 模式 cache-first（先試 Turso 快照有真數據即回）、新增 `?light=1`（強制 hybrid_light）。**等 Render 部署＋KL 提供 `CCASS_API_KEY` 先可以終測 `?code=01393&light=1`**。spec 中「 threads 2」冇跟——UvicornWorker 係 async，--threads 唔適用，用單 worker 避免免費 plan OOM |
| Z3 tab6 個股研究 | ✅ | 六區塊：基本／價格+上榜標記／事件 24 個月／射倉 ±5 日／RTSS 回放／CCASS／即市 alert；無數據寫「無紀錄」。驗收 01825（4 上榜日+1 事件）、00254（8+1）、08368（18+1）全部有料 |
| Z4 數據質量審計 | ✅ | 見 §13；腳本 `scripts/audit_data_quality.py` 可重跑 |
| Z5 收尾 | ✅ | 本檔更新＋pytest 54 綠＋push。Z5 舊 3 個射倉 xlsx（KL 未放 data/raw，記低）；Telegram 真發（KL 擺低） |

**新流程注意**：daemon 已註冊排程，聽日（09-09）09:20 HKT 會自動開始掃；佢自己判斷交易時段，PC 開機就會行（WakeToRun）。想停：`schtasks /change /tn STOCKSCAN_intraday /disable`。

## 13. 數據質量審計（2026-09-09 00:1x HKT，腳本可重跑）

1. **mcap_unreliable：4,006/4,036 行（99.3%）**——13 個月面板幾乎全部行嘅市值係用「今日股數 × 歷史價」近似（Codex 價格庫 X0 冇歷史股數）。按月 98.2%–100%。**研究含歷史 mcap 嘅結論前必須記住呢點**；上榜名單本身（價量口徑）唔受影響。
2. 種子 08-31 市值 vs 面板 2026-08-31 mcap_total：可比 21 隻中 **2 隻差 >30%**——00913 港灣數字 +162%（疑似合股/拆股）、00021 大中華控股 +31%（股數口徑/攤薄）。明細 `data/reports/data_quality_audit_20260909.csv`。
3. 09-08 即市 alert：25 條（VOLUME 18/SURGE 7）；corp_action_suspect=0、resumption_suspect=0、**price_gap_suspect=2**（全部係 02738 華津國際控股 SURGE+VOLUME，+830%/1506x，合股假訊號已正確標記）。

## 15. T1 RTSS CDP 文字抓取（2026-09-09）

- 狀態：✅ CDP 連接成功；`http://127.0.0.1:9222` 有 RTSS page（channel `-2795969450`），只讀 `.message` DOM 及 `.time-inner` 日期，不 click、不 focus、不截圖、不讀 media。
- 新增：`scripts/fetch_rtss_cdp.py`；raw staging 寫 `data/rtss/raw_dom_YYYYMMDD.jsonl`，目錄已加入 `.gitignore`，不 push。
- 參數：預設及 `--date` 用 `today_hkt()`／指定 HKT 日期；支援 `--backfill --from YYYY-MM-DD --to YYYY-MM-DD`，逐日 upsert raw DOM text。
- 驗證：`python scripts/fetch_rtss_cdp.py --date 2026-09-08` 成功連接及完成，當時 DOM 未載入目標日期 alert，輸出 0 條並發 warning，無 crash；目前可見 DOM 日期為 2026-07-30 至 2026-07-31，需 T2/T5 以現有歷史文字檔繼續驗證 parser。
- 基線：`python -m pytest -q --basetemp .pytest-tmp-baseline` → **54 passed**。
- T1 remote commit：`d089eed`（乾淨 clone apply；Drive `.git` 偽 `desktop.ini` ref 令本機 fetch 不穩）。
- T2：新增 `stockscan/rtss_parser.py::parse_alert`，支援代號、名稱、市值／成交額單位換算、升幅、最新價、時間、當日次數及 level range；失敗保留 `raw_text` 並標 `parse_failed=1`。01536 真樣本測試通過；全套 **56 passed**。
- T2 remote commit：`f6c7744`。
- T3：新增 `scripts/build_rtss_alerts.py`，將 raw DOM JSONL 轉 `data/rtss/rtss_alerts_YYYYMMDD.csv`；同 code5+time upsert，raw／parse failure 均保留；支援 HKT `--date` 及 `--backfill --from/--to`。輸出目錄 gitignored，不 push。
- T3 remote commit：`c87216e`。
- T4：新增 `scripts/compare_rtss_daily.py`，按 code5 輸出 `both`／`rtss_only`／`stockscan_only`，RTSS-only 只記可觀察的市值／成交額門檻及「daemon_or_definition_difference」可能原因，不落結論；diff report 留作可公開統計。
- T4 remote commit：`0134463`。
- T5：新增 `scripts/import_rtss_backfill.py`，支援 TGWebExporter CSV／SQLite，按 HKT timestamp 過濾日期、只讀 `message_text`，用同一 parser 寫入 gitignored `data/rtss/rtss_alerts_YYYYMMDD.csv`；source 原有資料範圍及 parse 統計只報數字。
- T5 parser 修正：兼容 TGWebExporter「一行一條 alert」格式，label 後按數字＋單位擷取，不把後續欄位誤併入市值／成交額。
- T5 remote commit：`22a60b8`。
- T6：Streamlit 新增標示「9️⃣ RTSS 對照」tab，逐日讀 diff report，顯示 both／rtss_only／stockscan_only 指標、趨勢及分組明細；不讀取 RTSS 圖片或 raw text。

### 15.1 RTSS 本機 GUI（2026-09-10）

- 狀態：✅ 新增 `rtss_console.py` 及根目錄 `啟動RTSS.bat`。
- GUI 只包住現有流程：`fetch_rtss_cdp.py` → `build_rtss_alerts.py` → `compare_rtss_daily.py`；歷史檔用現有 `import_rtss_backfill.py`，冇重寫抓取／parser 邏輯。
- 功能：自動檢查 `127.0.0.1:9222` RTSS tab；CDP 未連時可啟動指定 Chrome profile；今日／單日／範圍抓取；TGWebExporter SQLite／CSV 匯入；複製產物到固定 Drive 夾 `G:\我的雲端硬碟\RTSS\RTSS_TG`（folder ID：`1H0I2YUQn1_JRN1O3zBZUepm88YAarKpx`）；歷史 three-way diff 及 RTSS-only 趨勢。
- Drive 交收檔名固定為 `rtss_alerts_YYYYMMDD.csv`／`rtss_daily_diff_YYYYMMDD.csv`；同日重跑遇到目標同名檔會跳過，不覆蓋既有檔案。
- 安全口徑：GUI 只讀現有 script 產物及 exporter `message_text`；`data/rtss/` 繼續 gitignored，不納入 commit。
- 啟動：雙擊 `啟動RTSS.bat`，或 `streamlit run rtss_console.py`。
- 驗證：`python -m py_compile rtss_console.py` 通過；Streamlit 本機 8502 頁面成功載入；全套 **60 passed**。
- 數據質量修復（2026-09-10）：`stockscan/rtss_parser.py` 加入新逐條 schema（`msg_id`／`alert_ts`／原文數值／級距拆欄／category），`(code5, alert_ts)` 去重；新增 `scripts/rebuild_rtss_schema.py`、逐股日彙總及 `.meta.json` 時間範圍。
- 由 TGWebExporter SQLite 以 HKT 重建 2025-08-29 至 2026-09-10 共 **378** 個每日檔；來源實際涵蓋至 2026-08-28（`source range=2025-06-26..2026-08-28`），範圍後日期保留空 schema，唔虛構 alert。新 schema 重複鍵驗證 **0**。
- 01536 pytest 兩條樣本驗證 `14:24:13`／`14:42:53` 分開，第二條 `count_today=2`、級距 `22→32`；全套 pytest **61 passed**。逐條／by-stock／metadata／diff 產物已重送固定 `RTSS_TG`（共 1513 檔）。
- 09-10 空檔根因修復（2026-09-10）：Chrome 實際 RTSS URL 為 `https://web.telegram.org/a/#-1002795969450`，舊版只匹配 `-2795969450`；Telegram Web A DOM 亦由 `.message`／`.bubbles-scrollable` 改為 `.Message`／`.MessageList.custom-scroll`，日期改在 `.message-date-group .sticky-date`，時間改為 `.message-time`。`fetch_rtss_cdp.py` 已兼容兩種 channel ID、DOM selector 及 `Today`／`Yesterday`／星期日期（全用 HKT）。
- 修復後實測：09-10 raw **17** 條，build 後 **7** 條可解析＋**1** 條 `parse_failed`，最新 alert_ts=`2026-09-10 14:33:21`；重建 `rtss_alerts_20260910.csv`／by-stock／metadata／diff。故 09-10 並非無 alert，而係抓取層漏資料。
- Drive 唯一交收目標：`G:\我的雲端硬碟\RTSS\RTSS_TG`（folder ID `1H0I2YUQn1_JRN1O3zBZUepm88YAarKpx`）；全 Drive 盤點 09-10 檔只見於此夾，GUI／流程停止使用其他 parent 夾。
- 09-10 數據質量修補：`clean_alert_text()` 清除 Telegram 尾部 view count／瀏覽器本地時間（如 `77 02:48`），CDP 只接受有 `.text-content`／`.translatable-message` 的訊息泡，並清理既有 raw 檔中的純 UI 行（如 `77 04:31`）。parser 以 `📈` 後至 `(HK.xxxxx)` 前取 name；無 emoji 的舊 DOM 亦會先隔走標題行。
- 實測：01555 `alert_ts=2026-09-10 09:48:37`（HKT）、name=`MI能源`、raw_text 不含 `02:48`；重抓後 raw **7** 條，build **7** 行（`parse_failed=0`，舊 CSV 殘留 UI 行亦已清走），全套 pytest **63 passed**。09-10 產物已重送唯一 `RTSS_TG` 目標。


## 14. 第五階段 A2：即市上雲（zcode，2026-09-09 深夜）——等 KL 貼 env 即著

代碼全部落地（`stockscan/turso_state.py`＋`scan_intraday` 接駁＋`render.yaml`），
**唯一欠係 Turso 憑證**：`%USERPROFILE%\.stockscan\.env` 同 Render 都未有
`TURSO_DATABASE_URL`／`TURSO_AUTH_TOKEN`（Codex 第三階段合併 .env 時刪咗原始檔，呢組數字 lost）。

### KL 要貼嘅 Render env 清單（Render → Blueprint 部署後逐個貼，或者 Blueprint 過程貼）

| Key | Value |
|---|---|
| `LONGBRIDGE_APP_KEY` | 同 .env |
| `LONGBRIDGE_APP_SECRET` | 同 .env |
| `LONGBRIDGE_ACCESS_TOKEN` | 同 .env |
| `TURSO_DATABASE_URL` | `libsql://…`（Turso dashboard → 你個 DB → URL） |
| `TURSO_AUTH_TOKEN` | Turso dashboard → Tokens 生成 |
| （選）`INTRADAY_SOURCE` | `cloud`（render.yaml 已預設） |

同時建議本機 `%USERPROFILE%\.stockscan\.env` 都加埋 `TURSO_DATABASE_URL`／`TURSO_AUTH_TOKEN`
兩行——本機 daemon 就會自動同雲共享 state＋互相去重。

### 運作設計

- Cron `*/5 * * * *` UTC；`run_intraday --once --source cloud` 喺 HKT 非交易時段秒退（唔使 API）
- state 單一真相＝Turso（`intraday_state` 表，(trade_date, symbol) PK，state_json 整份存）；
  本機 JSON 照寫做 fallback
- alerts 鏡像上 `intraday_alerts` 表（PK ts+date+code5+alert_type 天然去重）；
  tab2 優先讀 Turso（Cloud 版都睇到），fallback 本機 CSV
- A2.4 去重：`scan_heartbeat` 表——另一 source 5 分鐘內掃過就 skip 呢輪（本機 daemon 同雲 Cron
  唔會重複 alert）。**建議：Render Cron 部署成功之後，本機 daemon 可以 disable**：
  `schtasks /change /tn STOCKSCAN_intraday /disable`
- 所有 Turso 出錯都只會 log＋fallback 本機，唔會搞冧掃描

## 15. 第五階段其餘狀態

- F1 ✅ workflow `git pull --rebase`（`7f3e854`）＋§5 陷阱 #11（`4b9f908`）
- F2 ✅ M3 對照重做：04 100%／05 91.9%／06 83%／07 91.3%（`dc204c5`+`f8bef43`）——舊表作廢
- F3 ✅ M4 GO 報時去重＋baseline_all：signal（去重）GO 180d 3.26% vs 全體基準 3.40%——
  呢個基準定義下見唔到 alpha（基準限定成交 ≥1M 活躍股，同舊研究 0.5% 口徑唔同；只記數字）（`e01537d`）
- A2 🔶 代碼 100%，等上面兩個 Turso env
- B1/B2/B3 見 §16


## 16. 第五階段 B 系＋收尾（zcode，2026-09-09 深夜）

| 任務 | 狀態 | 摘要 |
|---|---|---|
| F1 | ✅ | workflow `git pull --rebase`＋§5 陷阱 #11 |
| F2 | ✅ | M3 對照重做：04 100%／05 91.9%／06 83%／07 91.3%（§11 覆寫） |
| F3 | ✅ | M4 去重＋baseline_all（§11 M4 表重寫；signal GO 3.26% vs 全體基準 3.40%，基準口徑注意） |
| A2 | 🔶 代碼 100% | Turso state/alerts/heartbeat＋render.yaml＋tab2 Turso 優先——**等 KL 貼 TURSO_ 兩個 env**（清單 §14），貼完即著 |
| B1 春江鴨 | ✅ | `scripts/spring_duck.py` → tab8；broker 數據只到 08-05，CCASS Top10 待 M7 上游 |
| B2 L 型 | ✅ | `scripts/l_shape.py` → tab9；L 型研究 xlsx 未放 data/raw，純 events.db 版（7 隻 GO_等表演） |
| B3 brief | ✅ | `scripts/morning_brief.py` → `data/reports/morning_brief_*.md`，已加落 Actions（M4 之後） |

### KL 要貼嘅 Render env（重申，A2 用）
`LONGBRIDGE_APP_KEY`／`LONGBRIDGE_APP_SECRET`／`LONGBRIDGE_ACCESS_TOKEN`／
`TURSO_DATABASE_URL`／`TURSO_AUTH_TOKEN`（值同 .env／Turso dashboard；本機 .env 建議都加 TURSO_ 兩行）。

### 下手要做重排（§6 更新）
1. Render Blueprint 部署 `stockscan-intraday` cron（render.yaml 已喺 repo root）＋貼 5 個 env → 觀察 Turso 有冇雲端 alert
2. CCASS：Render 部署 ccass-tool（`50a1290`）＋貼 `CCASS_API_URL`／`CCASS_API_KEY` 喺 STOCKSCAN .env → `python scripts/run_ccass.py` 終測 `?light=1`
3. L 型研究 3 個 xlsx 放 `data/raw/` → B2 加交叉驗證
4. 舊 3 個券商射倉 xlsx 放 `data/raw/` → M5 補入
5. Actions log 檢查 09-08/09 失敗原因（zcode 冇權限，KL 貼 log）
6. 觀察一周：A 榜 vs RTSS 每日 diff（tab7）、daemon vs 雲 cron 表現

## 17. 第五階段之後（第六階段候選）

Telegram 推送真開；「當日第 N 次」前瞻力用自家＋RTSS 對照數據驗證（等 T 部分儲夠 20 交易日）；
人物網絡自動連結；完整 Round 4 五訊號 morning brief。
