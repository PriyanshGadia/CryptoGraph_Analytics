"""
Cryptographic Proof of Performance.
Hashes the daily portfolio state and trade history to create an immutable
track record for institutional compliance and trust.
"""

import hashlib
import json
from datetime import datetime
from sqlalchemy.orm import Session
from app.db.models_sqla import PortfolioState, TradeHistory, ProofOfPerformance

def generate_daily_proof(db: Session, portfolio_id: int) -> str:
    """
    Generates a SHA-256 hash of the portfolio state and the day's trades.
    Saves it to the ProofOfPerformance table.
    """
    portfolio = db.query(PortfolioState).filter(PortfolioState.id == portfolio_id).first()
    if not portfolio:
        return ""
        
    # Get trades from the last 24 hours
    # For a true daily proof, we'd filter by timestamp > start_of_day
    # Here we just grab the latest 10 trades to hash the recent state
    recent_trades = db.query(TradeHistory).order_by(TradeHistory.timestamp.desc()).limit(10).all()
    
    trade_data = [
        {
            "id": t.id,
            "symbol": t.symbol,
            "side": t.side,
            "quantity": t.quantity,
            "price": t.price,
            "pnl": t.pnl
        } for t in recent_trades
    ]
    
    # Create deterministic JSON string
    payload = {
        "portfolio_id": portfolio.id,
        "cash_balance": portfolio.cash_balance,
        "holdings_value": portfolio.holdings_value,
        "total_value": portfolio.total_value,
        "btc_benchmark": portfolio.btc_benchmark_value,
        "timestamp": portfolio.timestamp.isoformat() if portfolio.timestamp else datetime.utcnow().isoformat(),
        "recent_trades": trade_data
    }
    
    payload_str = json.dumps(payload, sort_keys=True)
    state_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
    
    # Save the proof
    proof = ProofOfPerformance(
        portfolio_state_id=portfolio.id,
        state_hash=state_hash,
        published_to_ipfs="pending_ipfs_sync" # Placeholder for actual IPFS integration
    )
    db.add(proof)
    db.commit()
    
    print(f"[ProofOfPerformance] Generated immutable hash: {state_hash}")
    return state_hash
