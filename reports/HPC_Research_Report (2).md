## Abstract

This study designs, implements and evaluates an unsupervised, machine-learning-based anomaly detection platform for High-Performance Computing (HPC) cluster monitoring, and reports what a fortnight of production-style telemetry can and cannot establish about its usefulness. Operational telemetry was collected at a 15-second resolution from one head node and three compute nodes of a purpose-built, virtualised Slurm cluster using Prometheus and Node Exporter, yielding 49,616,574 raw observations across 27 metric families between 18 and 31 October 2026. A counter-aware preprocessing pipeline, implemented in DuckDB, transformed these records into 60,475 one-minute compute-node observations, from which a 17-feature representation was derived. Six unsupervised algorithms (Isolation Forest, One-Class Support Vector Machine, Local Outlier Factor, Principal Component Analysis, Gaussian Mixture Model and an Autoencoder) were trained under a common chronological 70/15/15 protocol and compared on training cost and anomaly-designation behaviour.

The workload analysis showed that compute-node behaviour was dominated by a low-activity regime (99.73% of training observations fell in a single K-Means cluster), punctuated by legitimate benchmark executions (ASCOT5, DFTB+, HPCC and HemelB) whose resource signatures differ markedly from idle conditions. Under a threshold set at the 99th percentile of training scores, Isolation Forest designated 0.90% of validation and 6.74% of testing observations as potentially anomalous, whereas the five alternatives designated 1.71–1.98% and 24.99–25.98% respectively, reflecting differing sensitivity to the distribution shift between the training and later periods. Isolation Forest was therefore selected for deployment as a FastAPI inference service that maintains a 61-minute per-node history to compute one-hour temporal-change features.

The study is explicit about the limits of its evidence. Flag rates are not accuracy measures, no verified fault labels were available, and controlled anomaly-injection experiments and live end-to-end validation remain outstanding. The principal contributions are therefore a reproducible telemetry-to-inference pipeline, a documented treatment of counter and gap artefacts, an empirical characterisation of benign workload variability as a source of false alarms, and a validation protocol for establishing detection performance.

# Introduction
## 1.1 Background
High-Performance Computing, known as HPC, is the practice of combining computing resources - such as multiple servers, CPUs, RAM and storage - to solve complex problems that would otherwise be hard to solve when using a standard desktop computer. Over the past few years, HPC has evolved significantly. In the past, it would require custom-built machines that only a few institutions could afford, In today’s era, commercially available computers can be connected to ultra-fast networks.(Almeida 2018) HPC is applied in computationally intensive research. Scientists use it for climate modeling to predict the weather, molecular dynamics which help them discover new medicine and aerospace engineering to simulate airflow over airplanes. While continuous monitoring of resources such as CPU, memory, storage and network metrics is important to ensure stability, traditional monitoring systems only warn engineers after the system has crashed. To solve this problem, our research project proposes a predictive monitoring platform that uses Prometheus to gather real-time data, Scikit-Learn machine learning algorithms to identify anomaly patterns before the system crashes and Grafana to help us visualize what is happening in the system.(Wentzel 2026) This framework will be implemented in our four-node OpenStack environment, providing us a realistic test environment to simulate if the proposed model can identify failures in an HPC environment before the failure occurs. (Fruboes et al.2025)(Research Lifestyle Group 2025)

## 1.2 Problem Statement

The main problem that is faced in High-Performance Computing centers is the difficulty of monitoring and maintaining the health of distributed environments. HPC clusters today link hundreds to thousands of computing nodes together so that they can work simultaneously. This makes it harder for system administrators to find and track abnormal behavior across multiple machines at the same time. Traditional monitoring tools are reactive, only warning engineers after a critical slowdown has already occurred. They miss the early signs of system troubles, where minor issues are unnoticed. This leads to sudden failures that ruin weeks of important scientific simulations and research. Therefore, there is an urgent need to find out whether advance machine learning techniques can be applied to massive cluster datasets to find hidden patterns, detect anomalies, and provide a truly predictive monitoring solution that helps identify failures before they happen.

## 1.3 Research Motivation

The motivation for this research stands from the growing importance of reliable HPC infrastructure in driving modern scientific breakthroughs, making system uptime and stability more critical than ever. As these computational environments continue to scale, improving monitoring systems and deepening operational awareness is vital to prevent costly disruptions to complex simulation workloads, which can ruin months of valuable work. Modern clusters generate massive streams of performance telemetry every second. Machine learning has great potential to read through this mountain of information and identify complex patterns that human engineers could never spot on their own. (Operational Data Analytics Institute 2025).This project provides a unique opportunity to build a practical monitoring pipeline by combining industry-standard open-source tools like Prometheus and Grafana with Scikit-Learn machine learning models. (Wentzel 2026) By deploying this framework inside a virtualized, four-node OpenStack environment, we create a safe testbed where we can intentionally inject faults, simulate resource bottlenecks, and analyse exactly how systems behave right before they fail. Ultimately, there is immense scientific and practical value in testing and comparing different machine learning approaches against one another. This comparison will help the tech and DevOps industries discover which specific algorithms are best suited for predicting failures, while simultaneously bridging the skills gap between artificial intelligence and high-performance infrastructure operations.

## 1.4 Research Objectives

- **Objective 1:** Create our computing nodes inside our OpenStack environment using the resources that has been allocated us.
- **Objective 2:** Set up and configure our systems with the services that we need to ensure that the nodes can talk to each other safely and have the services needed for them to work as a team.
- **Objective 3:** Install and test all the necessary software services and tools to ensure that they are working within the environment and ready for us to use them.
- **Objective 4:** Set up Prometheus so that we an gather the live metrics from the nodes – such as CPU usage, memory levels and network speeds.
- **Objective 5:** Create and run a series of benchmarks, normal workloads and controlled tests intentionally to create the data that we would need to train our system such memory leaks, overload subscription and application running normally on a cluster, to allow us to record what the data looks like right before a failure occurs.
- **Objective 6:** Create a cleaning system to clean, organize and label the gathered data so that it is neat and ready to be used in the machine learning models
- **Objective 7:** Build and train different machine learning models using Scikit-Learn to teach the system how to differentiate between normal workloads and abnormal patterns.
- **Objective 8:** Compare the different machine models against each other and score which models is most accurate based on a certain criterion.
- **Object 9:** Design a dashboard and connect it to the machine learning software to show live health scores of the system and give warning to administrators before a failure occurs.

## 1.5 Research Aim

The aim of this research project is to design, implement and evaluate our predictive monitoring platform that uses machine learning to identify and catch failures before they occur within tour system environment and impacts the user. For us to reach our goal, we will implement a data pipeline using Prometheus to collect live performance metrics from multiple nodes and store this data in a central repository. The core focus of the study is to investigate how different machine-learning algorithms behave when analyzing data, training them to successfully distinguish between normal system workloads and abnormal behavior. This framework will be deployed in a 4-node cluster on OpenStack environment where it would consist of 1 headnode and 3 compute nodes. This framework would help us create a safe, realistic testbed where we can intentionally injection faults in our system such as – memory leaks, resource starvation and network bottlenecks – to test the accuracy and reliability of our trained models. 

At the end, the intended outcome of this research is the creation of a functional, real-time early warning system that helps HPC administrators visualize the health score and failure probabilities in the system to enable preventative maintenance. Another important outcome would be a detailed analysis of which specific machine learning algorithm are most accurate at predicting failures while minimizing the number of false alarms, providing valuable data for broader tech and DevOps industries.

## 1.6 Research Questions

- **RQ1.** What resource-utilisation regimes characterise a small HPC cluster across idle operation, a confirmed stress activity and recorded benchmark executions, and how heavily is the telemetry skewed towards any one of them?
- **RQ2.** How do six unsupervised anomaly-detection algorithms differ in training cost and in their anomaly-designation behaviour when evaluated on chronologically later telemetry than that used for training?
- **RQ3.** What data-quality safeguards and service design decisions are required for a trained model to be applied reliably to a live stream of node observations?
- **RQ4.** How well does the selected model detect controlled resource-stress conditions, and how does it be

## 1.7 Scope and delimitations

The investigation is confined to a three-compute-node virtualised cluster observed over fourteen days. Findings therefore describe the behaviour of this environment and should not be generalised to production systems of different scale, hardware or workload mix without further evidence. The head node is excluded from modelling because its monitoring and management workload differs from that of compute nodes. Workload annotations (the stress activity and the benchmark runs) are used as context, never as fault labels. Thermal and other hardware-sensor telemetry is outside the model's feature set.


# 2. Literature Review
## 2.1 Introduction

This literature review provides an analysis of existing research, methodologies and technologies that are related to predictive monitoring in High-performance Computing environments. As computational tasks continue to grow and evolve, maintaining cluster reliability has become more important than ever. This section explores the foundations of HPC systems, the transition from traditional monitoring to machine learning-driven monitoring and how telemetry data can be collected and preprocessed for anomaly detection. Furthermore, we will examine the use of specific machine learning algorithms, evaluate solutions that are currently being used in the market, identify gaps within current research and outline how our project can address these limitations.

## 2.2 High-Performance Computing
High-Performance Computing (HPC) involves the use of combining computational power to execute heavy computational processes that would otherwise be impossible to run on a standard desktop computer. Modern HPC architectures have evolved from being expensive to purchase supercomputers to being distributed cluster environments built from common hardware connected to ultra-fast, low latency networks. (Fruboes et al. 2025)

An HPC cluster operates as a single cohesive system, but its internal architecture is divided into specific roles (Google Cloud Technology Insights 2026):

* **Distributed Computing** – A design where a single massive task is split into smaller sub-tasks and shared across multiple physical or virtual machines working together (Scribd Academic Repository 2024).
* **Compute Nodes** – The worker units of the cluster where the computational simulations, calculations (Wentzel 2026), and heavy data processing happen, typically featuring high core counts and large amounts of RAM.
* **Head Nodes** – The gateway where users log in, compile code, and submit tasks; it hosts the workload manager or job scheduler and acts as a traffic controller to allocate resources based on user requests and node availability.(Almeida 2018)
* **Parallel Processing** – An architectural setup where software programs run instructions simultaneously across thousands of processor cores, using a Message Passing Interface (MPI) to share data and synchronize states between compute nodes in real time. (Fruboes et al. 2025)

This immense processing capability is vital for modern scientific research enabling simulations that would otherwise take years to finish. Important applications would include the following:

* **Climate Modeling** – Simulating global weather patterns, ocean currents, and long-term climate shifts to predict environmental changes.
* **Molecular Dynamics** – Simulating biological molecules at the atomic level, which serves as a foundational step in discovering life-saving medicines and understanding disease behaviors.
* **Aerospace Engineering** – Running computational fluid dynamics (CFD) simulations to analyze airflow over wings and rocket bodies, eliminating the need for constant, expensive physical wind-tunnel testing. (NVIDIA Technical Glossary 2026)

## 2.3 HPC Monioring and Performance Management

To keep complex HPC clusters operating efficiently, we need to constantly monitor and manage the performance of our environments. Monitoring platforms can collect massive amounts of time-series telemetry data from various layers of the cluster, such as hardware sensors, operating systems, hypervisors and network interfaces. (Data Science Clinic Analytics 2025)

System administrators must track thousands of variables at the same time to maintain operational awareness. Key metrics include:

* **CPU Utilization** – Tracking the processing loads across all cores to ensure that jobs are balanced and processors are not sitting idle or hitting continuous bottlenecks.
* **Memory Allocation** – Monitoring RAM usage to detect memory leaks, where a poorly written program continuously hogs memory until the node runs out of space and crashes. (Wentzel 2026)
* **Network Throughput** – Observing data transfer rates, packet drops, and latency across the cluster's network fabric to ensure communication between parallel processes remains unhindered.
* **Storage Input/Output (I/O)** – Measuring read and write speeds to shared parallel filesystems, ensuring data storage bottlenecks do not stall compute nodes.

Tracking these metrics effectively allows system administrators to ensure stability with the cluster, identify performance bottlenecks, optimize resource allocation, and ensure that intensive research simulation run to competition with unexpected interruptions.

## 2.4 Predictive Maintenance and Failure Management in HPC

Traditional failure management in HPC centers relies of reactive maintains which introduces serious limitations:


| Maintenance Strategy | Working Principle | Operational Limitations |
| :--- | :--- | :--- |
| **Reactive Maintenance** | Issues are only addressed after a component has already failed or crashed. | • Causes severe unscheduled downtime.<br>• Ruins active research workloads, forcing scientists to restart weeks-long simulations.<br>• Leads to high data recovery and hardware replacement costs. |
| **Conventional Preventative Maintenance** | Hardware is serviced or replaced based on a fixed schedule, regardless of the actual condition. | • Highly inefficient as healthy components are serviced prematurely.<br>• Relies on static, single-variable thresholds.<br>• Causes alert fatigue. |
| **Predictive Maintenance (Proposed Approach)** | Real-time multi-variable telemetry patterns are analyzed continuously by software. | • Identifies early indicators of performance degradation and anomalies.<br>• Catches failures before a crash happens.<br>• Allows for scheduled, targeted interventions without disrupting user jobs. |

Conventional monitoring frameworks rely on human-defined thresholds- such as triggering a critical alarm only when temperatures exceed 80 degrees or memory usage hits 95%. This approach is reactive, informing engineers after a failure has already occurred and disrupted workloads. To overcome this problem, the industry is shifting towards predictive maintenance. This allows for real-time data trends to be analyzed to spot early indicators of failure, allowing administrators to intervene before a full-scale failure happens.

## 2.5 Machine Learning for HPC Monitoring

Machine Learning (ML) shifts from reactive threshold monitoring to checking for proactive anomaly detection by tracking patterns across massive datasets. Unsupervised and semi-supervised ML algorithms are mostly suited for HPC environments because they don’t require pre-labeled failure data. Instead, they learn the cluster’s normal operating baseline and flag derivations.

Three prominent algorithmic approaches evaluated in modern research includes:

* **Isolation Forest** – This algorithm isolates anomalies instead of profiling normal data points by randomly selecting a feature and a split value between its maximum and minimum values. Because anomalies require fewer random splits to be isolated, they appear closer to the root of the decision trees, making this approach highly efficient for processing large streams of cluster telemetry.
* **One-Class Support Vector Machines (SVMs)** – A semi-supervised algorithm trained exclusively on data representing normal cluster operations (ResearchGate Publication Network 2025) that maps data into a high-dimensional space to establish a central boundary around normal points. Any live telemetry data falling outside this boundary is instantly flagged as an anomaly, making it excellent at identifying entirely new, unseen system errors. (Springer Nature 2025)
* **Autoencoders** – An unsupervised artificial neural network designed to compress input telemetry data into a lower-dimensional bottleneck layer and reconstruct the original input from this compression. When trained on normal system behavior, it learns to reconstruct normal data with very low error, while any anomalous system state results in a high reconstruction error that flags a potential failure.

## 2.6 Families of unsupervised anomaly detectors

Unsupervised detectors can be grouped by the notion of normality that they encode, and the six algorithms in this study were chosen to span these notions.

| Family | Algorithm | Notion of normality | Anomaly score | Scale sensitivity |
| --- | --- | --- | --- | --- |
| Isolation | Isolation Forest (Liu, Ting and Zhou, 2008) | Anomalies are few and easy to isolate by random partitioning | Shortness of average path length across the ensemble | Low: splits depend on feature order, not magnitude |
| Boundary | One-Class SVM (Schölkopf et al., 2001) | Normal data lie within a kernel-induced boundary around the training set | Signed distance from the learned boundary | High: kernel distances require standardisation |
| Density | Local Outlier Factor (Breunig et al., 2000) | Normal points have local density comparable to their neighbours | Ratio of neighbour density to local density | High: distance-based |
| Reconstruction | PCA (Jolliffe, 2002) | Normal data lie near a low-dimensional linear subspace | Reconstruction error from the retained components | High: variance-driven |
| Reconstruction | Autoencoder (Goodfellow, Bengio and Courville, 2016) | Normal data lie near a learned non-linear manifold | Reconstruction error of the network | High: gradient-based training |
| Probabilistic | Gaussian Mixture Model (McLachlan and Peel, 2000) | Normal data are generated by a mixture of Gaussians | Negative log-likelihood under the fitted mixture | High: covariance estimation |

## 2.7 HPC Telemetry and Data Processing for Machine Learning

