"""
Global LSTM Forecaster training script.
Loads 2 years of historical close prices across all assets, prepares sliding window sequences,
trains a single global LSTMForecaster model, and saves it to ml/artifacts/best_lstm.pt.
"""

import os
import torch
import torch.nn as nn
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from ml.data.feature_store.store import FeatureStore

class LSTMForecaster(nn.Module):
    def __init__(self, hidden_size=64, num_layers=2, dropout=0.1):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=1,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0
        )
        self.fc = nn.Sequential(
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Linear(32, 1)
        )
    
    def forward(self, x):
        # x shape: (batch, seq_len, 1)
        out, _ = self.lstm(x)
        # out[:, -1, :] gets the hidden state of the last time step
        return self.fc(out[:, -1, :]).squeeze(-1)

def train_global_lstm():
    print("Starting global LSTM training pipeline...")
    
    # Load assets
    store = FeatureStore()
    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=730)).strftime("%Y-%m-%d")
    end_date = now.strftime("%Y-%m-%d")
    
    symbols = [
        "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "LINK", "DOT",
        "MATIC", "UNI", "ATOM", "LTC", "BCH", "XLM", "ALGO", "VET", "FIL", "TRX",
        "NEAR", "SAND", "MANA", "AXS", "THETA", "XMR", "EOS", "AAVE", "MKR", "COMP",
        "SNX", "YFI", "SUSHI", "CRV", "BAL", "ZRX", "REN", "LRC", "BAT", "ZEC",
        "DASH", "WAVES", "ICX", "QTUM", "ONT", "ZIL", "IOTA", "DGB", "1INCH", "FTM",
    ]
    
    features = store.load_node_features(start_date, end_date, symbols, expected_features=24)
    available_symbols = [s for s in symbols if s in features and not features[s].empty]
    
    if not available_symbols:
        print("No features found. Cannot train LSTM.")
        return
        
    print(f"Loaded feature histories for {len(available_symbols)} assets.")
    
    # Prepare training sequences
    lookback = 14
    X_list = []
    y_list = []
    
    # Track min/max per symbol to allow normalization/denormalization
    scaler_stats = {}
    
    for sym in available_symbols:
        df = features[sym].sort_index()
        prices = df["close"].values.astype(np.float32)
        if len(prices) < lookback + 5:
            continue
            
        p_min = prices.min()
        p_max = prices.max()
        p_range = p_max - p_min if p_max > p_min else 1.0
        normalized = (prices - p_min) / p_range
        
        scaler_stats[sym] = {"min": float(p_min), "max": float(p_max), "range": float(p_range)}
        
        for i in range(lookback, len(normalized)):
            X_list.append(normalized[i-lookback:i])
            y_list.append(normalized[i])
            
    if not X_list:
        print("No training sequences could be formed.")
        return
        
    X_train = np.array(X_list, dtype=np.float32)
    y_train = np.array(y_list, dtype=np.float32)
    
    # Convert to PyTorch tensors
    X_tensor = torch.from_numpy(X_train).unsqueeze(-1) # shape: (N, lookback, 1)
    y_tensor = torch.from_numpy(y_train)
    
    dataset = torch.utils.data.TensorDataset(X_tensor, y_tensor)
    loader = torch.utils.data.DataLoader(dataset, batch_size=256, shuffle=True)
    
    # Initialize model
    model = LSTMForecaster()
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    criterion = nn.MSELoss()
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    
    print(f"Training LSTM model on {len(X_train)} sequences using device: {device}...")
    
    model.train()
    epochs = 20
    for epoch in range(epochs):
        epoch_loss = 0.0
        for batch_x, batch_y in loader:
            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)
            
            optimizer.zero_grad()
            pred = model(batch_x)
            loss = criterion(pred, batch_y)
            loss.backward()
            optimizer.step()
            
            epoch_loss += loss.item() * len(batch_x)
            
        print(f"Epoch {epoch+1:2d}/{epochs:2d} | Loss: {epoch_loss / len(X_train):.6f}")
        
    # Save pre-trained model and scale factors
    model.eval()
    os.makedirs("ml/artifacts", exist_ok=True)
    save_path = "ml/artifacts/best_lstm.pt"
    
    torch.save({
        "model_state_dict": model.cpu().state_dict(),
        "lookback": lookback,
        "scaler_stats": scaler_stats
    }, save_path)
    
    print(f"Global LSTM Forecaster saved successfully to {save_path}!")

if __name__ == "__main__":
    train_global_lstm()
