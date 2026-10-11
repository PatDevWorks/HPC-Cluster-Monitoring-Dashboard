# HPC Predictive Monitoring Using Machine Learning

**Machine Learning | High-Performance Computing | Predictive Analytics | System Reliability**

> Developing a data-driven monitoring approach to identify abnormal HPC system behaviour and investigate the potential for predicting failures before they disrupt computational workloads.

---

## 1. Overview

High-Performance Computing (HPC) systems support computationally intensive workloads across scientific research, engineering, data analysis, and machine learning. Their reliability depends on the coordinated operation of compute nodes, memory, storage, networks, and workload scheduling systems.

Unexpected node failures, hardware degradation, resource exhaustion, and abnormal system behaviour can interrupt workloads, waste computational resources, and delay research activities.

Traditional monitoring approaches primarily rely on collecting metrics, displaying system health, and triggering alerts when predefined thresholds are exceeded. Although essential, threshold-based monitoring may not adequately distinguish unusual behaviour from legitimate workload variations or identify developing problems before they become critical.

**HPC Predictive Monitoring Using Machine Learning** investigates how historical monitoring data and machine learning techniques can support earlier detection of abnormal behaviour and the identification of patterns associated with potential system failures.

The project aims to develop a monitoring pipeline that processes system metrics, extracts meaningful features, applies suitable analytical models, evaluates their performance, and presents useful monitoring insights through visualisation and alerting mechanisms.

The work is intended to support HPC administrators in making more informed, data-driven decisions about system reliability and operational health.

## 2. Problem Statement

HPC environments generate large volumes of time-series data describing the performance and condition of their computing infrastructure. Interpreting these metrics effectively is challenging because normal resource utilisation varies with workload type, execution phase, and node characteristics.

For example, high CPU utilisation may be expected during a compute-intensive workload, while a similar utilisation pattern under different operating conditions could warrant investigation. A monitoring system that relies exclusively on static thresholds may produce unnecessary alerts or overlook more subtle changes.

The central problem addressed by this project is:

**How can historical HPC monitoring metrics be analysed using machine learning to identify abnormal system behaviour and evaluate whether emerging patterns provide useful indications of potential failures?**

The project explores the relationship between monitoring data, workload behaviour, anomaly detection, and failure prediction within an HPC environment.

## 3. Project Objectives

The primary objectives are to:

1. **Collect and understand monitoring data** from available historical Prometheus metrics and other suitable data sources.
2. **Prepare the data** through cleaning, timestamp alignment, missing-value handling, and the identification of unreliable observation periods.
3. **Engineer relevant features** that capture resource utilisation, variability, trends, and changes in system behaviour.
4. **Develop analytical baselines** using statistical methods and suitable machine learning algorithms.
5. **Investigate failure prediction** by relating historical system behaviour to appropriately defined future failure windows, where reliable labels are available.
6. **Evaluate model performance** using suitable metrics, including precision, recall, F1-score, and precision-recall analysis.
7. **Integrate monitoring insights** with Prometheus and Grafana where supported by the available environment.
8. **Develop a monitoring dashboard** that communicates system behaviour, anomaly scores, model outputs, and relevant alerts.

## 4. Proposed System Architecture

The proposed workflow separates data collection, processing, analysis, and presentation into distinct stages.

```text
HPC Cluster / Historical Metrics
              |
              v
     Prometheus Data Source
              |
              v
      Data Extraction
              |
              v
  Data Cleaning and Validation
              |
              v
       Feature Engineering
              |
              v
  Statistical and ML Analysis
              |
              v
   Anomaly Scores / Predictions
              |
              v
  Evaluation, Dashboard and Alerts
              |
              v
       Grafana Visualisation
```

The architecture is a proposed workflow. Individual components will be implemented and evaluated as the project progresses.

### Pipeline components

| Component | Responsibility |
|---|---|
| Data collection | Obtain historical monitoring metrics and, where available, associated operational events. |
| Data preprocessing | Validate timestamps, handle missing observations, identify gaps, and prepare consistent time-series data. |
| Feature engineering | Calculate rolling statistics, variability, trends, and other useful indicators of system behaviour. |
| Statistical analysis | Establish baseline behaviour and identify deviations from expected patterns. |
| Machine learning | Apply suitable algorithms to identify anomalies and investigate predictive signals. |
| Evaluation | Measure detection quality, false alarms, missed events, and predictive usefulness. |
| Visualisation | Present metrics, model outputs, and monitoring insights through dashboards. |

## 5. Technologies and Tools

The project uses, or plans to evaluate, the following technologies according to the requirements of each stage.

