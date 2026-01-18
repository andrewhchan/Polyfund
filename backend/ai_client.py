"""
AI Client Module
================
Abstraction layer for AI API calls using Google Gemini.
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional

from google import genai


@dataclass
class AnchorSelectionResult:
    """Result from AI anchor selection."""
    market_index: Optional[int]
    reasoning: str
    token_choice: Literal["YES", "NO"]
    token_reasoning: str
    confidence: float
    raw_response: str  # For debugging


class AIClientError(Exception):
    """Raised when AI client encounters an error."""
    pass


ANCHOR_SELECTION_PROMPT = """You are a financial analyst selecting prediction market positions.

## Task
Given a user's abstract belief and a list of prediction markets, identify the
SINGLE BEST market that serves as a "numerical proxy" for their belief.

## What is a Numerical Proxy?
A market whose price movement will track the truth of the user's belief.
The market should have:
1. Strong semantic alignment with the thesis
2. Sufficient liquidity (higher volume = more reliable price signal)
3. Moderate specificity (not too broad, not too narrow)

## Selection Criteria (weigh these together)
- Semantic fit: How well does the market capture the user's belief?
- Liquidity: Higher volume markets have more reliable prices
- Specificity: "Lakers make playoffs" is better than "Lakers win championship"
  for a "good season" thesis

CRITICAL: If NO market is a strong semantic match (e.g. thesis is nonsense, irrelevant, or very different), return null for the selected_market_index. 
Do NOT force a match. It is better to return nothing than a bad anchor.
If you return an anchor, confidence must be > 0.7.

## Examples
- "Lakers good season" -> "Lakers Make Playoffs" (GOOD - moderate specificity)
- "Lakers good season" -> "Lakers Win Championship" (TOO SPECIFIC)
- "Trump loses" -> "Trump wins election" with NO token (GOOD - inverted alignment)
- "Aliens invade" -> "Soccer match result" (BAD - return null)

## User's Thesis
{user_thesis}

## Available Markets
{markets_json}

## Response (JSON only, no markdown code blocks)
{{
    "selected_market_index": <int or null>,
    "reasoning": "<2-3 sentences: why this market is the best proxy, or why none fit>",
    "token_choice": "YES" or "NO",
    "token_reasoning": "<1 sentence: why this token aligns with thesis>",
    "confidence": <0.0-1.0>
}}
"""


TOP_BETS_SELECTION_PROMPT = """You are a financial analyst constructing a basket of prediction market bets.

## Task
Given a user's abstract belief and a list of potentially relevant markets, select the TOP {top_k} markets that constitute the best "bets" to express this view.
These should be your "arbitrary bets" when a single perfect correlation anchor cannot be found.

## Filters
- Ignore markets that are completely irrelevant.
- Prefer higher volume markets when relevance is similar.
- You can select fewer than {top_k} if there aren't enough good matches.

## User's Thesis
{user_thesis}

## Available Markets
{markets_json}