Before raw cluster metrics can be fed into machine learning models, they must pass through a structured telemetry and data processing pipeline. In modern DevOps and cloud architectures, tools like Prometheus serve as the backbone for data collection. Prometheus uses lightweight software agents called "exporters" installed on each compute node. These exporters scrape hardware and operating system metrics at high frequencies (e.g., every 5 seconds) and pull them into a centralized, time-series metrics repository.

However, raw telemetry cannot be directly fed into Scikit-Learn machine learning algorithms because it is full of real-world irregularities. A dedicated data preprocessing pipeline must execute the following sequential stages:

1. **Data Cleaning** – Handles missing data points caused by temporary network drops or collection delays by applying interpolation methods to fill the gaps smoothly.
2. **Feature Alignment** – Synchronizes telemetry data arriving at slightly different timestamps as individual metrics, aligning these asynchronous streams into a unified time-series matrix.
3. **Data Normalization and Scaling** – Standardizes cluster metrics that use wildly different numerical scales (e.g., network throughput in millions of bytes vs. CPU utilization as a percentage) using Min-Max Scaling or Standardization to bring all metrics into a uniform range (such as 0 to 1) for optimal model performance.
4. **Feature Selection** – Drops redundant or uninformative metrics, such as static system configurations, to reduce data dimensionality and ensure machine learning models process the streams with minimal computational overhead.

## 2.8 Existing Research and Predictive HPC Monitoring Solutions

Considerable research has been conducted on predictive maintenance for large-scale enterprise infrastructures and traditional bare-metal supercomputers. Academic studies frequently explore how deep learning models can forecast disk drive failures or identify software deadlocks in specific physical clusters. In commercial settings, proprietary AIOps (Artificial Intelligence for IT Operations) platforms provide automated monitoring solutions.
However, these existing solutions often rely on closed-source, proprietary codebases that are highly expensive to license. Furthermore, these frameworks require massive training data footprints spanning several months or years of historical supercomputer logs. They are also designed exclusively for massive, bare-metal hardware infrastructures, making them incredibly rigid and difficult to customize, scale down, or apply to modern virtualized or containerized infrastructure environments.

## 2.9 Research Gap

Despite advancements in predictive analytics, a clear gap exists in the literature regarding accessible, open-source predictive monitoring frameworks tailored specifically for virtualized, cloud-based HPC environments. Most existing research focuses on large, physical supercomputers, ignoring the unique complexities—such as hypervisor resource contention, virtual network latency, and noisy-neighbor effects—found in virtualized infrastructures like OpenStack.

Furthermore, many proposed frameworks rely on heavy deep learning architectures that require massive computational overhead and dedicated GPUs just to run the monitoring system itself. There is a lack of documented research evaluating how lightweight, standard machine learning libraries (like Scikit-Learn) can be combined with popular, accessible open-source devops tools (like Prometheus and Grafana) to create an accessible, low-overhead early warning system. This leaves smaller research labs and institutions without a practical blueprint for protecting their virtualized clusters.

## 2.10 Literature Review Summary

In summary, while High-Performance Computing drives critical modern research, traditional reactive monitoring methods fall short of protecting these complex systems from disruptive and costly failures. Machine learning offers a powerful solution by detecting subtle, multi-variable anomaly signatures within telemetry streams before crashes occur. While previous research has successfully applied these algorithms to massive physical supercomputers, there is a clear lack of open-source, low-overhead frameworks designed for virtualized cloud environments. This research project directly addresses this gap by implementing an accessible predictive pipeline using Prometheus, Scikit-Learn, and Grafana within a four-node OpenStack environment, proving that proactive system safety can be achieved effectively, lightweight, and affordably.


# Chapter 3: Research Methodology

## 3.1 Research Design

This study adopts a design-and-development research methodology (Oates, 2006; Peffers et al., 2007) to construct, deploy and evaluate a machine-learning-based anomaly detection platform for High-Performance Computing (HPC) environments. The design-science paradigm is particularly appropriate for this investigation because the research objective is not merely to observe or describe a phenomenon but to create a purposeful artefact—a predictive monitoring system—and to evaluate its utility against clearly defined operational criteria (Hevner et al., 2004). The artefact encompasses the full operational pipeline: the collection of system-level monitoring telemetry from production compute nodes, the transformation of raw measurements into discriminative machine-learning features, the training and comparative evaluation of candidate anomaly-detection algorithms, and the deployment of the selected model as a service accessible to the cluster's monitoring infrastructure.

A comparative experimental approach is embedded within the broader design-science framework. Six candidate anomaly-detection algorithms, each representing a distinct mathematical formulation of the outlier-identification problem, are trained on the same prepared telemetry dataset and assessed under a consistent experimental protocol. The comparison examines how each algorithm responds to the statistical structure of HPC monitoring data and how frequently each produces anomaly designations in validation and testing periods that were withheld from training. This controlled comparison permits an empirical assessment of algorithmic suitability that extends beyond theoretical analysis alone.

The study further considers the practical implications of deploying machine-learning-based anomaly detection within a production-adjacent HPC environment. Particular attention is directed toward the reliability of anomaly identification, the prevalence of false-positive alerts, and the capacity of the system to deliver actionable warnings without generating excessive or misleading notifications—concerns that have been identified in the HPC operations literature as significant barriers to the adoption of automated monitoring (Tuncer et al., 2017; Borghesi et al., 2019). The investigation therefore addresses both the technical performance of candidate algorithms and the operational viability of the resulting detection system.

The overall research process is structured as a sequential progression through five interconnected phases: (i) monitoring infrastructure deployment and data collection, (ii) data preprocessing and quality management, (iii) feature engineering and dataset construction, (iv) model development, training and comparative evaluation, and (v) deployment of the selected model as an inference service integrated with the cluster's monitoring stack. This phased approach provides a systematic and reproducible basis for developing, evaluating and deploying an anomaly detection solution grounded in measurements obtained from the operational HPC environment.

## 3.2 Experimental Environment

### 3.2.1 System Hardware and Software Configuration

The hardware and software characteristics of the HPC cluster were established through system-level profiling of the head node and three compute nodes. The collection covered operating system configuration, processor architecture, allocated memory, network interfaces, storage resources and installed HPC software. This information provides a technical description of the environment in which telemetry was collected and machine-learning experiments were conducted.

**Table 3.1: HPC cluster overview.**

| Node | Role | Private IP address | Allocated logical CPUs | Reported memory | Local system disk |
| --- | --- | --- | --- | --- | --- |
| headnode | Head node | 10.100.0.240 | 4 | 7.8 GiB | 100 GB |
| compute001 | Compute node | 10.100.0.198 | 8 | 15 GiB | 150 GB |
| compute002 | Compute node | 10.100.0.167 | 8 | 15 GiB | 150 GB |
| compute003 | Compute node | 10.100.0.66 | 8 | 15 GiB | 150 GB |

**Table 3.2: Operating system and kernel information.**

| Field | headnode | compute001 | compute002 | compute003 |
| --- | --- | --- | --- | --- |
| Operating system | Ubuntu 22.04.5 LTS | Ubuntu 22.04.5 LTS | Ubuntu 22.04.5 LTS | Ubuntu 22.04.5 LTS |
| Kernel version | 5.15.0-1095-kvm | 5.15.0-1095-kvm | 5.15.0-1095-kvm | 5.15.0-1095-kvm |
| Architecture | x86_64 | x86_64 | x86_64 | x86_64 |
| Virtualisation | KVM | KVM | KVM | KVM |

**Table 3.3: CPU architecture and specifications.**

| Field | Head node | Compute nodes |
| --- | --- | --- |
| CPU vendor | AMD | AMD |
| Reported CPU model | AMD EPYC-Rome Processor | AMD EPYC-Rome Processor |
| Architecture | x86_64 | x86_64 |
| Allocated logical CPUs | 4 | 8 per node |
| Threads per core | 1 | 1 |
| Cores per socket reported by guest | 1 | 1 |
| Sockets reported by guest | 4 | 8 per node |
| NUMA nodes | 1 | 1 |
| L1 data cache | 128 KiB (4 instances) | 256 KiB (8 instances) |
| L1 instruction cache | 128 KiB (4 instances) | 256 KiB (8 instances) |
| L2 cache | 2 MiB (4 instances) | 4 MiB (8 instances) |
| L3 cache | 64 MiB (4 instances) | 128 MiB (8 instances) |

The reported processor topology and cache information are obtained from lscpu inside the virtual machines. They should not be interpreted as a description of the physical host processor topology. CPU frequency information was not exposed by the virtualised environment.

**Table 3.4: Memory configuration.**

| Field | Head node | Each compute node |
| --- | --- | --- |
| Guest-reported total memory | 7.8 GiB | 15 GiB |
| Memory device size reported by SMBIOS | 8 GB | 16 GB |
| Number of memory devices reported | 1 | 1 |
| Swap memory | 0 GiB | 0 GiB |
| Memory speed | Not available | Not available |
| Memory manufacturer reported by SMBIOS | Red Hat | Red Hat |

The memory capacity is consistent across the three compute nodes. The SMBIOS information is presented by the virtual machines, and memory speed and physical module specifications are not available from these reports.

**Table 3.5: Network interfaces and connectivity.**

| Node | Primary Interface | IP Address | State | Network Device |
| --- | --- | --- | --- | --- |
| headnode | enp3s0 | 10.100.0.240 | UP | Red Hat Virtio |
| compute001 | enp3s0 | 10.100.0.198 | UP | Red Hat Virtio |
| compute002 | enp3s0 | 10.100.0.167 | UP | Red Hat Virtio |
| compute003 | enp3s0 | 10.100.0.66 | UP | Red Hat Virtio |

All four nodes communicate through the private 10.100.0.0/24 network. The compute nodes also access shared directories hosted by the head node. The virtual network interfaces were detected successfully; however, the physical network adapter specifications and negotiated link speeds were not exposed by the guest operating systems.

**Table 3.6: Storage configuration.**

| Node | Local disk | Root filesystem | Additional storage |
| --- | --- | --- | --- |
| headnode | 100 GB (vda) | ext4, / | 200 GB disk (vdb) detected but not mounted |
| compute001 | 150 GB (vda) | ext4, / | NFS shared directories |
| compute002 | 150 GB (vda) | ext4, / | NFS shared directories |
| compute003 | 150 GB (vda) | ext4, / | NFS shared directories |

The compute nodes access shared storage provided by the head node through Network File System (NFS) version 4.2. The reported shared mounts are:

**Table 3.7: Shared NFS mounts.**

| NFS export | Mount point | Filesystem |
| --- | --- | --- |
| headnode:/home/ubuntu | /home/ubuntu | NFS 4.2 |
| headnode:/shared | /mnt/shared | NFS 4.2 |

At the time of profiling, the shared filesystem reported approximately 97 GB total capacity, 52 GB used and 46 GB available. These are shared filesystem figures, not additional local storage capacities for each compute node.

**Table 3.8: HPC software environment.**

| Software component | Head node | Compute001 | Compute002 | Compute003 |
| --- | --- | --- | --- | --- |
| Slurm | 21.08.5 | 21.08.5 | 21.08.5 | 21.08.5 |
| OpenMPI | 4.1.4 | 4.1.2 | 4.1.2 | 4.1.2 |
| GCC | 11.4.0 | 11.4.0 | 11.4.0 | 11.4.0 |
| Python | 3.10.12 | 3.10.12 | 3.10.12 | 3.10.12 |
| CMake | 3.22.1 | 3.22.1 | 3.22.1 | 3.22.1 |
| Docker | 29.9.1 | 29.9.1 | 29.9.1 | 29.9.1 |
| OpenBLAS | 0.3.20 | Version not established | Version not established | Version not established |

An important configuration difference is that the head node uses OpenMPI 4.1.4 installed under /home/ubuntu/opt/openmpi, whereas the compute nodes report OpenMPI 4.1.2 installed under /usr/bin. This difference should be considered when describing the MPI execution environment

### 3.2.2 Cluster Architecture and Computational Infrastructure

The experiments reported in this study are conducted on a purpose-built, small-scale High-Performance Computing cluster comprising one head node and three compute nodes interconnected through a dedicated local-area network. The head node serves as the central management, scheduling and monitoring platform, while the three compute nodes provide the computational resources upon which user workloads, benchmark applications and controlled experimental scenarios are executed. All four nodes operate Ubuntu Linux as their base operating system.

Workload management and resource allocation are governed by the Slurm Workload Manager (Yoo, Jette and Grondona, 2003), which provides job scheduling, queue management and resource accounting across the compute partition. Slurm's role in the experimental environment is significant beyond simple job dispatch: it generates accounting records and node-state transitions that contribute to the operational telemetry available for analysis. The use of a recognised production-grade scheduler ensures that the workload patterns, resource contention dynamics and scheduling artefacts observed in the experimental environment are representative of those encountered in larger production HPC installations.

This small-scale cluster architecture is consistent with the experimental environments employed in comparable anomaly detection studies in the HPC literature. Tuncer et al. (2017) demonstrated that anomaly detection techniques developed on modest test clusters can reveal operationally meaningful patterns, while Ates et al. (2019) validated their HPC Performance Anomaly Suite (HPAS) framework on clusters of similar scale. The cluster used in the present study provides a sufficiently complex environment to observe multi-dimensional resource interactions—CPU saturation affecting memory pressure, I/O contention propagating to network subsystems, and workload-induced thermal effects—while remaining tractable for systematic experimental control.

## 3.3 Data Collection

The empirical foundation of this study rests upon monitoring telemetry collected directly from the operational HPC cluster through the Prometheus and Node Exporter infrastructure described in Section 4.2. Unlike studies that rely upon externally provided or publicly available benchmark datasets—such as the Marconi-100 dataset (Borghesi et al., 2023) or the Blue Gene/L system logs (Oliner and Stearley, 2007)—the present investigation uses data generated by and collected from the same cluster environment on which the anomaly detection models are ultimately deployed. This design choice ensures that the statistical properties of the training data, including its distributional characteristics, temporal autocorrelation structure and inter-metric dependencies, are fully representative of the operational conditions under which the deployed model must perform.

### 3.3.1 Monitoring Configuration and Scrape Architecture

Prometheus was configured with a global scrape interval of 15 seconds and monitored the head node together with the three compute nodes. The monitoring architecture and deployed target configuration are described in Section 4.2.

The 15-second scrape interval was selected to balance temporal granularity against storage overhead. It provides sufficient resolution to capture transient resource-utilisation events while remaining within the storage and query-performance constraints of the single-node Prometheus deployment. This interval is consistent with monitoring configurations reported in comparable HPC telemetry studies (Borghesi et al., 2019; Netti et al., 2021).

### 3.3.2 Data Extraction Procedure

Historical monitoring measurements were retrieved from the Prometheus time-series database using a purpose-built Python extraction script that communicates with the Prometheus HTTP API. The script queries the /api/v1/query_range endpoint, which supports the retrieval of time-series data over specified temporal intervals at a configurable query resolution.

The extraction process was designed to retrieve 27 distinct metric families encompassing the full breadth of system-level telemetry exposed by Node Exporter. For each retrieved observation, the extraction script preserves five fields: the observation timestamp, the node identifier (derived from the Prometheus instance label), the metric name, any associated Prometheus labels (such as device identifiers, CPU modes or filesystem mount points), and the measured value. The extracted records are written into a long-format CSV dataset, a structure that preserves the original Prometheus metric semantics and permits the reconstruction of individual time-series during subsequent preprocessing.

A methodological detail warrants explicit documentation. The extraction script specifies a five-second query step in its API requests. However, because the underlying Prometheus scrape interval is 15 seconds, the Prometheus TSDB does not contain independent observations at five-second resolution. The query engine returns the most recently ingested value for each five-second evaluation point, resulting in the same underlying observation appearing at multiple query timestamps. This duplication is resolved during the preprocessing stage (Section 3.4.2) by deduplicating observations based on their original scrape timestamps. The five-second query step was employed to minimise the risk of missing observations near scrape boundaries, not to synthesise higher-resolution data. To manage the computational and memory demands of querying large time ranges, the extraction process partitions the overall collection period into smaller temporal windows and retrieves each window independently. The resulting partial datasets are subsequently concatenated into a single consolidated dataset covering the full collection period.

### 3.3.3 Dataset Characteristics and Coverage

The 27 collected metric families span the following operational domains:

**Table 3.9: Collected telemetry domains and representative metrics.**

