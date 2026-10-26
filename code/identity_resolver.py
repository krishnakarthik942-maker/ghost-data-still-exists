import csv
import os
from typing import Dict, Set, Optional

class IdentityResolver:
    def __init__(self, dataset_dir: str = 'dataset'):
        self.dataset_dir = dataset_dir
        self.identities: Dict[str, dict] = {}
        self.email_to_uid: Dict[str, str] = {}
        self.uid_to_idents: Dict[str, Set[str]] = {}
        self._load()

    def _load(self):
        # 1. Load user_identities.csv
        ident_path = os.path.join(self.dataset_dir, 'user_identities.csv')
        if os.path.exists(ident_path):
            with open(ident_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    uid = row['user_id']
                    self.identities[uid] = row
                    idents = {uid}
                    for field in ('email', 'phone', 'name', 'email_hash'):
                        val = row.get(field)
                        if val:
                            norm_val = val.strip().lower()
                            idents.add(norm_val)
                            if field == 'email':
                                self.email_to_uid[norm_val] = uid
                    self.uid_to_idents[uid] = idents

        # 2. Trace historical identity changes from user_audit_log.csv
        audit_path = os.path.join(self.dataset_dir, 'user_audit_log.csv')
        if os.path.exists(audit_path):
            with open(audit_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    uid = row['user_id']
                    if uid not in self.uid_to_idents:
                        self.uid_to_idents[uid] = {uid}
                    
                    field_name = row['field_name']
                    for val_key in ('old_value', 'new_value'):
                        val = row.get(val_key)
                        if val:
                            norm_val = val.strip().lower()
                            self.uid_to_idents[uid].add(norm_val)
                            if field_name == 'email':
                                self.email_to_uid[norm_val] = uid

    def resolve_email(self, email: str) -> Optional[str]:
        norm_email = email.strip().lower()
        return self.email_to_uid.get(norm_email)

    def get_user_identifiers(self, uid_or_email: str) -> Set[str]:
        uid = uid_or_email if uid_or_email.startswith('user_') else self.resolve_email(uid_or_email)
        if uid and uid in self.uid_to_idents:
            return set(self.uid_to_idents[uid])
        return {uid_or_email.strip().lower()}
