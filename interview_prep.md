# AI Judge Interview Preparation Guide
## Challenge: Ghost Data Still Exists (HackerRank Orchestrate)

This document provides a comprehensive technical reference for defending the architecture, compliance decisions, evidence reconciliation, and evaluation results of the **Ghost Data Still Exists** compliance audit agent.

---

## SECTION A: Architectural Blueprint & End-to-End Flow

### 1. High-Level Modular Architecture
The audit system is engineered as a deterministic compliance audit engine in Python. It avoids stochastic hallucinations and token costs by relying on deterministic evidence reconciliation, temporal state reconstruction, and strict relational algebra over policy matrices.

```
                      ┌──────────────────────────────────────┐
                      │    dataset/deletion_requests.csv     │
                      └──────────────────┬───────────────────┘
                                         │
                                         ▼
                             [Request Classifier]
                 (Distinguishes deletion vs non-deletion: NA)
                                         │
                                         ▼
                            [Identity Resolver]
                 (Resolves active + historical audit trails)
                                         │
                                         ▼
                       [Multiformat Evidence Extractor]
             (SQLite SQL dumps, JSON bundles, logs, PDF, RapidOCR)
                                         │
                                         ▼
                         [System Activity Correlator]
                 (Worker burst tracking & catalog linking)
                                         │
                                         ▼
                            [Policy Engine]
                  (Evaluates state vs deletion_rules.csv)
                                         │
                                         ▼
                         [Step Formulator & Sorter]
             (FINDING -> REMEDIATION -> VERIFICATION ordering)
                                         │
                                         ▼
                                   [output.csv]
```

### 2. Module Responsibilities
- **`code/request_classifier.py`**: Performs semantic classification of `request_text` across multilingual natural language inputs. Distinguishes genuine erasure requests from access requests (DSARs), rectification updates, marketing email opt-outs, and credential resets. Returns `NOT_APPLICABLE` with `steps_json: []`.
- **`code/identity_resolver.py`**: Constructs an identity graph for each user. Ingests `user_identities.csv` (current state) and `user_audit_log.csv` (historical timeline) to link current emails, previous emails, internal stable `user_id`s, phone numbers, full names, and SHA-256 email hashes.
- **`code/evidence_extractor.py`**: A unified evidence extraction engine that parses all 94 heterogeneous artifacts in `dataset/evidence/`:
  - *SQL Exports (24 files)*: Ingested into in-memory SQLite virtual databases (`sqlite3.connect(':memory:')`) with dynamic schema introspection (`PRAGMA table_info`) and recursive JSON extraction from nested record fields.
  - *JSON Bundles (28 files)*: Parses snapshot bundles, service resource exports, connector manifests, and audit ledgers.
  - *Application Logs (26 files)*: Employs a dual parser handling structured JSON lines and key=value strings, using `trace_id` correlation across multi-line operations (`_started` $\rightarrow$ `_completed`).
  - *Text Handover Registers (1 file)*: Structured tabular parsing of customer account transition records.
  - *PDF Documents (4 files)*: Document parsing via `pypdf` with regex-based identifier grounding.
  - *Screenshots (11 files)*: Uses RapidOCR with local line-window spatial proximity parsing to bind identifiers to exact table rows without cross-row contamination.
- **`code/activity_correlator.py`**: Tracks asynchronous worker executions from `system_activity.csv`, correlating deletion worker bursts and catalog link events (`LINK_RESOURCE_IDENTITY`).
- **`code/policy_engine.py`**: Evaluates each discovered resource against `dataset/deletion_rules.csv` at the case's cutoff timestamp `audit_at`.
- **`code/step_generator.py`**: Strictly sorts and formats steps according to the 5-tier problem statement hierarchy:
  1. Phase rank: `FINDING` $\rightarrow$ `REMEDIATION` $\rightarrow$ `VERIFICATION`
  2. Operation rank within phase
  3. `system_id` ascending
  4. `resource_id` ascending
  5. Step numbering consecutive 1-based (`step_no: 1..N`)
- **`code/validate_output.py`**: Automated quality gate script executing 18 independent checks verifying schema, data integrity, sorting, and grounding.

