---
name: hk-smallcap-surveillance
description: 港股細價股監察研究紀律——STOCKSCAN／CCASS 工具鏈嘅數據口徑、時區、財技分類、誠實紅線。當任務涉及 RTSS 對照、CCASS 集中度、財技事件、追蹤簿、GO 預示器、Webb-site 數據時使用。
---

# 港股細價股監察研究紀律（STOCKSCAN 生態）

一套喺 2026-06→09 實戰中用血淚換返嚟嘅紀律。任何喺呢個生態寫代碼／出報表嘅 agent，開工前照跟。

## 只列數字，唔落結論

- 報表只輸出數字、比率、lift、旗標；「有效／無效」「值得買」呢類判斷留俾 KL／研究端
- 唔用 BUY/SELL 字眼；分級語言用「偏似收貨或轉倉」「派貨風險上升」「未足以定性」
- 所有產出要有免責聲明：只供學術研究及風險分析，不構成投資建議

## 時區

- 所有「今日」用 `today_hkt()`（`stockscan.io_utils`）；部機時鐘係 GMT，用本地時間會寫錯日子
- Longbridge／任何 API timestamp 係 UTC；日 K timestamp 要 `.astimezone(HKT)`，直接 `.date()` 會早一日

## 財技分類（事件口徑）

- 有財技窗口：上榜日起 180 **日曆日**內 GO／RIGHTS／PLACING／CONSOLIDATION／CB 任一
- `fu_placing` 包埋 PLACING_AGENT；換主類＝TRANSFER_MB
- 合股／拆股跳空判斷用 `key_date_1`（生效日）fallback `key_date_2`→`announce_date`
- 跳空令回報／百分比機械失真：受影響數值一律標 `_est`／「唔潔」，**統計只計非 _est 行**，_est 行數另列 n_est

## CCASS 口徑

- CCASS 日期係 **T-2 結算日**：任何 as-of 特徵用 scan_date 之前 2 個**交易日**做 cutoff，防未來函數
- 覆蓋唔到＝`unknown`／留空，**唔准當 0**；「未知」同「零」意思唔同
- 集中度三個源口徑唔同（Webb 原始、of-issued、of-CCASS），唔可以直接互相比，欄位必須標明邊個源
- 分子分母必須同一條剔除規則；百分比旁邊保留絕對股數（防分母假象）

## 誠實紅線

- 無未來函數；唔准 p-hack（所有 bin 都要列，包括對自己論點不利嘅）；n<20 標 `insufficient_sample`
- 數字對不上如實報告，唔准自行校正遷就預期
- 缺數據標 `price_missing`／`unknown`，唔准靜靜當 0
- 大批量先試點（30 隻級），報告後先全量

## 憑證與安全

- Token 唔准 cat／print／commit／入 log；正印：`G:\我的雲端硬碟\STOCKSCAN\_secrets\.env`（gitignored）
- 讀取次序：st.secrets → repo .env → repo `_secrets/.env` → `%USERPROFILE%\.stockscan\.env` → 環境變數（setdefault，已設必贏）
- pytest 入面 `load_secrets_env()` 自動 skip，防測試誤觸生產 Turso

## 環境陷阱（全部實測中過伏）

- 工作夾喺 Google Drive：`.git` 會生 `desktop.ini` 偽 ref（`git fetch` 報 bad object → `find .git -name desktop.ini -delete`）；append 失敗就 `git config windows.appendAtomically false`；大量細檔讀寫慢，記得 memo
- Store Python 嘅 app-execution alias 喺排程／非交互環境解唔到；背景長跑用 zcode background task 或明確 exe 路徑
- webb-database.com（CCASS mirror）有 IP 速率規則：burst ~60-100 請求就硬 403（IIS 頁，冇挑戰可解），20-40 分鐘自動解封——用 chunk 100＋cool 8min（env：`WARM_CHUNK`／`WARM_CHUNK_COOL_S`／`WARM_BAN_COOL_S`）
- 0xmd mirror：CF cookie 移植技術可行但 CCASS 頁係空殼冇 table——判死，唔好再試
- Render free plan：冷啟動 30-60 秒＋worker 不穩（RemoteDisconnected／503）——重試退避照做，但大規模抓取一律本地直連
- 大數據產物放 `G:\我的雲端硬碟\STOCKSCAN\_data\`，**唔好放 Downloads**（會被資料夾整理清走，09-19 事故）

## 工具速查

- 追蹤簿：`scripts/build_tracking.py`；GO 預示器：`build_go_predictors.py`
- 集中度特徵：`build_concentration_features.py`（T-2 對齊）；Turso 直連：`stockscan/ccass_turso.py`
- Webb dump 抽取：CCASS repo `scripts/extract_webb_dump.py`（streaming，欄序已驗證）
- warm：CCASS repo `scripts/warm_ccass_cache.py`（手動）／`warm_incremental.py`（每日增量）／`warm_chunked_v2.py`（全量分批）
- 完整背景：`HANDOVER.md`（§5 陷阱、§18-21）
