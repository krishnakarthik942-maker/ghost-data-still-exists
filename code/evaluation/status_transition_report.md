# Status Transition Audit Report: 128/129 Baseline vs 165 Current COMPLETE Cases

## 1. Executive Summary

- Total requests evaluated: 518
- Baseline COMPLETE count: 128 total
- Current COMPLETE count: 165 total
- Total status transitions: 41
  - INCOMPLETE -> COMPLETE: 39
  - COMPLETE -> INCOMPLETE: 2
- Net increase in COMPLETE predictions: +37 cases (from 128 to 165)

## 2. Root Cause Analysis of Transitions

### A. Cross-User Worker Queue Profile Pollution in Baseline (39 cases)
In the Turn 2 baseline implementation (`BaselineTurn2Agent`), when auditing a user with missing `analytics_platform` evidence, the agent performed a naive proximity search on `system_activity.csv` (`correlator.get_worker_resources_near_reported`) without checking ownership or identity references. This grabbed adjacent `analytics_platform` profiles (e.g. `analytics_2572`) belonging to other users undergoing batch processing.
Because these foreign analytics records existed in snapshot evidence (`customer_analytics_reports`) with `state: PRESENT`, the baseline policy engine marked them non-compliant, artificially forcing otherwise fully completed deletions into `INCOMPLETE`.

In the current implementation (`AuditAgent`):
1. `is_resource_owned_by_other()` strictly inspects catalog and identity mappings up to `audit_at` to prevent attributing another person's resources.
2. Candidate worker activities are constrained to compliant state transitions and verified against authoritative evidence.
3. For users whose personal data across primary, replica, search, export, support, and integration systems was verified deleted, redacted, or retained under policy (Rule 12 security audit), the case is correctly decided as `COMPLETE`.

### B. Discovered Incomplete Cases in Current (2 cases: COMPLETE -> INCOMPLETE)
Current detected unpurged surviving records or replication drift that Baseline missed:

- **`case_481`** (`mei.t7930@zoho.com`): Reported as `COMPLETE`. Evidence inspection at `audit_at` revealed surviving resources requiring remediation:
  - FINDING | `integration_service` | `data_flow_173` | `REPORT_ACTIVE_DATA_FLOW` | `ACTIVE` (evidence: `evidence_45`)
  - REMEDIATION | `integration_service` | `data_flow_173` | `DISABLE_DATA_FLOW` | `DISABLED` (evidence: ``)
  - VERIFICATION | `account_service` | `account_9449` | `VERIFY_RECORD_ABSENT` | `ABSENT` (evidence: ``)
  - VERIFICATION | `security_service` | `audit_record_9025` | `VERIFY_RECORD_PRESENT` | `PRESENT` (evidence: ``)
  - VERIFICATION | `integration_service` | `data_flow_173` | `VERIFY_DATA_FLOW_DISABLED` | `DISABLED` (evidence: ``)

- **`case_482`** (`doyun.park@gmail.com`): Reported as `PARTIALLY_COMPLETE`. Evidence inspection at `audit_at` revealed surviving resources requiring remediation:
  - FINDING | `integration_service` | `data_flow_8519` | `REPORT_ACTIVE_DATA_FLOW` | `ACTIVE` (evidence: `evidence_45`)
  - REMEDIATION | `integration_service` | `data_flow_8519` | `DISABLE_DATA_FLOW` | `DISABLED` (evidence: ``)
  - VERIFICATION | `account_service` | `account_9394` | `VERIFY_RECORD_ABSENT` | `ABSENT` (evidence: ``)
  - VERIFICATION | `security_service` | `audit_record_2180` | `VERIFY_RECORD_PRESENT` | `PRESENT` (evidence: ``)
  - VERIFICATION | `integration_service` | `data_flow_8519` | `VERIFY_DATA_FLOW_DISABLED` | `DISABLED` (evidence: ``)

## 3. Case-by-Case Transition Ledger

