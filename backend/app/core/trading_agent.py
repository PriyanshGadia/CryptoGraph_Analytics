"""
Autonomous Paper-Trading Execution Agent.
Reads latest ST-GCN predictions and manages a virtual portfolio based on signals.
"""

from datetime import datetime, timezone
import asyncio
import threading
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db.database import SessionLocal
from app.db.models_sqla import Asset, Prediction, PortfolioState, TradeHistory, OHLCV, TradeDebate
from app.core.agents.analysts import MacroEconomistAgent, OnChainDetectiveAgent, SentimentAnalystAgent
from app.core.agents.cio import ChiefInvestmentOfficerAgent
from app.core.risk_manager import RiskManagerCore
import numpy as np
from app.core.smart_order_router import SmartOrderRouter
from app.core.proof_of_performance import generate_daily_proof
from app.core.multi_oracle_consensus import MultiOracleConsensus

_oracle = MultiOracleConsensus(deviation_threshold_pct=0.5)
_TRADING_LOCK = threading.Lock()


def get_asset_dynamic_risk_thresholds(db: Session, asset_id: int) -> tuple[float, float, float]:
    """
    Calculates dynamic stop-loss, take-profit, and conviction thresholds per asset
    scaled by rolling 7-day log volatility.
    Returns: (stop_loss_pct, take_profit_pct, min_conviction_threshold)
    """
    recent = db.query(OHLCV).filter(OHLCV.asset_id == asset_id).order_by(desc(OHLCV.timestamp)).limit(14).all()
    if len(recent) >= 3:
        closes = [r.close for r in recent if r.close]
        returns = np.diff(np.log(closes)) if len(closes) >= 2 else np.array([0.03])
        vol_7d = float(np.std(returns)) if len(returns) > 0 else 0.03
    else:
        vol_7d = 0.03

    # Dynamic stop loss: -1.5 * daily vol scaled to week, clamped between -4.0% and -12.0%
    stop_loss = -max(0.04, min(0.12, vol_7d * np.sqrt(7) * 1.5))
    # Dynamic take profit: 2:1 reward-to-risk ratio relative to stop loss, clamped between +8.0% and +24.0%
    take_profit = max(0.08, min(0.24, abs(stop_loss) * 2.0))
    # Dynamic conviction threshold: adapts between 0.58 and 0.70 based on volatility
    min_conviction = max(0.58, min(0.70, 0.60 + vol_7d * 2.0))

    return stop_loss, take_profit, min_conviction

async def _run_swarm_evaluations(db: Session, signals: list):
    """Run the MoA swarm for a list of (asset, prediction) tuples."""
    macro_agent = MacroEconomistAgent(db)
    onchain_agent = OnChainDetectiveAgent(db)
    sentiment_agent = SentimentAnalystAgent(db)
    cio = ChiefInvestmentOfficerAgent(db)
    
    results = {}
    for asset, pred in signals:
        print(f"[Swarm] Analyzing {asset.symbol}...")
        mac, onc, sen = await asyncio.gather(
            macro_agent.analyze(asset.symbol),
            onchain_agent.analyze(asset.symbol),
            sentiment_agent.analyze(asset.symbol)
        )
        
        pred_dict = {
            "direction": pred.direction,
            "confidence": pred.confidence
        }
        
        verdict = await cio.analyze(asset.symbol, pred_dict, mac, onc, sen)
        results[asset.symbol] = {
            "macro": mac,
            "onchain": onc,
            "sentiment": sen,
            "decision": verdict["decision"],
            "reasoning": verdict["reasoning"]
        }
        
        # Save the debate
        debate = TradeDebate(
            symbol=asset.symbol,
            stgcn_direction=pred.direction,
            stgcn_confidence=pred.confidence,
            macro_analysis=mac,
            onchain_analysis=onc,
            sentiment_analysis=sen,
            cio_decision=verdict["decision"],
            cio_reasoning=verdict["reasoning"]
        )
        db.add(debate)
        db.commit()
        
    return results

async def execute_daily_trades():
    """
    Cron-job function:
    1. Fetches the latest ST-GCN predictions.
    2. Runs the Mixture-of-Agents swarm to debate the trade.
    3. Executes paper trades based on the CIO's decision.
    4. Updates PortfolioState.
    Protected against concurrent execution by a non-blocking re-entrancy lock.
    """
    if not _TRADING_LOCK.acquire(blocking=False):
        print("[TradingAgent] Trade execution cycle already in progress. Skipping concurrent run.")
        return {"status": "skipped", "reason": "Trade execution cycle already in progress"}

    try:
        return await _execute_daily_trades_core()
    finally:
        _TRADING_LOCK.release()


