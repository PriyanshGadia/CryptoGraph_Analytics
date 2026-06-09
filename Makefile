.PHONY: help setup db-migrate collect-data build-features train hyperopt backtest serve dev docker-up test

help:
	@echo "Available commands:"
	@echo "  setup          - Install all dependencies (backend, ml, frontend)"
	@echo "  db-migrate     - Run database migrations"
	@echo "  collect-data   - Run all data collectors"
	@echo "  build-features - Run feature engineering pipeline"
	@echo "  train          - Train the ST-GCN model"
	@echo "  hyperopt       - Run hyperparameter optimization"
	@echo "  backtest       - Run backtester evaluation"
	@echo "  serve          - Start the FastAPI backend"
	@echo "  dev            - Start Next.js frontend in development mode"
	@echo "  docker-up      - Spin up the full stack using Docker Compose"
	@echo "  test           - Run tests for backend and ml"

setup:
	pip install -r backend/requirements.txt
	pip install -r ml/requirements.txt
	cd frontend && npm install

db-migrate:
	python database/run_migrations.py

collect-data:
	python ml/data/ingestion/binance_collector.py
	python ml/data/ingestion/fred_collector.py
	python ml/data/ingestion/sentiment_collector.py
	python ml/data/ingestion/fear_greed_collector.py

build-features:
	python ml/data/feature_engineering/technical_indicators.py
	python ml/data/feature_engineering/sentiment_features.py
	python ml/data/feature_engineering/macro_features.py
	python ml/data/feature_store/validator.py

train:
	python ml/pipelines/training_pipeline.py

hyperopt:
	python ml/hyperopt/optuna_search.py

backtest:
	python ml/evaluation/backtester.py

serve:
	cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

dev:
	cd frontend && npm run dev

docker-up:
	docker-compose up --build

test:
	pytest backend/tests
	pytest ml/tests
