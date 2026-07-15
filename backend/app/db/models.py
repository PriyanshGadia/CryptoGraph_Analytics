import uuid
from sqlalchemy import Column, String, Float, DateTime, Integer, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship, validates
from app.db.database import Base
from sqlalchemy.sql import func

class AppSetting(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    setting_key = Column(String, unique=True, index=True, nullable=False)
    setting_value = Column(String, nullable=False)

class Asset(Base):
    __tablename__ = "assets"

    # Using string for UUID
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol = Column(String, unique=True, index=True, nullable=False)
    name = Column(String)
    sector = Column(String)
    market_cap_usd = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    ohlcv = relationship("OHLCV", back_populates="asset", cascade="all, delete-orphan")
    predictions = relationship("Prediction", back_populates="asset", cascade="all, delete-orphan")
    news = relationship("AssetNews", back_populates="asset", cascade="all, delete-orphan")
    onchain_metrics = relationship("OnchainMetric", back_populates="asset", cascade="all, delete-orphan")

class OnchainMetric(Base):
    __tablename__ = "onchain_metrics"
    __table_args__ = (UniqueConstraint('asset_id', 'timestamp', name='_onchain_asset_timestamp_uc'),)

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(String, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    tvl = Column(Float, default=0.0)
    revenue = Column(Float, default=0.0)
    active_users = Column(Float, default=0.0)
    
    asset = relationship("Asset", back_populates="onchain_metrics")

class AssetNews(Base):
    __tablename__ = "asset_news"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(String, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    headline = Column(String, nullable=False)
    source = Column(String)
    published_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    asset = relationship("Asset", back_populates="news")

class OHLCV(Base):
    __tablename__ = "ohlcv"
    __table_args__ = (UniqueConstraint('asset_id', 'timestamp', name='_asset_timestamp_uc'),)

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(String, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)

    asset = relationship("Asset", back_populates="ohlcv")

class TechnicalFeature(Base):
    __tablename__ = "technical_features"
    __table_args__ = (UniqueConstraint('asset_id', 'timestamp', name='_tech_asset_timestamp_uc'),)

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(String, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    rsi_14 = Column(Float)
    returns_1d = Column(Float)
    returns_7d = Column(Float)
    volatility_7d = Column(Float)
    macd = Column(Float)
    macd_signal = Column(Float)
    atr_14 = Column(Float)
    bb_width = Column(Float)

    asset = relationship("Asset")

class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(String, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    predicted_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    direction = Column(String)
    confidence = Column(Float)
    confidence_interval_lower = Column(Float, nullable=True)
    confidence_interval_upper = Column(Float, nullable=True)
    volatility_regime = Column(String)
    shap_values = Column(JSON)  # Legacy SHAP
    model_version = Column(String)
    baseline_probability = Column(Float, default=0.3333, nullable=True)  # Expected random-guess baseline probability
    
    # Phase 9: Algorithmic Transparency Ledger (XAI & Inference Attestation)
    t_shap_attributions = Column(JSON, nullable=True) # Topological Shapley feature importance
    attestation_hash = Column(String, nullable=True) # Cryptographic attestation of unmodified inference

    asset = relationship("Asset", back_populates="predictions")

    @validates("confidence")
    def validate_confidence(self, key, value):
        if value is None:
            return None
        val = float(value)
        # Enforce 0.0 - 1.0 probability scale at ingestion boundary
        if val > 1.0 and val <= 100.0:
            val = val / 100.0
        if not (0.0 <= val <= 1.0):
            raise ValueError(f"Confidence value {value} out of valid probability range [0.0, 1.0]")
        return round(val, 4)

    @validates("confidence_interval_lower")
    def validate_confidence_interval_lower(self, key, value):
        if value is None:
            return None
        val = float(value)
        if val > 1.0 and val <= 100.0:
            val = val / 100.0
        if not (0.0 <= val <= 1.0):
            raise ValueError(f"confidence_interval_lower value {value} out of valid probability range [0.0, 1.0]")
        return round(val, 4)

    @validates("confidence_interval_upper")
    def validate_confidence_interval_upper(self, key, value):
        if value is None:
            return None
        val = float(value)
        if val > 1.0 and val <= 100.0:
            val = val / 100.0
        if not (0.0 <= val <= 1.0):
            raise ValueError(f"confidence_interval_upper value {value} out of valid probability range [0.0, 1.0]")
        return round(val, 4)

class PortfolioState(Base):
    __tablename__ = "portfolio_state"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    cash_balance = Column(Float, nullable=False, default=100000.0)
    holdings_value = Column(Float, nullable=False, default=0.0)
    total_value = Column(Float, nullable=False, default=100000.0)
    btc_benchmark_value = Column(Float, nullable=False, default=100000.0)

class TradeHistory(Base):
    __tablename__ = "trade_history"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    symbol = Column(String, nullable=False, index=True)
    side = Column(String, nullable=False)  # "buy" or "sell"
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    total_usd = Column(Float, nullable=False)
    reason = Column(String)
    confidence = Column(Float)
    status = Column(String, default="EXECUTED") # PENDING_WEB3_SIGNATURE, EXECUTED, CANCELLED
    pnl = Column(Float, default=0.0)  # realized P&L for sell trades
    overseer_grade = Column(Integer, nullable=True) # 1 to 5 stars
    overseer_notes = Column(String, nullable=True)

class TradeDebate(Base):
    __tablename__ = "trade_debates"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    symbol = Column(String, nullable=False, index=True)
    stgcn_direction = Column(String)
    stgcn_confidence = Column(Float)
    macro_analysis = Column(String)
    onchain_analysis = Column(String)
    sentiment_analysis = Column(String)
    cio_decision = Column(String)  # EXECUTE_BUY, EXECUTE_SELL, HOLD
    cio_reasoning = Column(String)

class ProofOfPerformance(Base):
    """Stores the daily cryptographic SHA-256 hash of the portfolio state for verifiable track record."""
    __tablename__ = "proof_of_performance"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    portfolio_state_id = Column(Integer, ForeignKey("portfolio_state.id", ondelete="CASCADE"), nullable=False)
    state_hash = Column(String, nullable=False, index=True)
    published_to_ipfs = Column(String, nullable=True) # E.g., IPFS CID if published


class Forecast(Base):
    """Stores daily ensembled forecasting outputs (LSTM, Prophet) for UI caching."""
    __tablename__ = "forecasts"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(String, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    forecast_prices = Column(JSON, nullable=False)
    lower_bound = Column(JSON, nullable=False)
    upper_bound = Column(JSON, nullable=False)
    lstm_forecast = Column(JSON, nullable=True)
    prophet_forecast = Column(JSON, nullable=True)

    asset = relationship("Asset")


class ModelRegistry(Base):
    """Audited run configurations, artifact hashes, and metrics validated via validation subsets."""
    __tablename__ = "model_registry"

    id = Column(Integer, primary_key=True, index=True)
    version = Column(String, unique=True, index=True, nullable=False)
    wandb_run_id = Column(String, nullable=True)
    metrics = Column(JSON, nullable=True)
    artifact_path = Column(String, nullable=True)
    deployed_at = Column(DateTime(timezone=True), server_default=func.now())


