
import sys
import os
from rapidfuzz import fuzz
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.search_pipeline import discover_markets, generate_keywords

def debug_relevance():
    load_dotenv()
    query = "Aliens invade earth and we all die"
    print(f"Query: {query}")
    
    # 1. Check Keywords
    keywords = generate_keywords(query)
    print(f"\nGenerated Keywords: {keywords}")
    
    # 2. Check Discovery
    print("\nDiscovering markets...")
    markets, explain = discover_markets(query, k=20)
    
    print(f"\nFound {len(markets)} markets.")
    print("Top 10 results:")
    for i, m in enumerate(markets[:10]):
        question = m.get('question')
        slug = m.get('slug')
        relevance = m.get('relevance_match')
        score = m.get('relevance_score')
        
        # Manually check fuzzy score against query
        manual_score = fuzz.partial_ratio(query.lower(), question.lower())
        
        print(f"{i+1}. [{relevance:.1f} / {manual_score:.1f}] {question} (Slug: {slug})")
        
    if "filters" in explain:
        print("\nFilters debug:", explain["filters"])

if __name__ == "__main__":
    debug_relevance()
