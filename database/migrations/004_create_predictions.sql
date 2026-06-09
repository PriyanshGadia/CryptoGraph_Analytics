CREATE TABLE predictions (
  id                BIGSERIAL PRIMARY KEY,
  asset_id          UUID REFERENCES assets(id) ON DELETE CASCADE,
  timestamp         TIMESTAMPTZ NOT NULL,
  predicted_at      TIMESTAMPTZ DEFAULT NOW(),
  direction         TEXT,
  confidence        NUMERIC,
  volatility_regime TEXT,
  shap_values       JSONB,
  model_version     TEXT
);
CREATE INDEX idx_predictions_asset_time ON predictions(asset_id, timestamp);
ALTER TABLE predictions ENABLE ROW LEVEL SECURITY;
