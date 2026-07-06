"""
Autonomous Paper-Trading Execution Agent.
Reads latest ST-GCN predictions and manages a virtual portfolio based on signals.
"""

from datetime import datetime, timezone
import asyncio
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db.database import SessionLocal
from app.db.models_sqla import Asset, Prediction, PortfolioState, TradeHistory, OHLCV, TradeDebate
from app.core.agents.analysts import MacroEconomistAgent, OnChainDetectiveAgent, SentimentAnalystAgent
from app.core.agents.cio import ChiefInvestmentOfficerAgent
from app.core.risk_manager import RiskManagerCore
from app.core.smart_order_router import SmartOrderRouter
from app.core.proof_of_performance import generate_daily_proof

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
    """
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

        # ── AUTOMATED RISK CIRCUIT BREAKER (Stop-Loss -6.0% & Take-Profit +12.0%) ──
        for asset in assets:
            h = holdings.get(asset.symbol, {})
            qty_held = h.get("qty", 0.0)
            total_invested = h.get("total_invested", 0.0)
            if qty_held > 0 and total_invested > 0:
                latest_p = db.query(OHLCV).filter(OHLCV.asset_id == asset.id).order_by(desc(OHLCV.timestamp)).first()
                if latest_p and latest_p.close:
                    curr_val = qty_held * latest_p.close
                    pnl_pct = (curr_val - total_invested) / total_invested
                    
                    circuit_triggered = None
                    if pnl_pct <= -0.06:
                        circuit_triggered = f"AUTOMATED STOP-LOSS CIRCUIT BREAKER: Trailing drawdown ({pnl_pct*100:.1f}%) reached threshold (-6.0%)."
                    elif pnl_pct >= 0.12:
                        circuit_triggered = f"AUTOMATED TAKE-PROFIT CIRCUIT BREAKER: Profit gain (+{pnl_pct*100:.1f}%) reached target (+12.0%)."
                        
                    if circuit_triggered:
                        route = sor.calculate_best_route(asset.symbol, "sell", curr_val, latest_p.close)
                        avg_fill = route["average_fill_price"]
                        gross_val = qty_held * avg_fill
                        net_val = gross_val * (1.0 - route["slippage_pct"])
                        realized_pnl = net_val - total_invested
                        
                        import uuid
                        t_ref = f"REF-{uuid.uuid4().hex[:12].upper()}"
                        
                        sl_trade = TradeHistory(
                            symbol=asset.symbol,
                            side="sell",
                            quantity=qty_held,
                            price=avg_fill,
                            total_usd=net_val,
                            pnl=realized_pnl,
                            reason=f"{circuit_triggered} | SIMULATED PAPER TRADE using live {route['exchange']} order book data. | Simulation ID: {t_ref}",
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
                c_norm = pred.confidence / 100.0 if pred.confidence > 1.0 else pred.confidence
                if pred.direction in ["up", "strong_up"] and c_norm >= 0.62:
                    high_conviction_unheld.append((asset, pred))
                    
        high_conviction_unheld.sort(key=lambda x: (x[1].confidence if x[1].confidence > 1.0 else x[1].confidence * 100.0), reverse=True)
        signals_to_evaluate = held_signals + high_conviction_unheld[:5]

        if not signals_to_evaluate:
            print("[TradingAgent] No high-conviction trade opportunities detected (confidence >= 62%). Portfolio remaining in HOLD state.")
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
            
            # Risk Management Interception
            risk_assessment = risk_manager.evaluate_trade(asset.symbol, cio_decision, pred.confidence, portfolio)
            if not risk_assessment["approved"]:
                print(f"[TradingAgent] {risk_assessment['reasoning']}")
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
                    trade_ref = f"REF-{uuid.uuid4().hex[:12].upper()}"
                    
                    new_trades.append(TradeHistory(
                        symbol=asset.symbol,
                        side="buy",
                        quantity=qty_to_buy,
                        price=avg_fill_price,
                        total_usd=allocation_target, # Total deducted from cash
                        reason=f"CIO Verdict: {verdict['reasoning'][:150]}... | SIMULATED PAPER TRADE using live {exchange_used} order book data. | Simulation ID: {trade_ref}",
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
                trade_ref = f"REF-{uuid.uuid4().hex[:12].upper()}"
                
                new_trades.append(TradeHistory(
                    symbol=asset.symbol,
                    side="sell",
                    quantity=qty_held,
                    price=avg_fill_price,
                    total_usd=net_sell_value, # Total added to cash
                    pnl=realized_pnl,
                    reason=f"CIO Verdict: {verdict['reasoning'][:150]}... | SIMULATED PAPER TRADE using live {exchange_used} order book data. | Simulation ID: {trade_ref}",
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
        old_btc_price = 1.0
        if btc and portfolio.btc_benchmark_value > 0:
            # Not perfectly accurate without tracking the exact BTC price at init, but works for a rolling benchmark
            # A better way is to see what BTC returned today and apply it.
            btc_old_record = db.query(OHLCV).filter(OHLCV.asset_id == btc.id).order_by(desc(OHLCV.timestamp)).offset(1).first()
            if btc_old_record:
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