| Technology | Intended use |
|---|---|
| Python | Data processing, experimentation, and model development. |
| Prometheus | Collection and querying of time-series monitoring metrics. |
| Grafana | Dashboard development and visualisation of monitoring results. |
| pandas | Data manipulation, cleaning, and time-series analysis. |
| NumPy | Numerical computation and feature calculations. |
| scikit-learn | Statistical preprocessing, anomaly detection, and machine learning experiments. |
| Jupyter Notebook | Interactive analysis, experimentation, and documentation of findings. |
| Parquet | Efficient storage of structured datasets and engineered features. |
| Git and GitHub | Version control, project documentation, and development tracking. |

The availability and integration of individual tools depend on the development environment and the data sources accessible to the project.

## 6. Monitoring Metrics

The selection of metrics will depend on data availability, sampling frequency, and their relevance to the research objectives.

Potential metric categories include:

- **CPU:** Utilisation, load, and changes in processor activity.
- **Memory:** Memory utilisation, available memory, and pressure indicators where available.
- **Storage:** Disk utilisation, I/O activity, and throughput where available.
- **Network:** Traffic volume, throughput, and communication-related indicators.
- **Hardware health:** Temperature, fan measurements, ECC errors, and EDAC events where exposed by the monitoring environment.
- **Workload behaviour:** Queue lengths, job activity, and scheduling-related information where available.

Metrics should be interpreted in context. High resource utilisation alone does not necessarily indicate a fault; its significance depends on workload characteristics, historical behaviour, and other available evidence.

## 7. Data Processing and Feature Engineering

Raw monitoring metrics may contain missing observations, irregular sampling intervals, duplicated timestamps, hardware-specific differences, and periods affected by maintenance or unavailable nodes.

The preprocessing stage will aim to produce reliable datasets for model development and evaluation.

Planned processing activities include:

1. Validate metric names, data types, timestamps, and observation ranges.
2. Identify missing data, duplicated records, and significant sampling gaps.
3. Separate invalid or unreliable observation periods from usable data.
4. Align relevant metrics to a consistent time resolution where appropriate.
5. Calculate features such as rolling means, standard deviations, minimums, maximums, and rates of change.
6. Preserve temporal ordering when creating training, validation, and test datasets.
7. Document assumptions and preprocessing decisions to support reproducibility.

Derived datasets may be stored separately from raw observations to preserve traceability and allow experiments to be repeated.

## 8. Analytical and Machine Learning Approaches

The project will investigate a range of approaches, beginning with simpler baselines before considering more complex models.

### Statistical baselines

Statistical methods, including z-scores and exponentially weighted moving averages (EWMA), can help identify observations or trends that deviate from established behaviour.

These methods provide interpretable baselines against which machine learning approaches can be compared.

### Unsupervised anomaly detection

Potential algorithms include:

- **Isolation Forest:** Identifies observations that are easier to isolate from the broader dataset.
- **Local Outlier Factor (LOF):** Identifies observations with substantially different local density from their neighbours.
- **One-Class Support Vector Machine:** Learns a boundary around data considered representative of normal behaviour.

These methods can help identify unusual patterns without requiring every observation to have a failure label. However, an anomaly is not automatically evidence of an impending failure.

### Failure prediction

Where sufficiently reliable historical event labels are available, supervised or time-window-based experiments may investigate whether monitoring features contain useful information about future failures.

A prediction task requires an explicit target definition, a prediction horizon, and appropriate handling of class imbalance. The project will assess whether predictive signals provide useful warning beyond the anomaly-detection baseline.

No particular model will be assumed to be the best before experimental evaluation.

## 9. Evaluation Methodology

Evaluation will consider both the technical performance of the models and their potential usefulness in an operational monitoring context.

Relevant metrics include:

| Metric | Purpose |
|---|---|
| Precision | Measures the proportion of predicted positive events that are correct. |
| Recall | Measures the proportion of actual positive events successfully identified. |
| F1-score | Balances precision and recall. |
| Precision-Recall AUC | Assesses the precision-recall trade-off across thresholds, particularly for imbalanced labels. |
| False-positive rate | Helps assess how frequently normal behaviour generates incorrect alerts. |
| Detection lead time | Measures how long before an event a useful warning is generated, where event timestamps support this calculation. |

Evaluation will distinguish between point-level anomaly detection and event-level failure prediction. These tasks have different targets and should not be compared as though they were equivalent.

For predictive experiments, future observations must not leak into training features. Time-based data splits and suitable event-level evaluation will be used where applicable.

Results will be documented alongside the experimental configuration, assumptions, limitations, and baseline comparisons.

## 10. Repository Structure

The repository is organised to separate data, documentation, machine learning artefacts, experiments, and reusable scripts.

```text
HPC-Predictive-Monitoring/
├── data/
│   ├── raw/
│   ├── processed/
│   └── features/
├── doc/
│   ├── architecture/
│   └── reports/
├── models/
├── notebooks/
├── scripts/
├── README.md
└── .gitignore
```

This structure represents the intended organisation and can be expanded as implementation requirements become clearer.

