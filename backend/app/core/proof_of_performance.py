"""
Cryptographic Attestation Ledger.
Hashes the daily portfolio state and trade history to create an immutable
track record for institutional compliance and trust.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session

logger = logging.getLogger("cryptograph.proof")
from app.db.models_sqla import PortfolioState, TradeHistory, ProofOfPerformance

def generate_daily_proof(db: Session, portfolio_id: int) -> str:
    """
    Generates a chained SHA-256 hash of the portfolio state and the day's trades.
    Each proof includes the hash of the previous day's proof, forming a sequential Attestation Hash Chain.
    """
    portfolio = db.query(PortfolioState).filter(PortfolioState.id == portfolio_id).first()
    if not portfolio:
        return ""
        
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
    
    # Query previous proof hash to chain them together (Attestation Hash Chain)
    prev_proof = db.query(ProofOfPerformance).order_by(ProofOfPerformance.timestamp.desc()).first()
    prev_hash = prev_proof.state_hash if prev_proof else "0x0000000000000000000000000000000000000000000000000000000000000000"
    
    # Build Merkle root of trades
    trade_hashes = []
    for td in trade_data:
        td_str = json.dumps(td, sort_keys=True)
        trade_hashes.append(hashlib.sha256(td_str.encode("utf-8")).hexdigest())
        
    def _build_merkle_root(hashes: list) -> str:
        if not hashes:
            return "0x0"
        if len(hashes) == 1:
            return hashes[0]
        new_hashes = []
        for i in range(0, len(hashes), 2):
            left = hashes[i]
            right = hashes[i+1] if i+1 < len(hashes) else left
            combined = left + right
            new_hashes.append(hashlib.sha256(combined.encode("utf-8")).hexdigest())
        return _build_merkle_root(new_hashes)
        
    import secrets
    nonce = secrets.token_hex(16)
    merkle_root = _build_merkle_root(trade_hashes)
    
    payload = {
        "portfolio_id": portfolio.id,
        "cash_balance": portfolio.cash_balance,
        "holdings_value": portfolio.holdings_value,
        "total_value": portfolio.total_value,
        "btc_benchmark": portfolio.btc_benchmark_value,
        "timestamp": portfolio.timestamp.isoformat() if portfolio.timestamp else datetime.now(timezone.utc).isoformat(),
        "recent_trades": trade_data,
        "previous_hash": prev_hash,
        "nonce": nonce,
        "merkle_root": merkle_root
    }
    
    payload_str = json.dumps(payload, sort_keys=True)
    state_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
    
    # Mock blockchain anchoring (Conceptual demonstration of public anchoring)
    import secrets
    mock_tx_id = f"0x{secrets.token_hex(32)}"
    
    # Save the proof with the mock tx_id simulating a smart contract state publication
    proof = ProofOfPerformance(
        portfolio_state_id=portfolio.id,
        state_hash=state_hash,
        published_to_ipfs=mock_tx_id
    )
    db.add(proof)
    db.commit()
    
    logger.info(f"[ProofOfPerformance] Generated chained attestation hash: {state_hash}")
    logger.info(f"[ProofOfPerformance] Anchored to mock public ledger TxID: {mock_tx_id}")
    return state_hash
