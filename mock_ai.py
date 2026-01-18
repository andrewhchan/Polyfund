"""
MockAI Belief Analyzer Module
=============================
Provides semantic intent analysis for market belief selection.

This module simulates an AI agent that understands semantic intent alignment
between a user's thesis and market questions. It can be easily replaced with
a real OpenAI/Claude API call later.
"""

from typing import Dict


class MockAIBeliefAnalyzer:
    """
    Simulates an AI agent that understands semantic intent alignment.
    
    This class checks whether a user's thesis (e.g., "Trump Loses") aligns
    with a market question and its outcomes. It can be easily replaced with
    a real OpenAI/Claude API call later.
    
    Key Logic:
    - Parse user intent keywords (wins, loses, fails, succeeds, etc.)
    - Match intent to market question sentiment
    - Return which token (YES/NO) aligns with the user's belief
    """

    # Intent keywords mapped to sentiment
    INTENT_KEYWORDS = {
        # Positive outcomes
        'win': ['win', 'wins', 'winning', 'victory', 'succeed', 'success', 'pass', 'positive'],
        'yes': ['yes', 'affirmative', 'happen', 'occurs', 'true', 'correct'],
        'high': ['high', 'increase', 'rise', 'grow', 'strengthen', 'above'],
        'best': ['best', 'highest', 'strongest', 'most', 'leading'],

        # Negative outcomes
        'lose': ['lose', 'loses', 'losing', 'loss', 'defeat', 'fail', 'failure', 'negative', 'loose'],
        'no': ['no', 'not', 'denial', 'false', "won't", "wont"],
        'low': ['low', 'decrease', 'fall', 'drop', 'weaken', 'below', 'lower'],
        'worst': ['worst', 'lowest', 'weakest', 'least', 'lagging'],
    }

    def __init__(self):
        """Initialize the MockAI analyzer."""
        pass

    @staticmethod
    def extract_intent(user_thesis: str) -> Dict[str, bool]:
        """
        Parse user's thesis to extract intent keywords.
        Returns a dict of detected intents: {intent_type: is_present}
        
        Example:
            "Trump loses" -> {'lose': True, 'win': False, ...}
        """
        thesis_lower = user_thesis.lower()
        detected = {}

        for intent_type, keywords in MockAIBeliefAnalyzer.INTENT_KEYWORDS.items():
            detected[intent_type] = any(kw in thesis_lower for kw in keywords)

        return detected

    @staticmethod
    def compute_match_score(
        user_thesis: str,
        market_question: str,
        use_yes_token: bool = True
    ) -> float:
        """
        Compute semantic alignment score between user thesis and market question.
        
        Returns score in range [0.0, 1.0]:
        - 1.0: Perfect alignment (user intent matches the token outcome)
        - 0.5: Neutral/unclear alignment
        - 0.0: Inverted (user intent contradicts the token outcome)
        
        Args:
            user_thesis: User's input (e.g., "Trump Loses")
            market_question: Market question text (e.g., "Will Trump win election?")
            use_yes_token: Whether we're evaluating the YES token (True) or NO token (False)
        """
        user_intent = MockAIBeliefAnalyzer.extract_intent(user_thesis)
        question_intent = MockAIBeliefAnalyzer.extract_intent(market_question)

        # Determine if user believes in positive or negative outcome
        user_positive = sum([user_intent.get('win', False), 
                            user_intent.get('yes', False),
                            user_intent.get('high', False),
                            user_intent.get('best', False)])
        
        user_negative = sum([user_intent.get('lose', False),
                            user_intent.get('no', False),
                            user_intent.get('low', False),
                            user_intent.get('worst', False)])

        # Determine if market question is about positive or negative outcome
        question_positive = sum([question_intent.get('win', False),
                                question_intent.get('yes', False),
                                question_intent.get('high', False),
                                question_intent.get('best', False)])

        question_negative = sum([question_intent.get('lose', False),
                                question_intent.get('no', False),
                                question_intent.get('low', False),
                                question_intent.get('worst', False)])

        # Calculate alignment based on YES vs NO token
        if use_yes_token:
            # For YES token: user positive intent should align with question being positive
            # For YES token: user negative intent should align with question being negative
            if user_positive > 0 and question_positive > 0:
                alignment = 1.0  # Perfect: user wants positive, market asks about positive
            elif user_negative > 0 and question_negative > 0:
                alignment = 1.0  # Perfect: user wants negative, market asks about negative
            elif user_positive > 0 and question_negative > 0:
                alignment = 0.0  # Inverted: user wants positive but market is about negative
            elif user_negative > 0 and question_positive > 0:
                alignment = 0.0  # Inverted: user wants negative but market is about positive
            else:
                alignment = 0.5  # Unclear
        else:
            # For NO token: opposite logic
            if user_positive > 0 and question_negative > 0:
                alignment = 1.0  # Perfect: user wants positive, NO flips negative to positive
            elif user_negative > 0 and question_positive > 0:
                alignment = 1.0  # Perfect: user wants negative, NO flips positive to negative
            elif user_positive > 0 and question_positive > 0:
                alignment = 0.0  # Inverted
            elif user_negative > 0 and question_negative > 0:
                alignment = 0.0  # Inverted
            else:
                alignment = 0.5  # Unclear

        return alignment

    def analyze_candidate(
        self,
        user_thesis: str,
        market_question: str,
        yes_token_id: str,
        no_token_id: str = None
    ) -> Dict[str, any]:
        """
        Analyze a single candidate market for semantic alignment.
        
        Returns:
        {
            'market_question': str,
            'yes_token_id': str,
            'no_token_id': Optional[str],
            'recommended_token_id': str,
            'alignment_score': float,  # 0.0-1.0
            'reasoning': str
        }
        """
        yes_score = self.compute_match_score(user_thesis, market_question, use_yes_token=True)
        no_score = self.compute_match_score(user_thesis, market_question, use_yes_token=False) if no_token_id else 0.0

        if yes_score > no_score:
            recommended_token = yes_token_id
            alignment_score = yes_score
            token_choice = "YES"
        elif no_score > yes_score and no_token_id:
            recommended_token = no_token_id
            alignment_score = no_score
            token_choice = "NO"
        else:
            # Equal or unclear - default to YES but with lower confidence
            recommended_token = yes_token_id
            alignment_score = yes_score
            token_choice = "YES"

        # Generate reasoning
        if alignment_score >= 0.9:
            reasoning = f"Strong alignment: {token_choice} token matches user intent"
        elif alignment_score >= 0.7:
            reasoning = f"Good alignment: {token_choice} token matches user intent"
        elif alignment_score >= 0.5:
            reasoning = "Moderate alignment: ambiguous match, using default"
        else:
            reasoning = f"WARNING: Potential intent mismatch. {token_choice} token used cautiously"

        return {
            'market_question': market_question,
            'yes_token_id': yes_token_id,
            'no_token_id': no_token_id,
            'recommended_token_id': recommended_token,
            'alignment_score': alignment_score,
            'token_choice': token_choice,
            'reasoning': reasoning
        }
