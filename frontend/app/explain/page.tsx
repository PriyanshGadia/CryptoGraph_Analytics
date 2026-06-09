"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher, Asset, apiService, ExplainResponse } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { Badge } from "@/components/ui/Badge";
import { MessageSquare, Bot, AlertCircle } from "lucide-react";

export default function ExplainPage() {
  const { data: assets, isLoading: assetsLoading } = useSWR<Asset[]>("/api/assets", fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 30000,
  });
  const [selectedSymbol, setSelectedSymbol] = useState<string>("ETH");
  const [explanation, setExplanation] = useState<ExplainResponse | null>(null);
  const [isExplaining, setIsExplaining] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleExplain = async () => {
    if (!selectedSymbol) return;
    
    setIsExplaining(true);
    setError(null);
    try {
      const data = await apiService.getExplain(selectedSymbol);
      setExplanation(data);
    } catch (err: any) {
      setError(err.message || "Failed to generate explanation");
    } finally {
      setIsExplaining(false);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div>
        <h1 className="text-3xl font-bold text-text">Explain Predictions</h1>
        <p className="text-textMuted mt-1">Get LLM-generated rationale behind the model's forecasting</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Select Asset</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-4">
            <select
              value={selectedSymbol}
              onChange={(e) => setSelectedSymbol(e.target.value)}
              className="flex-1 bg-surface border border-border rounded-md px-4 py-2 text-text focus:outline-none focus:ring-2 focus:ring-accent"
              disabled={assetsLoading || isExplaining}
            >
              {assetsLoading ? (
                <option>Loading assets...</option>
              ) : (
                assets?.map((asset) => (
                  <option key={asset.id} value={asset.symbol}>
                    {asset.symbol} - {asset.name}
                  </option>
                ))
              )}
            </select>
            <button
              onClick={handleExplain}
              disabled={!selectedSymbol || isExplaining || assetsLoading}
              className="bg-accent hover:bg-accent/80 text-white px-6 py-2 rounded-md font-semibold flex items-center gap-2 disabled:opacity-50 transition-colors"
            >
              <Bot size={20} />
              {isExplaining ? "Analyzing..." : "Explain"}
            </button>
          </div>
        </CardContent>
      </Card>

      {error && (
        <div className="bg-danger/10 border border-danger/20 text-danger p-4 rounded-md flex items-center gap-3">
          <AlertCircle size={20} />
          {error}
        </div>
      )}

      {isExplaining && (
        <Card>
          <CardContent className="pt-6">
            <div className="space-y-3">
              <Skeleton className="h-6 w-1/3" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
            </div>
          </CardContent>
        </Card>
      )}

      {explanation && !isExplaining && (
        <Card className="border-accent/30 shadow-[0_0_15px_rgba(99,102,241,0.1)]">
          <CardHeader className="border-b border-border bg-surface/50 pb-4">
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2 text-xl">
                <MessageSquare className="text-accent" />
                Analysis for {explanation.symbol}
              </CardTitle>
              <Badge variant={explanation.direction.toLowerCase() === 'up' ? 'success' : 'destructive'}>
                {explanation.direction.toUpperCase()}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            <div className="prose prose-invert max-w-none">
              {explanation.explanation.split('\n').map((paragraph, i) => (
                <p key={i} className="text-text/90 leading-relaxed mb-4 last:mb-0">
                  {paragraph}
                </p>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
