# Ghost Data Still Exists — Compliance Audit Agent

This directory contains the production-ready implementation of the compliance audit agent for the HackerRank Orchestrate challenge **"Ghost Data Still Exists"**.

---

## 1. Architecture Overview

The system is designed as a modular, deterministic compliance verification pipeline that establishes the temporal truth of deletion requests across distributed microservices and heterogeneous storage backends.

```
                  ┌──────────────────────────────┐
                  │   deletion_requests.csv      │
                  └──────────────┬───────────────┘
                                 │
                                 ▼
                     Request Intent Classifier
                     (Filters NOT_APPLICABLE)
                                 │
                                 ▼
                     Identity Resolution Engine
               (user_identities.csv + user_audit_log.csv)
                                 │
                                 ▼
                    Multiformat Evidence Reader
      (JSON bundles, SQLite SQL dumps, logs, PDF, RapidOCR PNG)
                                 │
                                 ▼
                   System Activity Correlator
                 (Temporal cluster matching)
                                 │
                                 ▼
                     Policy Compliance Engine
                       (deletion_rules.csv)
                                 │
                                 ▼
                 Status Decision & Step Generator
               (FINDING -> REMEDIATION -> VERIFICATION)
                                 │
                                 ▼
                            output.csv
               (Exactly 518 sorted rows, valid JSON)
```

---

## 2. Module Summary

- **`main.py`**: CLI entrypoint to audit deletion requests. Reads input CSV, coordinates agent processing, and generates sorted `output.csv`.
- **`audit_agent.py`**: Core orchestrator connecting identity resolution, evidence extraction, activity correlation, bipartite batch matching, observation proximity clustering, policy checking, and step formulation.
- **`request_classifier.py`**: Analyzes natural language request intent to distinguish valid deletion authorizations from non-deletion requests (data exports, profile rectifications, marketing opt-outs).
- **`identity_resolver.py`**: Reconstructs current and historical user identities (emails, previous emails, user IDs, phone numbers, email hashes) using `user_identities.csv` and `user_audit_log.csv`.
- **`evidence_extractor.py`**: Reusable multiformat extraction engine for all 94 evidence files in `dataset/evidence/`:
  - 28 JSON snapshot bundles, exports, and audit ledgers
  - 24 SQL database dump snapshots parsed via dynamic in-memory SQLite virtual databases
  - 26 Structured and plain-text application logs with `trace_id` correlation across multi-line operations
  - 1 TXT customer account handover report
  - 4 PDF compliance extracts with text extraction
  - 11 PNG screenshots with RapidOCR spatial text parsing
- **`activity_correlator.py`**: Correlates worker activities from `system_activity.csv` and tracks explicit catalog links (`LINK_RESOURCE_IDENTITY`).
- **`policy_engine.py`**: Implements compliance policies defined in `deletion_rules.csv` across all system types.
- **`step_generator.py`**: Implements strict deterministic ordering rules:
  1. Group by phase: `FINDING` -> `REMEDIATION` -> `VERIFICATION`
  2. Sort by allowed operation order within phase
  3. Sort by `system_id` ascending
  4. Sort by `resource_id` ascending
  5. Assign consecutive 1-based step numbers
- **`validate_output.py`**: Automated 18-point quality gate script verifying output schema, row counts, sorting, valid statuses, consecutive numbering, allowed operations, and evidence grounding.
- **`evaluation/main.py`**: Evaluator testing performance on official sample cases (`sample_output.csv`) and team-constructed edge cases, generating `evaluation_report.md` and `usage_report.md`.
- **`evaluation/test_regressions.py`**: Automated 11-test regression suite covering temporal leakage, concurrent worker isolation, tombstone preservation, active sync flows, and bipartite batch assignment.

---

## 3. How to Run

### Run Full Pipeline on All 518 Requests
```bash
python code/main.py --input dataset/deletion_requests.csv --output output.csv
```

### Run Evaluation Suite & Generate Reports
```bash
python code/evaluation/main.py
```

### Run Regression Test Suite
```bash
python code/evaluation/test_regressions.py
```

### Run 18-Point Automated Quality Gate
```bash
python code/validate_output.py
```

---

## 4. Key Performance Results

- **Sample Exact Full-Step Accuracy**: **90.6%** (29 / 32 cases exact JSON array match)
- **Sample Status Accuracy**: **100.0%** (32 / 32 cases correct)
- **Diagnostic Weighted Field Accuracy**: **99.7%** (1,333 / 1,337 fields)
- **Positional Field Accuracy**: **98.7%** (1,327 / 1,344 fields)
- **False COMPLETE Decisions**: **0** (Zero compliance violations)
- **Deterministic Ordering Validity**: **100.0%**
- **Evidence Citation Grounding**: **100.0%**
- **Automated Regression Suite**: **11 / 11 PASS** (0.175s)
- **Output Record Count**: Exactly 518 data rows (+ 1 header)
- **Total Token Usage & Cost**: 0 tokens, $0.00 (Fully deterministic, air-gapped local execution)
