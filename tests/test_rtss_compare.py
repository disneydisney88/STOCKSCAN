import pandas as pd

from scripts.compare_rtss_daily import compare_day


def test_compare_day_returns_three_groups_and_reason(tmp_path):
    rtss = tmp_path / "rtss.csv"
    ours = tmp_path / "ours.csv"
    out = tmp_path / "diff.csv"
    pd.DataFrame([
        {"code5": "01536", "name": "煜榮集團", "msg_type": "SURGE", "mcap": 2.55e8, "turnover": 5902500},
        {"code5": "09999", "name": "RTSS only", "msg_type": "SURGE", "mcap": 4e8, "turnover": 1e6},
    ]).to_csv(rtss, index=False, encoding="utf-8-sig")
    pd.DataFrame([
        {"code5": "01536", "name": "煜榮集團", "alert_type": "SURGE"},
        {"code5": "08888", "name": "Ours only", "alert_type": "VOLUME"},
    ]).to_csv(ours, index=False, encoding="utf-8-sig")
    compare_day(pd.Timestamp("2026-09-08").date(), rtss, ours, out)
    got = pd.read_csv(out, encoding="utf-8-sig", dtype={"code5": str})
    assert set(got["group"]) == {"both", "rtss_only", "stockscan_only"}
    assert got.loc[got["code5"] == "09999", "possible_reason"].iloc[0] == "mcap_over_3e8"
