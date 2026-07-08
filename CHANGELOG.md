# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **Ensemble Forecasting Pipeline**: Integrated LSTM, NeuralProphet, and ST-GCN models to provide robust price predictions.
- **Topological Data Analysis**: Graph-based representation of market correlations and sector motifs.
- **Cryptographic Attestation Ledger**: Implemented `proof_of_performance.py` to cryptographically hash and anchor daily portfolio states and trade histories to provide institutional-grade transparency.
- **Multi-Agent Trading Logic**: Simulated Chief Investment Officer, Quantitative Analyst, and Risk Manager agents.
- **Comprehensive API Security**: Unified API key validation across REST and WebSocket endpoints.
- **Multi-Stage Dockerfile**: Greatly reduced production Docker image size.

### Changed
- **ORM Consolidation**: Renamed and merged `models.py` and `models_sqla.py` into a standardized FastAPI `models.py` and `schemas.py` structure.
- **Documentation**: Updated marketing terminology in `README.md` to reflect ensemble forecasting over 'State-of-the-Art' ST-GCN claims.
- **CI Pipeline**: Enforced strict security gating with `bandit` and `safety`.

### Fixed
- Stabilized `cached` decorator to prevent thread-safety mutation issues.
- Fixed `run_lstm_forecast` initialization crashes and type signature mismatches in interpretability endpoints.
