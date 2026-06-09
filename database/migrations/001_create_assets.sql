CREATE TABLE assets (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol         TEXT UNIQUE NOT NULL,
  name           TEXT,
  sector         TEXT,
  market_cap_usd NUMERIC,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE assets ENABLE ROW LEVEL SECURITY;