| Domain | Representative Metrics |
| --- | --- |
| CPU activity | Per-mode CPU time (user, system, idle, iowait, irq, softirq, steal), system load averages (1-, 5-, 15-minute) |
| Memory | Total, available and free memory; buffer and cache allocations; swap utilisation |
| Disk I/O | Read and write operations completed; bytes read and written; I/O time; weighted I/O time; outstanding operations |
| Network | Bytes received and transmitted per interface; packets received and transmitted; receive and transmit errors; dropped packets |
| TCP | Active and passive connection openings; established connections; retransmitted segments |
| Filesystem | Total, available and free bytes per mount point; filesystem device and mount metadata |
| System availability | Node boot time; Node Exporter scrape duration and success indicators |

This breadth of telemetry coverage is intentional. Anomaly detection in HPC environments must contend with the multi-dimensional nature of system behaviour: a failing storage controller may manifest simultaneously as elevated disk I/O latency, increased CPU iowait time and degraded application throughput (Schroeder and Gibson, 2006). Restricting the collected telemetry to a single subsystem would risk excluding the correlated signals upon which effective anomaly detection depends. The raw dataset is stored in a five-field long-format structure (timestamp, node, metric, labels, value). This format is intentionally denormalised: each row represents a single scalar measurement at a single point in time on a single node for a single metric series. While this structure results in a large number of rows, it preserves the complete Prometheus label metadata, permits flexible reconstruction of arbitrary metric combinations during preprocessing, and avoids the schema rigidity of a wide-format representation in which each metric would occupy a separate column.

## 3.4 Data Processing Methodology

The transformation of raw monitoring telemetry into structured machine-learning input is a multi-stage process that constitutes a substantial portion of the analytical effort in this study. Raw Prometheus measurements—cumulative counters, instantaneous gauges and metadata labels—cannot be consumed directly by machine-learning algorithms. They must be cleaned, validated, derived into meaningful resource-activity indicators, aggregated to appropriate temporal resolutions and engineered into features that capture the operational dynamics of the monitored nodes. The preprocessing pipeline described in this section was designed to preserve data integrity, handle the specific characteristics of Prometheus counter metrics, and produce features that are both statistically meaningful and operationally interpretable.

### 3.4.1 Data Organisation and Metric Reconstruction

The extracted telemetry was retained initially in a long-format representation in which each row represented a single metric observation associated with a node, timestamp and Prometheus label set. The data-processing methodology reconstructed individual metric series using the node identifier, metric name and complete label set, then ordered the observations chronologically. This organisation provided the basis for validating successive measurements, deriving rates from cumulative counters and combining measurements from different resource subsystems.

Two related analytical workflows were used in the project. The DuckDB-based V6 feature-engineering workflow provided the one-minute candidate dataset used by the final comparative model-training pipeline. A separate Pandas-based workflow in Google Colab produced the strict 17-feature dataset used for exploratory clustering. These datasets and their different purposes are distinguished in the relevant implementation and results sections; their row counts and partitions are not interchangeable.

### 3.4.2 Data Cleaning and Quality Management

Data cleaning was performed to minimise the influence of measurement artefacts and inconsistencies before telemetry was transformed into machine-learning features. Although the initial raw extraction contained no missing values in its five structural fields, the monitoring data still required further validation. In particular, Prometheus metrics include cumulative counters whose values must be processed carefully, while temporary interruptions in metric collection can produce irregular observation intervals.

The cleaning process addressed five principal areas: duplicate observations, counter resets, temporal gaps, invalid measurements and filesystem context.

Duplicate observation handling

The extraction process used a five-second query step when retrieving historical measurements from Prometheus, while the underlying monitoring infrastructure collected data at 15-second intervals. Consequently, the extraction resolution did not represent an independent five-second sampling frequency. The same underlying scrape observation could be returned at multiple query evaluation points.

To prevent these repeated values from being treated as independent measurements, observations were checked using their original timestamps, node identifiers and metric-series identifiers. The metric-series identifiers included the relevant Prometheus labels, allowing measurements from different CPUs, interfaces, devices or filesystem mount points to remain distinct. Repeated representations of the same underlying observation were removed before subsequent time-series processing.

Counter-reset detection and rate derivation

Several Node Exporter metrics are cumulative counters that increase over time. Examples include CPU time, network bytes transmitted and received, and disk bytes read and written. These counters do not directly represent resource activity over a particular interval. Their changes between successive observations must be calculated to derive rates such as CPU utilisation and network or disk throughput.

For a cumulative counter (C), the change between successive valid observations is calculated as:
\[
\Delta C_t = C_t-C_{t-1}
\]

The corresponding rate is:
\[
R_t=\frac{\Delta C_t}{\Delta t}
\]

where (\Delta t) represents the elapsed time between the two observations.

A complication arises when a counter resets, for example following a node restart or exporter-related interruption. In such cases, the current counter value may be lower than the preceding value. Calculating a rate directly across this boundary would produce a negative result that does not represent valid resource activity.

The processing pipeline therefore checked successive counter differences for negative values. Where a counter reset was identified, the affected rate was treated as unavailable rather than being interpreted as negative activity or replaced with zero. This conservative approach prevented reset-related artefacts from distorting the derived resource measurements.

Temporal gaps and observation intervals

The expected monitoring interval was 15 seconds, based on the configured Prometheus scrape interval. However, interruptions in collection can result in successive observations being separated by longer intervals. Such gaps may arise from temporary network interruptions, monitoring-service disruptions or periods when a monitored node is unavailable.

The processing pipeline evaluated elapsed time between successive observations within each metric series. Where an interval exceeded the 20-second maximum accepted interval, the corresponding rate calculation was suppressed. This prevented the processing stage from treating activity accumulated over an extended, incompletely monitored interval as though it had occurred within a normal 15-second observation period. Importantly, a missing observation interval was not treated as evidence of zero resource utilisation. Suppressing the derived rate preserved the distinction between an absence of measured activity and an absence of valid measurement data.

Invalid measurement handling

Measurements were also assessed for conditions that could make them unsuitable for feature construction. These included zero or negative elapsed time intervals, negative counter differences associated with resets and unavailable measurements resulting from incomplete or invalid source observations. Where a derived measurement could not be validated, it was retained as unavailable during the relevant processing stage rather than being silently replaced with zero or an interpolated value. This distinction was important because zero is a legitimate resource measurement in an HPC environment. For example, a compute node may genuinely record negligible network transmission or disk activity during an idle period. Replacing unavailable measurements with zero would therefore introduce values that could be mistaken for genuine low-activity conditions. Quality indicators were retained in the derived datasets to distinguish observations that passed the applicable validation checks from those that required exclusion or further consideration.

Filesystem context differentiation

Filesystem measurements required additional treatment because the cluster used both local storage and shared Network File System (NFS) mounts. These storage resources serve different operational purposes and exhibit different utilisation characteristics.

Local root-filesystem measurements were distinguished from measurements associated with shared NFS mounts. This distinction was necessary because local filesystem exhaustion represents a condition affecting an individual compute node, whereas shared-filesystem utilisation reflects storage resources accessed by multiple nodes. The distinction was maintained during feature preparation so that local filesystem measurements could be interpreted as part of an individual compute node's operational state. Shared-storage measurements remained available as monitoring context rather than being treated as interchangeable with local filesystem utilisation.

Outcome of the cleaning process

The cleaning procedures established a consistent basis for deriving resource measurements from the raw Prometheus telemetry. Duplicate representations were removed, counter resets and extended observation intervals were prevented from producing misleading rates, invalid measurements were retained as unavailable, and local and shared filesystem observations were distinguished. These procedures were important for preserving the integrity of the subsequent feature-engineering process. In particular, they reduced the risk that monitoring artefacts would be interpreted by the machine-learning models as genuine resource behaviour. The resulting cleaned telemetry was then used to construct the 15-second feature dataset and the aggregated one-minute representation described in the following section.

In the V6 DuckDB implementation, the maximum accepted interval was configured as 20 seconds (`LONG_GAP_SECONDS = 20.0`). CPU interval alignment was additionally checked against a tolerance of 0.25 seconds. Counter-derived CPU, network and disk rates were set to unavailable when the relevant interval was incomplete, misaligned, reset, invalid or longer than the configured gap threshold.

### 3.4.3 Temporal Aggregation

Following data cleaning, the validated telemetry is organised into two temporal resolutions to support different analytical requirements.

The 15-second dataset retains the original scrape-level temporal granularity. At this resolution, each observation represents a single Prometheus scrape, preserving the finest available temporal detail of resource-activity dynamics. This resolution is valuable for investigating short-duration transient events—such as brief CPU saturation episodes during job startup or momentary memory pressure spikes—that may be attenuated or obscured by coarser aggregation.

The one-minute dataset aggregates the 15-second observations into 60-second windows. For each metric, each node and each one-minute interval, the aggregation process computes five summary statistics: the arithmetic mean, minimum, maximum, standard deviation and 95th percentile of the constituent observations. Sample counts and data-quality indicators (such as the number of valid observations within each window) are also retained to provide contextual information about the completeness of each aggregated record.

The one-minute resolution was selected as the primary input for model development for several reasons. First, it reduces the dataset volume by a factor of approximately four, which accelerates model training and hyperparameter exploration without sacrificing the temporal patterns relevant to anomaly detection at the operational timescales of interest (minutes to hours rather than seconds). Second, the within-window statistical summaries—particularly the standard deviation and 95th percentile—capture intra-minute variability that would be lost in a simple downsampling approach. Third, one-minute aggregation is consistent with the temporal resolutions commonly employed in HPC monitoring and anomaly detection studies (Tuncer et al., 2017; Borghesi et al., 2019), facilitating methodological comparability.



# 4. Raw HPC Telemetry Observation & Exploratory Analysis Notebook

## 4.1. Notebook Purpose, Execution Environment, and Dataset Architecture. 

In this section, we will be referencing the work done in the Jupyter notebook called "HPC_Dataset_Observation_Before_Cleaning_Modified".The primary objective of this Jupyter notebook is to conduct a strict, read-only observational audit of the raw Prometheus High-Performance Computing (HPC) telemetry dataset (raw_hpc_full.parquet) prior to any data cleaning, imputation, normalization, or feature engineering. By enforcing an immutable source-of-truth policy, the notebook evaluates whether the raw telemetry can reliably support three downstream machine-learning goals:

1. **Modelling normal cluster operating regimes**
2. **Detecting anomalous system behaviour**
3. **Predicting node or cluster failures ahead of occurrence**

* **Structural Dimensions:** The dataset contains **49,616,574 rows** across **5 columns** (248,082,870 total cells).
* **Long-Format Semantics:** Each row captures a single observation of one labelled Prometheus time series at a specific scrape timestamp. Consequently, repeated `(node_id, timestamp)` pairs are expected because each 15-second scrape emits hundreds of individual metric-label series simultaneously.

## 4.2. Data Integrity, Temporal Coverage and Sampling Audit

Sections 4 through 11 of the notebook verify structural completeness, deduplication keys, and temporal continuity across the cluster.

* **Missingness & Duplication:** Across all 49.62 million rows, there are **0 missing cells (0.000%)**, **0 exact duplicate rows**, and **0 duplicate time-series observations** when evaluated on the composite primary key `(node_id, metric, labels, timestamp)`.
* **Monitoring Horizon:** Converting `timestamp` from Unix epoch seconds establishes an exact UTC observation window from **`2026-10-18 00:00:04.336 UTC`** to **`2026-10-31 23:59:58.588 UTC`**, spanning **335.996 hours (14.00 days)**.
* **Scrape Interval Verification:** Dividing total elapsed seconds (`1,209,585s`) by `(distinct_scrape_timestamps - 1)` confirms a steady **15.0-second scrape interval** on every node.


| Node ID | Total Metric Rows | Distinct Scrape Timestamps | First Seen (UTC) | Last Seen (UTC) | Duration (Hours) | Approx. Interval |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`compute001`** | 13,061,640 | 80,639 | `2026-10-18 00:00:04.336` | `2026-10-31 23:59:49.336` | 335.9958 | 15.0 s |
| **`compute002`** | 12,789,782 | 80,639 | `2026-10-18 00:00:13.588` | `2026-10-31 23:59:58.588` | 335.9958 | 15.0 s |
| **`compute003`** | 12,789,104 | 80,639 | `2026-10-18 00:00:08.353` | `2026-10-31 23:59:53.354` | 335.9958 | 15.0 s |
| **`headnode`** | 10,976,048 | 80,640 | `2026-10-18 00:00:12.438` | `2026-10-31 23:59:57.437` | 335.9958 | 15.0 s |

** **Architectural Differences Across Nodes:** `headnode` contributes ~1.8–2.1 million fewer rows than the compute nodes despite having one additional scrape timestamp (`80,640` vs. `80,639`). This reflects hardware/configuration differences (4 logical CPUs on `headnode` versus 8 logical CPUs on each compute node, plus different mounted filesystems), which reduces the cardinality of `node_cpu_seconds_total` series on `headnode`.

---

## 4.3 Metric Inventory, Statistical Distributions, and Time-Series Behaviour (Sections 7, 12–18)

Because the `value` column mixes heterogeneous physical units (cumulative CPU seconds, bytes, load ratios, process counts, and binary health flags), the notebook explicitly avoids global aggregation or raw correlation across mixed metrics. Instead, Section 18 inventories all **27 metric families** across **638 unique label series** and classifies them heuristically by naming convention into **10 cumulative counters** (`_total`) and **17 gauges/other indicators**.

### Summary of the 27 Collected Metric Families