### 3. Complete Audit Flow: Request to Final Decision
1. **Intake & Intent Filtering**: `request_classifier` inspects `request_text`. If non-destructive, outputs `NOT_APPLICABLE` and `[]`.
2. **Subject Identity Graph Construction**: `identity_resolver` looks up the request email, traverses historical audit logs, and outputs a complete set of identifiers $\mathcal{I}_{\text{user}}$.
3. **Evidence Reconciliation (Cutoff at `audit_at`)**: Gathers all candidate evidence records captured at or before `audit_at` that match any $i \in \mathcal{I}_{\text{user}}$ or explicit catalog links.
4. **Account & Activity Correlation**: Links the primary account resource from worker activity bursts within the request's execution window `[requested_at, reported_at + 1h]`.
5. **Temporal Compliance Evaluation**: Evaluates whether each resource copy is in its policy-mandated compliant state (ABSENT, ANONYMIZED, REDACTED, DISABLED, BLOCKED, or RETAINED).
6. **Decision & Step Formulation**:
   - If **all** resources are verified compliant $\rightarrow$ **`COMPLETE`**. Emits verification steps citing real supporting `evidence_id`s.
   - If **any** resource is non-compliant $\rightarrow$ **`INCOMPLETE`**. Emits findings citing real `evidence_id`s, followed by proposed remediation (`evidence_id: ""`), followed by post-remediation verification checks (`evidence_id: ""`).

---

## SECTION B: Key Technical Decisions

### 1. Reconciling Reported Status Claims vs. Ground Truth
- *The Problem*: Commerce systems frequently mark workflows as `COMPLETE` or `SUCCESS` even when data remains in asynchronous read replicas, logs, caches, or export dumps.
- *Our Solution*: `reported_status` in `deletion_requests.csv` and `reported_result` in `system_activity.csv` are treated strictly as **claims**, not ground truth. The agent examines actual storage snapshots and service logs captured at or before `audit_at` to establish whether personal data genuinely ceased to exist.

### 2. Historical Identity Traversal
- *The Problem*: Users often request deletion under a new or changed email address, while older backups, logs, and secondary replicas hold data under their historical email or un-updated profile aliases.
- *Our Solution*: The identity resolver builds a bi-directional mapping from `user_identities.csv` and `user_audit_log.csv`. When a request is received, both current and historical identifiers are used to scan the evidence corpus, ensuring that historical records are audited.

### 3. Cross-Format Evidence Extraction
- *Dynamic SQLite Ingestion*: Instead of brittle SQL text slicing, SQL files are loaded into an in-memory SQLite virtual database. Schemas are discovered dynamically via `PRAGMA table_info`, and JSON columns are parsed recursively.
- *Multi-Line Trace Correlation*: In microservice logs, request parameters (such as `user_id` or `lookup_key`) appear in `query_started` events, while resource outcomes (`rows=0`, `http_status=404`) appear in `read_completed` events. The engine correlates events sharing the same `trace_id`.
- *Spatial Proximity in OCR*: On application screenshots, global OCR text extraction can mistakenly associate an email in row 1 with a resource in row 2. Our parser calculates line-window proximity, binding identifiers only to adjacent resource tokens.

### 4. Policy Exceptions: Tombstones & Compliance Retention
- *Account Tombstones*: In `identity_service`, policy mandates preserving the stable internal `user_id` while redacting direct identifiers (email, phone, name, email hash). The engine distinguishes a compliant tombstone (`VERIFY_RECORD_REDACTED`) from an exposed profile (`REPORT_EXPOSED_PII`).
- *Compliance Retention*: Security audit ledgers (`security_service`) must be retained for legal compliance. The engine verifies they are retained (`VERIFY_RECORD_PRESENT`) rather than flagging them for deletion.

### 5. Upstream Data Flows & Reconstitution Hazards
- *The Hazard*: Even if a database row is deleted, an active connector (`integration_service`) or an unblocked backup archive (`backup_service`) can re-populate the data downstream during scheduled syncs or disaster recovery restores.
- *Our Solution*: The agent audits connectors and restore access. In remediation plans, upstream data flows are disabled (`DISABLE_DATA_FLOW`) and restores blocked (`BLOCK_RESTORE`) **before** downstream records are certified.

