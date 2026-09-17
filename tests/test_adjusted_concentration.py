from stockscan.adjusted_concentration import ConcentrationConfig, compute_concentration


def test_adjusted_concentration_applies_same_exclusion_to_numerator_and_denominator():
    holdings = [
        {"pid": "A00001", "name": "settlement", "shares": 600},
        {"pid": "B01955", "name": "broker", "shares": 300},
        {"pid": "B02000", "name": "broker2", "shares": 100},
    ]
    out = compute_concentration(holdings, issued_shares=2000,
                                cfg=ConcentrationConfig(exclude_ids={"A00001"}))
    assert out["ccass_total_shares"] == 1000
    assert out["excluded_shares"] == 600
    assert out["adjusted_float_shares"] == 400
    assert out["adj_top5_pct"] == 100.0
    assert out["top5_shares"] == 400


def test_empty_holdings_is_explicit_error():
    assert compute_concentration([])["error"] == "NO_HOLDINGS"
