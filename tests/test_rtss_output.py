import json
from argparse import Namespace

import pandas as pd

from scripts.build_rtss_alerts import build_day
from scripts import fetch_rtss_cdp


def test_build_day_upserts_code_and_alert_ts(tmp_path):
    raw = tmp_path / "raw.jsonl"
    rows = [{
        "message_key": "a", "message_date": "2026-09-08",
        "raw_text": "🔥 急升異動 [當日第1次]\n📈 煜榮集團 (HK.01536)\n💰 市值: 2.55億\n📊 成交額: 590.25萬\n📶 升幅: +23.08%\n🕒 最新價: 0.560\n🕐 14:24:13"
    }, {
        "message_key": "b", "message_date": "2026-09-08",
        "raw_text": "🔥 急升異動 [當日第2次 (22%→32%)]\n📈 煜榮集團 (HK.01536)\n💰 市值: 2.55億\n📊 成交額: 590.25萬\n📶 升幅: +32.00%\n🕒 最新價: 0.560\n🕐 14:42:53"
    }]
    raw.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    out = tmp_path / "alerts.csv"
    build_day(pd.Timestamp("2026-09-08").date(), raw, out)
    build_day(pd.Timestamp("2026-09-08").date(), raw, out)
    got = pd.read_csv(out, encoding="utf-8-sig", dtype={"code5": str})
    assert len(got) == 2
    assert got.loc[0, "code5"] == "01536"
    assert set(got["alert_ts"]) == {"2026-09-08 14:24:13", "2026-09-08 14:42:53"}


def test_date_label_parser_resolves_relative_labels_from_fixed_monday(monkeypatch):
    """Calendar labels must be compared as dates, including Monday's Saturday."""
    fixed_today = pd.Timestamp("2026-09-14").date()  # Monday
    monkeypatch.setattr(fetch_rtss_cdp, "today_hkt", lambda: fixed_today)

    assert fetch_rtss_cdp._date_from_label("Today") == fixed_today
    assert fetch_rtss_cdp._date_from_label("Yesterday") == pd.Timestamp("2026-09-13").date()
    assert fetch_rtss_cdp._date_from_label("Monday") == fixed_today
    assert fetch_rtss_cdp._date_from_label("Saturday") == pd.Timestamp("2026-09-12").date()
    assert fetch_rtss_cdp._date_from_label("September 11") == pd.Timestamp("2026-09-11").date()


def test_date_label_parser_friday_means_today_when_today_is_friday(monkeypatch):
    fixed_today = pd.Timestamp("2026-09-11").date()  # Friday
    monkeypatch.setattr(fetch_rtss_cdp, "today_hkt", lambda: fixed_today)

    labels = ["Wednesday", "Thursday", "Friday", "Today"]
    parsed = {label: fetch_rtss_cdp._date_from_label(label) for label in labels}
    # Same-day weekday labels use the nearest occurrence, so Friday means today.
    assert parsed["Friday"] == fixed_today
    assert parsed["Today"] == fixed_today


def test_explicit_from_to_range_does_not_fall_back_to_today():
    args = Namespace(
        backfill=False,
        from_date="2026-08-15",
        to_date="2026-08-15",
        date=None,
    )
    assert fetch_rtss_cdp._date_range(args) == (
        pd.Timestamp("2026-08-15").date(),
        pd.Timestamp("2026-08-15").date(),
    )
