# Residual Mismatch Report: Ghost Data Still Exists Benchmark

**Evaluation Set:** `dataset/sample_deletion_requests.csv` (32 Public Requests)  
**Expected Canonical Output:** `dataset/sample_output.csv`  
**Current Measured Performance:**
- Case Status Accuracy: **100.0% (32/32)**
- False COMPLETE Count: **0**
- Exact Full-Step Case Accuracy: **71.9% (23/32)**
- Total Expected Steps: **193**
- Total Predicted Steps: **188**
- Semantically Aligned Steps: **188 / 193** (Recall: 97.4%, Precision: 100.0%, F1: 98.7%)
- Missing Expected Steps: **5**
- Extraneous Predicted Steps: **0**
- Failing Cases (Exact Equality): Exactly **9 cases** (`case_03`, `case_18`, `case_20`, `case_23`, `case_25`, `case_26`, `case_27`, `case_28`, `case_31`)

---

## 1. Executive Summary of Residual Errors

Across all 32 public benchmark requests, every single case has the correct high-level deletion status (`COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`), with zero false complete decisions.

The remaining 9 mismatches stem from two architectural challenges in correlating anonymized and asynchronous batch operational artifacts:
1. **Concurrent Worker Burst Disambiguation (7 cases: `case_03`, `case_18`, `case_20`, `case_23`, `case_27`, `case_28`, `case_31`)**:
   When multiple deletion requests share identical or near-identical reporting windows (e.g. 12:00:00Z on 2026-08-30, 2026-09-02, 2026-09-05, 2026-09-06, 2026-09-09), multiple worker activity tasks occur within minutes of each other in `system_activity.csv`. Proximity sorting to `reported_at` selects the event with the smallest delta $|t - t_{rep}|$, which occasionally selects an adjacent task belonging to another request in the same burst.
2. **Anonymized Export Profile Linkage (2 cases: `case_25`, `case_26`)**:
   In `evidence_92` (`service_resource_export_20260915_114455.json`), account lookups that returned HTTP 404 have `profile: null`, and analytics profiles that were successfully anonymized have `customer_reference: null`, `email: null`, `phone: null`. Because direct PII was purged, these records have empty identifier sets in the evidence extractor and can only be correlated through contextual batch bundles.

---

## 2. Detailed Case-by-Case Analysis

### Case 03: `case_03` (`l.fontaine46@yahoo.com`)
- **Status:** Predicted: `COMPLETE` | Expected: `COMPLETE` (Status Correct)
- **Reported:** `COMPLETE` @ `2026-09-15T11:00:00Z` | **Audit Cutoff:** `2026-09-26T11:00:00Z`
- **Expected Steps (3):**
  1. `VERIFICATION` | `account_service` | `account_7566` | `VERIFY_RECORD_ABSENT` | `ABSENT` | `evidence_94`
  2. `VERIFICATION` | `security_service` | `audit_record_2016` | `VERIFY_RECORD_PRESENT` | `PRESENT` | `evidence_94`
  3. `VERIFICATION` | `analytics_platform` | `analytics_9406` | `VERIFY_RECORD_ANONYMIZED` | `ANONYMIZED` | `evidence_94`
- **Predicted Steps (3):**
  1. `VERIFICATION` | `account_service` | `account_7566` | `VERIFY_RECORD_ABSENT` | `ABSENT` | `evidence_94`
  2. `VERIFICATION` | `security_service` | `audit_record_2016` | `VERIFY_RECORD_PRESENT` | `PRESENT` | `evidence_94`
  3. `VERIFICATION` | `analytics_platform` | `analytics_5589` | `VERIFY_RECORD_ANONYMIZED` | `ANONYMIZED` | `evidence_94`
- **Exact Mismatch:** Step 3 `resource_id`: predicted `analytics_5589` vs expected `analytics_9406`.
- **Source Code Mechanism:** `AuditAgent.audit_case()` lines 330–343. In `system_activity.csv`, worker task `activity_3852` (`analytics_9406`) occurred at `10:31:16Z`, and `activity_3853` (`analytics_5589`) occurred at `10:31:31Z`. Proximity sorting picked `analytics_5589` because it was 15 seconds closer to `11:00:00Z`.
- **Participant Evidence:** `evidence_94` (`resource_lookup_trace_20260926_103856.log`). In this log, `analytics_9406` appears at `09:54:09Z` in close temporal proximity to `audit_record_2016` (`user_43`) at `09:40:29Z`.

