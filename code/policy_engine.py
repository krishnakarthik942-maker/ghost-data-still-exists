import csv
import os
from typing import Dict, List, Tuple

class PolicyEngine:
    def __init__(self, dataset_dir: str = 'dataset'):
        self.dataset_dir = dataset_dir
        self.rules: Dict[str, dict] = {}
        self._load()

    def _load(self):
        rules_path = os.path.join(self.dataset_dir, 'deletion_rules.csv')
        if os.path.exists(rules_path):
            with open(rules_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.rules[row['data_category']] = row

    def is_compliant(self, system_id: str, state: str, category: str = '') -> bool:
        """
        Determines whether a resource's state at audit_at complies with deletion rules.
        """
        if system_id == 'security_service':
            # SECURITY_AUDIT_LOG -> RETAIN (mandatory compliance retention, must remain PRESENT)
            return state == 'PRESENT'
        if system_id in ('account_service', 'search_service', 'export_service'):
            # Must be deleted entirely -> ABSENT
            return state == 'ABSENT'
        if system_id == 'integration_service':
            # Data flow connector must be stopped / disabled
            return state == 'DISABLED'
        if system_id == 'backup_service':
            # Restore access must be blocked
            return state == 'BLOCKED'
        if system_id == 'analytics_platform':
            # Must be stripped of identifiable attributes -> ANONYMIZED
            return state in ('ANONYMIZED', 'ABSENT')
        if system_id == 'identity_service':
            # Tombstone must be redacted of direct identifiers
            return state in ('REDACTED', 'ABSENT')
        if system_id == 'support_platform':
            # Attachments deleted; messages redacted
            if category == 'SUPPORT_ATTACHMENT' or 'attachment' in category.lower():
                return state == 'ABSENT'
            return state in ('REDACTED', 'ABSENT')
        return state in ('ABSENT', 'REDACTED', 'ANONYMIZED', 'DISABLED', 'BLOCKED')
