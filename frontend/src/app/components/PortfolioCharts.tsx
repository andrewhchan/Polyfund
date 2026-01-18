import { useMemo } from 'react';
import { RecommendationResponse } from '@/services/polymarket';
import {
    LineChart,
    Line,
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    ReferenceLine
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/app/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/app/components/ui/tabs';

interface PortfolioChartsProps {
    data: RecommendationResponse;
}

export function PortfolioCharts({ data }: PortfolioChartsProps) {
    if (!data.timeseries) {
        return <div className="text-center text-gray-500 py-8">No historical data available</div>;
    }

    // Prepare P&L Data
    const pnlData = useMemo(() => {
        return data.timeseries!.pnl_curves.portfolio.map(pt => ({
            date: new Date(pt.date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
            value: (pt.value * 100).toFixed(2), // Convert to percentage
            rawDate: new Date(pt.date).getTime()
        }));
    }, [data]);

    // Prepare Price Data (Anchor vs Candidates - normalized?)
    // For simplicity, let's just show Anchor Price history
    const anchorPriceData = useMemo(() => {
        return data.timeseries!.price_series.anchor.map(pt => ({
            date: new Date(pt.date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
            price: (pt.value * 100).toFixed(1), // cents
        }));
    }, [data]);

    // Prepare Rolling Correlation Data (Window = 7 days default)
    const rollingCorrData = useMemo(() => {
        const windowKey = '7'; // Default to 7 days
        const rawPoints = data.timeseries!.rolling_correlations[windowKey] || [];

        // Group by date
        const byDate: Record<string, any> = {};
        rawPoints.forEach(pt => {
            const dateStr = new Date(pt.date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
            if (!byDate[dateStr]) byDate[dateStr] = { date: dateStr };
            // Find which market this is
            const market = data.portfolio.find(m => m.token_id === pt.token_id);
            if (market) {
                // Shorten question for legend
                const label = market.question.length > 20 ? market.question.substring(0, 20) + '...' : market.question;
                byDate[dateStr][pt.token_id] = pt.correlation;
                byDate[dateStr][`${pt.token_id}_name`] = label;
            }
        });

        return Object.values(byDate);
    }, [data]);

    const portfolioColors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];

    return (
        <div className="space-y-6">
            <Tabs defaultValue="pnl" className="w-full">
                <div className="flex justify-between items-center mb-4">
                    <h2 className="text-xl font-semibold text-white">Strategy Simulations</h2>
                    <TabsList className="bg-[#1a1a24]">
                        <TabsTrigger value="pnl" className="text-gray-400 data-[state=active]:bg-blue-600 data-[state=active]:text-white hover:text-white transition-colors">Backtest P&L</TabsTrigger>
                        <TabsTrigger value="correlation" className="text-gray-400 data-[state=active]:bg-blue-600 data-[state=active]:text-white hover:text-white transition-colors">Rolling Corr (7d)</TabsTrigger>
                        <TabsTrigger value="anchor" className="text-gray-400 data-[state=active]:bg-blue-600 data-[state=active]:text-white hover:text-white transition-colors">Anchor Price</TabsTrigger>
                    </TabsList>
                </div>

                <TabsContent value="pnl" className="animate-in fade-in duration-300">
                    <Card className="bg-[#1a1a24] border-gray-800">
                        <CardHeader className="pb-2">
                            <CardTitle className="text-gray-200 text-lg flex items-center gap-2">
                                Historical Basket Performance (Estimated)
                                <span className="text-xs font-normal text-gray-500 bg-gray-800 px-2 py-1 rounded-full">
                                    Weighted Average of all Positions
                                </span>
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="h-[300px]">
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={pnlData}>
                                    <defs>
                                        <linearGradient id="colorPnl" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                                            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />
                                    <XAxis
                                        dataKey="date"
                                        stroke="#6b7280"
                                        style={{ fontSize: '12px' }}
                                        tickLine={false}
                                        axisLine={false}
                                        tickMargin={10}
                                    />
                                    <YAxis
                                        stroke="#6b7280"
                                        style={{ fontSize: '12px' }}
                                        unit="%"
                                        tickLine={false}
                                        axisLine={false}
                                        tickFormatter={(value) => `${value > 0 ? '+' : ''}${value}`}
                                    />
                                    <Tooltip
                                        contentStyle={{ backgroundColor: '#1a1a24', borderColor: '#333', color: '#fff', borderRadius: '8px' }}
                                        labelStyle={{ color: '#9ca3af', marginBottom: '4px' }}
                                        cursor={{ stroke: '#3b82f6', strokeWidth: 1, strokeDasharray: '4 4' }}
                                    />
                                    <ReferenceLine y={0} stroke="#6b7280" strokeDasharray="3 3" />
                                    <Area
                                        type="monotone"
                                        dataKey="value"
                                        name="Basket Return"
                                        stroke="#3b82f6"
                                        strokeWidth={2}
                                        fillOpacity={1}
                                        fill="url(#colorPnl)"
                                    />
                                </AreaChart>
                            </ResponsiveContainer>
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="correlation" className="animate-in fade-in duration-300">
                    <Card className="bg-[#1a1a24] border-gray-800">
                        <CardHeader className="pb-2">
                            <CardTitle className="text-gray-200 text-lg">7-Day Rolling Correlations (Anchor vs Portfolio)</CardTitle>
                        </CardHeader>
                        <CardContent className="h-[300px]">
                            <ResponsiveContainer width="100%" height="100%">
                                <LineChart data={rollingCorrData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                                    <XAxis dataKey="date" stroke="#6b7280" style={{ fontSize: '12px' }} />
                                    <YAxis domain={[-1, 1]} stroke="#6b7280" style={{ fontSize: '12px' }} />
                                    <Tooltip
                                        contentStyle={{ backgroundColor: '#0f0f13', borderColor: '#333', color: '#fff' }}
                                    />
                                    <ReferenceLine y={0} stroke="#666" />
                                    {data.portfolio.slice(0, 5).map((item, i) => (
                                        <Line
                                            key={item.token_id}
                                            type="monotone"
                                            dataKey={item.token_id}
                                            name={item.question.substring(0, 15) + '...'}
                                            stroke={portfolioColors[i % portfolioColors.length]}
                                            dot={false}
                                            strokeWidth={1.5}
                                        />
                                    ))}
                                    <Legend />
                                </LineChart>
                            </ResponsiveContainer>
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="anchor" className="animate-in fade-in duration-300">
                    <Card className="bg-[#1a1a24] border-gray-800">
                        <CardHeader className="pb-2">
                            <CardTitle className="text-gray-200 text-lg">Anchor Market Price History</CardTitle>
                        </CardHeader>
                        <CardContent className="h-[300px]">
                            <ResponsiveContainer width="100%" height="100%">
                                <LineChart data={anchorPriceData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                                    <XAxis dataKey="date" stroke="#6b7280" style={{ fontSize: '12px' }} />
                                    <YAxis domain={[0, 100]} stroke="#6b7280" style={{ fontSize: '12px' }} unit="¢" />
                                    <Tooltip
                                        contentStyle={{ backgroundColor: '#0f0f13', borderColor: '#333', color: '#fff' }}
                                    />
                                    <Line
                                        type="stepAfter"
                                        dataKey="price"
                                        name={`Price (${data.anchor?.token_choice || 'YES'})`}
                                        stroke="#10b981"
                                        strokeWidth={2}
                                        dot={false}
                                    />
                                </LineChart>
                            </ResponsiveContainer>
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    );
}