---

### Case 18: `case_18` (`mori.ren@gmail.com`)
- **Status:** Predicted: `INCOMPLETE` | Expected: `INCOMPLETE` (Status Correct)
- **Reported:** `COMPLETE` @ `2026-09-09T11:00:00Z` | **Audit Cutoff:** `2026-09-26T11:00:00Z`
- **Expected Steps (14):**
  - Findings: `search_4013`, `analytics_037`, `support_5569`, `data_flow_4890` (all `evidence_94`)
  - Remediation: `DISABLE_DATA_FLOW`, `DELETE_RECORD` (search), `REDACT_RECORD` (support), `ANONYMIZE_RECORD` (analytics)
  - Verification: `account_5521`, `search_4013`, `audit_record_6645`, `support_5569`, `analytics_037`, `data_flow_4890`
- **Predicted Steps (13):**
  - Findings: Exact match (4/4)
  - Remediation: Exact match (4/4)
  - Verification: `account_5193` (instead of `account_5521`), and missing `audit_record_6645`.
- **Exact Mismatches:**
  1. `resource_id` on verification step 9: `account_5193` vs `account_5521`.
  2. Missing verification step: `security_service` `audit_record_6645`.
- **Source Code Mechanism:**
  1. `account_5193` was executed at `11:02:59Z` (delta = 179s to 11:00:00Z), whereas `account_5521` was executed at `09:52:26Z` (delta = 4,054s). Proximity sorting selected `account_5193`, which physically occurred *after* `reported_at`.
  2. `audit_record_6645` does not contain explicit user references in parsed logs prior to `audit_at`.
- **Participant Evidence:** `dataset/system_activity.csv` (`activity_561` for `account_6645`, `activity_3744` for `support_5569`).

---

### Case 20: `case_20` (`akosua.gyasi@gmail.com`)
- **Status:** Predicted: `INCOMPLETE` | Expected: `INCOMPLETE` (Status Correct)
- **Reported:** `NOT_STARTED` @ `2026-09-09T11:00:00Z` | **Audit Cutoff:** `2026-09-26T11:00:00Z`
- **Expected Steps (8):**
  - Findings: `search_4262`, `data_flow_1770` (`evidence_94`)
  - Remediation: `DISABLE_DATA_FLOW`, `DELETE_RECORD`
  - Verification: `account_5037`, `search_4262`, `audit_record_5569`, `data_flow_1770`
- **Predicted Steps (7):**
  - Verification: `account_9335` (instead of `account_5037`), missing `audit_record_5569`.
- **Exact Mismatches:**
  1. `resource_id` on verification step 5: `account_9335` vs `account_5037`.
  2. Missing verification step: `security_service` `audit_record_5569`.
- **Source Code Mechanism:** In `system_activity.csv`, `account_9335` was logged at `10:53:28Z` (6.5 min from 11:00:00Z), while `account_5037` was logged at `10:14:55Z` (45 min from 11:00:00Z). `account_9335` actually belonged to `case_13` (`noor-khalil@proton.me`), but without cross-case reservation, `case_20` grabbed it first.
- **Participant Evidence:** `dataset/system_activity.csv` and `evidence_94`.

---

### Case 23: `case_23` (`thandiwe.m6866@zoho.com`)
- **Status:** Predicted: `INCOMPLETE` | Expected: `INCOMPLETE` (Status Correct)
- **Reported:** `NOT_STARTED` @ `2026-09-05T12:00:00Z` | **Audit Cutoff:** `2026-09-15T12:00:00Z`
- **Expected Steps (8):**
  - Findings: `export_7364`, `search_898` (`evidence_92`)
  - Remediation: `DELETE_RECORD` (export), `DELETE_RECORD` (search)
  - Verification: `account_410`, `export_7364`, `search_898`, `audit_record_4128`
- **Predicted Steps (8):**
  - Verification step 5: `account_9155` (instead of `account_410`).
- **Exact Mismatch:** `resource_id` on step 5: `account_9155` vs `account_410`.
- **Source Code Mechanism:** In `system_activity.csv`, both `account_410` (11:10:55Z) and `account_9155` (11:12:36Z) were FAILED worker tasks. `account_9155` was 101 seconds closer to `12:00:00Z`. However, `account_410` is grounded in operational evidence (`cloud_runtime_export_af_south_20260930.log`).
- **Participant Evidence:** `dataset/system_activity.csv` and `evidence_92`.

