CREATE TABLE sentiment (
  id                   BIGSERIAL PRIMARY KEY,
  asset_id             UUID REFERENCES assets(id) ON DELETE CASCADE,
  timestamp            TIMESTAMPTZ NOT NULL,
  sentiment_score      NUMERIC,
  news_volume          INTEGER,
  fear_greed           INTEGER,
  community_score      NUMERIC,
  public_interest      NUMERIC,
  sentiment_rolling_3d NUMERIC,
  sentiment_momentum   NUMERIC,
  fear_greed_norm      NUMERIC,
  UNIQUE(asset_id, timestamp)
);
CREATE INDEX idx_sentiment_asset_time ON sentiment(asset_id, timestamp);
ALTER TABLE sentiment ENABLE ROW LEVEL SECURITY;
