# Machine Learning Model Specification

This document defines the Spatio-Temporal Graph Convolutional Network (ST-GCN) model specification, details tensor dimensions at each execution layer, and sets parameters for optimization, training, and multi-task learning.

---

## 1. Input Features

The model ingests a 3D tensor representing a dynamic lookback window of cryptocurrency states.

- **Dimension**: `(N, T, F)`
  - `N` (Nodes): `50` assets (top tokens by market cap).
  - `T` (Timesteps): `30` days lookback window.
  - `F` (Features): `24` features per node.

### Node Feature Vector Layout (Ordered)

The feature store serves features in this order:

1. **timestamp** (Used as alignment index, converted to sine/cosine temporal positional features or excluded from the raw matrix, resulting in 24 input features: the 22 features below plus the 2 engineered sentiment rolling features):
2. **open** (Raw opening price)
3. **high** (Raw high price)
4. **low** (Raw low price)
5. **close** (Raw close price)
6. **volume** (Raw trade volume)
7. **rsi_14** (Relative Strength Index - 14 days)
8. **macd** (Moving Average Convergence Divergence line)
9. **macd_signal** (MACD Signal line)
10. **atr_14** (Average True Range - 14 days)
11. **bb_width** (Bollinger Band Width)
12. **returns_1d** (1-day log returns)
13. **returns_7d** (7-day simple returns)
14. **volatility_7d** (7-day rolling std of returns)
15. **sentiment_score** (CoinGecko normalized sentiment score: `[-1, 1]`)
16. **fear_greed_norm** (Alternative.me fear and greed index: `[0, 1]`)
17. **community_score** (CoinGecko community index score)
18. **public_interest** (CoinGecko public interest score)
19. **market_cap_usd** (Asset market capitalization)
20. **sentiment_rolling_3d** (3-day rolling mean of sentiment score)
21. **sentiment_momentum** (Current sentiment score minus rolling average)
22. **fed_rate** (FRED effective federal funds rate)
23. **cpi** (FRED Consumer Price Index)
24. **inflation** (FRED 10-year breakeven inflation rate)
25. **vix** (FRED CBOE Volatility Index)

---

## 2. Model Architecture & Layer Shapes

The model processes spatial structure (cross-asset connections) and temporal patterns sequentially:

```text
       Input Tensor Sequence [30 x (N, 24)]
                      |
                      v
      +-------------------------------+
      |   Linear Input Projection     |  Shape: (N, 128) per timestep
      +---------------+---------------+
                      |
                      v
      +-------------------------------+
      |    Spatio-Temporal GAT        |  Applies GATv2Conv per timestep
      |  - Layer 1: 8 heads (concat)  |  Shape: (N, 128)
      |  - Layer 2: 4 heads (average) |  Shape: (N, 128)
      +---------------+---------------+
                      |
                      v
      +-------------------------------+
      |   Temporal Stacking Module    |  Combine steps along time axis
      +---------------+---------------+  Shape: (N, 30, 128)
                      |
                      v
      +-------------------------------+
      |  Temporal Transformer Encoder |  - Sinusoidal Pos Encoding
      |  - d_model: 128, nhead: 8     |  - 4 self-attention layers
      |  - Extraction: output[:, -1]  |  Shape: (N, 128)
      +---------------+---------------+
                      |
             +--------+--------+
             |                 |
             v                 v
      +--------------+  +--------------+
      |  Direction   |  | Volatility   |  Multi-Task Heads
      |  Class Head  |  | Class Head   |
      +------+-------+  +------+-------+
             |                 |
             v (5 logits)      v (4 logits)
```

### 2.1 Layer Execution Specification

1. **LinearProjection**:
   - **Math**: $\mathbf{H}_t^{(0)} = \mathbf{X}_t \mathbf{W}_{proj}$
   - **Tensor Shape**: `(N, 24) -> (N, 128)` for each timestep $t \in [1, 30]$.