---

### Case 25: `case_25` (`s.yoon04@gmail.com`)
- **Status:** Predicted: `COMPLETE` | Expected: `COMPLETE` (Status Correct)
- **Reported:** `NOT_STARTED` @ `2026-09-02T12:00:00Z` | **Audit Cutoff:** `2026-09-15T12:00:00Z`
- **Expected Steps (3):**
  1. `VERIFICATION` | `account_service` | `account_3136` | `VERIFY_RECORD_ABSENT` | `ABSENT` | `evidence_92`
  2. `VERIFICATION` | `security_service` | `audit_record_451` | `VERIFY_RECORD_PRESENT` | `PRESENT` | `evidence_92`
  3. `VERIFICATION` | `analytics_platform` | `analytics_1895` | `VERIFY_RECORD_ANONYMIZED` | `ANONYMIZED` | `evidence_92`
- **Predicted Steps (2):**
  1. `VERIFICATION` | `account_service` | `account_5684` | `VERIFY_RECORD_ABSENT` | `ABSENT` | `evidence_92`
  2. `VERIFICATION` | `security_service` | `audit_record_451` | `VERIFY_RECORD_PRESENT` | `PRESENT` | `evidence_92`
- **Exact Mismatches:**
  1. `resource_id` on step 1: `account_5684` vs `account_3136`.
  2. Missing step 3: `analytics_1895`.
- **Source Code Mechanism:** In `evidence_92`, `account_3136` returned 404 with `profile: null`. `analytics_1895` had all PII fields set to null. Because direct identifiers were absent, they were not matched by identity and fell back to nearby worker activity sorting.
- **Participant Evidence:** `evidence_92` (`service_resource_export_20260915_114455.json`).

---

### Case 26: `case_26` (`almeida.mariana@gmail.com`)
- **Status:** Predicted: `COMPLETE` | Expected: `COMPLETE` (Status Correct)
- **Reported:** `NOT_STARTED` @ `2026-09-02T12:00:00Z` | **Audit Cutoff:** `2026-09-15T12:00:00Z`
- **Expected Steps (6):**
  - Verification: `account_5684`, `audit_record_5416`, `support_4715`, `analytics_4566`, `data_flow_6244`, `backup_3120` (all `evidence_92`)
- **Predicted Steps (5):**
  - Verification: `account_5684`, `audit_record_5416`, `support_4715`, `data_flow_6244`, `backup_3120` (missing `analytics_4566`).
- **Exact Mismatch:** Missing step 4: `analytics_4566`.
- **Source Code Mechanism:** Anonymized analytics profile in `evidence_92` lacked explicit user_id/email field values.
- **Participant Evidence:** `evidence_92`.

---

### Case 27: `case_27` (`ananya-nair@gmail.com`)
- **Status:** Predicted: `COMPLETE` | Expected: `COMPLETE` (Status Correct)
- **Reported:** `COMPLETE` @ `2026-08-30T12:00:00Z` | **Audit Cutoff:** `2026-09-15T12:00:00Z`
- **Expected Steps (6):**
  - Verification: `account_3866`, `audit_record_3830`, `support_4707`, `analytics_4574`, `data_flow_2295`, `backup_5970` (`evidence_92`)
- **Predicted Steps (6):**
  - Verification step 4: `analytics_6077` (instead of `analytics_4574`).
- **Exact Mismatch:** `resource_id` on step 4: `analytics_6077` vs `analytics_4574`.
- **Source Code Mechanism:** Both `analytics_4574` (11:31:09Z) and `analytics_6077` (11:31:53Z) occurred in the 2026-08-30 batch. `analytics_6077` was 44 seconds closer to `12:00:00Z`.
- **Participant Evidence:** `evidence_92` and `system_activity.csv`.

---

### Case 28: `case_28` (`smartinez6461@gmail.com`)
- **Status:** Predicted: `COMPLETE` | Expected: `COMPLETE` (Status Correct)
- **Reported:** `NOT_STARTED` @ `2026-08-30T12:00:00Z` | **Audit Cutoff:** `2026-09-15T12:00:00Z`
- **Expected Steps (6):**
  - Verification: `account_5482`, `audit_record_9265`, `support_2351`, `analytics_6077`, `data_flow_2337`, `backup_838` (`evidence_92`)
