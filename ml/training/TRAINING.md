# Model Training Workflow

## Hardware Considerations
This project is designed to run efficiently on an Intel i3 with 4GB RAM for **inference and data ingestion**. However, training a deep ensemble model (LSTM + NeuralProphet) on 50 assets across years of OHLCV and macroeconomic features requires significantly more memory and compute than the deployment hardware provides. 

Performing full backpropagation on this dataset will result in Out-Of-Memory (OOM) crashes on 3-4GB systems.

## The Two-Stage Training Pipeline

### 1. Pre-Training (Cloud/High-Resource)
The base models must be trained offline using platforms like Google Colab, Kaggle, or a dedicated ML workstation with at least 16GB RAM and a GPU.

1. **Export Data:** Run a script to dump the `ohlcv` and `technical_features` tables to CSV.
2. **Train Offline:** Use the full historical dataset to train the LSTM. 
3. **Save Artifacts:** Export the trained PyTorch weights to `ml/artifacts/best_lstm.pt`.
4. **Deploy:** Check these binary files into your deployment pipeline or mount them via a volume.

### 2. Online Inference & Fine-Tuning (Local/Low-Resource)
Once the pre-trained weights are loaded onto the i3 host:
- **Inference:** The backend loads `best_lstm.pt` into memory once (Singleton cache) and uses it for extremely fast forward-passes.
- **Incremental Learning:** (Optional) PyTorch's `DataLoader` can be used to run mini-batch updates (batch size = 16 or 32) on new daily data, keeping memory footprint strictly bounded.

## Fallback
If no pre-trained `best_lstm.pt` model is found, the system will gracefully fall back to `NeuralProphet` fitting on-the-fly, and then finally a mean-reversion heuristic, ensuring 100% uptime.
