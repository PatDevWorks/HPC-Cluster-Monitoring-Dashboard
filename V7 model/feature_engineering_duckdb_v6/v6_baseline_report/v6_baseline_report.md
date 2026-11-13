# HPC Anomaly Detection — V6 Isolation Forest Baseline Report

Generated (UTC): 2026-11-08T16:27:09.395892+00:00

## Experiment setup

- Model: Isolation Forest (300 trees).
- Rows: 80,640; nodes: 4; features: 28.
- Clean normal rows used for fitting: 55,262.
- Threshold: 0.60064800 (clean_train_p99).
- Score convention: higher anomaly score means more anomalous.
- Threshold selected against the operational validation target where possible; otherwise clean-training percentile fallback.

## Held-out test metrics

| Metric | Operational-event target | Broader anomaly target |
|---|---:|---:|
| Positive rows | 53 | 251 |
| Positive prevalence | 0.4382% | 2.0751% |
| PR-AUC (Average Precision) | 0.0233 | 0.0620 |
| Precision | 0.0079 | 0.0625 |
| Recall | 0.1698 | 0.2829 |
| F1 | 0.0151 | 0.1024 |
| Flagged rows | 1,136 | 1,136 |

## Node behaviour

Headnode: 579/3,024 rows flagged (19.15%). Review node-level metrics before treating these as failures.

Headnode behaviour must be interpreted separately: a different node role and an absence of labelled positives mean its flagged minutes are not validated as failures. They are also not automatically proven benign false alarms.

## Limitations

- **Validation labels:** Validation contains zero operational-event positives. Impact: The deployment threshold falls back to the clean-training score percentile; it is not validation-optimised.
- **Headnode:** 3,024 test rows, 579 flags, and zero operational positives. Impact: Headnode operational anomaly candidates are not validated by recorded positive labels; investigate role-specific behaviour and improve labels.
- **Feature quality:** Constant clean-training features: collector_shortfall_pct_mean Impact: These features add no separation within the clean training baseline; review their source and consider them for V7.
- **Event semantics:** events.csv has no rows with is_failure=1. Impact: The event register cannot currently substantiate failure-specific recall; describe event-window correlation instead.
- **Score interpretation:** Isolation Forest anomaly scores are uncalibrated ranking scores. Impact: Do not present them as failure probabilities.
- **Temporal interpretation:** Event correlation uses -5 to +10 minute windows around recorded events. Impact: A hit does not demonstrate a pre-failure prediction or lead time.
- **Generalisation:** The input contains 4 nodes over 15.0 calendar days. Impact: V6 should remain an experimental baseline until evaluated on longer and future unseen periods.

## Interpretation and deployment status

V6 is retained as an experimental hosted baseline. It demonstrates the end-to-end anomaly-scoring pipeline, but its metrics and label coverage do not establish production-grade failure prediction. High-busy/benchmark activity should be assessed against the broad anomaly target, not described automatically as an operational failure. A future V7 should be compared against this V6 baseline using the same target definitions and a new untouched future test period.

Model bundle: `C:\Users\Admin\Documents\chpc\capstone project\models\hpc_isolation_forest_v6_baseline_bundle.joblib`
Scored timeline: `C:\Users\Admin\Documents\chpc\capstone project\data\feature_engineering_duckdb_v6\v6_baseline_report\anomaly_timeline_scored_v6_baseline.parquet`
Manifest: `C:\Users\Admin\Documents\chpc\capstone project\data\feature_engineering_duckdb_v6\v6_baseline_report\v6_baseline_manifest.json`