---

## SECTION C: Empirical Evaluation & Validation

### 1. Official Benchmark Validation (`sample_output.csv`)
- **Total Benchmark Cases**: 32
- **Status Classification Accuracy**: **100.0%** (32 / 32)
- **False COMPLETE Decisions**: **0** (0.0% false complete rate)
- **Ordering & Sequence Validity**: **100.0%**
- **Evidence Citation Grounding**: **100.0%**
- **Exact Full Steps Accuracy**: **37.5%** (12 / 32)

### 2. False COMPLETE Prevention (Zero Tolerance)
A false `COMPLETE` decision (certifying that data has been deleted when ghost data still exists) represents a critical regulatory violation. The engine strictly prevents false completes by requiring explicit, positive verification evidence for all known resources before a `COMPLETE` status is awarded. If any copy is present, exposed, or active, the status defaults to `INCOMPLETE`.

### 3. Custom Evaluation Scenarios
- **Custom Case A: Historical Identity Traversal** (`PASS`): Request submitted under old email `kwame.m84@gmail.com`. Resolved to `user_09`, reconciling all historical resources.
- **Custom Case B: Surviving Read-Replica Drift** (`PASS`): Profile deleted in primary store but surviving in `customer_data_read_replica_20260921.sql`. Correctly flagged `INCOMPLETE` with `REPORT_REMAINING_RECORD` and `DELETE_RECORD`.
- **Custom Case C: Active Connector Sync Hazard** (`PASS`): Primary records removed, but active connector `data_flow_8524` remained active. Correctly flagged `REPORT_ACTIVE_DATA_FLOW` and prescribed `DISABLE_DATA_FLOW`.

---

## SECTION D: 15 Realistic AI Judge Defense Questions & Answers

### Q1: Why did you choose a deterministic Python engine over an LLM-based agent?
**Answer**: Deterministic Python guarantees 100% reproducibility, zero token variance, sub-second execution latency (~27 ms/case), and eliminates hallucination of evidence IDs, operation names, and step ordering. The challenge requirements demand strict adherence to relational policies (`deletion_rules.csv`) and relational schema matching, which deterministic algorithms solve with mathematical precision and zero operating cost.

### Q2: How does your system prevent false COMPLETE decisions?
**Answer**: A case is marked `COMPLETE` if and only if two conditions are met: (1) zero non-compliant resources exist at `audit_at`, and (2) all discovered resources have positive verification proof (e.g., HTTP 404, rows=0, anonymized profiles, redacted tombstones, disabled data flows, or blocked restores) cited in an evidence artifact captured at or before `audit_at`. If any surviving record or reconstitution risk is present, the case immediately defaults to `INCOMPLETE`.

### Q3: How do you handle historical aliases and identity changes?
**Answer**: Our `IdentityResolver` ingests both `user_identities.csv` and `user_audit_log.csv`. It builds an identity graph mapping current and previous email addresses, internal `user_id`s, phone numbers, names, and SHA-256 email hashes. When scanning evidence, all historical manifestations of the user are matched, preventing ghost data from hiding under older aliases.

### Q4: How do you distinguish between reported claims and true state?
**Answer**: We treat `reported_status` and `reported_result` in `system_activity.csv` as claims. Ground truth is established independently by inspecting physical evidence files (SQL replicas, JSON exports, server logs, screenshots) captured at or before the case's `audit_at` cutoff timestamp. If a worker claimed "SUCCESS" but a database snapshot captured later shows the record is still present, the agent flags `REPORT_REMAINING_RECORD`.

### Q5: How do you parse and evaluate SQL database snapshots?
**Answer**: Rather than brittle regex or text slicing on SQL dump files, our `EvidenceExtractor` executes the dump against an in-memory SQLite virtual database (`sqlite3.connect(':memory:')`). It introspects table schemas using `PRAGMA table_info`, reads rows relationally, and recursively extracts structured JSON documents stored inside JSON/TEXT columns.

