-- REFERENCE DDL SETUP FOR SUPABASE POSTGRESQL (PRODUCTION MODE)
-- Run these commands in the Supabase SQL Editor to enable Row Level Security (RLS) and define read-only policies.

-- 1. Enable RLS on all primary tables
ALTER TABLE assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE ohlcv ENABLE ROW LEVEL SECURITY;
ALTER TABLE sentiment_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE technical_features ENABLE ROW LEVEL SECURITY;
ALTER TABLE onchain_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE forecasts ENABLE ROW LEVEL SECURITY;

-- 2. Define READ access policies (SELECT)
-- Allow public (anon role) and authenticated users read-only access to market data & analytics
CREATE POLICY "Allow public read access on assets" ON assets FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow public read access on ohlcv" ON ohlcv FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow public read access on sentiment" ON sentiment_metrics FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow public read access on technicals" ON technical_features FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow public read access on onchain" ON onchain_metrics FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow public read access on predictions" ON predictions FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow public read access on graph_snapshots" ON graph_snapshots FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow public read access on forecasts" ON forecasts FOR SELECT TO anon, authenticated USING (true);

-- Settings and trades should be restricted to authenticated dashboard operators only
CREATE POLICY "Allow authenticated read on settings" ON app_settings FOR SELECT TO authenticated USING (true);
CREATE POLICY "Allow authenticated read on trades" ON trades FOR SELECT TO authenticated USING (true);

-- 3. Define WRITE access policies (INSERT/UPDATE/DELETE)
-- Restrict all writes to service_role (the FastAPI backend database client running with admin credentials)
-- By enabling RLS and not defining general write policies, only users connecting with service_role bypass RLS,
-- or database owners can make writes. This matches the standard high-assurance production setup.
