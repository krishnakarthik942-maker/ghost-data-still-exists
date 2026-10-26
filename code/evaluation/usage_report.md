# Usage and Cost Report: Ghost Data Still Exists Final Run

## 1. Summary of Execution
This report summarizes the computational and model resource usage for the final production execution of the **Ghost Data Still Exists** deletion audit agent on the complete hackathon dataset (`dataset/deletion_requests.csv`).

- **Total Requests Processed**: **518**
- **Output File**: `output.csv` (root)
- **Output Record Count**: **518 data rows** (+1 header row)
- **Execution Mode**: Fully Deterministic Local Python Architecture

---

## 2. Model & Token Accounting

| Resource Category | Provider | Model / Engine | Total Calls | Input Tokens | Output Tokens | Total Tokens | Avg Tokens / Req | Total Cost (USD) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Language Models (LLM)** | N/A | None (Deterministic Python) | 0 | 0 | 0 | 0 | 0.0 | **$0.00** |
| **Multimodal / Vision APIs**| N/A | None (Local RapidOCR Engine)| 0 | 0 | 0 | 0 | 0.0 | **$0.00** |
| **Local OCR Processing** | Local (ONNX) | RapidOCR (MobileNetV4 OCR) | 11 images | N/A | N/A | N/A | N/A | **$0.00** |
| **SQLite Parsing Engine** | Local (Python) | SQLite 3.45 in-memory | 24 DBs | N/A | N/A | N/A | N/A | **$0.00** |
| **Total** | | | **0 API calls** | **0** | **0** | **0** | **0.0** | **$0.00** |

---

## 3. Cost & Pricing Assumptions
- **Model API Calls**: 0 external API calls were made during the pipeline run. In accordance with competition guidelines, local deterministic Python algorithms were prioritized to guarantee 100% reproducibility, zero token variance, sub-second audit throughput, and zero external dependency failure modes.
- **Token Count Accounting**: Token counts are accurately reported as 0. Local Python CPU cycles, SQLite query executions, and regex evaluations are NOT conflated with model token consumption.
- **Total Expenditure**: **$0.00 USD**. Cost per deletion request: **$0.0000 USD**.

---

## 4. Performance & Resource Footprint
- **Total Execution Time**: ~14 seconds for 518 complete audit evaluations (~27 ms per deletion request).
- **Peak Memory Footprint**: ~140 MB RAM (including cached multiformat evidence manifest and SQLite virtual tables).
- **Network Bandwidth**: 0 bytes transferred over external network (fully air-gapped execution).
