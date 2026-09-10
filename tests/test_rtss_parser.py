from stockscan.rtss_parser import parse_alert
from pytest import approx


SAMPLE = """🔥 3億以下急升異動 [當日第1次 (20%→41%)]
📈 煜榮集團 (HK.01536)
💰 市值: 2.55億
📊 成交額: 590.25萬
📶 升幅: +23.08%
🕒 最新價: 0.560
🕐 15:26:31
相關範疇：港股細市值急升監控"""


def test_parse_rtss_surge_sample():
    got = parse_alert(SAMPLE)
    assert got["msg_type"] == "SURGE"
    assert got["code5"] == "01536"
    assert got["name"] == "煜榮集團"
    assert got["mcap"] == approx(255_000_000)
    assert got["turnover"] == approx(5_902_500)
    assert got["chg_pct"] == approx(23.08)
    assert got["last_price"] == approx(0.56)
    assert got["time"] == "15:26:31"
    assert got["count_today"] == 1
    assert got["level_range"] == "20%→41%"
    assert got["parse_failed"] == 0


def test_parse_failure_keeps_raw_text_without_raising():
    got = parse_alert("RTSS message without structured fields")
    assert got["parse_failed"] == 1
    assert got["raw_text"].startswith("RTSS message")


def test_parse_single_line_alert():
    got = parse_alert("3億以下急升異動 [當日第1次] 煜榮集團 (HK.01536) 市值: 2.55億 成交額: 590.25萬 升幅: +23.08% 最新價: 0.560 15:26:31")
    assert got["code5"] == "01536"
    assert got["mcap"] == approx(255_000_000)
    assert got["turnover"] == approx(5_902_500)
    assert got["parse_failed"] == 0


def test_01536_two_alerts_keep_distinct_alert_ts():
    first = parse_alert(
        "急升異動 [當日第1次]\n煜榮集團 (HK.01536) 市值: 1.50億 成交額: 231.77萬 "
        "升幅: +22.00% 最新價: 0.300 🕐 14:24:13",
        message_date="2026-09-08",
    )
    second = parse_alert(
        "急升異動 [當日第2次 (22%→32%)]\n煜榮集團 (HK.01536) 市值: 1.50億 成交額: 231.77萬 "
        "升幅: +32.00% 最新價: 0.330 🕐 14:42:53",
        message_date="2026-09-08",
    )
    assert first["alert_ts"] == "2026-09-08 14:24:13"
    assert second["alert_ts"] == "2026-09-08 14:42:53"
    assert first["alert_ts"] != second["alert_ts"]
    assert second["count_today"] == 2
    assert second["level_from"] == 22
    assert second["level_to"] == 32
