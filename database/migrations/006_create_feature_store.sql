CREATE TABLE technical_features (
  id            BIGSERIAL PRIMARY KEY,
  asset_id      UUID REFERENCES assets(id) ON DELETE CASCADE,
  timestamp     TIMESTAMPTZ NOT NULL,
  rsi_14        NUMERIC,
  macd          NUMERIC,
  macd_signal   NUMERIC,
  atr_14        NUMERIC,
  bb_width      NUMERIC,
  returns_1d    NUMERIC,
  returns_7d    NUMERIC,
  volatility_7d NUMERIC,
  UNIQUE(asset_id, timestamp)
);
CREATE INDEX idx_technical_asset_time ON technical_features(asset_id, timestamp);
ALTER TABLE technical_features ENABLE ROW LEVEL SECURITY;

CREATE TABLE macro_indicators (
  id          BIGSERIAL PRIMARY KEY,
  timestamp   TIMESTAMPTZ NOT NULL UNIQUE,
  fed_rate    NUMERIC,
  cpi         NUMERIC,
  inflation   NUMERIC,
  vix         NUMERIC,
  fed_rate_z  NUMERIC,
  cpi_z       NUMERIC,
  inflation_z NUMERIC,
  vix_z       NUMERIC
);
ALTER TABLE macro_indicators ENABLE ROW LEVEL SECURITY;

CREATE TABLE model_registry (
  id            BIGSERIAL PRIMARY KEY,
  version       TEXT UNIQUE,
  wandb_run_id  TEXT,
  metrics       JSONB,
  artifact_path TEXT,
  deployed_at   TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE model_registry ENABLE ROW LEVEL SECURITY;
