import pandas as pd

from scripts.build_go_predictors import _asof_features, _predictors


def test_predictors_are_asof_and_mark_small_samples():
    d = pd.DataFrame({
        "code5": ["1", "1", "2"], "scan_date": ["2026-01-01", "2026-02-01", "2026-01-03"],
        "appearance_seq": [1, 2, 1], "first_action_type": ["GO", "", ""],
        "first_action_days": [10, 0, 0], "fu_go": [1, 0, 0], "fu_rights": [0, 0, 1],
    })
    out = _asof_features(d)
    assert out.loc[out.scan_date == pd.Timestamp("2026-02-01").date(), "prior_go_365d"].iloc[0] == 1
    p = _predictors(out, "led_to_go_180d")
    assert "insufficient_sample" in set(p.sample_note)