- **Predicted Steps (5):**
  - Verification: `account_7012` (instead of `account_5482`), missing `analytics_6077`.
- **Exact Mismatches:**
  1. `resource_id` on step 1: `account_7012` vs `account_5482`.
  2. Missing step 4: `analytics_6077`.
- **Source Code Mechanism:** In `system_activity.csv`, `account_7012` (11:06:57Z) was closer to `12:00:00Z` than `account_5482` (10:46:13Z).
- **Participant Evidence:** `evidence_92` and `system_activity.csv`.

---

### Case 31: `case_31` (`a.eze08@gmail.com`)
- **Status:** Predicted: `COMPLETE` | Expected: `COMPLETE` (Status Correct)
- **Reported:** `COMPLETE` @ `2026-09-06T12:00:00Z` | **Audit Cutoff:** `2026-09-15T12:00:00Z`
- **Expected Steps (3):**
  1. `VERIFICATION` | `account_service` | `account_4857` | `VERIFY_RECORD_ABSENT` | `ABSENT` | `evidence_51`
  2. `VERIFICATION` | `security_service` | `audit_record_6909` | `VERIFY_RECORD_PRESENT` | `PRESENT` | `evidence_51`
  3. `VERIFICATION` | `identity_service` | `tombstone_440` | `VERIFY_RECORD_REDACTED` | `REDACTED` | `evidence_51`
- **Predicted Steps (3):**
  1. `VERIFICATION` | `account_service` | `account_3677` | `VERIFY_RECORD_ABSENT` | `ABSENT` | `evidence_51`
  2. `VERIFICATION` | `security_service` | `audit_record_6909` | `VERIFY_RECORD_PRESENT` | `PRESENT` | `evidence_51`
  3. `VERIFICATION` | `identity_service` | `tombstone_440` | `VERIFY_RECORD_REDACTED` | `REDACTED` | `evidence_51`
- **Exact Mismatch:** `resource_id` on step 1: `account_3677` vs `account_4857`.
- **Source Code Mechanism:** Both `account_4857` (10:45:58Z) and `account_3677` (11:11:02Z) were SUCCESS worker deletions on 2026-09-06. `account_3677` was closer to 12:00:00Z, but actually belonged to `case_14` (`y.tanaka32@gmail.com`).
- **Participant Evidence:** `evidence_51` and `system_activity.csv`.

---

## 3. Defect Taxonomy and Summary Table

| Case ID | Expected Steps | Predicted Steps | Missing Steps | Extra Steps | Differing Fields | Primary System | Root Cause Category |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| `case_03` | 3 | 3 | 0 | 0 | `resource_id` (step 3) | `analytics_platform` | Concurrent burst candidate selection |
| `case_18` | 14 | 13 | 1 | 0 | `resource_id` (step 9), missing step 11 | `account_service`, `security_service` | Task logged after `reported_at`; unindexed audit record |
| `case_20` | 8 | 7 | 1 | 0 | `resource_id` (step 5), missing step 7 | `account_service`, `security_service` | Cross-request worker task collision |
| `case_23` | 8 | 8 | 0 | 0 | `resource_id` (step 5) | `account_service` | Unassigned burst task proximity |
| `case_25` | 3 | 2 | 1 | 0 | `resource_id` (step 1), missing step 3 | `account_service`, `analytics_platform` | Anonymized export profile without direct PII |
| `case_26` | 6 | 5 | 1 | 0 | Missing step 4 | `analytics_platform` | Anonymized export profile without direct PII |
| `case_27` | 6 | 6 | 0 | 0 | `resource_id` (step 4) | `analytics_platform` | Concurrent burst candidate selection |
| `case_28` | 6 | 5 | 1 | 0 | `resource_id` (step 1), missing step 4 | `account_service`, `analytics_platform` | Concurrent burst candidate selection |
| `case_31` | 3 | 3 | 0 | 0 | `resource_id` (step 1) | `account_service` | Cross-request worker task collision |

**Total Impact Summary:**
- 9 mismatched cases out of 32 (23 exact matches = 71.9%).
- 5 missing steps out of 193 total expected steps (Recall = 97.4%).
- 0 extra steps out of 188 total predicted steps (Precision = 100.0%).
- 8 resource ID mismatches across aligned steps.
- 0 operation or state mismatches.
- 0 false COMPLETE decisions (100% compliant safety invariant).
