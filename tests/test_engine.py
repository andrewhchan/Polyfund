import pandas as pd

from backend.llm_keywords import _generate_mock
from backend.search_pipeline import discover_markets, _flatten_market
from backend.correlation import compute_correlation_matrix


def test_generate_mock_keywords_dedup():
    kws = _generate_mock("Lakers Lakers playoffs season win")
    assert len(kws) == len(set(kws))
    assert "lakers" in kws


def test_correlation_overlap_filter():
    belief = pd.Series([1, 2, 3, 4], index=pd.date_range("2024-01-01", periods=4, freq="D"))
    candidate = {
        "a": pd.Series([1, 2, 3, 4], index=pd.date_range("2024-01-01", periods=4, freq="D")),
        "b": pd.Series([1, 1, 1], index=pd.date_range("2024-01-01", periods=3, freq="D")),
    }
    df = compute_correlation_matrix(belief, candidate)
    assert "a" in set(df["token_id"])
    assert "b" not in set(df["token_id"])  # zero variance filtered


def test_flatten_market_parses_basic_fields():
    event = {"title": "Event"}
    market = {"conditionId": "cid", "question": "Q?", "clobTokenIds": '["yes","no"]', "volume": 10}
    res = _flatten_market(event, market)
    assert res["condition_id"] == "cid"
    assert res["token_id"] == "yes"
