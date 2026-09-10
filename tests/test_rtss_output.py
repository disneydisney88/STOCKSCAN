import json

import pandas as pd

from scripts.build_rtss_alerts import build_day


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