2. **SpatioTemporalGAT**:
   - Applies message-passing across graph edges for each timestep $t$. Uses `GATv2Conv` layers:
     - **GATv2 L1**:
       - Input channels: `128`
       - Output channels: `16` (multiplied by `8` heads = `128` channels)
       - Activation: `ELU` + `Dropout(0.1)`
       - Output shape: `(N, 128)`
     - **GATv2 L2**:
       - Input channels: `128`
       - Output channels: `128` (`4` heads, `concat=False` -> averaged output)
       - Activation: `ELU` + `Dropout(0.1)`
       - Output shape: `(N, 128)`

3. **Temporal Stacking**:
   - Compiles embeddings chronologically.
   - Output shape: `(N, 30, 128)`

4. **TemporalTransformer**:
   - Models dependencies across timesteps.
   - **Sinusoidal Position Encoding**: Standard sine/cosine values added directly to the spatial-temporal tensor:
     - Output shape: `(N, 30, 128)`
   - **Transformer Encoder**:
     - `d_model`: `128`
     - `nhead`: `8`
     - `num_layers`: `4`
     - `dim_feedforward`: `512`
     - `dropout`: `0.1`
     - `batch_first`: `True`
   - **Extraction**: Selects output at the final timestep $t=30$.
     - Output shape: `(N, 128)`

5. **MultiTaskHead**:
   - Splits into two parallel feed-forward heads:
     - **Direction Head**:
       - Layer 1: `Linear(128, 64) -> ReLU() -> Dropout(0.2)`
       - Layer 2: `Linear(64, 5)`
       - Output shape: `(N, 5)` logits representing classification classes.
     - **Volatility Head**:
       - Layer 1: `Linear(128, 64) -> ReLU() -> Dropout(0.2)`
       - Layer 2: `Linear(64, 4)`
       - Output shape: `(N, 4)` logits representing volatility categories.

---

## 3. Output Class Definitions

### 3.1 Direction Categories
Predicts the forward log return threshold classification over $H$ horizon days (default $H=1$):
- **strong_up**: Forward Return $> 3\%$
- **up**: Forward Return $\in (0\%, 3\%]$
- **neutral**: Forward Return $\in (-1\%, 0\%]$
- **down**: Forward Return $\in [-3\%, -1\%)$
- **strong_down**: Forward Return $< -3\%$

### 3.2 Volatility Regimes
Categorizes asset standard deviation patterns:
- **low**: Low volatility (stable consolidations)
- **medium**: Medium volatility (normal trading conditions)
- **high**: High volatility (news events, trend breakouts)
- **extreme**: Extreme volatility (capitulations, flash moves)

---

## 4. Loss Function

A composite multi-task objective balances classification cross-entropy:

$$\mathcal{L}_{total} = 0.7 \cdot \mathcal{L}_{direction} + 0.3 \cdot \mathcal{L}_{volatility}$$

- **Direction Loss ($\mathcal{L}_{direction}$)**: Categorical Cross-Entropy, weighted by **inverse class frequency** computed across the training batch to address asset imbalance:
  $$w_c = \frac{\sum_{k} N_k}{C \cdot N_c}$$
- **Volatility Loss ($\mathcal{L}_{volatility}$)**: Categorical Cross-Entropy, calculated using equal class weights.

---

## 5. Training Configurations

- **Optimizer**: `AdamW`
  - Learning Rate: `1e-3`
  - Weight Decay: `1e-4`
- **Scheduler**: `CosineAnnealingLR`
  - Max iterations ($T_{max}$): `50` epochs
- **Gradient Clipping**: L2 Norm threshold $\le 1.0$ (via `torch.nn.utils.clip_grad_norm_`)
- **Precision**: Mixed Precision (`torch.cuda.amp.autocast()`) enabled dynamically if a CUDA-supported GPU is available.
- **Max Epochs**: `100` epochs
- **Early Stopping**: Patience = `10` epochs, monitoring validation subset macro-averaged F1 score.