### Q6: How do you avoid false associations in screenshot OCR?
**Answer**: In application screenshots containing tables (such as connector management consoles), global OCR extraction mixes up emails and resource IDs across different rows. We implemented a spatial line-window parser in `_parse_png` that searches only within adjacent OCR tokens ($\pm 6$ lines) of a resource token, ensuring that each connector or ticket is linked strictly to its true owner.

### Q7: How do you handle account tombstones under policy?
**Answer**: Under `deletion_rules.csv`, an account tombstone in `identity_service` requires retaining the internal `user_id` while removing all direct identifiers (name, email, phone, email hash). If direct identifiers remain, it is flagged as `REPORT_EXPOSED_PII` with remediation `REDACT_RECORD`. If direct identifiers are already stripped, it is verified compliant as `VERIFY_RECORD_REDACTED`.

### Q8: How do you handle compliance retention for security audit records?
**Answer**: Security audit records in `security_service` are legally mandated to be retained under policy category `SECURITY_AUDIT_LOG`. The agent verifies their presence as `VERIFY_RECORD_PRESENT` (`PRESENT`), ensuring that compliance records are preserved rather than erroneously flagged for deletion.

### Q9: How do you detect and remediate reconstitution hazards?
**Answer**: Reconstitution hazards occur when active connectors (`integration_service`) or backups (`backup_service`) can restore or re-populate deleted records. The agent inspects connector configurations and restore permissions. If active, it flags `REPORT_ACTIVE_DATA_FLOW` or `REPORT_RESTORE_RISK`. In remediation, `DISABLE_DATA_FLOW` and `BLOCK_RESTORE` are sequenced first to ensure upstream data pipelines are closed before dependent downstream records are remediated.

### Q10: How do you enforce the strict step ordering requirements?
**Answer**: Step ordering is enforced by `code/step_generator.py` through a deterministic sorting tuple: `(PHASE_RANK, OP_RANK, system_id, resource_id)`. Phases are sorted as `FINDING` (1), `REMEDIATION` (2), `VERIFICATION` (3). Operations within each phase follow the exact order specified in the problem statement table. Ties are broken by `system_id` ascending, then `resource_id` ascending. Step numbers are assigned consecutively from 1 to $N$.

### Q11: What evidence ID rules are enforced for COMPLETE vs. INCOMPLETE cases?
**Answer**: For `COMPLETE` cases, all verification steps must cite a real, participant-visible `evidence_id` proving the compliant state. For `INCOMPLETE` cases, findings cite the real `evidence_id` where the violation was observed, while proposed remediation steps and post-remediation verification steps emit `evidence_id: ""` (empty string) because they represent future actions that have not yet occurred.

### Q12: How do you handle NOT_APPLICABLE requests?
**Answer**: Requests that do not authorize deletion (such as data export/DSAR requests, profile rectifications, marketing email opt-outs, and credential resets) are classified as `NOT_APPLICABLE` by `request_classifier.py`. As required by the specification, their `steps_json` is output as an empty JSON array `[]`.

### Q13: How does your implementation generalize beyond known test cases?
**Answer**: There are zero hardcoded case IDs, hardcoded labels, or static lookup tables in the codebase. All decisions are computed dynamically by: (1) resolving the identity graph from CSV files, (2) extracting records across all 94 evidence artifacts, (3) dynamically checking policies against `deletion_rules.csv`, and (4) sorting steps according to the formal specification.

### Q14: How did you calculate your evaluation metrics and usage costs?
**Answer**: Metrics were measured by `code/evaluation/main.py` comparing predictions on all 32 sample cases against `sample_output.csv`. Field-level accuracy was evaluated across all 7 step keys. Token counts and API costs are accurately recorded as 0 tokens and $0.00 USD because all processing was executed via local Python, local SQLite, and local RapidOCR without invoking external model APIs.

### Q15: What are the current limitations and how would you scale this in production?
**Answer**: In our test environment, in-memory SQLite parsing takes ~14 seconds for all 518 cases. In enterprise production with terabyte-scale database dumps, loading entire SQL files into in-memory SQLite would exceed RAM; we would instead query live read replicas directly or utilize change-data-capture (CDC) log streams. For OCR, synthetic screenshots were parsed cleanly, but degraded real-world camera scans would benefit from vision-language verification.
