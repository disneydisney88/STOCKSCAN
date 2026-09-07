"""STOCKSCAN 全部參數集中喺呢度——改門檻只准改呢個檔，改完要喺 HANDOVER.md 記低原因。"""
from pathlib import Path

# ── 時區：任何「今日」一律用 HKT，唔好用機器本地時間 ──
TZ = "Asia/Hong_Kong"

# ── 訊號門檻（規格書 §3 口徑）──
MCAP_CAP_EOD    = 10e8      # 訊號 A：市值上限（港元，last_price × total_shares）
MCAP_CAP_INTRA  = 3e8       # 訊號 B：市值上限
TURNOVER_MIN    = 5e5       # 成交額下限 50 萬（A、B 同用；嚴格大於）
MA_DAYS         = 10        # 前 N 個交易日成交額均值，唔含今日
RATIO_MIN       = 10.0      # 今日成交額 ÷ N 日均 ≥ 10 倍
INTRA_FIRST_PCT = 20.0      # 訊號 B：首次 alert 升幅門檻（%）
INTRA_STEP_PCT  = 20.0      # 訊號 B：之後每級 pt

# ── Longbridge quote 每批上限（probe 實測後可改，結果記 HANDOVER）──
QUOTE_BATCH = 500
# 訊號 A 要逐隻攞日 K 線（SDK 無批量 kline），用細線程池控制節奏
CANDLE_WORKERS = 4

# ── 路徑 ──
ROOT         = Path(__file__).resolve().parent
DATA_DIR     = ROOT / "data"
SEED_CSV     = DATA_DIR / "universe_seed_20260831.csv"
FULL_CSV     = DATA_DIR / "universe_full_20260907.csv"
UNIVERSE_CSV = DATA_DIR / "universe.csv"
EOD_DIR      = DATA_DIR / "eod"
INTRADAY_DIR = DATA_DIR / "intraday"
STATE_DIR    = ROOT / "state"
LOGS_DIR     = ROOT / "logs"
FIXTURE_DIR  = ROOT / "tests" / "fixtures"

# ── 種子檔已知疑似除牌（有 universe_full 時以 code5 交叉為準；full 檔缺席時以此為準）──
DELISTED_SUSPECT_SEED = {"02900", "02901", "02903", "02912", "08577"}

# ── RTSS 對照 fixture（H2 驗收）──
RTSS_FIXTURE_DATE = "20260904"

DISCLAIMER = "本工具只供學術研究及風險分析，不構成投資建議。"
