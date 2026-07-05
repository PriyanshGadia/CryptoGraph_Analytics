"""FastAPI routes for Portfolio and Autonomous Trading."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db.database import get_db
from app.db.models_sqla import PortfolioState, TradeHistory, Asset, TradeDebate, OHLCV
from pydantic import BaseModel, Field
from app.core.trading_agent import execute_daily_trades
from app.core.auth import get_api_key
from typing import Dict, Any, List

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

@router.get("")
def get_portfolio_state(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get the current state of the autonomous trading portfolio with live mark-to-market valuation."""
    # Get all portfolio history for the equity curve
    history = db.query(PortfolioState).order_by(PortfolioState.timestamp.asc()).all()
    
    if not history:
        return {
            "cash_balance": 100000.0,
            "holdings_value": 0.0,
            "total_value": 100000.0,
            "initial_capital": 100000.0,
            "roi_pct": 0.0,
            "btc_benchmark_value": 100000.0,
            "btc_roi_pct": 0.0,
            "win_rate": 0.0,
            "total_trades": 0,
            "max_drawdown_pct": 0.0,
            "holdings": {},
            "equity_curve": []
        }
        
    current = history[-1]
    initial_capital = history[0].total_value
    
    # Trade statistics
    trades = db.query(TradeHistory).all()
    total_trades = len(trades)
    
    # Win rate calculation (based on closed positions / sell orders with positive PnL)
    sells = [t for t in trades if t.side == "sell"]
    winning_sells = [t for t in sells if getattr(t, 'pnl', 0.0) > 0]
    win_rate = (len(winning_sells) / len(sells)) * 100 if sells else 0.0
    
    # Calculate current holdings breakdown with live mark-to-market pricing
    holdings_dict = {}
    for t in trades:
        if t.symbol not in holdings_dict:
            holdings_dict[t.symbol] = {"qty": 0.0, "total_invested": 0.0}
            
        if t.side == "buy":
            holdings_dict[t.symbol]["qty"] += t.quantity
            holdings_dict[t.symbol]["total_invested"] += t.total_usd
        elif t.side == "sell":
            fraction_sold = t.quantity / holdings_dict[t.symbol]["qty"] if holdings_dict[t.symbol]["qty"] > 0 else 1.0
            holdings_dict[t.symbol]["qty"] -= t.quantity
            holdings_dict[t.symbol]["total_invested"] -= (holdings_dict[t.symbol]["total_invested"] * fraction_sold)
            
    # Compute dynamic mark-to-market value for active holdings
    active_holdings = {}
    live_holdings_value = 0.0
    for symbol, data in holdings_dict.items():
        if data["qty"] > 0.0001:
            asset = db.query(Asset).filter(Asset.symbol == symbol).first()
            current_price = 0.0
            if asset:
                latest_bar = db.query(OHLCV).filter(OHLCV.asset_id == asset.id).order_by(desc(OHLCV.timestamp)).first()
                if latest_bar:
                    current_price = latest_bar.close
            
            avg_price = max(0.0, data["total_invested"] / data["qty"])
            mkt_val = data["qty"] * current_price if current_price > 0 else data["total_invested"]
            unrealized_pnl = mkt_val - data["total_invested"]
            live_holdings_value += mkt_val
            
            active_holdings[symbol] = {
                "qty": data["qty"],
                "total_invested": data["total_invested"],
                "avg_price": avg_price,
                "current_price": current_price,
                "market_value": mkt_val,
                "unrealized_pnl": unrealized_pnl
            }

    # Total live portfolio valuation
    total_live_value = current.cash_balance + live_holdings_value
    roi_pct = ((total_live_value - initial_capital) / initial_capital) * 100
    btc_roi_pct = ((current.btc_benchmark_value - initial_capital) / initial_capital) * 100
    
    # Calculate Max Drawdown
    peak = initial_capital
    max_dd = 0.0
    equity_curve = []
    for state in history:
        if state.total_value > peak:
            peak = state.total_value
        dd = (peak - state.total_value) / peak
        if dd > max_dd:
            max_dd = dd
            
        equity_curve.append({
            "timestamp": state.timestamp.isoformat(),
            "portfolio": state.total_value,
            "btc_benchmark": state.btc_benchmark_value
        })
        
    # Append current live state if different from last recorded
    if equity_curve:
        equity_curve[-1]["portfolio"] = total_live_value
    
    return {
        "cash_balance": current.cash_balance,
        "holdings_value": live_holdings_value,
        "total_value": total_live_value,
        "initial_capital": initial_capital,
        "roi_pct": roi_pct,
        "btc_benchmark_value": current.btc_benchmark_value,
        "btc_roi_pct": btc_roi_pct,
        "win_rate": win_rate,
        "total_trades": total_trades,
        "max_drawdown_pct": max_dd * 100,
        "holdings": active_holdings,
        "equity_curve": equity_curve
    }

