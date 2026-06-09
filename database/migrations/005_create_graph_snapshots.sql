CREATE TABLE graph_snapshots (
  id           BIGSERIAL PRIMARY KEY,
  timestamp    TIMESTAMPTZ NOT NULL,
  source_asset UUID REFERENCES assets(id),
  target_asset UUID REFERENCES assets(id),
  weight       NUMERIC,
  edge_type    TEXT
);
CREATE INDEX idx_graph_snapshots_time ON graph_snapshots(timestamp);
ALTER TABLE graph_snapshots ENABLE ROW LEVEL SECURITY;