| Case ID | Email | Reported Status | Baseline Status | Current Status | Current Verified Steps | Reason & Evidence Grounding |
|---|---|---|---|---|---|---|
| `case_58` | `fournier.manon@icloud.com` | `NOT_STARTED` | `INCOMPLETE` | `COMPLETE` | 2 steps: `account_service`, `security_service` | Clean worker isolation; verified absence in snapshot |
| `case_59` | `lars-nielsen@proton.me` | `COMPLETE` | `INCOMPLETE` | `COMPLETE` | 3 steps: `account_service`, `security_service`, `analytics_platform` | Clean worker isolation; verified absence in snapshot |
| `case_60` | `anowak4031@fastmail.com` | `COMPLETE` | `INCOMPLETE` | `COMPLETE` | 3 steps: `account_service`, `security_service`, `analytics_platform` | Clean worker isolation; verified absence in snapshot |
| `case_61` | `priya.raman@gmail.com` | `PARTIALLY_COMPLETE` | `INCOMPLETE` | `COMPLETE` | 1 steps: `account_service` | Clean worker isolation; verified absence in snapshot |
| `case_103` | `mandla.m4548@outlook.com` | `COMPLETE` | `INCOMPLETE` | `COMPLETE` | 3 steps: `account_service`, `security_service`, `analytics_platform` | Clean worker isolation; verified absence in snapshot |
| `case_107` | `priya-patel@proton.me` | `COMPLETE` | `INCOMPLETE` | `COMPLETE` | 3 steps: `account_service`, `security_service`, `analytics_platform` | Clean worker isolation; verified absence in snapshot |
| `case_108` | `vfernandez4143@fastmail.com` | `PARTIALLY_COMPLETE` | `INCOMPLETE` | `COMPLETE` | 2 steps: `account_service`, `security_service` | Clean worker isolation; verified absence in snapshot |
| `case_111` | `O.ANDERSSON00@GMAIL.COM` | `PARTIALLY_COMPLETE` | `INCOMPLETE` | `COMPLETE` | 2 steps: `account_service`, `security_service` | Clean worker isolation; verified absence in snapshot |
| `case_134` | `mateo.alvarez@gmail.com` | `NOT_STARTED` | `INCOMPLETE` | `COMPLETE` | 1 steps: `account_service` | Clean worker isolation; verified absence in snapshot |
| `case_135` | `o.morgan56@gmail.com` | `COMPLETE` | `INCOMPLETE` | `COMPLETE` | 2 steps: `account_service`, `analytics_platform` | Clean worker isolation; verified absence in snapshot |
| `case_136` | `rousseau.hugo80@gmail.com` | `COMPLETE` | `INCOMPLETE` | `COMPLETE` | 2 steps: `account_service`, `analytics_platform` | Clean worker isolation; verified absence in snapshot |
| `case_157` | `soojin.l2174@zoho.com` | `NOT_STARTED` | `INCOMPLETE` | `COMPLETE` | 2 steps: `account_service`, `security_service` | Clean worker isolation; verified absence in snapshot |
| `case_178` | `rahman.laila@icloud.com` | `NOT_STARTED` | `INCOMPLETE` | `COMPLETE` | 1 steps: `account_service` | Clean worker isolation; verified absence in snapshot |
| `case_195` | `a.sato96@gmail.com` | `COMPLETE` | `INCOMPLETE` | `COMPLETE` | 3 steps: `account_service`, `security_service`, `analytics_platform` | Clean worker isolation; verified absence in snapshot |
| `case_196` | `kim.hyunwoo@gmail.com` | `COMPLETE` | `INCOMPLETE` | `COMPLETE` | 3 steps: `account_service`, `security_service`, `analytics_platform` | Clean worker isolation; verified absence in snapshot |
| `case_206` | `ama.agyeman84@gmail.com` | `COMPLETE` | `INCOMPLETE` | `COMPLETE` | 3 steps: `account_service`, `security_service`, `analytics_platform` | Clean worker isolation; verified absence in snapshot |
| `case_253` | `mathis.l2398@zoho.com` | `PARTIALLY_COMPLETE` | `INCOMPLETE` | `COMPLETE` | 2 steps: `account_service`, `security_service` | Clean worker isolation; verified absence in snapshot |
| `case_257` | `yetunde-nwosu@gmail.com` | `COMPLETE` | `INCOMPLETE` | `COMPLETE` | 3 steps: `account_service`, `security_service`, `analytics_platform` | Clean worker isolation; verified absence in snapshot |
| `case_260` | `daichi.takahashi@outlook.com` | `NOT_STARTED` | `INCOMPLETE` | `COMPLETE` | 2 steps: `account_service`, `security_service` | Clean worker isolation; verified absence in snapshot |
| `case_274` | `han.minjun86@icloud.com` | `COMPLETE` | `INCOMPLETE` | `COMPLETE` | 3 steps: `account_service`, `security_service`, `analytics_platform` | Clean worker isolation; verified absence in snapshot |
| `case_309` | `t.oladipo62@yahoo.com` | `PARTIALLY_COMPLETE` | `INCOMPLETE` | `COMPLETE` | 2 steps: `account_service`, `security_service` | Clean worker isolation; verified absence in snapshot |
| `case_314` | `beatriz.lima@gmail.com` | `COMPLETE` | `INCOMPLETE` | `COMPLETE` | 3 steps: `account_service`, `security_service`, `analytics_platform` | Clean worker isolation; verified absence in snapshot |
| `case_354` | `nmenon2217@gmail.com` | `COMPLETE` | `INCOMPLETE` | `COMPLETE` | 3 steps: `account_service`, `security_service`, `analytics_platform` | Clean worker isolation; verified absence in snapshot |
| `case_362` | `efua.asante@gmail.com` | `PARTIALLY_COMPLETE` | `INCOMPLETE` | `COMPLETE` | 2 steps: `account_service`, `security_service` | Clean worker isolation; verified absence in snapshot |
| `case_393` | `a.menon58@yahoo.com` | `PARTIALLY_COMPLETE` | `INCOMPLETE` | `COMPLETE` | 1 steps: `account_service` | Clean worker isolation; verified absence in snapshot |
| `case_403` | `haruka.w248@outlook.com` | `COMPLETE` | `INCOMPLETE` | `COMPLETE` | 3 steps: `account_service`, `security_service`, `analytics_platform` | Clean worker isolation; verified absence in snapshot |
| `case_408` | `abennett9843@fastmail.com` | `COMPLETE` | `INCOMPLETE` | `COMPLETE` | 3 steps: `account_service`, `security_service`, `analytics_platform` | Clean worker isolation; verified absence in snapshot |
| `case_409` | `leonie.d7762@zoho.com` | `COMPLETE` | `INCOMPLETE` | `COMPLETE` | 3 steps: `account_service`, `security_service`, `analytics_platform` | Clean worker isolation; verified absence in snapshot |
| `case_411` | `e.petrescu00@gmail.com` | `COMPLETE` | `INCOMPLETE` | `COMPLETE` | 3 steps: `account_service`, `security_service`, `analytics_platform` | Clean worker isolation; verified absence in snapshot |
| `case_412` | `haddad.omar@gmail.com` | `COMPLETE` | `INCOMPLETE` | `COMPLETE` | 3 steps: `account_service`, `security_service`, `analytics_platform` | Clean worker isolation; verified absence in snapshot |
| `case_456` | `hhan9955@fastmail.com` | `PARTIALLY_COMPLETE` | `INCOMPLETE` | `COMPLETE` | 2 steps: `account_service`, `security_service` | Clean worker isolation; verified absence in snapshot |
| `case_457` | `rafael.c7874@zoho.com` | `COMPLETE` | `INCOMPLETE` | `COMPLETE` | 3 steps: `account_service`, `security_service`, `analytics_platform` | Clean worker isolation; verified absence in snapshot |
| `case_458` | `ishaan.kapoor@gmail.com` | `PARTIALLY_COMPLETE` | `INCOMPLETE` | `COMPLETE` | 2 steps: `account_service`, `security_service` | Clean worker isolation; verified absence in snapshot |
| `case_464` | `salma.hamdan@outlook.com` | `COMPLETE` | `INCOMPLETE` | `COMPLETE` | 6 steps: `account_service`, `security_service`, `support_platform` (+3 more) | Clean worker isolation; verified absence in snapshot |
| `case_474` | `claurent2497@gmail.com` | `NOT_STARTED` | `INCOMPLETE` | `COMPLETE` | 3 steps: `account_service`, `security_service`, `support_platform` | Clean worker isolation; verified absence in snapshot |
| `case_478` | `nwosu.ikenna@icloud.com` | `NOT_STARTED` | `INCOMPLETE` | `COMPLETE` | 3 steps: `account_service`, `security_service`, `support_platform` | Clean worker isolation; verified absence in snapshot |
| `case_481` | `mei.t7930@zoho.com` | `COMPLETE` | `COMPLETE` | `INCOMPLETE` | 5 steps: `integration_service`, `integration_service`, `account_service` (+2 more) | Surviving unpurged record detected |
| `case_482` | `doyun.park@gmail.com` | `PARTIALLY_COMPLETE` | `COMPLETE` | `INCOMPLETE` | 5 steps: `integration_service`, `integration_service`, `account_service` (+2 more) | Surviving unpurged record detected |
| `case_494` | `kenta.kato@gmail.com` | `COMPLETE` | `INCOMPLETE` | `COMPLETE` | 2 steps: `account_service`, `analytics_platform` | Clean worker isolation; verified absence in snapshot |
| `case_512` | `hannah.carter@outlook.com` | `COMPLETE` | `INCOMPLETE` | `COMPLETE` | 3 steps: `account_service`, `security_service`, `analytics_platform` | Clean worker isolation; verified absence in snapshot |
| `case_524` | `mateo.castillo@outlook.com` | `NOT_STARTED` | `INCOMPLETE` | `COMPLETE` | 2 steps: `account_service`, `security_service` | Clean worker isolation; verified absence in snapshot |
