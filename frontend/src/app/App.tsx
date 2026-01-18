import { useEffect, useState } from 'react';
import { Search, Github, Loader2 } from 'lucide-react';
import { TrendingCard } from '@/app/components/TrendingCard';
import { fetchTrendingMarkets, fetchRecommendations, TrendingMarket, RecommendationResponse, PortfolioItem } from '@/services/polymarket';

export default function App() {
    const [trendingItems, setTrendingItems] = useState<TrendingMarket[]>([]);
    const [loading, setLoading] = useState(true);

    // Search & Recommendations State
    const [searchQuery, setSearchQuery] = useState('');
    const [isSearching, setIsSearching] = useState(false);
    const [recommendations, setRecommendations] = useState<RecommendationResponse | null>(null);

    useEffect(() => {
        const loadMarkets = async () => {
            setLoading(true);
            const markets = await fetchTrendingMarkets(10);
            setTrendingItems(markets);
            setLoading(false);
        };
        loadMarkets();
    }, []);

    const handleSearch = async (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter' && searchQuery.trim()) {
            setIsSearching(true);
            setRecommendations(null); // clear previous results
            const results = await fetchRecommendations(searchQuery);
            setRecommendations(results);
            setIsSearching(false);
        }
    };

    return (
        <div className="size-full bg-[#0a0a0f] text-white overflow-auto">
            {/* Header */}
            <header className="flex items-center justify-between p-6">
                <a href="/" className="flex items-center gap-2 hover:opacity-80 transition-opacity">
                    <div className="w-8 h-8 bg-blue-600 rounded flex items-center justify-center text-white font-bold">
                        P
                    </div>
                    <span className="text-xl font-semibold">Polyfund</span>
                </a>
                <a href="https://github.com/andrewhchan/Polyfund" target="_blank" rel="noopener noreferrer" className="p-2 text-gray-400 hover:text-white transition-colors">
                    <Github size={24} />
                </a>
            </header>

            {/* Hero Section */}
            <main className="max-w-4xl mx-auto px-6 pt-12 pb-8">
                <h1 className="text-6xl font-bold text-center mb-6">
                    Trade on your <span className="text-blue-500">thesis.</span>
                </h1>

                <p className="text-gray-400 text-lg text-center mb-10">
                    Discover correlation-aware opportunities across Polymarket's most liquid events.
                </p>

                {/* Search Bar */}
                <div className="relative mb-16">
                    <input
                        type="text"
                        placeholder="What's your thesis? (e.g. 'Trump 2024', 'Fed Rates')"
                        className="w-full h-14 bg-[#1a1a24] text-gray-300 px-5 pr-12 rounded-lg border border-gray-800 focus:outline-none focus:border-gray-700 placeholder:text-gray-600"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        onKeyDown={handleSearch}
                        disabled={isSearching}
                    />
                    {isSearching ? (
                        <Loader2 className="absolute right-4 top-1/2 -translate-y-1/2 text-blue-500 animate-spin" size={20} />
                    ) : (
                        <Search className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-600" size={20} />
                    )}
                </div>

                {/* Logic: If recommendations exist, show them. Else, show trending. */}
                {recommendations ? (
                    <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <section className="mb-12">
                            <h2 className="text-2xl font-bold mb-4 text-blue-400">Anchor Market</h2>
                            <div className="bg-[#13131a] border border-blue-500/30 rounded-lg p-6 flex flex-col md:flex-row gap-6 items-start md:items-center">
                                <div className="flex-1">
                                    <div className="flex items-center gap-3 mb-2">
                                        <span className="bg-blue-600 text-xs px-2 py-1 rounded font-bold">ANCHOR</span>
                                        <span className="text-sm text-gray-400">Confidence: {(recommendations.anchor.ai_confidence * 100).toFixed(0)}%</span>
                                    </div>
                                    <a href={`https://polymarket.com/event/${recommendations.anchor.slug}`} target="_blank" rel="noopener noreferrer" className="hover:underline">
                                        <h3 className="text-xl font-bold mb-2">{recommendations.anchor.question}</h3>
                                    </a>
                                    <p className="text-gray-400 text-sm italic">"{recommendations.anchor.ai_reasoning}"</p>
                                </div>
                                <div className="text-right">
                                    <button className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-6 rounded-lg transition-colors">
                                        Trade {recommendations.anchor.token_choice}
                                    </button>
                                </div>
                            </div>
                        </section>

                        <section>
                            <h2 className="text-xl font-semibold mb-6">Correlated Opportunities</h2>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {recommendations.portfolio.map((item: PortfolioItem, index: number) => (
                                    <div key={index} className="bg-[#1a1a24] border border-gray-800 rounded-xl p-4 hover:border-gray-600 transition-colors">
                                        <div className="flex justify-between items-start mb-2">
                                            <a href={`https://polymarket.com/event/${item.slug}`} target="_blank" rel="noopener noreferrer" className="hover:underline pr-2 flex-1">
                                                <h3 className="font-semibold line-clamp-2">{item.question}</h3>
                                            </a>
                                            <div className={`px-2 py-1 rounded text-xs font-bold ${item.correlation > 0 ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                                                {item.correlation > 0 ? '+' : ''}{item.correlation.toFixed(2)}
                                            </div>
                                        </div>
                                        <div className="flex justify-between items-end mt-4">
                                            <div className="text-sm text-gray-400">
                                                Action: <span className={item.action.includes('YES') ? 'text-green-400' : 'text-red-400'}>{item.action}</span>
                                            </div>
                                            <div className="text-sm text-gray-500">
                                                Weight: {(item.weight * 100).toFixed(1)}%
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </section>
                    </div>
                ) : (
                    /* Trending Now Section */
                    <section>
                        <div className="flex items-center gap-2 mb-6">
                            <h2 className="text-xl font-semibold">Trending Now</h2>
                            <span className="text-xs text-gray-500 bg-gray-800 px-2 py-1 rounded">Top Liquid</span>
                        </div>

                        {loading ? (
                            <div className="flex justify-center py-12">
                                <Loader2 className="animate-spin text-blue-500" size={32} />
                            </div>
                        ) : (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 px-4">
                                {trendingItems.map((item, index) => (
                                    <TrendingCard key={index} {...item} />
                                ))}
                            </div>
                        )}
                    </section>
                )}
            </main>
        </div>
    );
}