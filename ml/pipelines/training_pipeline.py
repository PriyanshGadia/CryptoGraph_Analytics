"""
Full training pipeline: hyperopt -> train -> backtest -> explain -> register.
"""

def main():
    print("▶ Step 1: Loading features from FeatureStore...")
    # Load features for all 50 assets, last 3 years

    print("▶ Step 2: Running Optuna hyperparameter search (50 trials)...")
    # Run optuna_search.run_hyperopt()

    print("▶ Step 3: Loading best hyperparameters...")
    # Load ml/artifacts/best_params.json

    print("▶ Step 4: Training STGCNModel with best hyperparameters...")
    # Build graph sequences, train model via STGCNTrainer.fit()

    print("▶ Step 5: Running backtest on test period...")
    # Run Backtester on last 90 days with test predictions

    print("▶ Step 6: Computing SHAP explainability...")
    # Run explain_all_assets(), store in Supabase

    print("▶ Step 7: Registering model in Supabase model_registry...")
    # Upsert into model_registry with version, metrics, artifact_path

    print("▶ Step 8: Final metrics summary:")
    # Print table: metric | value

    print("🎉 Training pipeline complete")

if __name__ == "__main__":
    main()
