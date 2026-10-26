import csv
import json
import os
import sys

def validate():
    input_path = 'dataset/deletion_requests.csv'
    output_path = 'output.csv'
    ev_path = 'dataset/evidence_files.csv'

    print(f"Running automated quality gate validation on {output_path}...")
    errors = []

    # 1. Existence
    if not os.path.exists(output_path):
        print(f"FATAL: {output_path} does not exist!")
        sys.exit(1)

    # 2. Schema and columns
    with open(output_path, 'r', encoding='utf-8') as f:
        reader = list(csv.DictReader(f))
        f.seek(0)
        first_line = f.readline().strip()

    expected_header = "case_id,deletion_status,steps_json"
    if first_line != expected_header:
        errors.append(f"Header mismatch: expected '{expected_header}', got '{first_line}'")

    # 3. Row count
    with open(input_path, 'r', encoding='utf-8') as f:
        in_reader = list(csv.DictReader(f))

    if len(reader) != len(in_reader):
        errors.append(f"Row count mismatch: input has {len(in_reader)}, output has {len(reader)}")
    if len(reader) != 518:
        errors.append(f"Row count must be exactly 518 data rows, got {len(reader)}")

    # 4. Case IDs match and duplicates
    in_case_ids = [r['case_id'] for r in in_reader]
    out_case_ids = [r['case_id'] for r in reader]

    if len(set(out_case_ids)) != len(out_case_ids):
        errors.append("Duplicate case_ids found in output.csv!")
    if set(out_case_ids) != set(in_case_ids):
        errors.append("Case IDs in output do not match input case IDs!")

    # 5. Sorting order
    def case_sort_key(cid):
        parts = cid.split('_')
        if len(parts) == 2 and parts[1].isdigit():
            return (parts[0], int(parts[1]))
        return (cid, 0)

    expected_sorted_ids = sorted(in_case_ids, key=case_sort_key)
    if out_case_ids != expected_sorted_ids:
        errors.append("Rows are not sorted by case_id ascending!")

    # 6. Load valid evidence IDs
    with open(ev_path, 'r', encoding='utf-8') as f:
        valid_ev_ids = set(r['file_id'] for r in csv.DictReader(f))

    # Allowed sets
    ALLOWED_STATUSES = {'COMPLETE', 'INCOMPLETE', 'NOT_APPLICABLE'}
    ALLOWED_PHASES = {'FINDING', 'REMEDIATION', 'VERIFICATION'}
    ALLOWED_KEYS = {'step_no', 'phase', 'system_id', 'resource_id', 'operation', 'state', 'evidence_id'}

    OP_STATE_MAP = {
        'REPORT_REMAINING_RECORD': 'PRESENT',
        'REPORT_EXPOSED_PII': 'PRESENT',
        'REPORT_ACTIVE_DATA_FLOW': 'ACTIVE',
        'REPORT_RESTORE_RISK': 'ACTIVE',
        'DISABLE_DATA_FLOW': 'DISABLED',
        'BLOCK_RESTORE': 'BLOCKED',
        'DELETE_RECORD': 'ABSENT',
        'REDACT_RECORD': 'REDACTED',
        'ANONYMIZE_RECORD': 'ANONYMIZED',
        'VERIFY_RECORD_ABSENT': 'ABSENT',
        'VERIFY_RECORD_PRESENT': 'PRESENT',
        'VERIFY_RECORD_REDACTED': 'REDACTED',
        'VERIFY_RECORD_ANONYMIZED': 'ANONYMIZED',
        'VERIFY_DATA_FLOW_DISABLED': 'DISABLED',
        'VERIFY_RESTORE_BLOCKED': 'BLOCKED'
    }

    PHASE_RANK = {'FINDING': 1, 'REMEDIATION': 2, 'VERIFICATION': 3}
    OP_RANK = {
        'REPORT_REMAINING_RECORD': 1, 'REPORT_EXPOSED_PII': 2, 'REPORT_ACTIVE_DATA_FLOW': 3, 'REPORT_RESTORE_RISK': 4,
        'DISABLE_DATA_FLOW': 1, 'BLOCK_RESTORE': 2, 'DELETE_RECORD': 3, 'REDACT_RECORD': 4, 'ANONYMIZE_RECORD': 5,
        'VERIFY_RECORD_ABSENT': 1, 'VERIFY_RECORD_PRESENT': 2, 'VERIFY_RECORD_REDACTED': 3, 'VERIFY_RECORD_ANONYMIZED': 4, 'VERIFY_DATA_FLOW_DISABLED': 5, 'VERIFY_RESTORE_BLOCKED': 6
    }

    # 7. Deep Step-level checks
    for row in reader:
        cid = row['case_id']
        st = row['deletion_status']
        s_json = row['steps_json']

        if st not in ALLOWED_STATUSES:
            errors.append(f"{cid}: invalid status '{st}'")

        try:
            steps = json.loads(s_json)
        except Exception as e:
            errors.append(f"{cid}: invalid JSON in steps_json: {e}")
            continue

        if not isinstance(steps, list):
            errors.append(f"{cid}: steps_json is not an array")
            continue

        if st == 'NOT_APPLICABLE':
            if steps != []:
                errors.append(f"{cid}: NOT_APPLICABLE must have empty array [], got {steps}")
            continue

        # COMPLETE cases have verification steps only
        if st == 'COMPLETE':
            for s in steps:
                if s.get('phase') != 'VERIFICATION':
                    errors.append(f"{cid} (COMPLETE): contains non-verification step {s}")
                if not s.get('evidence_id'):
                    errors.append(f"{cid} (COMPLETE): verification step missing evidence_id: {s}")

        # Check consecutive numbering & ordering
        prev_key = (-1, -1, "", "")
        for idx, s in enumerate(steps):
            if set(s.keys()) != ALLOWED_KEYS:
                errors.append(f"{cid} step {idx+1}: keys mismatch. Expected {ALLOWED_KEYS}, got {set(s.keys())}")

            if s.get('step_no') != idx + 1:
                errors.append(f"{cid} step {idx+1}: non-consecutive step_no {s.get('step_no')}")

            phase = s.get('phase')
            op = s.get('operation')
            state = s.get('state')
            ev_id = s.get('evidence_id')

            if phase not in ALLOWED_PHASES:
                errors.append(f"{cid} step {idx+1}: invalid phase {phase}")
            if op not in OP_STATE_MAP:
                errors.append(f"{cid} step {idx+1}: invalid operation {op}")
            elif OP_STATE_MAP[op] != state:
                errors.append(f"{cid} step {idx+1}: operation {op} expects state {OP_STATE_MAP[op]}, got {state}")

            # Evidence ID checks
            if phase == 'REMEDIATION' and ev_id != '':
                errors.append(f"{cid} step {idx+1} (REMEDIATION): evidence_id must be empty string, got '{ev_id}'")
            elif st == 'INCOMPLETE' and phase == 'VERIFICATION' and ev_id != '':
                errors.append(f"{cid} step {idx+1} (INCOMPLETE VERIFICATION): evidence_id must be empty string, got '{ev_id}'")
            elif ev_id != '' and ev_id not in valid_ev_ids:
                errors.append(f"{cid} step {idx+1}: evidence_id '{ev_id}' not found in evidence_files.csv")

            # Check sort ordering
            cur_key = (PHASE_RANK.get(phase, 99), OP_RANK.get(op, 99), s.get('system_id', ''), s.get('resource_id', ''))
            if cur_key < prev_key:
                errors.append(f"{cid} step {idx+1}: out-of-order step. Prev key: {prev_key}, cur key: {cur_key}")
            prev_key = cur_key

    print(f"\nQuality Gate Verification Results:")
    if errors:
        print(f"FAILED with {len(errors)} errors:")
        for e in errors[:10]:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("ALL 18 QUALITY GATE CHECKS PASSED PERFECTLY!")
        print(f"  - 518 data rows validated")
        print(f"  - Schema, headers, and column order verified")
        print(f"  - Consecutive step numbering and deterministic sorting verified")
        print(f"  - Allowed operations, states, and phases verified")
        print(f"  - Evidence ID grounding verified")
        print(f"  - COMPLETE vs INCOMPLETE vs NOT_APPLICABLE schemas verified")

if __name__ == '__main__':
    validate()
