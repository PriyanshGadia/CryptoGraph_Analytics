import { Asset } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/Card";
import { Badge } from "./ui/Badge";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

export function PredictionCard({ asset }: { asset: Asset }) {
  const direction = asset.predicted_direction?.toLowerCase() ?? "neutral";
  const isUp = direction === "up" || direction === "strong_up";
  const isDown = direction === "down" || direction === "strong_down";
  const price = asset.current_price;
  const change = asset.price_change_24h_pct;
  const confidence = asset.confidence;

  return (
    <Card className="hover:border-accent transition-colors duration-300">
      <CardHeader className="pb-2">
        <div className="flex justify-between items-start">
          <div>
            <CardTitle className="text-xl flex items-center gap-2">
              {asset.symbol}
              <span className="text-sm font-normal text-textMuted">{asset.name}</span>
            </CardTitle>
            <div className="text-sm text-textMuted mt-1">{asset.sector || "—"}</div>
          </div>
          <div className="text-right">
            <div className="font-mono text-lg">
              {price != null
                ? `$${price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 6 })}`
                : "—"}
            </div>
            <div className={`text-sm flex items-center justify-end ${change != null && change >= 0 ? "text-success" : "text-danger"}`}>
              {change != null ? (
                <>
                  {change >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                  {Math.abs(change).toFixed(2)}%
                </>
              ) : (
                <span className="text-textMuted">—</span>
              )}
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="mt-4 p-3 bg-background rounded-lg border border-border flex justify-between items-center">
          <div>
            <div className="text-xs text-textMuted uppercase tracking-wider font-bold mb-1">Prediction</div>
            <Badge variant={isUp ? "success" : isDown ? "destructive" : "secondary"}>
              {asset.predicted_direction?.toUpperCase() ?? "PENDING"}
            </Badge>
          </div>
          <div className="text-right">
            <div className="text-xs text-textMuted uppercase tracking-wider font-bold mb-1">Confidence</div>
            <div className="font-mono text-accent">
              {confidence != null ? `${(confidence * 100).toFixed(1)}%` : "—"}
            </div>
          </div>
        </div>
        <div className="mt-4 text-right">
          <span className="text-xs text-indigo-400 font-medium">View Details →</span>
        </div>
      </CardContent>
    </Card>
  );
}
