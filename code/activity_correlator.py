import csv
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional

def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace('Z', '+00:00'))

class ActivityCorrelator:
    def __init__(self, dataset_dir: str = 'dataset'):
        self.dataset_dir = dataset_dir
        self.activities: List[dict] = []
        self.del_worker_acts: List[dict] = []
        self.explicit_links: Dict[str, Set[str]] = {} # uid/email -> set of resource_ids
        self._load()

    def _load(self):
        act_path = os.path.join(self.dataset_dir, 'system_activity.csv')
        if not os.path.exists(act_path):
            return

        with open(act_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                row['dt'] = parse_iso(row['event_time'])
                self.activities.append(row)
                if row['source_system'] == 'deletion_worker':
                    self.del_worker_acts.append(row)

                # Track explicit link events
                if row['event_type'] == 'LINK_RESOURCE_IDENTITY':
                    res = row['resource_id']
                    det = row['details']
                    m_uid = re.search(r'user_\d+', det)
                    if m_uid:
                        self.explicit_links.setdefault(m_uid.group(0), set()).add(res)
                    m_email = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', det)
                    if m_email:
                        self.explicit_links.setdefault(m_email.group(0).lower(), set()).add(res)

        self.del_worker_acts.sort(key=lambda x: x['dt'])

    def get_explicit_resources(self, uid: Optional[str], emails: Set[str]) -> Set[str]:
        res = set()
        if uid and uid in self.explicit_links:
            res.update(self.explicit_links[uid])
        for em in emails:
            norm_em = em.lower()
            if norm_em in self.explicit_links:
                res.update(self.explicit_links[norm_em])
        return res

    def get_worker_resources_near_reported(self, reported_at_iso: str, window_minutes: int = 90) -> List[dict]:
        rep_dt = parse_iso(reported_at_iso)
        window = timedelta(minutes=window_minutes)
        nearby = [a for a in self.del_worker_acts if abs((a['dt'] - rep_dt).total_seconds()) <= window.total_seconds()]
        return nearby
