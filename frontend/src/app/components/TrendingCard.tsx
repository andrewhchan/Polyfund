interface TrendingCardProps {
    question: string;
    probability: number;
    volume: string;
    spread?: string;
    tag?: string;
    icon: string;
    slug: string;
}

export function TrendingCard({ question, probability, volume, spread, tag, icon, slug }: TrendingCardProps) {
    return (
        <a
            href={`https://polymarket.com/event/${slug}`}
            target="_blank"
            rel="noopener noreferrer"
            className="block"
        >
            <div className="bg-[#1a1a24] border border-gray-800 rounded-lg p-4 hover:border-gray-700 transition-colors cursor-pointer">
                <div className="flex items-start gap-3 mb-3">
                    {icon.startsWith('http') ? (
                        <img src={icon} alt={question} className="w-8 h-8 rounded-full object-cover" />
                    ) : (
                        <div className="text-2xl">{icon}</div>
                    )}
                    <div className="flex-1">
                        <h3 className="text-sm text-gray-300 mb-2">{question}</h3>
                        {tag && (
                            <span className="text-xs text-gray-500 bg-gray-800 px-2 py-1 rounded">
                                {tag}
                            </span>
                        )}
                    </div>
                </div>

                <div className="space-y-1">
                    <div className="text-xs text-gray-500 uppercase">Probability</div>
                    <div className="flex items-baseline gap-2">
                        <span className="text-2xl font-bold">{probability}%</span>
                        <span className="text-xs text-gray-500">Yes</span>
                    </div>

                    <div className="flex items-center justify-between text-xs text-gray-500 mt-2">
                        <span>{volume}</span>
                        {spread && <span>{spread}</span>}
                    </div>
                </div>
            </div>
        </a>
    );
}
