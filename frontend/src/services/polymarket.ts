export interface TrendingMarket {
    question: string;
    probability: number;
    volume: string;
    tag: string;
    icon: string;
    spread?: string;
}

interface GammaMarket {
    question: string;
    volume: number;
    tags?: string[];
    outcomePrices?: string; // JSON string "[0.5, 0.5]"
    lastTradePrice?: number;
    bestAsk?: number;
    bestBid?: number;
    clobTokenIds?: string; // JSON string "['yes_id', 'no_id']"
    active: boolean;
    closed: boolean;
    conditionId: string;
    // Fallback fields as API structure can vary
    volumeNum?: number;
    icon?: string;
    image?: string;
}

interface GammaEvent {
    id: string;
    title: string;
    markets: GammaMarket[];
    // Event level images
    icon?: string;
    image?: string;
}

export async function fetchTrendingMarkets(limit: number = 20): Promise<TrendingMarket[]> {
    try {
        // Determine base URL: simplified for Vite proxy
        const baseUrl = '/api/gamma';

        // Fetch active events
        const response = await fetch(`${baseUrl}/events?active=true&closed=false&limit=50`);

        if (!response.ok) {
            console.error('Failed to fetch from Polymarket API:', response.statusText);
            return [];
        }

        const events: GammaEvent[] = await response.json();

        const trendingMarkets: TrendingMarket[] = [];

        for (const event of events) {
            // Each event can have multiple markets. We want the most relevant one (usually the main liquid one).
            // Filter for active and open markets first
            let bestMarket = event.markets.find(m => m.active && !m.closed);

            // If no active market found, fallback to the first one (might be closed)
            if (!bestMarket) {
                bestMarket = event.markets[0];
            }

            // Better strategy: sort by volume to get the main market
            if (event.markets.length > 1) {
                const sorted = [...event.markets].sort((a, b) => {
                    const volA = a.volume || a.volumeNum || 0;
                    const volB = b.volume || b.volumeNum || 0;
                    return volB - volA;
                });
                // Prefer the highest volume active AND open market
                const bestActive = sorted.find(m => m.active && !m.closed);
                bestMarket = bestActive || sorted[0];
            }

            if (!bestMarket) continue;

            const volume = bestMarket.volume || bestMarket.volumeNum || 0;

            // Parse outcome price (YES probability)
            let probability = 50; // default

            // Prefer direct values if available to avoid parsing
            if (typeof bestMarket.lastTradePrice === 'number') {
                probability = bestMarket.lastTradePrice * 100;
            } else if (typeof bestMarket.bestAsk === 'number' && typeof bestMarket.bestBid === 'number') {
                probability = ((bestMarket.bestAsk + bestMarket.bestBid) / 2) * 100;
            } else {
                try {
                    if (bestMarket.outcomePrices) {
                        const prices = JSON.parse(bestMarket.outcomePrices);
                        if (prices.length > 0) {
                            // Assuming binary [YES, NO] or similar. 1st is usually YES or Long.
                            // Polymarket convention: [YES, NO]
                            probability = parseFloat(prices[0]) * 100;
                        }
                    }
                } catch (e) {
                    console.warn('Error parsing prices', e);
                }
            }

            // Format volume
            const volumeFormatted = new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: 'USD',
                notation: 'compact',
                maximumFractionDigits: 1
            }).format(volume);

            // Resolve icon: try market icon, then market image, then event icon, then event image
            const iconUrl = bestMarket.icon || bestMarket.image || event.icon || event.image || '📈';

            trendingMarkets.push({
                question: bestMarket.question || event.title,
                probability: Math.round(probability),
                volume: volumeFormatted,
                tag: 'Top Liquid',
                icon: iconUrl,
                spread: undefined
            });
        }

        // Naively take top N from the API response
        return trendingMarkets.slice(0, limit);

    } catch (error) {
        console.error('Error fetching trending markets:', error);
        return [];
    }
}

// Recommendation Types
export interface RecommendationRequest {
    thesis: string;
    days?: number;
    top_k?: number;
}

export interface RecommendationResponse {
    thesis: string;
    status: string;
    anchor: {
        question: string;
        slug: string;
        token_id: string;
        volume_usd: number;
        token_choice: string;
        ai_reasoning: string;
        ai_confidence: number;
    };
    portfolio: PortfolioItem[];
}

export interface PortfolioItem {
    question: string;
    slug: string;
    token_id: string;
    correlation: number;
    weight: number;
    action: 'BUY_YES' | 'BUY_NO';
}

export async function fetchRecommendations(thesis: string): Promise<RecommendationResponse | null> {
    try {
        const response = await fetch('/api/recommendations', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ thesis }),
        });

        if (!response.ok) {
            console.error('Failed to fetch recommendations:', response.statusText);
            return null;
        }

        return await response.json();
    } catch (error) {
        console.error('Error fetching recommendations:', error);
        return null;
    }
}
