import { useState, useMemo } from 'react';
import { RecommendationResponse } from '@/services/polymarket';
import { Card, CardContent, CardHeader, CardTitle } from '@/app/components/ui/card';
import { Slider } from '@/app/components/ui/slider';

interface ScenarioSimulatorProps {
    data: RecommendationResponse;
}

export function ScenarioSimulator({ data }: ScenarioSimulatorProps) {
    // Current price of the anchor market from the most recent data point
    const initialPrice = useMemo(() => {
        if (!data.timeseries?.price_series?.anchor) return 50;
        const series = data.timeseries.price_series.anchor;
        return series[series.length - 1]?.value * 100 || 50;
    }, [data]);

    const [simulatedPrice, setSimulatedPrice] = useState(initialPrice);

    // Calculate simulated P&L for each asset
    // Logic: Delta_Candidate approx = Correlation * Delta_Anchor
    const simulationResults = useMemo(() => {
        const deltaPct = (simulatedPrice - initialPrice) / 100; // e.g. +0.10

        return data.portfolio.map(item => {
            // Correlation assumption: P_candidate moves by Correlation * Delta_P_anchor
            // Note: This is a linear approximation and purely illustrative
            const simulatedMove = item.correlation * deltaPct;

            // If action is BUY NO, we profit if price goes DOWN. But correlation is to YES price.
            // If correlation is positive (item moves WITH anchor):
            //   Anchor UP -> Item UP -> BUY YES gains, BUY NO loses.
            // If correlation is negative (item moves AGAINST anchor):
            //   Anchor UP -> Item DOWN -> BUY YES loses, BUY NO gains.

            // Simplified P&L calculation based on direction
            let estimatedPnL = 0;
            if (item.action === 'BUY_YES') {
                estimatedPnL = simulatedMove;
            } else {
                // SHORT YES (BUY NO)
                estimatedPnL = -simulatedMove;
            }

            return {
                ...item,
                estimatedPnL: estimatedPnL * 100 // convert to %
            };
        });

    }, [data, initialPrice, simulatedPrice]);

    const totalPortfolioPnL = useMemo(() => {
        return simulationResults.reduce((acc, item) => acc + (item.estimatedPnL * item.weight), 0);
    }, [simulationResults]);

    return (
        <Card className="bg-[#1a1a24] border-gray-800">
            <CardHeader>
                <CardTitle className="text-gray-200">Scenario Simulator</CardTitle>
                <p className="text-sm text-gray-500">
                    Estimate portfolio impact if the Anchor market moves.
                </p>
            </CardHeader>
            <CardContent>
                <div className="space-y-8">
                    {/* Slider Section */}
                    <div className="space-y-4">
                        <div className="flex justify-between text-sm">
                            <span className="text-gray-400">Anchor Price: {data.anchor.question}</span>
                            <span className="font-bold text-white">{simulatedPrice.toFixed(1)}¢</span>
                        </div>
                        <Slider
                            defaultValue={[initialPrice]}
                            value={[simulatedPrice]}
                            min={1}
                            max={99}
                            step={1}
                            onValueChange={(vals: number[]) => setSimulatedPrice(vals[0])}
                            className="py-4"
                        />
                        <div className="flex justify-between text-xs text-gray-600">
                            <span>0¢</span>
                            <span className="text-blue-500 font-semibold">Current: {initialPrice.toFixed(1)}¢</span>
                            <span>100¢</span>
                        </div>
                    </div>

                    {/* Results Section */}
                    <div className="rounded-lg bg-[#0a0a0f] p-4 border border-gray-800">
                        <div className="flex justify-between items-center mb-4 border-b border-gray-800 pb-2">
                            <span className="text-gray-300">Est. Portfolio Impact</span>
                            <span className={`text-xl font-bold ${totalPortfolioPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                {totalPortfolioPnL > 0 ? '+' : ''}{totalPortfolioPnL.toFixed(2)}%
                            </span>
                        </div>

                        <div className="space-y-2 max-h-[200px] overflow-y-auto pr-2">
                            {simulationResults.map((item) => (
                                <div key={item.token_id} className="flex justify-between items-center text-sm">
                                    <span className="text-gray-500 truncate w-2/3" title={item.question}>{item.question}</span>
                                    <span className={item.estimatedPnL >= 0 ? 'text-green-500' : 'text-red-500'}>
                                        {item.estimatedPnL > 0 ? '+' : ''}{item.estimatedPnL.toFixed(1)}%
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
