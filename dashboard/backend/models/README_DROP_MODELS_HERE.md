# Hot-Swap ML Model Drop-In Directory (`backend/models/`)

While Phase 1 model debugging/training is in progress, the backend runs in **Statistical & Trend Baseline Mode** so the real-time Prometheus pipeline, alerting engine, Slurm integration, and React dashboard work immediately without fabricating metrics.

## How to Activate Trained Models (Zero Code Changes)
Once your teammate finishes exporting the cleaned models from `Modelling_Predictive_HPC_Cleaned.ipynb`, copy any or all of the following files into this folder (`backend/models/`) and click **Reload `.pkl` Models** in **AI & Predictions** or **Settings**:

### 1. Live Cluster Unsupervised Anomaly Detection Models
- `hpc_feature_scaler.pkl` — Fitted `StandardScaler` / `RobustScaler`
- `isolation_forest_hpc.pkl` — Fitted `IsolationForest`
- `one_class_svm_hpc.pkl` — Fitted `OneClassSVM`
- `lof_hpc.pkl` — Fitted `LocalOutlierFactor(novelty=True)`
- `kmeans_hpc.pkl` — Fitted `KMeans`
- `kmeans_threshold.pkl` — Float distance threshold (99th percentile)

### 2. Supervised Failure Prediction Model
- `final_rf_failure_model.pkl` (or `final_xgb_failure_model.pkl`) — Fitted scikit-learn `Pipeline` with `.predict_proba(X)`
- `rf_feature_columns.json` — JSON list of ordered feature column names expected by the supervised pipeline

### 3. Optional Validation Metrics (`model_metrics.json`)
To display real offline validation metrics (Precision, Recall, F1, ROC-AUC, Event Recall) in the **AI & Predictions** view without hardcoding or inventing numbers, export `model_metrics.json`:
```json
{
  "precision": 0.84,
  "recall": 0.91,
  "f1": 0.87,
  "roc_auc": 0.95,
  "event_recall": 0.94,
  "split_info": "Chronological split (Jul train / Aug val / Sep test)"
}
```