| Subsystem | Metric Name | Heuristic Type | Rows | Label Series | Key Statistical Observations (`min` / `median` / `max`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **CPU & Load** | `node_cpu_seconds_total` | Counter | 18,062,592 | 224 | `0.0` / `33.26` / `1,300,857.0` s (8 modes × cores across 4 nodes) |
| | `node_load1` / `load5` / `load15` | Gauge | 322,544 each | 4 each | `0.0` / `0.0` / `13.30` (`load1`), `7.34` (`load5`), `5.22` (`load15`) |
| **Memory** | `node_memory_MemTotal_bytes` | Gauge | 322,544 | 4 | `8.35 GB` (`headnode`) vs. `16.79 GB` (compute nodes) |
| | `node_memory_MemAvailable_bytes` | Gauge | 322,544 | 4 | `40.72 MB` min / `16.34 GB` median / `16.36 GB` max |
| | `node_memory_MemFree_bytes` | Gauge | 322,544 | 4 | `47.13 MB` min / `13.20 GB` median / `14.36 GB` max |
| | `node_memory_SwapTotal_bytes` / `SwapFree` | Gauge | 322,544 each | 4 each | Constant `0.0` across all nodes (swap disabled) |
| **Disk I/O** | `node_disk_read_bytes_total` | Counter | 394,912 | 5 | `1.07 MB` / `765.87 MB` / `163.07 GB` |
| | `node_disk_written_bytes_total` | Counter | 394,912 | 5 | `0.0` / `42.56 GB` / `67.60 GB` |
| | `node_disk_io_time_seconds_total` | Counter | 394,912 | 5 | `0.02` / `459.90` / `5,592.58` s |
| | `node_disk_io_now` | Gauge | 394,912 | 5 | `0.0` / `0.0` / `426.0` concurrent I/O operations |
| **Network & TCP** | `node_network_receive_bytes_total` | Counter | 1,041,580 | 13 | `0.0` / `490.10 MB` / `364.84 GB` |
| | `node_network_transmit_bytes_total` | Counter | 1,041,580 | 13 | `306.0 B` / `140.98 MB` / `364.84 GB` |
| | `node_network_receive_drop_total` | Counter | 1,041,580 | 13 | `0.0` / `0.0` / `1.0` packet |
| | `node_network_receive_errs_total` / `tx_errs` / `tx_drop` | Counter | 1,041,580 each | 13 each | Constant `0.0` across the entire 14-day window |
| | `node_netstat_Tcp_RetransSegs` | Counter* | 322,544 | 4 | `3.0` / `347.0` / `69,143.0` cumulative segments (*classified as Gauge by suffix heuristic, but semantically a counter) |
| **Filesystem** | `node_filesystem_avail_bytes` / `size_bytes` | Gauge | 1,876,918 each | 33 each | Covers local disks (`/dev/vda1`, `/dev/vda15`) and NFS mounts |
| **Process & Scrape** | `node_procs_running` / `procs_blocked` | Gauge | 322,544 each | 4 each | Running: `1.0` median / `19.0` max; Blocked: `0.0` median / `9.0` max |
| | `node_scrape_collector_success` | Gauge | 15,777,920 | 198 | Binary (`0.0` or `1.0`); `0.6825` mean (some collectors disabled/unavailable, e.g., `zfs`, `infiniband`) |
| | `scrape_duration_seconds` | Gauge | 322,557 | 4 | `8.62 ms` min / `12.91 ms` median / `17.19 s` max |
| | `up` | Gauge | 322,557 | 4 | `0.99996` mean (13 scrapes with `up == 0.0` across 322,557 node-scrapes) |

### Key Analytical Findings from Sections 12–17

* **Extreme Right-Skewness & Zero-Inflation:** IQR screening (Section 13) shows that metrics like `node_load1`, `node_load5`, `node_load15`, `node_procs_blocked`, and `node_disk_io_now` have `Q1 = Q3 = 0.0` (`IQR = 0`), reflecting long idle periods punctuated by intense bursts during benchmark executions (`node_load1` reaching `13.30`, `node_memory_MemAvailable_bytes` dropping from `16.34 GB` down to `40.72 MB`).
* **Absence of Ground-Truth Failure Labels:** Section 16 scans all column names for fault/event tokens (`event`, `failure`, `anomaly`, `label`, `fault`, `error`) and confirms that **only `labels` (Prometheus dimension metadata) exists**—meaning the raw telemetry contains no embedded ground-truth failure labels.

---

## 4.4 Focused `stress-ng` Case Study (21 Oct 2026), Bug Diagnosis, and Readiness Assessment (Sections 19–22)

Section 19 isolates a 3-hour window on **21 October 2026** around a known `stress-ng` workload (`19:00–20:00 SAST` / `17:00–18:00 UTC`), yielding **443,168 rows** partitioned into three 1-hour phases: **Before** (`16:00–17:00 UTC`), **During** (`17:00–18:00 UTC`), and **After** (`18:00–19:00 UTC`).

### Methodology & Technical Bug Identified in Execution

* **Counter-to-Rate Conversion:** The code sorts counter series by `(node_id, metric, labels, timestamp)`, computes consecutive differences (`delta_value / delta_seconds`), filters out negative deltas (counter resets) and `delta_seconds <= 0`, and derives 11 rate-based features (`derived_cpu_busy_percent`, disk read/write/IO-time rates, network RX/TX/error/drop rates, and TCP retransmission rates) alongside 10 gauge metrics.
* **Root Cause of the `InvalidIndexError` in Cell 21:** When Cell 21 ran, `pd.concat([gauge_data, derived_data])` failed with `InvalidIndexError: Reindexing only valid with uniquely valued Index objects`. Cell 22 diagnosed the exact cause: `derived_data` had duplicate column names `['timestamp', 'node_id', 'metric', 'value', 'value']` because `cpu_busy` originally named its metric column `cpu_busy_percent` before the fix was edited into Cell 21 (which has not yet been re-executed since the fix was applied). Re-running Cell 21 from top to bottom will resolve the error cleanly because Cell 24 confirms all 11 individual frames in `derived_frames` now have unique columns.
* **Unexecuted Final Cells:** Because execution halted at Cell 21, **Section 20** (automated raw-data quality summary table) and **Section 22** (exporting summary CSVs to `/shared/collab/hpc_dataset_observation/`) have not yet been executed.

### Research Suitability Assessment (Section 21)

1. **Normal-Behaviour Learning (Suitable with Caveats):** Complete 14-day coverage across 4 nodes with a stable 15-second scrape cadence provides ample idle and workload data, though `headnode` (`8 GB` RAM, 4 cores) must be modelled separately from compute nodes (`16 GB` RAM, 8 cores).
2. **Anomaly Detection (Suitable with Feature Engineering):** Multi-subsystem metrics capture correlated CPU, memory, disk, and TCP retransmission spikes, provided cumulative counters (including `node_netstat_Tcp_RetransSegs`) are converted to rates and `node_scrape_collector_success` / `up` flags are used to filter invalid scrapes.
3. **Failure Prediction (Requires External Ground-Truth Alignment):** Because the Parquet file contains zero failure labels and only 13 `up == 0` scrape events, supervised failure prediction cannot be trained or evaluated without joining external Slurm job logs and controlled fault-injection timestamps.

# Chapter 5: Dataset Characteristics and Coverage

## 5.1. Exposed OS-level Telemetry (What we collected)
o understand how the cluster works and behaves, we collected system metrics using Prometheus and Node Exporter. Node Exporter is responsible for reading the live data directly from the Linux operating system virtual folder (/proc and /sys). Prometheus is responsible for pulling these measurement every specific time interval. These metrics from the cluster produced 49 616 574 raw records across 27 different metric groups.

Each raw record is stored in a simple five-column format using the following: the exact timestamps, the node name, the metric name, extra labels such as the CPU core and hard drive and the measured number. Keeping this raw format data allows us to rebuild the exact timeline for every single part of the system later on in our model.

The metrics were successful collected to cover seven main areas of the operating system:

| System Area | What We Measured | Where Linux/Prometheus Gets It |
| :--- | :--- | :--- |
| **CPU Activity** | How much time the CPU spent running user tasks, system tasks, sitting idle, or waiting for slow storage (iowait), plus 1-, 5-, and 15-minute system load averages. | `/proc/stat`, `/proc/loadavg` (`node_cpu_seconds_total`, `node_load*`) |
| **Memory (RAM)** | Total memory on the node, how much is currently in use, how much is free, how much is truly available for new programs, and swap usage. | `/proc/meminfo` (`node_memory_*`) |
| **Disk Storage (I/O)** | How many read and write actions finished, how many megabytes were read or written, how long the disk was busy, and how many disk requests were waiting in line. | `/proc/diskstats` (`node_disk_*`) |
| **Network Traffic** | How many bytes and packets were sent and received on the main network card (`enp3s0`), plus any network errors or dropped packets. | `/proc/net/dev` (`node_network_*`) |
| **TCP Connections** | How many network connections opened, how many stayed active, and how many data packets had to be sent again (retransmissions) because of network trouble. | `/proc/net/snmp`, `/proc/net/netstat` (`node_netstat_Tcp_*`) |
| **File Storage Space** | Total disk space, used space, and free space on each drive, keeping the node's own local hard drive separate from the shared network storage (NFS). | `statfs()` system call (`node_filesystem_*`) |
| **System Health** | When the node last booted up, how many programs were actively running or stuck waiting, and whether Prometheus successfully collected data on time. | `/proc/stat`, `/proc/uptime` (`node_boot_time_seconds`, `node_procs_*`, `up`) |

## 5.2. Unexposed Hardware & Out-of-Band Telemetry
We collected this data across seven key areas on purpose. This is because in an HPC cluster, the problem rarely shows on one metric. In order to idea what caused a problem or to identify what caused the problem, you need to look at a combination of patterns which we would be identified by looking at several combinations of metrics. For example, if a storage drive slows down, you will often see disk queue times go up, CPU iowait rise and running programs stall all in the same time. Keeping track of all seven areas together gives our machine-learning models the full picture of what is happening on a compute node.


## 5.3 Metric Inventory, Statistical Distrbutions, and Time-Series Behaviour.

In this part, wer are referring to section 7 and 12-18 of the notebook. Because the value column mixes heterogeneous physical units (cumulative CPU seconds, bytes, load ratios, process counts, and binary health flags), the notebook explicitly avoids global aggregation or raw correlation across mixed metrics. Instead, Section 18 inventories all 27 metric families across 638 unique label series and classifies them heuristically by naming convention into 10 cumulative counters (_total) and 17 gauges/other indicators.


| Column Name | Data Type | Non-Null Count | Null Count | Unique Values | In-Memory Size | Role & Representation |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`timestamp`** | `float64` | 49,616,574 | 0 | 322,557 | 378.55 MB | Unix epoch timestamp in seconds (`unit='s'`, UTC) |
| **`node_id`** | `str` | 49,616,574 | 0 | 4 | 830.79 MB | Host identifier (`compute001`, `compute002`, `compute003`, `headnode`) |
| **`metric`** | `str` | 49,616,574 | 0 | 27 | 1,595.02 MB | Prometheus/Node Exporter metric family name |
| **`labels`** | `str` | 49,616,574 | 0 | 638 | 4,934.46 MB | Pipe-delimited dimensional metadata (`cpu`, `device`, `mode`, `instance`, etc.) |
| **`value`** | `float64` | 49,616,574 | 0 | 3,937,410 | 378.55 MB | Scalar measurement mixing counter totals, bytes, ratios, and gauges |



# Chapter 6: System Architecture and Implementation

## 6.1 Overall System Architecture

The implemented system combines the HPC compute environment, monitoring infrastructure, telemetry-processing pipeline, machine-learning components and an inference service. The monitoring layer exposes node-level measurements through Node Exporter and collects them centrally through Prometheus. Historical telemetry is extracted and processed into resource-oriented feature datasets. The machine-learning pipeline prepares the final feature matrix, trains and compares candidate anomaly-detection algorithms, and exports the selected Isolation Forest model and detection threshold. A FastAPI inference service loads these artefacts, maintains per-node observation history and returns anomaly assessments when the required temporal context is available.

The architecture is presented in terms of its implemented components and data-processing responsibilities. The service is deployed on the head node and binds to the loopback interface; therefore, direct observation submission from compute nodes or external systems is not established by the current deployment description.

## 6.2 Monitoring Infrastructure

The collection of system-level telemetry is facilitated through the integration of two complementary open-source monitoring components: Prometheus (Prometheus Authors, 2023) and Node Exporter (Prometheus Authors, 2023).

Node Exporter is deployed on each of the four cluster nodes. It operates as a lightweight daemon process that reads hardware and operating-system-level metrics from the Linux kernel's virtual filesystems (/proc, /sys) and exposes them through an HTTP endpoint on port 9100. The metrics exposed include CPU scheduling statistics, memory allocation and availability counters, block-device I/O operations, network interface traffic and error counters, filesystem capacity and utilisation, thermal sensor readings where available, and process scheduling statistics. Node Exporter does not store data; it functions solely as a real-time metrics exporter, presenting the instantaneous state of the host system upon each request.

Prometheus operates on the head node as the central time-series collection and storage engine. It employs a pull-based monitoring architecture, periodically issuing HTTP requests to each Node Exporter endpoint to retrieve the current metric values. The retrieved measurements are stored as time-series data in Prometheus's local time-series database (TSDB), indexed by metric name, label set and observation timestamp. This pull-based model is a deliberate architectural choice within the Prometheus ecosystem: it decouples the instrumentation of monitored targets from the collection schedule, permits centralised control of scrape frequency, and ensures that the monitoring system remains operational even when individual targets become temporarily unreachable (Prometheus Authors, 2023).

Grafana (Grafana Labs, 2023) is integrated into the monitoring environment to provide interactive visualisation of the collected telemetry. Grafana connects to Prometheus as a data source and supports the construction of time-series panels, heatmaps and threshold-based alert rules using Prometheus Query Language (PromQL) expressions. Within the present study, Grafana serves both as an operational monitoring dashboard during data collection and as a visual diagnostic tool during the model development and evaluation phases.

The operational Prometheus scrape configuration used by the monitoring infrastructure is shown below.

```yaml
global:
  scrape_interval: 15s
scrape_configs:
  - job_name: 'node-exporter'
    static_configs:
      - targets:
          - '127.0.0.1:9100'
          - '10.100.0.198:9100'
          - '10.100.0.167:9100'
          - '10.100.0.66:9100'
```

Source: Operational Prometheus configuration deployed on the HPC head node (/opt/monitoring_stack/prometheus.yml).

## 6.3 Telemetry Collection and Data Pipeline Implementation

### 6.3.1 DuckDB-Based Feature-Engineering Environment

The final V6 feature-engineering workflow was implemented in a local Jupyter Notebook environment on Windows using DuckDB, Python, Pandas and NumPy. The notebook processes historical telemetry already stored in the DuckDB database; it does not scrape the live cluster. DuckDB performs large analytical queries over the raw telemetry, while Pandas DataFrames are used for selected validation, joining, aggregation and reporting operations.

The notebook connects to the DuckDB database and verifies the required source objects before processing. These include `main.raw_hpc_all`, `main.benchmark_events` and `main.benchmark_event_nodes`. The raw telemetry and benchmark annotation sources are treated as read-only inputs. Derived feature tables and Parquet files are written only through an explicitly enabled save stage; saving is disabled by default in the notebook.

### 6.3.2 Metric-Series Reconstruction and Feature-Family Processing

The V6 pipeline reconstructs measurements separately for CPU, memory, network, disk, system activity and filesystem. Each feature family is processed using its own metric-specific logic. Cumulative CPU, network and disk counters are differenced within each node and complete Prometheus label set, and rate calculations use the actual elapsed time between observations. Instantaneous measurements, including memory gauges, load values, process counts and outstanding disk I/O, are handled as gauge measurements rather than cumulative counters.

Network throughput features use the explicitly selected compute-node interface `enp3s0`. Loopback, Docker and other virtual interfaces are not substituted silently. Filesystem measurements distinguish the local root filesystem from shared NFS mounts. Collector availability and collector success are audited separately, using the 95% presence criterion documented in the feature-engineering notebook. NFS collector diagnostics are kept separate from filesystem capacity measurements.

### 6.3.3 Feature-Table Integration and Stored Outputs

The individual feature-family outputs are combined using node identifiers and observation timestamps as the common keys. The V6 notebook uses full outer joins so that observations are not discarded solely because a particular feature family is unavailable. It retains quality indicators and applies final validation gates before saving derived datasets.

**Table 4.1: Principal outputs of the V6 DuckDB feature-engineering pipeline.**

| Output dataset | Rows | Resolution / coverage |
| --- | --- | --- |
| `hpc_features_15s_v6` | 322,557 | 15-second features; four nodes |
| `hpc_features_1min_v6` | 80,640 | One-minute features; four nodes |
| `model_input_15s_v6` | 241,902 | 15-second compute-node model candidates |
| `model_input_1min_v6` | 60,475 | One-minute compute-node model candidates |

The notebook also produces subsystem-specific Parquet outputs, collector profiles, NFS collector audits, benchmark-event audits, benchmark-to-telemetry alignments and daily feature-distribution summaries. A run manifest records the execution environment, source row count, feature output shapes, quality-audit results, selected interfaces, exclusions and final validation gates.

### 6.3.4 Separate Pandas-Based Exploratory Workflow

A separate exploratory workflow was implemented using Pandas in Google Colab. It produced the strict 17-feature dataset stored as `model_input_1min_v6_strict_17features.parquet`, containing 60,463 observations from the three compute nodes. This dataset was used for the exploratory K-Means analysis and related comparisons reported in Chapter 6. It is not the same dataset as the 60,475-row DuckDB model-candidate dataset used by the final comparative model-training pipeline.

## 6.4 Feature Engineering Implementation

### 6.4.1 Candidate Resource Features

Feature engineering transforms the processed and temporally aggregated monitoring measurements into a structured set of indicators that describe the operational behaviour of each HPC node at each observation timestamp. The engineering process organises the candidate features into six thematically coherent categories, reflecting the principal subsystems of a compute node:
CPU features. CPU utilisation (the proportion of total CPU time spent in non-idle states), CPU busy time, I/O wait percentage (the proportion of time the CPU spends waiting for I/O operations to complete) and system load averages at 1-minute, 5-minute and 15-minute intervals. Load averages are particularly informative in HPC contexts because they reflect not only CPU demand but also the depth of the run queue, providing an indirect measure of resource contention that is not captured by utilisation alone (Schroeder and Gibson, 2006).

Memory features. Memory utilisation (the proportion of total memory currently in use), absolute available memory and free memory. The distinction between available and free memory is operationally significant: Linux reclaims buffer and cache memory under pressure, meaning that free memory may approach zero during normal operation while available memory remains substantial.

Network features. Network receive and transmit throughput (bytes per second per interface), network error rates (receive and transmit errors per second), dropped-packet rates and TCP retransmission rates. Retransmission activity is included because it serves as an indicator of network congestion or link-layer errors that may precede observable application-level performance degradation.

Disk and I/O features. Disk read and write throughput (bytes per second), disk I/O time (the proportion of time during which I/O operations were in progress) and the count of outstanding I/O operations. These metrics collectively characterise storage subsystem load and responsiveness.

System activity features. System load averages (shared with the CPU category in interpretation but derived from process-scheduling statistics), counts of running processes and counts of processes in uninterruptible sleep (blocked processes). An elevated count of blocked processes is a well-established indicator of I/O subsystem contention or storage-controller dysfunction.

Filesystem features. Local root filesystem utilisation percentage and absolute available storage capacity. Filesystem exhaustion is a common operational failure mode that can produce cascading effects including log truncation, swap-space unavailability and application crashes.

The feature-engineering stage produces an initial candidate set of 20 resource-monitoring features. Additional diagnostic metrics—including Node Exporter collector health indicators and NFS-related measurements—are retained separately for operational monitoring purposes but excluded from the machine-learning feature set, as they reflect monitoring-infrastructure behaviour rather than compute-node operational state.

### 6.4.2 Final Model Input Preparation and Transformations

The final comparative model-training pipeline reads `model_input_1min_v6.parquet`. The source dataset contains 60,475 one-minute observations across the three compute nodes. The training notebook selects 17 source measurements, applies feature-specific transformations, removes six redundant or less suitable source features, and constructs four binary activity indicators and two one-hour temporal-difference features. The resulting model matrix contains 17 features.

The six source features removed from the selected input matrix are the three per-core load averages, blocked-process count, root-filesystem used percentage and memory-free percentage. The retained source columns and the resulting engineered features are reflected in the final feature list below.

**Table 4.2: Final 17-feature representation used by the comparative model-training pipeline.**

| No. | Final feature name | Category | Description / unit | Transformation |
| --- | --- | --- | --- | --- |
| 1 | `cpu_utilisation_pct_mean` | CPU | Mean CPU utilisation (%) | Log1p |
| 2 | `iowait_pct_mean` | CPU | Mean CPU I/O wait (%) | Log1p |
| 3 | `memory_used_pct_mean` | Memory | Mean memory utilisation (%) | None |
| 4 | `network_rx_mib_s_mean` | Network | Mean receive throughput (MiB/s) | Log1p |
| 5 | `network_tx_mib_s_mean` | Network | Mean transmit throughput (MiB/s) | Log1p |
| 6 | `tcp_retrans_per_s_mean` | Network | Mean TCP retransmissions per second | Log1p |
| 7 | `disk_read_mib_s_mean` | Disk / I/O | Mean disk read throughput (MiB/s) | None |
| 8 | `disk_write_mib_s_mean` | Disk / I/O | Mean disk write throughput (MiB/s) | Clip at 50, then Log1p |
| 9 | `disk_io_time_pct_sum_mean` | Disk / I/O | Mean aggregate disk I/O time (%) | Clip at 100, then Log1p |
| 10 | `disk_io_now_mean` | Disk / I/O | Mean outstanding I/O operations (count) | Clip at 50 |
| 11 | `node_procs_running_mean` | System activity | Mean number of running processes | None |
| 12 | `is_nonzero_disk_write_mib_s_mean` | Disk / I/O | Indicator for non-zero disk-write activity | Binary (0/1) |
| 13 | `is_nonzero_disk_io_now_mean` | Disk / I/O | Indicator for non-zero outstanding I/O | Binary (0/1) |
| 14 | `is_nonzero_iowait_pct_mean` | CPU | Indicator for non-zero I/O wait | Binary (0/1) |
| 15 | `is_nonzero_tcp_retrans_per_s_mean` | Network | Indicator for non-zero TCP retransmissions | Binary (0/1) |
| 16 | `memory_used_delta_1h` | Memory | One-hour change in memory utilisation (percentage points) | 60-observation difference |
| 17 | `root_fs_used_delta_1h` | Filesystem | One-hour change in root-filesystem utilisation (percentage points) | 60-observation difference |

Selected right-skewed resource features were transformed using the natural logarithm of one plus the original value, `log1p(x)`. Before logarithmic transformation, disk I/O time was clipped at 100, disk I/O outstanding operations at 50, and disk-write throughput at 50. Four binary indicators were generated before logarithmic transformation to preserve the presence or absence of sparse activity independently of its magnitude.

Two one-hour temporal-change features were computed within each node by comparing the current observation with the observation 60 one-minute records earlier. The memory feature represents the change in mean memory utilisation percentage; the filesystem feature represents the change in root-filesystem used percentage. The temporal differences were computed against the full chronological dataset before the partition-specific matrices were filtered for missing values.

The feature list and column ordering are maintained consistently between the training pipeline and deployed inference service. This consistency is required to ensure that the feature vector supplied during inference has the same meaning and ordering as the vector used to fit the model.

## 6.5 Machine-Learning Implementation

### 6.5.1 Candidate Anomaly-Detection Algorithms

To investigate the suitability of different computational approaches for identifying anomalous resource behaviour in HPC telemetry, six candidate algorithms were implemented and evaluated. The selection spans four distinct families of unsupervised anomaly detection, providing breadth of comparison across fundamentally different mathematical formulations of the outlier-identification problem.

Isolation Forest (Liu, Ting and Zhou, 2008) is an ensemble-based algorithm that identifies anomalies through a recursive random-partitioning process. The algorithm constructs an ensemble of isolation trees, each built by randomly selecting a feature and a split value at each internal node. Observations that are anomalous—lying in sparse regions of the feature space—require fewer partitioning steps to become isolated in their own leaf node, producing shorter average path lengths across the ensemble. The anomaly score for an observation is derived from its average path length normalised against the expected path length for the dataset size. Isolation Forest is computationally efficient, scales linearly with sample size, and does not require distance or density computations that become expensive in high-dimensional spaces.

One-Class Support Vector Machine (OC-SVM) (Schölkopf et al., 2001) is a boundary-based algorithm that learns a decision boundary enclosing the region of the feature space occupied by the training data. It maps the input features into a higher-dimensional space using a kernel function and identifies the maximum-margin hyperplane that separates the training observations from the origin. Observations falling on the origin side of the boundary—outside the learned region of normality—are classified as potential anomalies. OC-SVM is sensitive to feature scaling, necessitating standardisation of the input features prior to training.

Local Outlier Factor (LOF) (Breunig et al., 2000) is a density-based algorithm that assesses anomalousness by comparing the local density of an observation with the local densities of its k-nearest neighbours. An observation surrounded by neighbours with substantially higher local densities—indicating that it lies in a sparser region than its immediate context—receives a high LOF score. This local-density comparison makes LOF capable of detecting anomalies in datasets with varying density across the feature space, a property relevant to HPC telemetry where different operational regimes (idle, partially loaded, fully saturated) occupy regions of differing density.

Principal Component Analysis (PCA) (Jolliffe, 2002) is employed as an anomaly detector through the reconstruction-error paradigm. PCA identifies the principal components—orthogonal directions of maximum variance—in the training data and projects observations onto the subspace defined by the top *k* components. Observations are then reconstructed by inverse-projecting from this reduced representation. The reconstruction error, measured as the Euclidean distance between the original observation and its reconstruction, serves as the anomaly score. Observations that do not conform to the dominant variance structure learned from the training data produce large reconstruction errors. This approach exploits the assumption that normal observations exhibit regular covariance structure, while anomalous observations introduce variance in directions not captured by the principal subspace.

Gaussian Mixture Model (GMM) (McLachlan and Peel, 2000) is a probabilistic generative model that represents the training data as a mixture of *K*-variate Gaussian distributions. Each component represents a cluster of similar observations in the feature space. The model is fitted by expectation-maximisation, and the anomaly score for a new observation is derived from its log-likelihood under the fitted mixture. Observations assigned low log-likelihood—indicating that they are poorly explained by any of the learned Gaussian components—are considered potential anomalies. GMM provides a principled probabilistic framework for anomaly detection and can capture multi-modal distributions of normal behaviour.

Autoencoder (Goodfellow, Bengio and Courville, 2016, Chapter 14) is a neural network architecture trained to reconstruct its input through a constrained intermediate representation. The network consists of an encoder, which compresses the input features into a lower-dimensional latent representation, and a decoder, which reconstructs the original input from this compressed representation. The model is trained by minimising the reconstruction error on the training data. At inference time, observations that differ from the patterns learned during training produce elevated reconstruction errors, which serve as anomaly scores. The Autoencoder's capacity to learn nonlinear representations of normal behaviour makes it potentially more expressive than PCA for capturing complex inter-metric dependencies, though this expressiveness comes at the cost of longer training times and additional hyperparameter sensitivity.

### 6.5.2 Isolation Forest Configuration and Anomaly Scoring

The Isolation Forest model was configured with the following hyperparameters:

**Table 6.3: Isolation Forest hyperparameter configuration.**

| Parameter | Value | Rationale |
| --- | --- | --- |
| `n_estimators` | 300 | Ensemble size used in the final model configuration |
| `max_samples` | `auto` | Allows the algorithm to select its subsample size |
| `contamination` | `auto` | Uses the estimator default offset; the study applies a separately calculated percentile threshold to the anomaly scores |
| `max_features` | 1.0 | Each tree considers the complete feature set |
| `bootstrap` | False | Subsampling without replacement |
| `random_state` | 42 | Fixed random seed for reproducibility |
| `n_jobs` | −1 | Uses available CPU cores for parallel tree construction |

The model assigns a continuous score using `score_samples()`. The raw score is negated so that higher values represent greater anomalousness:

\[s_i=-\operatorname{score\_samples}(x_i)\]

A detection threshold is established using the 99th percentile of the training anomaly-score distribution:

\[\tau=P_{99}\left(\{s_i:x_i\in D_{\mathrm{train}}\}\right)\]

The saved threshold for the deployed V6 model is approximately 0.6454224919. Observations with an anomaly score greater than or equal to this threshold are designated as potential anomalies. The threshold is a decision boundary for flagging and is not an accuracy measure.

## 6.6 Model API and Inference Service

### 6.6.1 Deployment Rationale

The transition from a trained model artefact to an operational anomaly detection capability requires an inference service that can receive monitoring observations, apply the trained model and return anomaly assessments in near-real time. This deployment stage is architecturally significant: it transforms the model from a static analytical result into an operational component of the HPC monitoring infrastructure, fulfilling the end-to-end pipeline objective established in Section 4.1.

The inference service was developed using FastAPI (Ramírez, 2018), a Python web framework that provides asynchronous HTTP request handling, automatic request validation through type annotations, and interactive API documentation. FastAPI was selected for its combination of development speed, runtime performance and native support for the data-validation patterns required when receiving structured monitoring observations from external systems.

### 6.6.2 Application Architecture

The inference service follows a modular architecture in which the concerns of HTTP request handling, model operations, data preprocessing and configuration management are separated into distinct components:
**Table 4.4: Components of the inference-service architecture.**

| Component | Responsibility |
| --- | --- |
| main.py | Defines the FastAPI application instance, application lifecycle management (model loading at startup) and HTTP endpoint routing |
| model_service.py | Manages model loading, per-node observation history maintenance, feature preparation, anomaly scoring and prediction state tracking |
| preprocessing.py | Implements the identical feature transformations applied during model training (Section 4.4.2), ensuring consistency between training-time and inference-time feature preparation |
| schemas.py | Defines Pydantic request and response schemas that validate the structure and types of incoming monitoring observations |
| config.py | Manages application configuration, model file paths and environment-variable-driven settings |

The trained Isolation Forest model and its associated detection threshold are stored as serialised artefacts (using the joblib format) in a dedicated models/ directory:
```text
v6-model-api/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── main.py
│   ├── model_service.py
│   ├── preprocessing.py
│   └── schemas.py
├── models/
│   ├── isolation_forest_if_v6.joblib
│   └── threshold_if_v6.joblib
├── tests/
│   ├── test_history.py
│   └── test_preprocessing.py
└── README.md
This separation of concerns ensures that modifications to the preprocessing logic, model artefacts or API endpoint structure can be made independently, reducing the risk of unintended interactions between components—a software engineering principle particularly important in machine-learning systems, where the boundary between data processing and model inference is a frequent source of subtle errors (Sculley et al., 2015).
```

### 6.6.3 Observation History Management and Temporal Feature Support

The feature set employed by the Isolation Forest V6 model includes one-hour temporal-change features: the change in memory utilisation and root filesystem usage over the preceding 60 minutes. Computing these features at inference time requires access not only to the current observation but also to the observation recorded 60 minutes earlier.

To support this requirement, the inference service maintains a per-node observation history using an in-memory queue with a maximum capacity of 61 consecutive one-minute observations. This capacity corresponds to the current observation plus the 60 preceding observations required to compute the one-hour temporal differences.

The history-management component enforces several data-integrity constraints:
- Timestamp normalisation. All incoming observation timestamps are normalised to Coordinated Universal Time (UTC) to prevent timezone-related inconsistencies.
- Duplicate rejection. Observations with timestamps already present in the node's history are silently discarded.
- Temporal ordering enforcement. Observations with timestamps earlier than the most recent entry in the history are rejected, preventing out-of-order submissions from corrupting the temporal sequence.
- Continuity verification. Consecutive one-minute intervals are required between successive observations. If a gap is detected—indicating a period of missing monitoring data—the existing history and any prior prediction state are cleared, and the current observation initiates a new history sequence.
- No interpolation of missing data. The service does not synthesise or interpolate missing observations. This conservative policy ensures that the model is never presented with fabricated temporal context, a design choice that prioritises prediction reliability over prediction availability.
These constraints collectively ensure that the model only generates anomaly assessments when the temporal context required by its feature set is complete and internally consistent.

### 6.6.4 Feature Preparation and Anomaly Scoring

Once a node's observation history reaches the required depth of 61 consecutive observations, the inference service extracts the current (most recent) observation and the observation recorded 60 minutes earlier. These two observations are passed to the build_v6_features() function in the preprocessing component, which applies the identical sequence of transformations described in Section 4.4.2: logarithmic compression, upper-bound clipping, binary indicator construction, one-hour temporal differencing and fixed-order feature arrangement.

The resulting 17-element feature vector is submitted to the trained Isolation Forest model for anomaly scoring:
\[s=-\operatorname{model.score\_samples}(x)\]

The computed score is compared against the stored detection threshold (τ=0.6454224919). An observation is classified as a potential anomaly when s≥τ.

The identity between the training-time and inference-time preprocessing pipelines is maintained by construction: both invoke the same Python function with the same transformation parameters. This architectural decision eliminates the training–serving skew that Sculley et al. (2015) identified as one of the most common and insidious failure modes in deployed machine-learning systems.

### 6.6.5 Prediction Readiness and State Management

The inference service reports a processing status for each submitted observation that reflects the current state of the node's observation history:
**Table 4.5: Observation-processing statuses returned by the inference service.**

| Status | Meaning |
| --- | --- |
| warming_up | The node has not yet accumulated the required 61 consecutive observations; anomaly scoring is not yet available |
| scored | The observation has been processed through the full feature-preparation and scoring pipeline; an anomaly score and classification are returned |
| duplicate | The submitted observation has already been received and processed |
| model_unavailable | The model artefact is not loaded or has failed to initialise |

The warming_up state is an inherent consequence of the temporal-change features: following any service restart, monitoring gap or new node registration, the service requires 61 minutes of continuous one-minute observations before it can begin producing anomaly assessments. This warm-up period represents a deliberate trade-off between feature richness and detection latency that should be considered in the operational deployment context.

> **Important:**
The 61-observation history is maintained in application memory. Consequently, restarting the inference service clears all accumulated histories, and each node must complete the full warm-up period before scoring resumes. In production deployments where service restarts are anticipated, a persistence mechanism—such as writing the most recent history to disk at shutdown and restoring it at startup—would mitigate this limitation.

## 6.7 Service Security, Deployment and API Interface

### 6.7.1 Security and Access Control

The inference service implements API-key authentication to restrict access to observation-processing endpoints. Clients must provide a valid API key through the X-API-Key HTTP request header. The submitted key is validated against the configured server-side key using Python's hmac.compare_digest() function, which performs a constant-time string comparison to mitigate timing-based side-channel attacks that could reveal information about the expected key through response-time analysis.

The authentication behaviour is defined as follows:
- Requests omitting the API key receive an HTTP 401 (Unauthorised) response.
- Requests providing an invalid API key receive an HTTP 401 (Unauthorised) response.
- If no API key has been configured on the server, inference endpoints return HTTP 503 (Service Unavailable), preventing unauthenticated operation by default.
The API key is stored in an environment configuration file (/etc/v6-model-api.env) rather than being embedded in the application source code, following the twelve-factor application configuration methodology (Wiggins, 2017).

### 6.7.2 System Service Deployment

The inference service is deployed on the HPC cluster's head node as a systemd-managed service, providing process supervision, automatic restart on failure and integration with the operating system's service management framework. The service configuration establishes the following operational characteristics:
Execution context. The application runs under a dedicated non-root user account (ubuntu), following the principle of least privilege. The NoNewPrivileges=true directive prevents the process from acquiring elevated privileges through setuid binaries or capability escalation.

Network binding. The Uvicorn ASGI server listens exclusively on the loopback interface (127.0.0.1:8100), restricting direct network access to processes running on the head node itself. This binding prevents compute nodes or external systems from directly submitting observations to the inference service over the network. Any integration with remote monitoring agents requires an intermediary component—such as a reverse proxy, a message queue or a Prometheus-based metrics bridge—to relay observations to the locally bound service.

Process isolation. The PrivateTmp=true directive provides the service with an isolated temporary directory, preventing other processes from accessing or modifying temporary files created by the application. The UMask=0077 setting restricts the default permissions of files created by the service to owner-only access.

Resilience. The service is configured to restart automatically following an application failure, with a five-second delay between restart attempts. This provides basic fault tolerance against transient errors, though the warm-up period described in Section 4.6.5 means that scoring capability is not immediately restored following a restart.

### 6.7.3 API Endpoint Specification

The inference service exposes the following HTTP endpoints:
**Table 4.6: Inference-service API endpoints.**

| Method | Endpoint | Authentication | Purpose |
| --- | --- | --- | --- |
| GET | / | No | Returns basic API identification and version information |
| GET | /health | No | Reports application health status |
| GET | /ready | No | Reports whether the model is loaded and the service is ready to process observations |
| GET | /model/info | Yes | Returns metadata about the loaded model, including algorithm type and detection threshold |
| POST | /observations | Yes | Accepts a single node observation for processing |
| POST | /observations/batch | Yes | Accepts between 1 and 5,000 observations in a single request |
| GET | /nodes/{node_id}/status | Yes | Returns the current observation history depth, prediction state and most recent anomaly assessment for a specified node |
| POST | /model/reload | Yes | Triggers reloading of the model artefacts from disk, permitting model updates without service restart |

The separation of /health and /ready endpoints follows the health-check pattern established in container orchestration platforms (Burns et al., 2016): /health indicates that the application process is running and responsive, while /ready indicates that all dependencies (including the loaded model artefact) are available and the service is prepared to process inference requests. This distinction permits monitoring systems to differentiate between an application that has crashed and one that is operational but temporarily unable to serve predictions—for example, during model loading at startup.

The /model/reload endpoint provides operational flexibility by permitting model artefact updates without requiring a full service restart and the consequent loss of accumulated observation histories. When a retrained model is deployed to the models/ directory, an authenticated POST to this endpoint causes the service to load the updated artefact and threshold, after which subsequent observations are scored using the new model.

The current service deployment binds Uvicorn to `127.0.0.1:8100`. Direct network access from compute nodes is therefore not provided by this binding. A Prometheus-to-API ingestion client, reverse proxy, message queue or other intermediary that submits observations from remote nodes is not established by the deployment description above and should not be described as completed integration unless separately verified.

# Chapter 7: Experimental Design and Evaluation

## 7.1 Experimental Design

This study adopts a staged experimental design to investigate the suitability of machine-learning-based anomaly detection for monitoring resource behaviour in a High-Performance Computing (HPC) environment. The experimental approach combines retrospective analysis of collected cluster telemetry, comparative evaluation of unsupervised anomaly-detection algorithms and planned operational validation of the deployed inference service.

The first component involves a retrospective comparative experiment using the prepared one-minute telemetry dataset collected from the three compute nodes. Six unsupervised anomaly-detection algorithms are trained using a chronological training partition and evaluated against subsequent validation and testing observations. The algorithms are assessed using a consistent feature representation and training protocol. Their computational training times and the proportions of observations designated as potential anomalies are examined to support an initial comparison of their suitability for the monitoring application.

The second component examines resource behaviour under different workload conditions recorded during the monitoring period. These conditions include extended low-activity periods, a user-confirmed stress-test activity on 21 October 2026, and benchmark executions involving ASCOT5, DFTB+, HPCC and HemelB between 28 and 31 October 2026. This analysis provides workload context for interpreting the anomaly scores generated by the candidate models. These workload annotations are not treated as verified hardware-failure labels.

The third component concerns the operational validation of the selected Isolation Forest inference service. This component is designed to examine the behaviour of the deployed service during normal workload activity and controlled resource-stress scenarios. The proposed validation includes CPU contention, memory pressure, disk I/O congestion, network degradation and elevated CPU temperature. The objective is to investigate whether the inference service identifies unusual resource behaviour while minimising unnecessary anomaly designations during legitimate workloads.

The comparative model experiment and historical workload analysis were completed using the available telemetry and recorded execution outputs. However, the supplied experiment records do not establish that the proposed controlled anomaly-injection scenarios or a complete live end-to-end validation were executed. These activities are therefore treated as planned experimental procedures rather than completed experimental results.

The evaluation distinguishes between anomaly designation and verified anomaly detection. An observation receiving an anomaly flag indicates that its resource measurements deviate from the patterns learned during training; it does not, by itself, establish that a hardware failure has occurred. Precision, recall, F1-score and false-positive rate require observations with reliable ground-truth labels. Where such labels are available from controlled experiments, they will be used to evaluate detection performance alongside operational measures such as detection latency and alert frequency.

This staged design allows the study to examine both the statistical behaviour of candidate anomaly-detection algorithms and the practical requirements of operating an inference service within an HPC monitoring environment.

## 7.2 Experimental Workload Conditions

The workload observations used in the study include low-activity operating periods, a user-confirmed stress-test activity on 21 October 2026, and recorded benchmark executions between 28 and 31 October 2026. The benchmark applications represented in the telemetry-alignment dataset are ASCOT5, DFTB+, HPCC and HemelB. The alignment dataset contains 39 job-node records representing 21 unique Slurm jobs. These workload records provide context for interpreting resource utilisation and model flags; they are not ground-truth hardware-failure labels.

For the 21 October stress-test analysis, the telemetry inspection window was defined as 19:15–20:00 UTC, with 30-minute periods before and after it used for comparison. The exact execution start and completion times were not independently established. Accordingly, the inspection period is used for descriptive comparison and must not be presented as a verified execution interval.

For benchmark analysis, Slurm execution records and participating node identifiers were aligned with the corresponding monitoring observations. Where one Slurm job used multiple compute nodes, separate job-node records were retained. This distinction is important when calculating workload counts and when interpreting application-level averages.

## 7.3 Dataset Partitioning and Training Protocol

The final comparative model-development experiment used `model_input_1min_v6.parquet`, containing 60,475 one-minute observations from the three compute nodes. The head node was excluded because its resource profile, dominated by monitoring and management processes, differs from the compute-node workload profile targeted by the model.

The dataset was divided chronologically into three non-overlapping partitions using a 70/15/15 strategy. Partition boundaries were calculated from the sorted unique minute timestamps so observations from different compute nodes at the same minute remained in the same subset.

**Table 7.1: Chronological partitioning and retained model observations.**

| Subset | Proportion | Initial observations | Retained after feature preprocessing | Temporal coverage |
| --- | --- | --- | --- | --- |
| Training | 70% | 42,332 | 42,152 | Before 27 October 2026, 19:12 UTC |
| Validation | 15% | 9,072 | 9,072 | 27 October 2026, 19:12 – 29 October 2026, 21:35 UTC |
| Testing | 15% | 9,071 | 9,071 | From 29 October 2026, 21:36 UTC onward |
| Total | 100% | 60,475 | 60,295 | 18–31 October 2026 |

The training matrix contained 42,152 observations after preprocessing, compared with the original training partition of 42,332. The difference of 180 observations resulted from the one-hour temporal-difference features: the first 60 one-minute observations for each of the three compute nodes did not have the preceding 60 observations required to calculate these features. Those rows were removed from the model-training matrix using complete-case filtering. The validation and testing matrices retained their original observation counts because the temporal differences were calculated using the full chronological node histories before partition-specific filtering.

Chronological partitioning was selected to reduce temporal leakage. A random split could place observations from similar operating periods into different subsets, resulting in an overly optimistic assessment. The chronological strategy evaluates how the models respond to observations from later periods than those used for fitting.

The exploratory K-Means analysis used a separate strict 17-feature Pandas dataset with 60,463 observations and a 70/10/20 chronological split. Its training, validation and testing counts were 42,322, 6,048 and 12,093 respectively. These partitions belong to the exploratory clustering analysis and are not the partitions used in the final six-model comparison.

## 7.4 Comparative Model Evaluation Protocol

The six candidate algorithms were evaluated using a common chronological dataset and a consistent preprocessing sequence. Algorithms sensitive to feature scale—One-Class SVM, Local Outlier Factor, PCA, Gaussian Mixture Model and the Autoencoder—used standardisation fitted on training data and applied to validation and testing data. Isolation Forest was trained on the unscaled model feature matrix.

After temporal feature construction and removal of rows with unavailable one-hour history, the six candidate models were fitted to the 42,152-observation training matrix. This is the retained training matrix size; the original chronological training partition contained 42,332 observations.

The comparative evaluation considered model training time and the proportion of validation and testing observations designated as potential anomalies. These designation rates describe the frequency of model flags; they are not measures of detection accuracy. Verified ground-truth labels are required to calculate precision, recall and F1-score.

The testing partition was examined during the model-selection process. It was therefore not preserved as a fully independent final evaluation set. This limitation is considered when interpreting the comparative results in Chapter 6.

## 7.5 Normal-Workload Validation

Normal-workload validation is intended to examine whether the deployed model produces stable anomaly scores during routine operation and legitimate computational workloads. The validation conditions include low-activity periods and benchmark executions with different resource-use profiles. This is important because intensive CPU, memory, disk or network activity is not necessarily evidence of a system fault; legitimate applications may produce resource patterns that differ substantially from the low-activity training baseline.

The evaluation should record the workload or benchmark, participating compute nodes, job start and completion times, resource allocation, telemetry observations, anomaly scores and resulting flags. Workload annotations should be aligned with telemetry using the recorded execution intervals. A benchmark annotation is workload context and must not be treated as a hardware-failure label.

## 7.6 Controlled Anomaly Injection

Controlled anomaly injection is intended to evaluate whether the monitoring and inference pipeline responds to specific resource-stress conditions. Each scenario should be executed separately, with a documented baseline period, injection interval and post-injection recovery period. The injected condition, target compute node, start and end timestamps, resource measurements and inference-service outputs should be recorded to establish a traceable experimental record.

**Table 7.2: Proposed controlled anomaly-injection scenarios.**

| Scenario | Intended condition | Relevant telemetry indicators | Implementation consideration |
| --- | --- | --- | --- |
| CPU contention | Artificially sustained processor demand | CPU utilisation, CPU busy time, load average, running processes | Control the requested CPU load and record the target node and duration |
| Memory exhaustion / pressure | Progressive or sustained memory consumption | Memory used percentage, memory available, memory change over one hour | Use controlled allocation and establish a safe stop condition |
| Disk I/O congestion | Increased disk reads/writes or outstanding I/O | Disk read/write throughput, disk I/O time, outstanding I/O, I/O wait, blocked processes | Use a controlled test file and avoid stressing the shared system filesystem |
| Network degradation | Increased retransmissions, errors or constrained throughput | Network receive/transmit rates, TCP retransmissions and interface error/drop counters | Use a controlled network test and verify that the selected interface is monitored |
| High CPU temperature | Elevated thermal readings under workload | CPU temperature and related hardware sensor telemetry | Temperature is not one of the 17 V6 model input features; this scenario requires an additional sensor feature or separate monitoring assessment |

The thermal scenario requires particular care. Although temperature measurements may be exposed by Node Exporter where hardware sensors are available, CPU temperature is not included in the current V6 17-feature model input or inference schema. Consequently, the deployed model cannot be claimed to detect a thermal anomaly directly without extending and retraining the model. Temperature may be monitored separately as experimental context.

The injection procedure should preserve system safety. Each experiment should use a defined resource limit, a maximum duration and a recovery procedure. Workloads should be terminated if the node becomes unresponsive or if a predefined resource-safety limit is reached. Only one controlled anomaly type should be introduced at a time when the objective is to attribute model behaviour to a known injection.

## 7.7 Evaluation Metrics

Where verified injection labels are available, the anomaly-detection results can be evaluated using the following metrics:

**Precision** measures the proportion of observations flagged by the model that correspond to verified injected anomalies:

\[\mathrm{Precision}=\frac{TP}{TP+FP}\]

**Recall** measures the proportion of verified anomaly observations detected by the model:

\[\mathrm{Recall}=\frac{TP}{TP+FN}\]

**F1-score** is the harmonic mean of precision and recall:

\[F1=2\times\frac{\mathrm{Precision}\times\mathrm{Recall}}{\mathrm{Precision}+\mathrm{Recall}}\]

**False-positive rate** measures the proportion of verified normal observations incorrectly flagged as anomalous:

\[\mathrm{FPR}=\frac{FP}{FP+TN}\]

Additional operational measures include detection latency, measured as the elapsed time between the verified anomaly-injection start and the first corresponding model flag, and alert frequency, measured as the number of alerts generated over a defined observation period. Alert frequency and repeated alerts should be considered when assessing the risk of alert fatigue.

The terms true positive (TP), false positive (FP), false negative (FN) and true negative (TN) require a defined ground-truth labelling interval. The user-confirmed 21 October stress-test annotation is a workload event and is not a ground-truth hardware-failure label. Therefore, it cannot be used by itself to calculate failure-detection precision or recall.

# Chapter 8: Results and Findings

## 8.1 Exploratory Data Analysis

This section presents the exploratory findings obtained from the monitoring data. It examines resource behaviour during the recorded stress-test inspection window, differences between benchmark workload profiles, temporal workload patterns identified through exploratory clustering, and the quality of the derived telemetry datasets.

### 8.1.1 Resource Behaviour During the Stress-Test Period

A focused analysis was conducted to examine the behaviour of the three compute nodes during a user-confirmed stress-test activity on 21 October 2026. The purpose of this investigation was to understand how resource utilisation changed around the activity and to identify the extent to which the workload affected the monitored compute nodes. This analysis provides additional context for interpreting the resource patterns observed in the telemetry dataset.

The investigation considered three periods: a 30-minute period before the inspection window (18:45–19:15 UTC), a 45-minute inspection window (19:15–20:00 UTC), and a 30-minute period after the inspection window (20:00–20:30 UTC). These periods were compared across compute001, compute002 and compute003 using the 15-second telemetry dataset. The comparison covered eight resource metrics: CPU utilisation, memory utilisation, system load, disk read throughput, disk write throughput, disk I/O time, network receive throughput and network transmit throughput.

The analysis indicated elevated resource activity during the inspection window, particularly in CPU, memory and disk-related measurements. Comparing the observations before, during and after the inspection window provided a basis for examining changes in resource behaviour across the three compute nodes. The post-inspection period was also included to observe whether resource utilisation moved towards the levels recorded before the inspection window.

The stress-test activity requires an important distinction when interpreting these results. Although the user confirmed that a stress test took place on 21 October, its exact execution start and completion times were not independently established. Therefore, 19:15–20:00 UTC represents the selected inspection window used for the telemetry comparison, rather than a verified record of the precise execution interval. The observed resource changes can consequently be discussed in the context of the confirmed stress-test activity, but individual changes within this window cannot all be attributed conclusively to the test.

Furthermore, this event was retained as a workload annotation and was not used as a ground-truth hardware failure label. The purpose of the analysis was to characterise resource behaviour under an elevated workload, not to classify the stress test as a system failure. This distinction is important for the subsequent machine-learning experiments, where workload-induced resource utilisation must be distinguished from abnormal behaviour associated with genuine failure conditions.

The comparison therefore provides a reference for understanding how the compute nodes behave during a known period of increased workload activity. It also supports the interpretation of subsequent anomaly-detection results by providing workload context for resource fluctuations that might otherwise be incorrectly interpreted as evidence of a system fault.

**Table 8.1: Comparison of compute-node resource behaviour during the low-activity baseline and the 21 October 2026 stress-test inspection window.**

| Period | Compute node | Observations | CPU mean (%) | CPU P95 (%) | Memory mean (%) | Memory P95 (%) | I/O wait mean (%) | I/O wait P95 (%) | Disk write mean (MiB/s) | Disk I/O time mean (%) | Network RX mean (MiB/s) | Network TX mean (MiB/s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Low-activity baseline | compute001 | 8,594 | 0.0223 | 0.0271 | 2.6708 | 2.7173 | 0.0013 | 0.0063 | 0.0051 | 0.0137 | 0.0007 | 0.0009 |
| Low-activity baseline | compute002 | 8,594 | 0.0199 | 0.0250 | 2.6252 | 2.6807 | 0.0027 | 0.0062 | 0.0045 | 0.0244 | 0.0003 | 0.0008 |
| Low-activity baseline | compute003 | 8,594 | 0.0187 | 0.0208 | 2.6229 | 2.6830 | 0.0021 | 0.0042 | 0.0047 | 0.0202 | 0.0004 | 0.0008 |
| Stress-test inspection | compute001 | 45 | 6.9965 | 43.1994 | 3.7838 | 2.9397 | 1.8684 | 13.5505 | 15.1385 | 5.6985 | 0.0072 | 0.0010 |
| Stress-test inspection | compute002 | 45 | 12.5969 | 53.3594 | 4.0383 | 2.9401 | 1.5402 | 5.5531 | 18.2547 | 5.3671 | 0.0083 | 0.0009 |
| Stress-test inspection | compute003 | 45 | 6.7496 | 40.9148 | 3.8443 | 2.8851 | 1.5298 | 6.5854 | 18.1553 | 5.2384 | 0.0068 | 0.0008 |

Note: The low-activity baseline covers 18–23 October 2026, excluding the approximate stress-test inspection window. The stress-test inspection window covers 21 October 2026, 19:15–20:00 UTC. Each stress-test node has 45 one-minute observations. Disk I/O time is the aggregated disk I/O time percentage feature.

### 8.1.2 Benchmark Workload Characteristics

An additional exploratory analysis was conducted to investigate how different benchmark applications influenced resource utilisation across the three compute nodes. Unlike the earlier stress-test investigation, which focused on a specific period of elevated resource activity, this analysis examined recorded benchmark executions performed between 28 and 31 October 2026.

The purpose was to establish whether different applications exhibited distinct resource-utilisation patterns and whether these patterns were consistent across compute001, compute002 and compute003. This investigation also provides workload context for interpreting unusual resource measurements in the collected telemetry, particularly where intensive benchmark activity may produce behaviour that differs considerably from the low-activity baseline.

#### Benchmark execution records and telemetry alignment

The benchmark analysis used the prepared benchmark-to-telemetry alignment dataset, which contained 39 job-node records representing 21 unique Slurm jobs. The records covered four benchmark applications: ASCOT5, DFTB+, HPCC and HemelB.

The distribution of job-node records was as follows:
**Table 8.2: Distribution of benchmark job-node records by application.**

| Benchmark application | Job-node records | Unique compute-node coverage |
| --- | --- | --- |
| ASCOT5 | 4 | compute001 and compute002 |
| DFTB+ | 8 | compute001, compute002 and compute003 |
| HPCC | 12 | compute001, compute002 and compute003 |
| HemelB | 15 | compute001, compute002 and compute003 |
| Total | 39 |  |

The distinction between job-node records and unique jobs is important because a single multi-node Slurm job can generate separate alignment records for each participating compute node. Consequently, the 39 records should not be interpreted as 39 independent benchmark executions.

Benchmark execution timestamps and node identifiers were used to align the recorded workloads with the corresponding telemetry observations. Resource measurements were examined during benchmark execution, with corresponding pre-execution and post-execution measurements retained for recovery analysis.

#### Resource utilisation across benchmark applications

The initial comparison examined the average resource utilisation associated with each benchmark application. The analysis considered CPU utilisation, memory consumption, I/O wait, disk-write throughput and network traffic.

**Table 8.3: Average resource utilisation associated with recorded benchmark applications.**

| Application | Job-node records | CPU mean (%) | Memory mean (%) | I/O wait mean (%) | Disk write mean (MiB/s) | Network RX mean (MiB/s) | Network TX mean (MiB/s) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ASCOT5 | 4 | 14.8683 | 3.1714 | 0.2034 | 0.2397 | 0.0620 | 13.4804 |
| DFTB+ | 8 | 5.3910 | 2.9029 | 0.4638 | 0.1155 | 5.8222 | 5.7387 |
| HPCC | 12 | 76.5621 | 23.5058 | 0.0093 | 0.0194 | 52.7035 | 52.7487 |
| HemelB | 15 | 38.6751 | 2.9104 | 0.0126 | 0.0512 | 2.2483 | 2.2500 |

Note: The values represent averages of the per-job-node resource means recorded during benchmark execution. They are not pooled averages across every individual telemetry observation. Network RX and TX represent received and transmitted network throughput, respectively.

The results reveal different resource-utilisation characteristics across the benchmark applications. HPCC exhibited the highest average CPU utilisation, at approximately 76.56%, alongside the highest average memory utilisation, at approximately 23.51%. It also recorded considerably higher network throughput than the other applications, with average receive and transmit rates of approximately 52.70 MiB/s and 52.75 MiB/s, respectively. Its mean I/O wait and disk-write throughput were comparatively low.

HemelB exhibited an average CPU utilisation of approximately 38.68%, while memory utilisation remained relatively low at approximately 2.91%. Its average network receive and transmit rates were both approximately 2.25 MiB/s. This indicates a resource profile characterised by substantial CPU activity without the comparatively high memory utilisation and network throughput observed during HPCC executions.

DFTB+ exhibited lower average CPU utilisation, approximately 5.39%, and memory utilisation of approximately 2.90%. However, its mean I/O wait was approximately 0.46%, the highest among the four applications. Its average network throughput was approximately 5.82 MiB/s for received traffic and 5.74 MiB/s for transmitted traffic. These measurements indicate that the resource behaviour associated with DFTB+ differed from the predominantly CPU- and network-intensive patterns observed for HPCC.

ASCOT5 recorded an average CPU utilisation of approximately 14.87% and memory utilisation of approximately 3.17%. Its average disk-write throughput was approximately 0.24 MiB/s. The network measurements also showed an asymmetric pattern, with average transmit throughput of approximately 13.48 MiB/s compared with receive throughput of approximately 0.06 MiB/s. This observation should be interpreted in the context of the limited number of ASCOT5 records and the fact that the recorded executions involved only compute001 and compute002.

#### Differences in resource behaviour across compute nodes

A further comparison examined the resource profiles of individual compute nodes during the execution of the same benchmark applications. The results showed that the degree of consistency differed between applications.

HPCC exhibited relatively similar CPU utilisation across the three compute nodes. The average CPU utilisation was approximately 78.20% on compute001, 78.92% on compute002 and 72.57% on compute003. Memory utilisation also showed a comparable pattern, with averages ranging from approximately 22.66% to 24.26%.

HemelB displayed a similarly consistent CPU profile across the three nodes. Average CPU utilisation ranged from approximately 38.17% to 39.04%, while memory utilisation remained between approximately 2.81% and 3.07%.

DFTB+ showed greater variation between nodes. Its average CPU utilisation was approximately 1.88% on compute001, 5.32% on compute002 and 12.75% on compute003. However, the number of aligned records was not equal across these nodes: compute001 contributed two records, compute002 five and compute003 one. The node-level differences must therefore be interpreted with consideration of the unequal observation counts.

ASCOT5 was represented by two job-node records on compute001 and two on compute002, with no corresponding compute003 record. Its results consequently do not support a three-node comparison.

These findings indicate that workload characteristics and node-level resource behaviour should be considered together when interpreting monitoring measurements. A single application-level average may conceal differences between individual compute nodes, particularly where the number of recorded executions is limited or unevenly distributed.

#### Post-benchmark resource behaviour

The analysis also compared resource measurements before, during and after benchmark execution to investigate whether resource utilisation moved towards pre-execution levels once workloads ended.

CPU utilisation generally increased during benchmark execution relative to the corresponding pre-execution measurements. For example, during HPCC executions, compute001 recorded an average CPU utilisation of approximately 0.0679% before execution, 78.1956% during execution and 1.1569% after execution. Compute002 recorded 0.0804%, 78.9226% and 0.0531%, respectively, while compute003 recorded 0.0661%, 72.5681% and 0.3755%.

The memory comparison showed that HPCC executions were associated with substantial increases in memory utilisation. Across the three nodes, the during-execution averages ranged from approximately 22.66% to 24.26%, compared with pre-execution levels of approximately 2.71% to 2.94%. The post-execution measurements moved back towards the respective pre-execution levels.

Other resource measurements did not demonstrate an identical recovery pattern for every application and node. In particular, disk-write throughput sometimes remained elevated after execution or differed between the pre-execution, execution and post-execution periods. This indicates that recovery behaviour should be considered separately for each resource metric rather than assuming that all measurements immediately return to their original levels after a benchmark terminates.

Overall, the benchmark analysis demonstrates that legitimate HPC workloads can produce substantially different resource-utilisation patterns. HPCC was associated with high CPU, memory and network activity, while HemelB showed high CPU activity with comparatively low memory utilisation. DFTB+ and ASCOT5 exhibited different combinations of CPU, I/O and network behaviour.

These findings are relevant to the development of the anomaly-detection component because elevated resource utilisation is not necessarily evidence of abnormal system behaviour. Intensive but legitimate benchmark executions can generate measurements that differ substantially from the low-activity baseline. The benchmark records therefore provide useful operational context for interpreting potential anomalies and for assessing whether the monitoring solution can distinguish expected workload-related activity from other unusual resource behaviour.

The analysis is descriptive and based on the available recorded executions. It does not establish that the observed resource patterns are universal characteristics of the applications, nor does it independently confirm that every post-execution measurement represents complete system recovery.

### 8.1.3 Temporal Workload Patterns and Exploratory Clustering

#### Temporal distribution of workload activity

The chronological distribution of resource activity was examined to understand how workload conditions changed throughout the monitoring period. The dataset was divided chronologically into training, validation and testing partitions to preserve the temporal ordering of observations.

For this exploratory analysis, the training partition contained 42,322 observations, the validation partition contained 6,048 observations, and the testing partition contained 12,093 observations. The training period ended on 27 October 2026 at 19:11 UTC, while the validation period ended on 29 October 2026 at 04:47 UTC. The remaining observations formed the testing period, extending to 31 October 2026 at 23:59 UTC.

The training data exhibited a strong concentration of observations around low resource-utilisation levels. For example, the mean CPU utilisation across the training observations was approximately 0.089%, while median CPU utilisation was approximately 0.015%. Memory utilisation had a mean of approximately 2.674%. The distributions of several resource measurements were highly concentrated near zero, with comparatively few observations exhibiting substantially higher activity.

This distribution is consistent with the workload conditions captured during the monitoring period, which included extended periods of low activity alongside benchmark executions and other periods of increased resource utilisation. The concentration of observations around low-activity conditions is an important consideration for subsequent machine-learning development because less frequently observed workload conditions may be difficult to represent adequately during model training.

#### Exploratory K-Means clustering

To investigate whether the telemetry contained distinguishable workload patterns, K-Means clustering was applied to the 17-feature baseline dataset. The clustering procedure used three clusters, with the K-Means++ initialisation method, 20 initialisation runs and a random state of 42.

Before clustering, the existing selective logarithmic transformations were applied to the relevant skewed resource features. The transformed features were subsequently scaled using RobustScaler. The scaler was fitted exclusively on the training partition and then used to transform the other partitions. K-Means was fitted using the training observations only.

Three clusters were selected to investigate whether the telemetry could be organised into broad low-activity, moderate-activity and higher-activity patterns. These descriptions were treated as provisional interpretations rather than predefined labels because K-Means does not inherently understand workload categories. The clusters were interpreted after examining their resulting resource profiles.

The clustering process produced the following distribution:
**Table 8.4: Distribution of K-Means clusters in the training dataset.**

| Cluster | Observations | Percentage | Preliminary interpretation |
| --- | --- | --- | --- |
| Cluster 0 | 42,209 | 99.73% | Dominant low-activity profile |
| Cluster 1 | 45 | 0.11% | Elevated CPU and network activity |
| Cluster 2 | 68 | 0.16% | Elevated disk and I/O activity |
| Total | 42,322 | 100.00% |  |

The results demonstrate a strongly imbalanced cluster distribution. Cluster 0 contained approximately 99.73% of the training observations, while Clusters 1 and 2 contained only 45 and 68 observations, respectively. This indicates that the majority of recorded compute-node observations shared a relatively similar low-activity resource profile, while a much smaller number displayed different combinations of resource activity.

#### Resource characteristics of the identified clusters

The mean resource measurements associated with each cluster were examined to establish the characteristics distinguishing the three groups.

**Table 6.5: Mean resource characteristics of the K-Means clusters.**

| Resource feature | Cluster 0 | Cluster 1 | Cluster 2 |
| --- | --- | --- | --- |
| CPU utilisation (%) | 0.0625 | 17.2992 | 5.0208 |
| CPU busy excluding I/O wait (%) | 0.0485 | 17.2957 | 4.6896 |
| I/O wait (%) | 0.0140 | 0.0035 | 0.3313 |
| Memory utilisation (%) | 2.6739 | 2.8205 | 2.8439 |
| Load average per core (1-minute) | 0.0088 | 0.1308 | 0.1295 |
| Running processes | 1.0744 | 2.5722 | 1.4632 |
| Blocked processes | 0.0012 | 0.0000 | 0.0404 |
| Disk read (MiB/s) | 0.0000 | 0.0001 | 0.0009 |
| Disk write (MiB/s) | 0.0616 | 0.0310 | 1.4135 |
| Disk I/O time (%) | 0.0401 | 0.0391 | 4.2735 |
| Network receive (MiB/s) | 0.0005 | 4.6003 | 0.9217 |
| Network transmit (MiB/s) | 0.0009 | 1.7332 | 0.2598 |

Note: Values represent the mean of the corresponding resource features within each training cluster. Load values are expressed per core.

Cluster 0 represents the dominant low-activity profile. It exhibits very low average CPU utilisation, low system load and negligible network throughput. Its average memory utilisation is approximately 2.67%. These characteristics are consistent with the low-activity operating conditions that account for most observations in the training dataset.

Cluster 1 is characterised by substantially higher CPU and network activity. Its average CPU utilisation is approximately 17.30%, compared with approximately 0.06% in Cluster 0. It also exhibits higher process activity and network throughput, with mean network receive and transmit rates of approximately 4.60 MiB/s and 1.73 MiB/s, respectively. These characteristics suggest a workload profile involving increased computational and network activity.

Cluster 2 exhibits a different resource-use pattern. Its average disk-write throughput is approximately 1.41 MiB/s, while mean disk I/O time is approximately 4.27%. It also has a higher average I/O wait value and a greater number of blocked processes than the other clusters. These characteristics indicate comparatively stronger disk and I/O activity.

The findings demonstrate that the clusters are distinguished by combinations of resource measurements rather than CPU utilisation alone. In particular, the higher CPU and network activity associated with Cluster 1 differs from the disk- and I/O-oriented behaviour of Cluster 2. Consequently, a workload cannot necessarily be characterised by a single resource measurement.

#### Temporal distribution of the training clusters

The temporal distribution of the smaller clusters was investigated to establish when their observations occurred and whether they were concentrated within particular periods.

The daily cluster distribution for the training partition is presented below.

**Table 6.6: Daily distribution of K-Means clusters during the training period.**

| Date (October 2026) | Cluster 0 | Cluster 1 | Cluster 2 |
| --- | --- | --- | --- |
| 18 | 4,314 | 0 | 3 |
| 19 | 4,320 | 0 | 0 |
| 20 | 4,320 | 0 | 0 |
| 21 | 4,320 | 0 | 0 |
| 22 | 4,320 | 0 | 0 |
| 23 | 4,320 | 0 | 0 |
| 24 | 4,320 | 0 | 0 |
| 25 | 4,319 | 0 | 0 |
| 26 | 4,274 | 27 | 16 |
| 27 | 3,382 | 18 | 49 |
| Total | 42,209 | 45 | 68 |

The temporal distribution shows that the smaller clusters were concentrated towards the later part of the training period. Cluster 1 first appeared on 26 October 2026 at 00:41 UTC and its final training observation occurred on 27 October at 17:37 UTC. Its 45 observations were distributed across the compute nodes, with 18 observations on compute001, 18 on compute002 and 9 on compute003.

Cluster 2 covered a wider time range, from 18 October at 06:55 UTC to 27 October at 17:38 UTC. Its 68 observations were distributed as 31 on compute001, 21 on compute002 and 16 on compute003. Although three observations occurred on 18 October, most of the cluster's observations appeared on 26 and 27 October.

This temporal concentration indicates that the less frequently observed resource profiles were not distributed uniformly throughout the training period. Instead, they appeared more frequently towards the later part of the observed training interval, when the cluster experienced additional workload activity.

#### Cluster assignments during the testing period

Following training, the fitted K-Means model was used to assign clusters to the observations in the testing partition. This provided an opportunity to examine whether the resource profiles identified in the training data were also present in the later monitoring period.

The testing partition contained 12,093 observations, distributed as follows:
**Table 6.7: K-Means cluster distribution during the testing period.**

| Cluster | Observations | Percentage |
| --- | --- | --- |
| Cluster 0 | 11,753 | 97.19% |
| Cluster 1 | 279 | 2.31% |
| Cluster 2 | 61 | 0.50% |
| Total | 12,093 | 100.00% |

The daily distribution further illustrates the changing frequency of the identified workload profiles.

| Date | Cluster 0 | Cluster 1 | Cluster 2 |
| --- | --- | --- | --- |
| 29 October 2026 | 3,378 | 39 | 39 |
| 30 October 2026 | 4,218 | 90 | 12 |
| 31 October 2026 | 4,157 | 150 | 10 |

Cluster 1 increased from 39 observations on 29 October to 90 observations on 30 October and 150 observations on 31 October. Cluster 2, in contrast, decreased from 39 observations on 29 October to 12 on 30 October and 10 on 31 October.

These results indicate that the less frequently observed resource profiles continued to appear during the testing period, although their relative distribution changed over time. In particular, the increase in Cluster 1 observations suggests a greater frequency of the CPU- and network-oriented profile during the final days of the monitoring period.

#### Relationship between cluster assignments and benchmark activity

The testing-period cluster assignments were also compared with the recorded benchmark execution windows. The purpose was to determine whether the less frequently observed resource profiles coincided with known benchmark activity.

The alignment process identified 314 unique telemetry observations overlapping recorded benchmark execution windows. The remaining 11,779 observations occurred outside those windows. The total was deduplicated to avoid counting the same telemetry observation more than once when benchmark execution windows overlapped.

**Table 8.8: Distribution of testing-period clusters inside and outside recorded benchmark execution windows.**

| Observation category | Cluster 0 | Cluster 1 | Cluster 2 | Total |
| --- | --- | --- | --- | --- |
| Outside benchmark windows | 11,525 | 197 | 57 | 11,779 |
| Benchmark-aligned | 228 | 82 | 4 | 314 |
| Total | 11,753 | 279 | 61 | 12,093 |

Among benchmark-aligned observations, 82 were assigned to Cluster 1 and four to Cluster 2. In comparison, 197 Cluster 1 observations and 57 Cluster 2 observations occurred outside the recorded benchmark execution windows.

The application-level comparison showed that HPCC contributed 67 observations to Cluster 1 out of 121 unique HPCC-aligned observations. HemelB contributed 11 Cluster 1 observations and four Cluster 2 observations, while DFTB+ contributed four Cluster 1 observations. The nine ASCOT5-aligned observations were all assigned to Cluster 0. These findings demonstrate an association between some benchmark executions and the less common resource profiles, particularly for HPCC. However, the presence of Cluster 1 and Cluster 2 observations outside recorded benchmark windows indicates that the identified resource patterns cannot be attributed exclusively to benchmark activity. Other workload activity or unrecorded system behaviour may also contribute to these observations.

#### Interpretation and research implications

The exploratory clustering analysis provides evidence that the monitored HPC environment exhibited several distinct combinations of resource behaviour. The dominant cluster represents low-activity operating conditions, while the smaller clusters capture observations associated with increased CPU and network activity or elevated disk and I/O activity.

The pronounced imbalance between the clusters reflects the distribution of workload conditions within the collected dataset. It does not, by itself, establish that the smaller clusters represent hardware faults or system failures. They may reflect legitimate benchmark activity, other workload conditions or unusual resource behaviour that requires further investigation.

The clustering analysis also highlights an important consideration for anomaly detection. A model trained predominantly on low-activity observations may assign high anomaly scores to legitimate but less frequently observed benchmark workloads. This creates a risk of false-positive alerts if workload context is not considered when interpreting model outputs.

The K-Means model produced a silhouette score of 0.9954. Although this indicates strong separation according to the calculated silhouette measure, the score must be interpreted alongside the highly imbalanced cluster distribution. The two smaller clusters contain very few observations, and the silhouette score alone does not establish that the identified workload categories are stable, representative or suitable as ground-truth labels.

Therefore, K-Means was used as an exploratory technique for identifying and describing resource-use patterns rather than as a final anomaly classifier. The resulting cluster profiles provide additional context for the subsequent development and evaluation of the machine-learning-based anomaly-detection solution.

### 8.1.4 Data Quality Findings

The following assessment summarises the observed data-quality outcomes for the raw telemetry extraction, the separate 15-second Pandas-based exploratory feature dataset and the strict 17-feature dataset used for clustering. These results are distinct from the DuckDB model-candidate output sizes documented in Section 4.3.

A data-quality assessment was conducted to examine the completeness, consistency and suitability of the collected telemetry for subsequent preprocessing and machine-learning development. The assessment considered the original Prometheus extraction, the derived 15-second feature dataset and the final one-minute model-input dataset. Examining these representations separately is important because the absence of missing values in the raw extraction does not necessarily imply that every derived resource measurement is valid. In particular, several features are calculated from cumulative counters and therefore depend on the availability and validity of consecutive observations.

Completeness of the raw telemetry extraction

The consolidated raw dataset contained 49,616,574 records across the four monitored nodes. A full inspection of its five fields—timestamp, node identifier, metric name, labels and value—identified no missing values, invalid timestamps or non-numeric measurement values. This confirms that the extracted records were structurally complete with respect to the fields required for subsequent processing.

The distribution of records across the monitored nodes was not uniform.

**Table 8.9: Distribution of raw telemetry records across monitored nodes.**

| Node | Raw telemetry records | Percentage of records |
| --- | --- | --- |
| compute001 | 13,061,640 | 26.32% |
| compute002 | 12,789,782 | 25.77% |
| compute003 | 12,789,104 | 25.77% |
| headnode | 10,976,048 | 22.12% |
| Total | 49,616,574 | 100.00% |

The differences in raw record counts should not, on their own, be interpreted as evidence of incomplete monitoring on particular nodes. The long-format dataset contains separate time series for individual metric and label combinations. Consequently, the number of records generated by a node is influenced by the metric series and associated labels exposed by that node, including device, processor and filesystem identifiers. Raw record counts therefore provide an indication of the distribution of extracted telemetry, but they are not a direct measure of scrape completeness.

Furthermore, the absence of missing values in the raw CSV fields does not establish that every metric series contains an uninterrupted sequence of observations. Temporal gaps and counter irregularities must be assessed at the individual time-series level, particularly before deriving resource-activity rates.

Quality of the derived 15-second feature dataset

Following the initial processing of the raw telemetry, the derived 15-second dataset contained 322,560 rows and 106 columns. It represented all four nodes, with 80,640 observations per node. The dataset included engineered CPU, memory, disk, network, filesystem and system-load measurements, together with data-quality indicators.
**Table 8.10: CPU measurement validity in the 15-second exploratory dataset.**


The quality checks identified a small number of observations with invalid or unavailable resource measurements. For the compute nodes, the CPU validity checks produced the following results:
| Compute node | Total observations | Valid CPU observations | Invalid CPU observations |
| --- | --- | --- | --- |
| compute001 | 80,640 | 80,634 | 6 |
**Table 6.11: Model-row quality-check outcomes for the compute nodes.**

| compute002 | 80,640 | 80,633 | 7 |
| compute003 | 80,640 | 80,633 | 7 |

Memory and system-load validity checks identified three observations per compute node that did not satisfy the corresponding quality requirements. The model-row quality indicator also identified a small number of observations that were unsuitable for inclusion in the prepared compute-node data:
| Compute node | Observations passing the model-row quality check | Excluded observations |
| --- | --- | --- |
| compute001 | 80,627 | 13 |
| compute002 | 80,633 | 7 |
| compute003 | 80,629 | 11 |

These results indicate that the large majority of the derived observations passed the applicable quality checks. Nevertheless, retaining explicit quality indicators was important because a structurally present observation may still contain a resource measurement that cannot be reliably derived or interpreted.

An additional observation concerns the initial part of the monitoring period. The first 15-second feature record contained unavailable resource measurements and was not considered suitable for model-row inclusion. This is consistent with the need to establish valid measurement intervals when deriving features from cumulative counters. However, the available results do not establish a single definitive cause for every unavailable value in that initial record.

Quality of the final model-input dataset

The strict 17-feature exploratory dataset contained 60,463 observations and represented the three compute nodes. It covered the period from 18 October 2026 at 00:01 UTC to 31 October 2026 at 23:59 UTC. Quality checks on this prepared dataset identified no missing feature values, infinite values or duplicate node-timestamp observations.

This provides evidence that the final model-input representation satisfied the principal structural requirements for the subsequent model-development stage. Each retained observation contained the complete set of 17 features in the prepared feature matrix, and the node-timestamp combination was unique. The head node was not included in this modelling dataset because the model-development objective focused on the operational behaviour of the compute nodes.

The quality of the final dataset should, however, be interpreted in the context of the filtering and preparation applied during feature engineering. The absence of missing or infinite values in the final model input does not mean that the original monitoring data was entirely free of measurement limitations. Rather, it indicates that observations failing the applicable preparation requirements were not retained in the strict model-input dataset.

Implications for the subsequent analysis

The data-quality assessment provides three important observations for the remainder of the study. First, the raw extraction was structurally complete across its five fields, but temporal continuity still required validation at the metric-series level. Second, the derived 15-second dataset contained a small number of observations that did not satisfy the resource-measurement quality checks. Third, the final strict 17-feature dataset contained no missing values, infinite values or duplicate node-timestamp records.

These observations support the use of the prepared dataset for machine-learning development while emphasising the importance of maintaining quality checks throughout the transformation process. In particular, monitoring gaps, counter resets and unavailable measurements must not be interpreted as genuine zero-resource activity. Treating such conditions explicitly helps reduce the risk of introducing artificial patterns into the feature matrix.

The assessment also establishes an important limitation of the collected data: it represents a specific monitoring period from a small-scale, three-compute-node environment. Although the observations provide a useful empirical basis for investigating resource behaviour and anomaly detection, they do not represent every possible workload condition or failure mode that may occur in larger HPC installations. The subsequent experimental validation is therefore necessary to examine how the developed model responds to controlled conditions that may not be sufficiently represented in the collected operational telemetry.

Overall, the data-quality results indicate that the final prepared dataset was structurally suitable for the modelling experiments, while also demonstrating why quality assessment and conservative handling of unavailable measurements are necessary components of an HPC telemetry-processing pipeline.

## 8.2 Comparative Model Benchmarking Results

The six candidate algorithms were compared using model training time and the percentage of validation and testing observations designated as potential anomalies. The results below are taken from the final V6 model-training notebook and correspond to the DuckDB-based 60,475-row candidate dataset and its model-specific 70/15/15 chronological partition.

Following training, a comparative benchmarking exercise was conducted to examine the computational performance and anomaly-designation behaviour of the six candidate algorithms. Two dimensions of comparison were evaluated: model training time (wall-clock duration of the fitting process) and the proportion of observations designated as potential anomalies in the validation and testing datasets.

Benchmarking Results

**Table 8.12: Comparative model benchmarking results.**

| Model | Training Time (s) | Validation Flags (%) | Testing Flags (%) |
| --- | --- | --- | --- |
| Isolation Forest | 2.46 | 0.90 | 6.74 |
| Local Outlier Factor | 7.27 | 1.71 | 24.99 |
| Gaussian Mixture Model | 4.05 | 1.94 | 25.39 |
| PCA (Reconstruction Error) | 0.06 | 1.98 | 25.61 |
| Autoencoder | 30.28 | 1.75 | 25.87 |
| One-Class SVM | 6.38 | 1.95 | 25.98 |

Source: V6 model training notebook, computed over the chronologically partitioned telemetry dataset.

The results reveal a notable divergence in anomaly-designation behaviour. Isolation Forest designated 0.90% of validation observations and 6.74% of testing observations as anomalous. The remaining five algorithms designated between 1.71% and 1.98% of validation observations and between 24.99% and 25.98% of testing observations—a strikingly consistent range suggesting that these algorithms respond similarly to the distributional shift between the training and testing periods.

The elevated flagging rates observed in the testing period across all models are consistent with a distributional shift in cluster behaviour during the final days of the collection period. If the workload composition, node utilisation patterns or external conditions changed between the training and testing periods, models that learned a tight characterisation of training-period normality would be expected to flag a larger proportion of testing-period observations. The critical operational distinction is that Isolation Forest's flagging rate (6.74%) remained within a range that could plausibly be investigated by an administrator, whereas flagging rates approaching 25% would generate alert volumes that are operationally unmanageable—a condition that contributes to the alert fatigue identified in the HPC operations literature (Tuncer et al., 2017).

PCA recorded the shortest training time (0.06 seconds), reflecting the closed-form eigen decomposition underlying its fitting procedure. The Autoencoder required the longest training time (30.28 seconds), consistent with the iterative gradient-based optimisation process inherent in neural network training.

Model Selection Rationale

Based on the benchmarking results, Isolation Forest was selected for the initial deployment of the anomaly detection system. The selection was motivated by three considerations:
- Operationally viable flagging rate. Isolation Forest's lower designation rate reduces the burden of false-positive investigation, a critical factor for adoption in operational HPC environments.
- Computational efficiency. Its 2.46-second training time and linear-complexity inference permit rapid retraining and real-time scoring within the monitoring pipeline.
- Algorithmic robustness. Isolation Forest's random-partitioning mechanism does not require feature scaling, is relatively insensitive to the curse of dimensionality, and degrades gracefully as feature count increases (Liu et al., 2008).
Acknowledged Limitations of the Selection Process

Several limitations of the benchmarking exercise must be documented transparently.

First, the anomaly-flagging percentages represent the proportion of observations designated as anomalous by each model. They do not constitute measures of detection accuracy, as no verified ground-truth anomaly labels are available against which to compute precision, recall or F1-score. A model that flags fewer observations is not necessarily more accurate; it may simply be less sensitive.

Second, the testing dataset was examined during the model-selection process. Consequently, the testing subset was not retained as a fully independent held-out evaluation set in the strict methodological sense. Future work should incorporate a separate held-out period or external dataset for final evaluation.

Third, the hyperparameter configurations for the non-selected models were not exhaustively optimised. It is possible that alternative configurations—particularly different contamination rates, kernel parameters for OC-SVM, or architectural choices for the Autoencoder—could yield more competitive results. The benchmarking exercise provides an initial comparative assessment rather than a definitive ranking.

Isolation Forest is therefore described as the model selected for the initial implementation, rather than conclusively established as the optimal anomaly detection algorithm for HPC telemetry.

## 8.3 Isolation Forest Anomaly-Score Distribution Analysis

This section is reserved for the distributional analysis of Isolation Forest anomaly scores across the training, validation and testing periods. The score-distribution plot and its supporting descriptive statistics have not yet been incorporated into the consolidated report. The section should be completed using the actual saved scores from the final V6 training run; no distributional statistics are inferred here.

## 8.4 Normal-Workload Validation and Anomaly-Injection Results

This section is reserved for the results of the normal-workload validation and controlled anomaly-injection experiments described in Chapter 5. The consolidated report currently contains the experimental methodology but does not contain completed results for the five proposed injection scenarios. Precision, recall, F1-score, false-positive rate, detection latency and alert frequency should only be reported after ground-truth injection intervals and corresponding inference outputs have been recorded.

## 8.5 Discussion of Findings

The discussion should synthesise the exploratory workload findings, comparative model results and controlled validation outcomes. It should distinguish legitimate workload-related resource variation from behaviour associated with controlled anomaly injections and should discuss the operational implications and limitations of the deployed inference service. This section should be completed after the score-distribution and anomaly-injection results have been incorporated.


---

## Editorial checklist — not part of the report text

1. Confirm final consistency between the DuckDB V6 model-candidate workflow (60,475 rows) and the separate Pandas/Colab exploratory dataset (60,463 rows). They are deliberately described as separate datasets in this draft.
2. Verify the source reference list and complete bibliographic details for every in-text citation.
3. Insert the actual architecture/data-pipeline diagrams and notebook figures where required by the final document layout.
4. Add the previously drafted anomaly-injection procedure details if they differ from the concise methodology reconstructed here. Do not report injection results until the experiments have been executed and labelled.
5. Complete Sections 6.3–6.5 after exporting the actual Isolation Forest score distributions and running the validation experiments.
6. The current API binding is loopback-only; do not describe remote ingestion or Prometheus-to-API integration as operational until that integration is separately demonstrated.