def run_autonomous_trading_cycle():
    """
    Synchronous entry point for trade execution cycles.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return asyncio.run_coroutine_threadsafe(execute_daily_trades(), loop).result(timeout=120)
        else:
            return asyncio.run(execute_daily_trades())
    except Exception as e:
        print(f"[TradingAgent] Direct execution error: {e}")
        return asyncio.run(execute_daily_trades())


async def _execute_daily_trades_core():
    db: Session = SessionLocal()
    try:
        # Get current portfolio state
        portfolio = db.query(PortfolioState).order_by(desc(PortfolioState.timestamp)).first()
        if not portfolio:
            # Initialize portfolio with $100,000 USD
            portfolio = PortfolioState(
                cash_balance=100000.0,
                holdings_value=0.0,
                total_value=100000.0,
                btc_benchmark_value=100000.0
            )
            db.add(portfolio)
            db.commit()
            db.refresh(portfolio)

        assets = db.query(Asset).all()
        
        # Calculate current active holdings via SQL aggregation
        from sqlalchemy import func
        holdings = {}
        trade_summary = db.query(
            TradeHistory.symbol,
            TradeHistory.side,
            func.sum(TradeHistory.quantity).label("total_qty"),
            func.sum(TradeHistory.total_usd).label("total_usd")
        ).group_by(TradeHistory.symbol, TradeHistory.side).all()

        for symbol, side, qty, usd in trade_summary:
            if symbol not in holdings:
                holdings[symbol] = {"qty": 0.0, "avg_price": 0.0, "total_invested": 0.0}
            if side == "buy":
                holdings[symbol]["qty"] += (qty or 0.0)
                holdings[symbol]["total_invested"] += (usd or 0.0)
            elif side == "sell":
                holdings[symbol]["qty"] -= (qty or 0.0)
                holdings[symbol]["total_invested"] -= (usd or 0.0)

        for sym, data in holdings.items():
            if data["qty"] > 1e-8:
                data["avg_price"] = max(0.0, data["total_invested"] / data["qty"])
            else:
                data["qty"] = 0.0
                data["avg_price"] = 0.0
                data["total_invested"] = 0.0

        # Process new signals
        total_cash = portfolio.cash_balance
        new_trades = []
        sor = SmartOrderRouter()

        # ── AUTOMATED DYNAMIC RISK CIRCUIT BREAKER (Volatility-Adapted Stop-Loss & Take-Profit) ──
        for asset in assets:
            h = holdings.get(asset.symbol, {})
            qty_held = h.get("qty", 0.0)
            total_invested = h.get("total_invested", 0.0)
            if qty_held > 0 and total_invested > 0:
                latest_p = db.query(OHLCV).filter(OHLCV.asset_id == asset.id).order_by(desc(OHLCV.timestamp)).first()
                if latest_p and latest_p.close:
                    curr_val = qty_held * latest_p.close
                    pnl_pct = (curr_val - total_invested) / total_invested
                    
                    stop_loss_pct, take_profit_pct, _ = get_asset_dynamic_risk_thresholds(db, asset.id)
                    
                    circuit_triggered = None
                    if pnl_pct <= stop_loss_pct:
                        circuit_triggered = f"AUTOMATED DYNAMIC STOP-LOSS CIRCUIT BREAKER: Trailing drawdown ({pnl_pct*100:.1f}%) reached dynamic threshold ({stop_loss_pct*100:.1f}%)."
                    elif pnl_pct >= take_profit_pct:
                        circuit_triggered = f"AUTOMATED DYNAMIC TAKE-PROFIT CIRCUIT BREAKER: Profit gain (+{pnl_pct*100:.1f}%) reached dynamic target (+{take_profit_pct*100:.1f}%)."
                        
                    if circuit_triggered:
                        route = sor.calculate_best_route(asset.symbol, "sell", curr_val, latest_p.close)
                        avg_fill = route["average_fill_price"]
                        gross_val = qty_held * avg_fill
                        net_val = gross_val * (1.0 - route["slippage_pct"])
                        realized_pnl = net_val - total_invested
                        
                        import uuid
                        sim_id = f"SIM-{uuid.uuid4().hex[:8].upper()}"
                        
                        sl_trade = TradeHistory(
                            symbol=asset.symbol,
                            side="sell",
                            quantity=qty_held,
                            price=avg_fill,
                            total_usd=net_val,
                            pnl=realized_pnl,
                            reason=f"{circuit_triggered} | SIMULATED PAPER TRADE using live {route['exchange']} order book data. | Simulation ID: {sim_id}",
                            confidence=None,  # Deterministic circuit breaker, not a model prediction — kept out of calibration stats.
                            status="EXECUTED"
                        )
                        new_trades.append(sl_trade)
                        total_cash += net_val
                        holdings[asset.symbol] = {"qty": 0.0, "avg_price": 0.0, "total_invested": 0.0}
                        print(f"[TradingAgent] {circuit_triggered} Sold {asset.symbol} for ${net_val:,.2f} (Realized PnL: ${realized_pnl:,.2f})")

        # Collect and prioritize actionable signals (all active holdings + top 5 highest edge predictions)
        candidate_signals = []
        for asset in assets:
            pred = db.query(Prediction).filter(Prediction.asset_id == asset.id).order_by(desc(Prediction.predicted_at)).first()
            if not pred:
                continue
            qty_held = holdings.get(asset.symbol, {}).get("qty", 0.0)
            candidate_signals.append((asset, pred, qty_held))

        held_signals = [(asset, pred) for asset, pred, qty in candidate_signals if qty > 0]
        high_conviction_unheld = []
        for asset, pred, qty in candidate_signals:
            if qty == 0:
                _, _, min_conviction = get_asset_dynamic_risk_thresholds(db, asset.id)
                if pred.direction in ["up", "strong_up"] and pred.confidence >= min_conviction:
                    high_conviction_unheld.append((asset, pred))
                    
        high_conviction_unheld.sort(key=lambda x: x[1].confidence, reverse=True)
        signals_to_evaluate = held_signals + high_conviction_unheld[:5]

        if not signals_to_evaluate:
            print("[TradingAgent] No high-conviction trade opportunities detected meeting dynamic threshold criteria. Portfolio remaining in HOLD state.")
            return new_trades

        # Run Swarm
        swarm_decisions = await _run_swarm_evaluations(db, signals_to_evaluate)

        risk_manager = RiskManagerCore(db)
        sor = SmartOrderRouter()

        # Execute Trades based on CIO
        for asset, pred in signals_to_evaluate:
            verdict = swarm_decisions.get(asset.symbol)
            if not verdict:
                continue
                
            cio_decision = verdict["decision"]
            
            latest_price_record = db.query(OHLCV).filter(OHLCV.asset_id == asset.id).order_by(desc(OHLCV.timestamp)).first()
            if not latest_price_record:
                continue
            
            current_price = latest_price_record.close
            qty_held = holdings.get(asset.symbol, {}).get("qty", 0.0)
            
            # Risk Management Interception with Dynamic Baseline Edge Validation
            baseline_prob = getattr(pred, 'baseline_probability', 0.3333) or 0.3333
            risk_assessment = risk_manager.evaluate_trade(
                asset.symbol, cio_decision, pred.confidence, portfolio, baseline_prob=baseline_prob
            )
            if not risk_assessment["approved"]:
                print(f"[TradingAgent] {risk_assessment['reasoning']}")
                continue

            # Multi-Oracle Consensus Price Validation
            if not _oracle.validate_price(asset.symbol, current_price):
                print(f"[TradingAgent] Multi-Oracle Consensus REJECTED trade for {asset.symbol} — price validation failed. Skipping.")
                continue

            # Trading Logic
            if cio_decision == "EXECUTE_BUY":
                # BUY Signal: Use Risk Manager's suggested allocation
                allocation_target = risk_assessment["suggested_allocation_usd"]
                if total_cash >= allocation_target and allocation_target > 0:
                    
                    # Web3 Smart Order Routing
                    route = sor.calculate_best_route(asset.symbol, "buy", allocation_target, current_price)
                    avg_fill_price = route["average_fill_price"]
                    exchange_used = route["exchange"]
                    
                    fee_and_slippage = allocation_target * route["slippage_pct"]
                    actual_investment = allocation_target - fee_and_slippage
                    qty_to_buy = actual_investment / avg_fill_price
                    
                    import uuid
                    sim_id = f"SIM-{uuid.uuid4().hex[:8].upper()}"
                    
                    new_trades.append(TradeHistory(
                        symbol=asset.symbol,
                        side="buy",
                        quantity=qty_to_buy,
                        price=avg_fill_price,
                        total_usd=allocation_target, # Total deducted from cash
                        reason=f"CIO Verdict: {verdict['reasoning'][:150]}... | SIMULATED PAPER TRADE using live {exchange_used} order book data. | Simulation ID: {sim_id}",
                        confidence=pred.confidence,
                        status="EXECUTED"
                    ))
                    total_cash -= allocation_target
                    
            elif cio_decision == "EXECUTE_SELL" and qty_held > 0:
                # SELL Signal: Liquidate position via SOR and calculate realized PnL
                route = sor.calculate_best_route(asset.symbol, "sell", qty_held * current_price, current_price)
                avg_fill_price = route["average_fill_price"]
                exchange_used = route["exchange"]
                
                gross_sell_value = qty_held * avg_fill_price
                fee_and_slippage = gross_sell_value * route["slippage_pct"]
                net_sell_value = gross_sell_value - fee_and_slippage
                
                total_invested = holdings.get(asset.symbol, {}).get("total_invested", 0.0)
                realized_pnl = net_sell_value - total_invested
                
                import uuid
                sim_id = f"SIM-{uuid.uuid4().hex[:8].upper()}"
                
                new_trades.append(TradeHistory(
                    symbol=asset.symbol,
                    side="sell",
                    quantity=qty_held,
                    price=avg_fill_price,
                    total_usd=net_sell_value, # Total added to cash
                    pnl=realized_pnl,
                    reason=f"CIO Verdict: {verdict['reasoning'][:150]}... | SIMULATED PAPER TRADE using live {exchange_used} order book data. | Simulation ID: {sim_id}",
                    confidence=pred.confidence,
                    status="EXECUTED"
                ))
                total_cash += net_sell_value
                
        # Commit new trades
        if new_trades:
            for t in new_trades:
                db.add(t)
            db.commit()
            
        # Re-calculate holdings value based on latest prices
        new_holdings_value = 0.0
        # Re-run holdings accumulation with new trades
        for t in new_trades:
            if t.symbol not in holdings:
                holdings[t.symbol] = {"qty": 0.0}
            if t.side == "buy":
                holdings[t.symbol]["qty"] += t.quantity
            else:
                holdings[t.symbol]["qty"] -= t.quantity
                
        # Value the current holdings
        for sym, data in holdings.items():
            if data["qty"] > 0:
                # find asset by symbol
                a = next((x for x in assets if x.symbol == sym), None)
                if a:
                    latest = db.query(OHLCV).filter(OHLCV.asset_id == a.id).order_by(desc(OHLCV.timestamp)).first()
                    if latest:
                        new_holdings_value += data["qty"] * latest.close

        # Update Portfolio Benchmark (BTC)
        btc = next((x for x in assets if x.symbol == "BTC"), None)
        btc_price = 1.0
        if btc:
            btc_latest = db.query(OHLCV).filter(OHLCV.asset_id == btc.id).order_by(desc(OHLCV.timestamp)).first()
            if btc_latest:
                btc_price = btc_latest.close
                
        # Simple benchmark calculation: assume we bought 100k of BTC at epoch
        # For a true benchmark, we'd store the BTC price when the portfolio was initialized.
        # Let's just track it from the previous state relative change.
        # Simple benchmark calculation: assume we bought 100k of BTC at epoch
        old_btc_price = 1.0
        if btc and portfolio.btc_benchmark_value > 0:
            from datetime import timedelta
            yesterday = datetime.now(timezone.utc) - timedelta(days=1)
            btc_old_record = db.query(OHLCV).filter(
                OHLCV.asset_id == btc.id,
                OHLCV.timestamp <= yesterday
            ).order_by(desc(OHLCV.timestamp)).first()
            
            if btc_old_record and btc_old_record.close > 0:
                old_btc_price = btc_old_record.close
                btc_return = (btc_price - old_btc_price) / old_btc_price
                new_benchmark = portfolio.btc_benchmark_value * (1 + btc_return)
            else:
                new_benchmark = portfolio.btc_benchmark_value
        else:
            new_benchmark = 100000.0

        # Save new portfolio state
        new_state = PortfolioState(
            cash_balance=total_cash,
            holdings_value=new_holdings_value,
            total_value=total_cash + new_holdings_value,
            btc_benchmark_value=new_benchmark
        )
        db.add(new_state)
        db.commit()
        db.refresh(new_state)
        
        # Phase 5: Generate Cryptographic Proof of Performance
        generate_daily_proof(db, new_state.id)
        
        print(f"[TradingAgent] Execution complete. New Total Value: ${new_state.total_value:,.2f}")
        
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(execute_daily_trades())
