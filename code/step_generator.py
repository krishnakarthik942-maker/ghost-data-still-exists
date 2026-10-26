from typing import List, Dict

PHASE_ORDER = {'FINDING': 1, 'REMEDIATION': 2, 'VERIFICATION': 3}

FINDING_OPS = {
    'REPORT_REMAINING_RECORD': 1,
    'REPORT_EXPOSED_PII': 2,
    'REPORT_ACTIVE_DATA_FLOW': 3,
    'REPORT_RESTORE_RISK': 4
}

REMEDIATION_OPS = {
    'DISABLE_DATA_FLOW': 1,
    'BLOCK_RESTORE': 2,
    'DELETE_RECORD': 3,
    'REDACT_RECORD': 4,
    'ANONYMIZE_RECORD': 5
}

VERIFICATION_OPS = {
    'VERIFY_RECORD_ABSENT': 1,
    'VERIFY_RECORD_PRESENT': 2,
    'VERIFY_RECORD_REDACTED': 3,
    'VERIFY_RECORD_ANONYMIZED': 4,
    'VERIFY_DATA_FLOW_DISABLED': 5,
    'VERIFY_RESTORE_BLOCKED': 6
}

def op_rank(phase: str, op: str) -> int:
    if phase == 'FINDING':
        return FINDING_OPS.get(op, 99)
    if phase == 'REMEDIATION':
        return REMEDIATION_OPS.get(op, 99)
    if phase == 'VERIFICATION':
        return VERIFICATION_OPS.get(op, 99)
    return 99

def sort_and_number_steps(steps: List[dict]) -> List[dict]:
    """
    Sorts steps according to problem statement rules:
    1. Phase: FINDING -> REMEDIATION -> VERIFICATION
    2. Operation order from allowed-operations table
    3. system_id ascending
    4. resource_id ascending
    Assigns consecutive 1-based step numbers.
    """
    def key_func(s):
        return (
            PHASE_ORDER[s['phase']],
            op_rank(s['phase'], s['operation']),
            s['system_id'],
            s['resource_id']
        )
    
    sorted_steps = sorted(steps, key=key_func)
    for idx, s in enumerate(sorted_steps):
        s['step_no'] = idx + 1
    return sorted_steps