## Response (JSON only, no markdown code blocks)
{{
    "selected_bets": [
        {{
            "market_index": <int>,
            "reasoning": "<1 sentence: why this is a good bet for the thesis>",
            "token_choice": "YES" or "NO",
            "confidence": <0.0-1.0>
        }},
        ...
    ]
}}
"""


class AIClient:
    """
    AI client for anchor selection using Google Gemini.

    Usage:
        client = AIClient()
        result = client.select_anchor(user_thesis, markets)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-flash-lite"
    ):
        """
        Initialize AI client.

        Args:
            api_key: Gemini API key (defaults to GEMINI_API_KEY env var)
            model: Model name (default: gemini-2.5-flash)
        """
        api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise AIClientError(
                "GEMINI_API_KEY not found. Set it as an environment variable or pass api_key parameter."
            )

        self.client = genai.Client(api_key=api_key)
        self.model_name = model

    def select_anchor(
        self,
        user_thesis: str,
        markets: List[Dict]
    ) -> AnchorSelectionResult:
        """
        Use AI to select the best anchor market.

        Args:
            user_thesis: User's abstract belief (e.g., "Lakers will have a good season")
            markets: List of market dicts with 'question', 'yes_token_id', 'no_token_id', 'volume_usd'

        Returns:
            AnchorSelectionResult with selected market index and token choice

        Raises:
            AIClientError: If API call fails or response is invalid
        """
        # Format markets for prompt (include index, question, volume)
        markets_for_prompt = []
        for i, m in enumerate(markets):
            markets_for_prompt.append({
                "index": i,
                "question": m.get("question", ""),
                "volume_usd": m.get("volume_usd", 0),
            })

        markets_json = json.dumps(markets_for_prompt, indent=2)

        prompt = ANCHOR_SELECTION_PROMPT.format(
            user_thesis=user_thesis,
            markets_json=markets_json
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            raw_response = response.text
            if raw_response is None:
                raise AIClientError("Gemini API returned empty response")
        except Exception as e:
            raise AIClientError(f"Gemini API call failed: {e}")

        return self._parse_response(raw_response, len(markets))

    def _parse_response(self, response: str, num_markets: int) -> AnchorSelectionResult:
        """Parse AI response JSON into AnchorSelectionResult with fallbacks."""

        # Try 1: Direct JSON parse
        try:
            data = json.loads(response.strip())
            return self._validate_and_create_result(data, num_markets, response)
        except json.JSONDecodeError:
            pass

        # Try 2: Extract JSON from markdown code block
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                return self._validate_and_create_result(data, num_markets, response)
            except json.JSONDecodeError:
                pass

        # Try 3: Find JSON object in response
        json_match = re.search(r'\{[^{}]*"selected_market_index"[^{}]*\}', response, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                return self._validate_and_create_result(data, num_markets, response)
            except json.JSONDecodeError:
                pass

        # Try 4: Regex extraction of key fields
        index_match = re.search(r'"selected_market_index"\s*:\s*(\d+)', response)
        token_match = re.search(r'"token_choice"\s*:\s*"(YES|NO)"', response)

        if index_match and token_match:
            token_value = token_match.group(1)
            if token_value not in ("YES", "NO"):
                token_value = "YES"
            return AnchorSelectionResult(
                market_index=int(index_match.group(1)),
                token_choice=token_value,  # type: ignore
                reasoning="[Partial parse - check raw response]",
                token_reasoning="[Partial parse]",
                confidence=0.5,
                raw_response=response
            )

        raise AIClientError(f"Failed to parse AI response: {response[:500]}...")

    def _validate_and_create_result(
        self,
        data: Dict,
        num_markets: int,
        raw_response: str
    ) -> AnchorSelectionResult:
        """Validate parsed data and create result object."""

        market_index = data.get("selected_market_index")
        
        # Allow explicit null/None for no selection
        if market_index is None:
            pass
        elif not isinstance(market_index, int):
             raise AIClientError(f"Invalid market_index: {market_index}")
        elif market_index < 0 or market_index >= num_markets:
            raise AIClientError(f"Market index {market_index} out of range (0-{num_markets-1})")

        token_choice = data.get("token_choice", "YES")
        if token_choice not in ("YES", "NO"):
            token_choice = "YES"  # Default to YES if invalid

        confidence = data.get("confidence", 0.5)
        if not isinstance(confidence, (int, float)):
            confidence = 0.5
        confidence = max(0.0, min(1.0, float(confidence)))

        return AnchorSelectionResult(
            market_index=market_index,
            reasoning=data.get("reasoning", ""),
            token_choice=token_choice,
            token_reasoning=data.get("token_reasoning", ""),
            confidence=confidence,
            raw_response=raw_response
        )

    def select_top_bets(
        self,
        user_thesis: str,
        markets: List[Dict],
        top_k: int = 10
    ) -> List[Dict]:
        """
        Use AI to select the top K bets for a thesis (fallback mode).

        Returns:
            List of dicts with:
            - market (original market dict)
            - reasoning
            - token_choice
            - confidence
        """
        markets_for_prompt = []
        for i, m in enumerate(markets):
            markets_for_prompt.append({
                "index": i,
                "question": m.get("question", ""),
                "volume_usd": m.get("volume_usd", 0),
            })

        markets_json = json.dumps(markets_for_prompt, indent=2)
        prompt = TOP_BETS_SELECTION_PROMPT.format(
            user_thesis=user_thesis,
            markets_json=markets_json,
            top_k=top_k
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            raw_response = response.text
            if not raw_response:
                raise AIClientError("Gemini API returned empty response for top bets")
        except Exception as e:
            print(f"[ERROR] Gemini API call failed for top bets: {e}")
            return []

        # Parse logic for list of bets
        try:
            # 1. Strip markdown
            clean_response = raw_response.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            if clean_response.startswith("```"):
                clean_response = clean_response[3:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]

            data = json.loads(clean_response)
            selected = data.get("selected_bets", [])

            results = []
            for item in selected:
                idx = item.get("market_index")
                if idx is not None and 0 <= idx < len(markets):
                    market = markets[idx]
                    results.append({
                        "market": market,
                        "reasoning": item.get("reasoning", ""),
                        "token_choice": item.get("token_choice", "YES"),
                        "confidence": float(item.get("confidence", 0.5))
                    })
            return results

        except Exception as e:
            print(f"[ERROR] Failed to parse top bets response: {e}")
            print(f"Raw response: {raw_response}")
            return []