| Directory | Intended contents |
|---|---|
| `data/` | Raw, cleaned, and feature-engineered datasets, subject to data-access and storage restrictions. |
| `doc/` | Design documentation, methodology, experiment reports, and project notes. |
| `models/` | Model configurations and selected saved model artefacts where appropriate. |
| `notebooks/` | Exploratory analysis, feature engineering experiments, and model evaluation. |
| `scripts/` | Reusable scripts for extraction, preprocessing, training, evaluation, and integration. |

Empty directories can be retained in Git using `.gitkeep` placeholder files. The exact directory layout may evolve as the implementation develops.

## 11. Development Workflow

The project follows an incremental workflow:

1. **Environment and data discovery:** Confirm access to the development environment, historical metrics, and relevant monitoring sources.
2. **Data exploration:** Examine data coverage, metric quality, workload variation, and available event labels.
3. **Preprocessing:** Develop repeatable procedures for cleaning and preparing time-series data.
4. **Baseline development:** Implement statistical methods and establish reference performance.
5. **Model experimentation:** Evaluate suitable anomaly-detection and failure-prediction approaches.
6. **Evaluation:** Compare results using consistent splits, metrics, and documented assumptions.
7. **Monitoring integration:** Connect selected outputs to the monitoring and visualisation pipeline where feasible.
8. **Documentation:** Record results, limitations, implementation decisions, and directions for further work.

## 12. Current Project Status

The repository provides the foundation for organising the HPC predictive monitoring work.

The project is intended to progress through data preparation, model development, evaluation, and monitoring integration. The completion status of each component must be established from the implementation and experimental results.

| Area | Status |
|---|---|
| Repository structure | Created |
| Data-source validation | To be documented |
| Preprocessing pipeline | To be implemented and evaluated |
| Statistical baselines | To be implemented and evaluated |
| Machine learning experiments | To be implemented and evaluated |
| Model evaluation | Pending experimental results |
| Prometheus/Grafana integration | Planned and subject to environment validation |
| Monitoring dashboard | Planned |

This table should be updated as features are implemented and verified. No model accuracy, failure-prediction capability, or operational integration should be claimed without supporting evidence.

## 13. Reproducibility and Data Management

Reproducibility is an important consideration when evaluating monitoring and machine learning methods.

Experiments should record relevant parameters, feature definitions, preprocessing decisions, data splits, random seeds where applicable, model configurations, and evaluation results.

The repository should not contain credentials, private keys, access tokens, or restricted infrastructure information. Large datasets, raw operational metrics, and generated model artefacts should be managed according to applicable access restrictions and storage requirements.

Where datasets cannot be shared, documentation should describe their origin, structure, preparation, and access limitations without exposing sensitive information.

## 14. Limitations and Research Considerations

Predictive monitoring presents several challenges:

- Historical failures may be rare or incompletely labelled.
- Normal workload variation can resemble abnormal behaviour.
- Monitoring gaps may obscure the sequence of events preceding a failure.
- Hardware and workload differences can affect model generalisation.
- False alarms can reduce the practical value of a monitoring system.
- Correlation between metrics and failures does not, by itself, establish causation.
- Models evaluated on synthetic data may not generalise to real operational failures.

These limitations will inform the experimental design and interpretation of results. Any claims about early warning or failure prediction must be supported by appropriately designed experiments.

## 15. Future Directions

Potential extensions include:

- Evaluating models across different node types and workload classes.
- Comparing threshold-based alerts with statistical and machine learning approaches.
- Investigating feature importance and the interpretability of anomaly scores.
- Exploring event-based alert aggregation to reduce repetitive notifications.
- Integrating selected model outputs into Grafana dashboards.
- Evaluating prediction horizons and warning lead time using reliable historical events.
- Investigating model drift as workloads and infrastructure change.

These are potential research directions rather than confirmed deliverables.

## 16. Contributing and Discussions

Questions, technical discussions, methodology suggestions, and evidence-based improvements are welcome.

Use GitHub Issues to report reproducible problems or track proposed implementation changes, and GitHub Discussions to ask questions, exchange ideas, and share experimental observations.

When contributing, include sufficient context to explain the problem, the proposed change, and its expected benefit. Keep discussions constructive and avoid publishing confidential monitoring data or credentials.

## 17. Research Goal

The broader goal of this project is to investigate whether machine learning can improve the interpretation of HPC monitoring data and provide useful, measurable indications of abnormal behaviour or potential failures.

By combining systematic data preparation, interpretable baselines, model evaluation, and monitoring visualisation, the project aims to establish an evidence-based foundation for predictive monitoring in HPC environments.

---

**Project:** HPC Predictive Monitoring Using Machine Learning  
**Focus:** System monitoring, anomaly detection, and failure-prediction research  
**Repository:** HPC-Predictive-Monitoring
