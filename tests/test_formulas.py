"""純函數測試：代號轉換、10MA（含不足 10 支）、ratio、級距、狀態機、中文數字。pytest 全綠為過。"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stockscan.io_utils import (  # noqa: E402
    lb_to_code5,
    parse_cn_number,
    seed_code_to_lb,
)
from stockscan.scan_eod import calc_ma, calc_ratio  # noqa: E402
from stockscan.scan_intraday import decide_alert, level_of  # noqa: E402


# ── 代號轉換 ──

@pytest.mark.parametrize("raw,expect", [
    ("00623.hk", "623.HK"),
    ("0700.hk", "700.HK"),
    ("00001.hk", "1.HK"),
    ("9988.HK", "9988.HK"),
    ("8083.hk", "8083.HK"),  # GEM
])
def test_seed_code_to_lb(raw, expect):
    assert seed_code_to_lb(raw) == expect


@pytest.mark.parametrize("sym,expect", [
    ("623.HK", "00623"),
    ("700.HK", "00700"),
    ("1.HK", "00001"),
    ("8083.HK", "08083"),
])
def test_lb_to_code5(sym, expect):
    assert lb_to_code5(sym) == expect


# ── 10MA ──

def test_calc_ma_full_10():
    turnovers = [float(i) for i in range(1, 11)]  # 1..10
    ma, n = calc_ma(turnovers)
    assert n == 10
    assert ma == pytest.approx(5.5)


def test_calc_ma_ignores_beyond_10():
    turnovers = [100.0] + [float(i) for i in range(1, 11)]  # 11 支，取最後 10 支
    ma, n = calc_ma(turnovers)
    assert n == 10
    assert ma == pytest.approx(5.5)


def test_calc_ma_short_history():
    ma, n = calc_ma([2.0, 4.0, 6.0])
    assert n == 3
    assert ma == pytest.approx(4.0)


def test_calc_ma_empty():
    assert calc_ma([]) == (None, 0)


def test_calc_ratio():
    assert calc_ratio(100.0, 10.0) == pytest.approx(10.0)
    assert calc_ratio(100.0, 0.0) is None
    assert calc_ratio(100.0, None) is None


# ── 訊號 B 級距同狀態機（P3：SURGE 20pt；VOLUME 10x 級）──

@pytest.mark.parametrize("chg,expect", [
    (-5.0, 0), (0.0, 0), (19.99, 0), (20.0, 20), (39.99, 20),
    (40.0, 40), (59.9, 40), (60.0, 60), (120.5, 120),
])
def test_level_of_surge(chg, expect):
    assert level_of(chg, 20.0, 20.0) == expect


@pytest.mark.parametrize("ratio,expect", [
    (9.99, 0), (10.0, 10), (19.99, 10), (20.0, 20),
    (80.0, 80), (186.17, 180), (-3.0, 0),
])
def test_level_of_volume(ratio, expect):
    assert level_of(ratio, 10.0, 10.0) == expect


def test_decide_first_alert():
    fire, frm, to = decide_alert(None, 25.0, 20.0, 20.0)
    assert fire and frm == 0 and to == 20


def test_decide_below_first_no_alert():
    assert decide_alert(None, 19.99, 20.0, 20.0) == (False, 0, 0)


def test_decide_same_level_no_repeat():
    rec = {"level": 20, "count": 1, "last_alert": "10:00:00"}
    assert decide_alert(rec, 35.0, 20.0, 20.0) == (False, 0, 0)  # 仲未過下一級


def test_decide_next_level_fires():
    rec = {"level": 20, "count": 1, "last_alert": "10:00:00"}
    fire, frm, to = decide_alert(rec, 41.0, 20.0, 20.0)
    assert fire and frm == 20 and to == 40


def test_decide_volume_types_independent():
    """同一隻股 SURGE／VOLUME 各自計級——rec 分開儲。"""
    rec_v = {"level": 10, "count": 1, "last_alert": "10:00:00"}
    assert decide_alert(rec_v, 12.0, 10.0, 10.0) == (False, 0, 0)
    assert decide_alert(rec_v, 21.0, 10.0, 10.0)[0] is True


# ── 中文數字（種子檔市值欄）──

@pytest.mark.parametrize("text,expect", [
    ("9.9億", 9.9e8),
    ("6.8千萬", 6.8e7),
    ("1,234萬", 1.234e7),
    ("1.2兆", 1.2e12),
    ("-", None),
    ("", None),
    (None, None),
])
def test_parse_cn_number(text, expect):
    if expect is None:
        assert parse_cn_number(text) is None
    else:
        assert parse_cn_number(text) == pytest.approx(expect)


# ── fixtures 同檔案介面存在性 ──

def test_rtss_fixture_exists_with_15_rows():
    fx = ROOT / "tests" / "fixtures" / "rtss_20260904.csv"
    assert fx.exists()
    df = pd.read_csv(fx, dtype=str)
    assert list(df.columns) == ["code5"]
    assert len(df) == 15
    assert set(df["code5"].str.len()) == {5}


def test_seed_csv_exists():
    seed = ROOT / "data" / "universe_seed_20260831.csv"
    assert seed.exists()
    df = pd.read_csv(seed, encoding="utf-8-sig", dtype=str)
    assert len(df) == 1564
    assert "編號" in df.columns and "內資股(佔比)" in df.columns


def test_seed_known_duplicate_codes():
    """種子有 2 個重複代號——load_seed 要去重。"""
    from stockscan.universe import load_seed

    raw = pd.read_csv(ROOT / "data" / "universe_seed_20260831.csv",
                      encoding="utf-8-sig", dtype=str)
    assert raw["編號"].map(seed_code_to_lb).duplicated().sum() >= 1
    df = load_seed()
    assert not df["code5"].duplicated().any()


def test_state_roundtrip(tmp_path, monkeypatch):
    import stockscan.io_utils as iou

    monkeypatch.setattr(iou, "STATE_DIR", tmp_path)
    d = date(2026, 9, 7)
    assert iou.load_state(d) == {}
    iou.save_state(d, {"700.HK": {"level": 20, "count": 1, "last_alert": "10:00:00"}})
    assert iou.load_state(d)["700.HK"]["level"] == 20


# ── P1 快取：UTC→HKT 日期回歸測試（09-04 全空榜慘案疫苗）──

def test_cache_date_uses_hkt_not_utc(tmp_path, monkeypatch):
    """官方文檔：API timestamp 係 UTC。日 K timestamp 係 HKT 零晨（= UTC 前一日 16:00），
    merge_save 必須轉 HKT 先取日期，否則全快取日期早一日。"""
    from datetime import datetime, timezone
    from types import SimpleNamespace

    import stockscan.kline_cache as kc

    monkeypatch.setattr(kc, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(kc, "_MEMO", {})
    bars = [
        SimpleNamespace(
            timestamp=datetime(2026, 9, 3, 16, 0, tzinfo=timezone.utc),  # = HKT 09-04 00:00
            open=1, high=1, low=1, close=1, volume=1, turnover=1.0),
        SimpleNamespace(
            timestamp=datetime(2026, 9, 6, 16, 0, tzinfo=timezone.utc),  # = HKT 09-07 00:00
            open=2, high=2, low=2, close=2, volume=2, turnover=2.0),
    ]
    df = kc.merge_save("99999", bars)
    assert list(df["date"]) == ["2026-09-04", "2026-09-07"]


def test_cache_window_upto_and_memo(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from datetime import date as _date

    import stockscan.kline_cache as kc

    monkeypatch.setattr(kc, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(kc, "_MEMO", {})
    bars = [
        SimpleNamespace(timestamp=datetime(2026, 9, 2, 16, tzinfo=timezone.utc),
                        open=1, high=1, low=1, close=1, volume=1, turnover=100.0),
        SimpleNamespace(timestamp=datetime(2026, 9, 3, 16, tzinfo=timezone.utc),
                        open=1, high=1, low=1, close=1, volume=1, turnover=200.0),
        SimpleNamespace(timestamp=datetime(2026, 9, 6, 16, tzinfo=timezone.utc),
                        open=1, high=1, low=1, close=1, volume=1, turnover=300.0),
    ]
    kc.merge_save("99998", bars)
    df = kc.load("99998")
    assert df is not None and kc.load("99998") is df  # memo 命中
    win = kc.window_upto(df, _date(2026, 9, 4), 11)
    assert list(win["date"]) == ["2026-09-03", "2026-09-04"]
    assert list(kc.window_upto(df, _date(2026, 9, 4), 1)["date"]) == ["2026-09-04"]


def test_rtss_compare_matches_fixture():
    """09-04 對照：命中 15/15（2026-09-08 凌晨實測結果，回歸保護）。"""
    import json

    cmp_path = ROOT / "data" / "eod" / "compare_rtss_20260904.json"
    if not cmp_path.exists():
        import pytest
        pytest.skip("compare JSON 未生成")
    res = json.loads(cmp_path.read_text(encoding="utf-8"))
    assert res["hit_count"] == 15
    assert res["missing"] == [] and res["extra"] == []
