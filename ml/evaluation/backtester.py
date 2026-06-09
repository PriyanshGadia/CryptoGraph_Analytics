import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from ml.evaluation.finance_metrics import compute_all_finance_metrics

class Backtester:
    """Simulates a long-only trading strategy driven by model predictions."""

    def __init__(self, starting_capital: float = 10_000.0):
        self.starting_capital = starting_capital
        self.transaction_cost = 0.001  # 0.1%
        self.equity_curve = None
        self.benchmark_curve = None

    def run(
        self,
        predictions: pd.DataFrame,
        actual_returns: pd.DataFrame
    ) -> dict:
        """
        predictions columns: date, symbol, direction, confidence
        actual_returns: DataFrame with date index, symbol columns, daily return values

        Strategy per day:
          signals = rows where direction in ["up","strong_up"] AND confidence > 0.65
          If no signals: hold cash
          If signals: allocate equal capital across all signal assets
            Buy: deduct transaction_cost (0.1%) from allocation
            Next day: apply actual return to that allocation
            Sell: deduct transaction_cost (0.1%)

        Benchmark: BTC buy-and-hold from same start date
        """
        dates = sorted(predictions['date'].unique())
        
        portfolio_value = self.starting_capital
        btc_value = self.starting_capital
        
        equity_series = []
        benchmark_series = []
        
        # Track daily percentage return of portfolio
        port_returns = []
        
        for i in range(len(dates) - 1):
            today = dates[i]
            tomorrow = dates[i + 1]
            
            # Record start of day values
            equity_series.append(portfolio_value)
            benchmark_series.append(btc_value)
            
            # --- Strategy ---
            # Get today's signals to hold overnight into tomorrow
            day_preds = predictions[predictions['date'] == today]
            signals = day_preds[
                (day_preds['direction'].isin(["up", "strong_up"])) & 
                (day_preds['confidence'] > 0.65)
            ]
            
            if len(signals) == 0:
                # Hold cash, no return, no cost
                port_returns.append(0.0)
            else:
                allocation_per_asset = portfolio_value / len(signals)
                daily_total = 0.0
                
                for _, row in signals.iterrows():
                    sym = row['symbol']
                    # Get actual return for tomorrow
                    # If missing, assume 0
                    if tomorrow in actual_returns.index and sym in actual_returns.columns:
                        ret = actual_returns.loc[tomorrow, sym]
                        if pd.isna(ret):
                            ret = 0.0
                    else:
                        ret = 0.0
                        
                    # Calculate value after buy cost, return, and sell cost
                    capital_after_buy = allocation_per_asset * (1 - self.transaction_cost)
                    capital_after_return = capital_after_buy * (1 + ret)
                    capital_after_sell = capital_after_return * (1 - self.transaction_cost)
                    
                    daily_total += capital_after_sell
                    
                prev_value = portfolio_value
                portfolio_value = daily_total
                port_returns.append((portfolio_value - prev_value) / prev_value)
                
            # --- Benchmark ---
            if tomorrow in actual_returns.index and 'BTC' in actual_returns.columns:
                btc_ret = actual_returns.loc[tomorrow, 'BTC']
                if pd.isna(btc_ret):
                    btc_ret = 0.0
            else:
                btc_ret = 0.0
                
            btc_value = btc_value * (1 + btc_ret)
            
        # Add final day
        equity_series.append(portfolio_value)
        benchmark_series.append(btc_value)
        port_returns.append(0.0) # No return on last day since we don't know the next day
        
        self.equity_curve = pd.Series(equity_series, index=dates)
        self.benchmark_curve = pd.Series(benchmark_series, index=dates)
        daily_returns_series = pd.Series(port_returns, index=dates)
        
        metrics = compute_all_finance_metrics(daily_returns_series)
        
        comparison_df = pd.DataFrame({
            "Strategy": self.equity_curve,
            "Benchmark (BTC)": self.benchmark_curve
        })
        
        results = {
            "equity_curve": self.equity_curve,
            "benchmark_curve": self.benchmark_curve,
            "daily_returns": daily_returns_series,
            "comparison_table": comparison_df
        }
        results.update(metrics)
        return results

    def plot_results(self, output_path: str = "ml/artifacts/backtest_results.png") -> None:
        """
        Saves matplotlib figure comparing equity_curve vs benchmark_curve.
        Include: title, axis labels, legend, grid.
        """
        if self.equity_curve is None or self.benchmark_curve is None:
            print("Run backtest first before plotting.")
            return
            
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
        plt.figure(figsize=(12, 6))
        plt.plot(self.equity_curve.index, self.equity_curve.values, label="ST-GCN Strategy", color='blue', linewidth=2)
        plt.plot(self.benchmark_curve.index, self.benchmark_curve.values, label="Benchmark (BTC)", color='orange', alpha=0.8)
        
        plt.title("Backtest Results: ST-GCN Strategy vs BTC Buy & Hold")
        plt.xlabel("Date")
        plt.ylabel("Portfolio Value ($)")
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(output_path)
        plt.close()
