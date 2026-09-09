import pandas as pd

from scripts.import_rtss_backfill import import_backfill


def test_import_backfill_uses_hkt_date_and_parser(tmp_path):
    source = tmp_path / "messages.csv"
    pd.DataFrame([{
        "chat_key": "-2795969450", "message_id": "1", "timestamp_text": "1787885036",
        "message_text": "🔥 急升異動 [當日第1次]\n📈 煜榮集團 (HK.01536)\n💰 市值: 2.55億\n📊 成交額: 590.25萬\n📶 升幅: +23.08%\n🕒 最新價: 0.560\n🕐 10:00:00",
        "source_url": "https://web.telegram.org/k/#-2795969450",
    }]).to_csv(source, index=False, encoding="utf-8-sig")
    result = import_backfill(source, pd.Timestamp("2026-08-28").date(), pd.Timestamp("2026-08-28").date())
    assert result["parsed"] == 1
    assert result["days"] == 1
