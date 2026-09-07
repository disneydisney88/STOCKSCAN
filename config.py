"""STOCKSCAN 全部參數集中喺呢度——改門檻只准改呢個檔，改完要喺 HANDOVER.md 記低原因。"""
from pathlib import Path

# ── 時區：任何「今日」一律用 HKT，唔好用機器本地時間 ──
TZ = "Asia/Hong_Kong"

# ── 訊號門檻（規格書 §3 口徑）──
MCAP_CAP_EOD    = 10e8      # 訊號 A：市值上限（港元，last_price × total_shares）
MCAP_CAP_INTRA  = 10e8      # 訊號 B：市值上限（P3：由 3 億放寬到 10 億，補返 RTSS 兩榜各自漏嘅股）
TURNOVER_MIN    = 5e5       # 成交額下限 50 萬（訊號 A 用；嚴格大於）
MA_DAYS         = 10        # 前 N 個交易日成交額均值，唔含今日
RATIO_MIN       = 10.0      # 今日成交額 ÷ N 日均 ≥ 10 倍
INTRA_FIRST_PCT = 20.0      # 訊號 B SURGE：首次 alert 升幅門檻（%）
INTRA_STEP_PCT  = 20.0      # 訊號 B SURGE：之後每級 pt
INTRA_TURNOVER_MIN = 5e5    # 訊號 B：即市成交額下限（P3）
INTRA_POLL_SEC  = 60        # 訊號 B loop 每輪間隔秒（P3）
INTRA_VOL_FIRST = 10.0      # 訊號 B VOLUME：首警倍數（即市成交額/ma10 ≥ 10x）
INTRA_VOL_STEP  = 10.0      # 訊號 B VOLUME：級距（每多 10x 再發）

# ── Longbridge quote 每批上限（probe 實測後可改，結果記 HANDOVER）──
QUOTE_BATCH = 500
# 訊號 A 數據層：即市K線端點一次拉幾多支日 K 入快取（40 支 ≈ 兩個月，夠 20 日回填＋MA）
WINDOW_BARS = 40
CANDLE_WORKERS = 2          # 快取拉數線程數（301607 歷史配額教訓：寧慢莫爆）

# ── 路徑 ──
ROOT         = Path(__file__).resolve().parent
DATA_DIR     = ROOT / "data"
CACHE_DIR    = DATA_DIR / "cache"
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
