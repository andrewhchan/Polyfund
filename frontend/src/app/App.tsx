import { useEffect, useState } from 'react';
import { Search, Github, Loader2 } from 'lucide-react';
import { TrendingCard } from '@/app/components/TrendingCard';
import { fetchTrendingMarkets, TrendingMarket } from '@/services/polymarket';

export default function App() {
    const [trendingItems, setTrendingItems] = useState<TrendingMarket[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const loadMarkets = async () => {
            setLoading(true);
            const markets = await fetchTrendingMarkets(10);
            setTrendingItems(markets);
            setLoading(false);
        };
        loadMarkets();
    }, []);

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
                    />
                    <Search className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-600" size={20} />
                </div>

                {/* Trending Now Section */}
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
            </main>
        </div>
    );
}