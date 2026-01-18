
import sys
import os
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.api_server import build_recommendations, RecommendationRequest

def test_fallback_logic():
    print("Testing Fallback Logic...")

    # Mock discover_markets to return some dummy markets
    mock_markets = [
        {
            "condition_id": "1",
            "question": "Market 1",
            "yes_token_id": "yes1",
            "no_token_id": "no1",
            "volume_usd": 1000
        },
        {
            "condition_id": "2",
            "question": "Market 2",
            "yes_token_id": "yes2",
            "no_token_id": "no2",
            "volume_usd": 2000
        }
    ]

    # Mock anchor selection to simulate low confidence
    mock_anchor = MagicMock()
    mock_anchor.confidence = 0.5 # Below 0.90 threshold

    # Mock select_arbitrary_bets to return fake bets
    mock_bets = [
        {
            "question": "Arbitrary Bet 1",
            "action": "BUY YES",
            "weight_pct": 0,
            "ai_reasoning": "Because it is arbitrary"
        }
    ]

    with patch('backend.api_server.discover_markets', return_value=(mock_markets, {})) as mock_discover, \
         patch('backend.api_server.select_anchor_market', return_value=mock_anchor) as mock_select_anchor, \
         patch('backend.api_server.generate_proxy_theses', return_value=[]), \
         patch('backend.belief_selection.select_arbitrary_bets', return_value=mock_bets) as mock_select_bets:
        
        req = RecommendationRequest(thesis="Impossible Thesis")
        result = build_recommendations(req)

        print("\nResult Keys:", result.keys())
        print("Status:", result.get("status"))
        print("Warning:", result.get("warning"))
        print("Portfolio Len:", len(result.get("portfolio", [])))
        
        if result.get("warning") == "Thesis is too far off an existing market for data analysis.":
            print("\nSUCCESS: Warning message present.")
        else:
            print("\nFAILURE: Warning message missing.")

        if result.get("portfolio") == mock_bets:
             print("SUCCESS: Portfolio contains arbitrary bets.")
        else:
             print("FAILURE: Portfolio does not contain arbitrary bets.")

if __name__ == "__main__":
    test_fallback_logic()