@router.get("/trades")
def get_portfolio_trades(limit: int = 100, offset: int = 0, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get trade history for the portfolio."""
    trades = db.query(TradeHistory).order_by(desc(TradeHistory.timestamp)).offset(offset).limit(limit).all()
    total = db.query(TradeHistory).count()
    
    trade_list = []
    for t in trades:
        debate = db.query(TradeDebate).filter(
            TradeDebate.symbol == t.symbol,
            TradeDebate.timestamp <= t.timestamp
        ).order_by(desc(TradeDebate.timestamp)).first()
        
        trade_list.append({
            "id": t.id,
            "timestamp": t.timestamp.isoformat() if t.timestamp else None,
            "symbol": t.symbol,
            "side": t.side,
            "quantity": t.quantity,
            "price": t.price,
            "total_usd": t.total_usd,
            "reason": t.reason,
            "confidence": t.confidence,
            "pnl": getattr(t, 'pnl', 0.0),
            "status": getattr(t, 'status', "EXECUTED"),
            "overseer_grade": getattr(t, 'overseer_grade', None),
            "overseer_notes": getattr(t, 'overseer_notes', None),
            "debate": {
                "macro_analysis": debate.macro_analysis if debate else None,
                "onchain_analysis": debate.onchain_analysis if debate else None,
                "sentiment_analysis": debate.sentiment_analysis if debate else None,
                "cio_reasoning": debate.cio_reasoning if debate else None
            } if debate else None
        })
        
    return {
        "trades": trade_list,
        "total": total
    }

class GradeTradeRequest(BaseModel):
    grade: int = Field(..., ge=1, le=5)
    notes: str = ""

@router.post("/trades/{trade_id}/grade")
def grade_trade(trade_id: int, payload: GradeTradeRequest, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    """Assign an RLHF grade to a trade."""
    trade = db.query(TradeHistory).filter(TradeHistory.id == trade_id).first()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
        
    trade.overseer_grade = payload.grade
    trade.overseer_notes = payload.notes
    db.commit()
    return {"status": "success"}

class ConfirmTradeRequest(BaseModel):
    tx_hash: str

@router.post("/trades/{trade_id}/confirm")
def confirm_web3_trade(trade_id: int, payload: ConfirmTradeRequest, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    """Confirm a PENDING trade has been executed via simulated routing."""
    trade = db.query(TradeHistory).filter(TradeHistory.id == trade_id).first()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
        
    trade.status = "EXECUTED"
    trade.reason = trade.reason + f" | Simulated Tx ID: {payload.tx_hash}"
    db.commit()
    return {"status": "success"}

@router.post("/execute")
async def trigger_agent_execution(api_key: str = Depends(get_api_key)):
    """Manually trigger the trading agent execution (for testing/demo)."""
    await execute_daily_trades()
    return {"status": "success", "message": "Agent execution completed"}

@router.post("/reset")
def reset_portfolio(db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    """Reset portfolio state and clear trades to restart paper trading with $100,000 capital."""
    db.query(TradeHistory).delete()
    db.query(TradeDebate).delete()
    db.query(PortfolioState).delete()
    
    initial = PortfolioState(
        cash_balance=100000.0,
        holdings_value=0.0,
        total_value=100000.0,
        btc_benchmark_value=100000.0
    )
    db.add(initial)
    db.commit()
    return {"status": "success", "message": "Portfolio state reset to $100,000 initial capital."}
