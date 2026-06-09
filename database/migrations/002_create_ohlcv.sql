CREATE TABLE ohlcv (
  id         BIGSERIAL PRIMARY KEY,
  asset_id   UUID REFERENCES assets(id) ON DELETE CASCADE,
  timestamp  TIMESTAMPTZ NOT NULL,
  open       NUMERIC,
  high       NUMERIC,
  low        NUMERIC,
  close      NUMERIC,
  volume     NUMERIC,
  UNIQUE(asset_id, timestamp)
);
CREATE INDEX idx_ohlcv_asset_time ON ohlcv(asset_id, timestamp);
ALTER TABLE ohlcv ENABLE ROW LEVEL SECURITY;
