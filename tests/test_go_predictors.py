import pandas as pd

from scripts.build_go_predictors import _asof_features, _groups, _predictors


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


def test_perform_outcome_uses_known_t60_return_only():
    d = pd.DataFrame({
        "code5": ["1", "2", "3"], "scan_date": ["2026-01-01"] * 3,
        "appearance_seq": [1, 1, 1], "ret_t60": [5.0, -1.0, None],
    })
    out = _asof_features(d)
    assert out["led_to_perform"].tolist()[:2] == [True, False]
    assert pd.isna(out["led_to_perform"].iloc[2])
    p = _predictors(out, "led_to_perform")
    assert set(p["n"]) == {2}


def test_numeric_predictor_bins_are_domain_bins():
    d = pd.DataFrame({
        "mcap": [50_000_000, 200_000_000, 500_000_000, 1_500_000_000],
        "ratio": [10, 20, 50, 80],
        "turnover_to_mcap": [0.5, 1, 5, 8],
        "led_to_go_180d": [0, 1, 0, 1],
    })
    assert set(_groups(d["mcap"], "mcap")) == {"<1億", "1-3億", "3-10億", ">=10億"}
    assert set(_groups(d["ratio"], "ratio")) == {"<20x", "20-50x", ">50x"}
    assert set(_groups(d["turnover_to_mcap"], "turnover_to_mcap")) == {"<1%", "1-5%", ">5%"}
