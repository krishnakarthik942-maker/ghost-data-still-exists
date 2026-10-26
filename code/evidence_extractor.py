import csv
import json
import os
import re
import sqlite3
import pypdf

class EvidenceExtractor:
    def __init__(self, dataset_dir='dataset'):
        self.dataset_dir = dataset_dir
        self.evidence_files = list(csv.DictReader(open(os.path.join(dataset_dir, 'evidence_files.csv'), encoding='utf-8')))
        self.ev_by_id = {f['file_id']: f for f in self.evidence_files}
        
        # Load precomputed OCR for images
        ocr_path = os.path.join(dataset_dir, 'evidence', 'images_ocr.json')
        self.images_ocr = {}
        if os.path.exists(ocr_path):
            with open(ocr_path, 'r', encoding='utf-8') as f:
                self.images_ocr = json.load(f)

    def extract_all(self):
        records = []
        for ef in self.evidence_files:
            file_id = ef['file_id']
            origin = ef['origin']
            captured_at = ef['captured_at']
            rel_path = ef['file_path']
            abs_path = os.path.join(self.dataset_dir, rel_path)
            if not os.path.exists(abs_path):
                continue
            
            ext = rel_path.split('.')[-1].lower()
            try:
                if ext == 'json':
                    records.extend(self._parse_json(file_id, origin, captured_at, abs_path))
                elif ext == 'sql':
                    records.extend(self._parse_sql(file_id, origin, captured_at, abs_path))
                elif ext == 'txt':
                    records.extend(self._parse_txt(file_id, origin, captured_at, abs_path))
                elif ext == 'log':
                    records.extend(self._parse_log(file_id, origin, captured_at, abs_path))
                elif ext == 'pdf':
                    records.extend(self._parse_pdf(file_id, origin, captured_at, abs_path))
                elif ext == 'png':
                    records.extend(self._parse_png(file_id, origin, captured_at, rel_path))
            except Exception as e:
                pass
        return records

    def _parse_json(self, file_id, origin, captured_at, path):
        records = []
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 1. service_resource_export
        if 'service_exports' in data:
            se = data['service_exports']
            for rec in se.get('account_service', {}).get('profile_lookups', []):
                res_id = rec.get('resource_id')
                status_code = rec.get('status_code')
                profile = rec.get('profile')
                idents = set()
                if profile:
                    for k in ('email', 'customer_reference', 'full_name', 'phone'):
                        if profile.get(k): idents.add(str(profile[k]).strip().lower())
                state = 'ABSENT' if status_code == 404 else 'PRESENT'
                records.append({
                    'evidence_id': file_id, 'captured_at': captured_at,
                    'system_id': 'account_service', 'resource_id': res_id,
                    'state': state, 'category': 'USER_PROFILE', 'identifiers': idents,
                    'raw': rec
                })
            for rec in se.get('search_service', {}).get('index_queries', []):
                res_id = rec.get('resource_id')
                hits = rec.get('hits', {}).get('total', 0)
                idents = set()
                if rec.get('query'): idents.add(rec['query'].strip().lower())
                for doc in rec.get('hits', {}).get('documents', []):
                    for k in ('email', 'customer_reference', 'display_name', 'phone'):
                        if doc.get(k): idents.add(str(doc[k]).strip().lower())
                state = 'PRESENT' if hits > 0 else 'ABSENT'
                records.append({
                    'evidence_id': file_id, 'captured_at': captured_at,
                    'system_id': 'search_service', 'resource_id': res_id,
                    'state': state, 'category': 'SEARCH_INDEX_ENTRY', 'identifiers': idents,
                    'raw': rec
                })
            for rec in se.get('analytics_platform', {}).get('profiles', []):
                res_id = rec.get('resource_id')
                idents = set()
                for k in ('email', 'customer_reference', 'phone', 'email_hash'):
                    if rec.get(k): idents.add(str(rec[k]).strip().lower())
                state = 'PRESENT' if any(rec.get(k) for k in ('email', 'phone', 'customer_reference', 'email_hash')) else 'ANONYMIZED'
                records.append({
                    'evidence_id': file_id, 'captured_at': captured_at,
                    'system_id': 'analytics_platform', 'resource_id': res_id,
                    'state': state, 'category': 'ANALYTICS_PROFILE', 'identifiers': idents,
                    'raw': rec
                })
            for rec in se.get('support_platform', {}).get('tickets', []):
                res_id = rec.get('resource_id')
                idents = set()
                for k in ('customer_reference', 'requester_email', 'requester_name', 'requester_phone'):
                    if rec.get(k): idents.add(str(rec[k]).strip().lower())
                state = 'PRESENT' if any(rec.get(k) for k in ('requester_email', 'requester_name', 'requester_phone')) else 'REDACTED'
                records.append({
                    'evidence_id': file_id, 'captured_at': captured_at,
                    'system_id': 'support_platform', 'resource_id': res_id,
                    'state': state, 'category': 'SUPPORT_MESSAGE', 'identifiers': idents,
                    'raw': rec
                })
            for rec in se.get('export_service', {}).get('exports', []):
                res_id = rec.get('resource_id')
                idents = set()
                for k in ('customer_reference', 'owner_email', 'owner_phone'):
                    if rec.get(k): idents.add(str(rec[k]).strip().lower())
                records.append({
                    'evidence_id': file_id, 'captured_at': captured_at,
                    'system_id': 'export_service', 'resource_id': res_id,
                    'state': 'PRESENT', 'category': 'USER_EXPORT', 'identifiers': idents,
                    'raw': rec
                })
            for rec in se.get('integration_service', {}).get('connectors', []):
                res_id = rec.get('resource_id')
                idents = set()
                for k in ('customer_reference', 'customer_email'):
                    if rec.get(k): idents.add(str(rec[k]).strip().lower())
                enabled = rec.get('enabled', False)
                state = 'ACTIVE' if enabled else 'DISABLED'
                records.append({
                    'evidence_id': file_id, 'captured_at': captured_at,
                    'system_id': 'integration_service', 'resource_id': res_id,
                    'state': state, 'category': 'DATA_FLOW', 'identifiers': idents,
                    'raw': rec
                })
            for rec in se.get('backup_service', {}).get('restore_entries', []):
                res_id = rec.get('resource_id')
                idents = set()
                for k in ('customer_reference', 'customer_email'):
                    if rec.get(k): idents.add(str(rec[k]).strip().lower())
                allowed = rec.get('restore_allowed', False)
                state = 'ACTIVE' if allowed else 'BLOCKED'
                records.append({
                    'evidence_id': file_id, 'captured_at': captured_at,
                    'system_id': 'backup_service', 'resource_id': res_id,
                    'state': state, 'category': 'RESTORE_RISK', 'identifiers': idents,
                    'raw': rec
                })
            for rec in se.get('security_service', {}).get('audit_records', []):
                res_id = rec.get('resource_id')
                idents = set()
                if rec.get('subject_reference'): idents.add(rec['subject_reference'].strip().lower())
                records.append({
                    'evidence_id': file_id, 'captured_at': captured_at,
                    'system_id': 'security_service', 'resource_id': res_id,
                    'state': 'PRESENT', 'category': 'SECURITY_AUDIT_LOG', 'identifiers': idents,
                    'raw': rec
                })

        # 2. records_assurance_snapshot_bundle
        elif 'snapshots' in data:
            for snap in data['snapshots']:
                store = snap.get('data_store')
                coll = snap.get('collection')
                for rec in snap.get('records', []):
                    res_id = rec.get('resource_id')
                    idents = set()
                    for k in ('customer_reference', 'subject_reference', 'user_id', 'email', 'phone', 'full_name', 'name', 'email_hash', 'owner_email', 'requester_email'):
                        if rec.get(k): idents.add(str(rec[k]).strip().lower())
                    
                    if store == 'identity_service' or coll == 'deleted_customer_references':
                        has_pii = any(rec.get(k) for k in ('name', 'email', 'phone', 'email_hash'))
                        state = 'PRESENT' if has_pii else 'REDACTED'
                        records.append({
                            'evidence_id': file_id, 'captured_at': captured_at,
                            'system_id': 'identity_service', 'resource_id': res_id,
                            'state': state, 'category': 'ACCOUNT_TOMBSTONE', 'identifiers': idents,
                            'raw': rec
                        })
                    elif store == 'security_service' or coll == 'security_audit_events':
                        records.append({
                            'evidence_id': file_id, 'captured_at': captured_at,
                            'system_id': 'security_service', 'resource_id': res_id,
                            'state': 'PRESENT', 'category': 'SECURITY_AUDIT_LOG', 'identifiers': idents,
                            'raw': rec
                        })
                    elif store == 'analytics_platform' or coll == 'customer_analytics_reports':
                        has_pii = any(rec.get(k) for k in ('email', 'phone', 'email_hash', 'user_id', 'customer_reference'))
                        state = 'PRESENT' if has_pii else 'ANONYMIZED'
                        records.append({
                            'evidence_id': file_id, 'captured_at': captured_at,
                            'system_id': 'analytics_platform', 'resource_id': res_id,
                            'state': state, 'category': 'ANALYTICS_PROFILE', 'identifiers': idents,
                            'raw': rec
                        })
                    elif store == 'integration_service' or coll == 'connector_configurations':
                        enabled = rec.get('enabled', False) or rec.get('status') == 'ACTIVE'
                        state = 'ACTIVE' if enabled else 'DISABLED'
                        records.append({
                            'evidence_id': file_id, 'captured_at': captured_at,
                            'system_id': 'integration_service', 'resource_id': res_id,
                            'state': state, 'category': 'DATA_FLOW', 'identifiers': idents,
                            'raw': rec
                        })
                    elif store == 'backup_service' or coll == 'backup_catalog':
                        allowed = rec.get('restore_allowed', False)
                        state = 'ACTIVE' if allowed else 'BLOCKED'
                        records.append({
                            'evidence_id': file_id, 'captured_at': captured_at,
                            'system_id': 'backup_service', 'resource_id': res_id,
                            'state': state, 'category': 'RESTORE_RISK', 'identifiers': idents,
                            'raw': rec
                        })
                    elif store == 'support_platform' or coll in ('support_conversations', 'ticket_attachments'):
                        cat = 'SUPPORT_ATTACHMENT' if coll == 'ticket_attachments' else 'SUPPORT_MESSAGE'
                        if cat == 'SUPPORT_ATTACHMENT':
                            records.append({
                                'evidence_id': file_id, 'captured_at': captured_at,
                                'system_id': 'support_platform', 'resource_id': res_id,
                                'state': 'PRESENT', 'category': cat, 'identifiers': idents,
                                'raw': rec
                            })
                        else:
                            has_pii = any(rec.get(k) for k in ('requester_email', 'requester_name', 'requester_phone', 'email', 'phone'))
                            state = 'PRESENT' if has_pii else 'REDACTED'
                            records.append({
                                'evidence_id': file_id, 'captured_at': captured_at,
                                'system_id': 'support_platform', 'resource_id': res_id,
                                'state': state, 'category': cat, 'identifiers': idents,
                                'raw': rec
                            })
                    elif store == 'search_service' or coll == 'customer_search_documents':
                        records.append({
                            'evidence_id': file_id, 'captured_at': captured_at,
                            'system_id': 'search_service', 'resource_id': res_id,
                            'state': 'PRESENT', 'category': 'SEARCH_INDEX_ENTRY', 'identifiers': idents,
                            'raw': rec
                        })
                    elif store == 'export_service' or coll == 'customer_export_jobs':
                        records.append({
                            'evidence_id': file_id, 'captured_at': captured_at,
                            'system_id': 'export_service', 'resource_id': res_id,
                            'state': 'PRESENT', 'category': 'USER_EXPORT', 'identifiers': idents,
                            'raw': rec
                        })
                    elif store == 'account_service' or coll == 'customer_profiles':
                        records.append({
                            'evidence_id': file_id, 'captured_at': captured_at,
                            'system_id': 'account_service', 'resource_id': res_id,
                            'state': 'PRESENT', 'category': 'USER_PROFILE', 'identifiers': idents,
                            'raw': rec
                        })

        # 3. Specific JSON files
        elif 'records' in data and isinstance(data['records'], list):
            coll = data.get('collection', '')
            for rec in data['records']:
                res_id = rec.get('resource_id')
                idents = set()
                for k in ('customer_reference', 'subject_reference', 'user_id', 'email', 'phone', 'full_name', 'name', 'email_hash', 'owner_email', 'requester_email'):
                    if rec.get(k): idents.add(str(rec[k]).strip().lower())
                if 'analytics' in coll or 'analytics' in origin:
                    has_pii = any(rec.get(k) for k in ('email', 'phone', 'email_hash', 'user_id'))
                    state = 'PRESENT' if has_pii else 'ANONYMIZED'
                    records.append({
                        'evidence_id': file_id, 'captured_at': captured_at,
                        'system_id': 'analytics_platform', 'resource_id': res_id,
                        'state': state, 'category': 'ANALYTICS_PROFILE', 'identifiers': idents,
                        'raw': rec
                    })
                elif 'export' in coll or 'export' in origin:
                    records.append({
                        'evidence_id': file_id, 'captured_at': captured_at,
                        'system_id': 'export_service', 'resource_id': res_id,
                        'state': 'PRESENT', 'category': 'USER_EXPORT', 'identifiers': idents,
                        'raw': rec
                    })
                elif 'audit' in coll or 'audit' in origin:
                    records.append({
                        'evidence_id': file_id, 'captured_at': captured_at,
                        'system_id': 'security_service', 'resource_id': res_id,
                        'state': 'PRESENT', 'category': 'SECURITY_AUDIT_LOG', 'identifiers': idents,
                        'raw': rec
                    })
        return records

    def _parse_sql(self, file_id, origin, captured_at, path):
        records = []
        conn = sqlite3.connect(':memory:')
        with open(path, 'r', encoding='utf-8') as f:
            conn.executescript(f.read())
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cur.fetchall()]

        for t in tables:
            cur.execute(f"PRAGMA table_info({t});")
            col_info = cur.fetchall()
            cols = [c[1] for c in col_info]
            col_idx = {name: i for i, name in enumerate(cols)}

            cur.execute(f"SELECT * FROM {t}")
            rows = cur.fetchall()

            for row in rows:
                res_id = row[col_idx['resource_id']] if 'resource_id' in col_idx else None
                if not res_id:
                    continue

                # Collect all potential identifiers
                idents = set()
                for ident_col in ('customer_reference', 'user_id', 'email', 'customer_email', 'owner_email', 'requester_email', 'phone', 'customer_phone', 'owner_phone', 'requester_phone', 'full_name', 'display_name', 'requester_name', 'email_hash'):
                    if ident_col in col_idx and row[col_idx[ident_col]]:
                        idents.add(str(row[col_idx[ident_col]]).strip().lower())

                # Determine system and state
                if t in ('customer_profiles', 'customer_profiles_primary', 'customer_profiles_failover_replica'):
                    records.append({
                        'evidence_id': file_id, 'captured_at': captured_at,
                        'system_id': 'account_service', 'resource_id': res_id,
                        'state': 'PRESENT', 'category': 'USER_PROFILE', 'identifiers': idents
                    })
                elif t in ('customer_search_documents', 'search_documents_primary'):
                    records.append({
                        'evidence_id': file_id, 'captured_at': captured_at,
                        'system_id': 'search_service', 'resource_id': res_id,
                        'state': 'PRESENT', 'category': 'SEARCH_INDEX_ENTRY', 'identifiers': idents
                    })
                elif t in ('customer_analytics_profiles',):
                    has_pii = bool(idents)
                    records.append({
                        'evidence_id': file_id, 'captured_at': captured_at,
                        'system_id': 'analytics_platform', 'resource_id': res_id,
                        'state': 'PRESENT' if has_pii else 'ANONYMIZED', 'category': 'ANALYTICS_PROFILE', 'identifiers': idents
                    })
                elif t in ('support_records',):
                    has_pii = any(row[col_idx[c]] for c in ('requester_email', 'requester_phone', 'requester_name') if c in col_idx)
                    records.append({
                        'evidence_id': file_id, 'captured_at': captured_at,
                        'system_id': 'support_platform', 'resource_id': res_id,
                        'state': 'PRESENT' if has_pii else 'REDACTED', 'category': 'SUPPORT_MESSAGE', 'identifiers': idents
                    })
                elif t in ('customer_exports',):
                    records.append({
                        'evidence_id': file_id, 'captured_at': captured_at,
                        'system_id': 'export_service', 'resource_id': res_id,
                        'state': 'PRESENT', 'category': 'USER_EXPORT', 'identifiers': idents
                    })
                elif t in ('connector_subscriptions',):
                    st_val = str(row[col_idx['status']]) if 'status' in col_idx else ''
                    enabled = st_val in ('ACTIVE', 'ENABLED', 'true', '1')
                    records.append({
                        'evidence_id': file_id, 'captured_at': captured_at,
                        'system_id': 'integration_service', 'resource_id': res_id,
                        'state': 'ACTIVE' if enabled else 'DISABLED', 'category': 'DATA_FLOW', 'identifiers': idents
                    })
                elif t in ('backup_restore_entries',):
                    allowed_val = str(row[col_idx['restore_allowed']]) if 'restore_allowed' in col_idx else ''
                    allowed = allowed_val in ('ACTIVE', 'ALLOWED', 'true', '1', 'True')
                    records.append({
                        'evidence_id': file_id, 'captured_at': captured_at,
                        'system_id': 'backup_service', 'resource_id': res_id,
                        'state': 'ACTIVE' if allowed else 'BLOCKED', 'category': 'RESTORE_RISK', 'identifiers': idents
                    })
                elif t in ('security_audit_records',):
                    records.append({
                        'evidence_id': file_id, 'captured_at': captured_at,
                        'system_id': 'security_service', 'resource_id': res_id,
                        'state': 'PRESENT', 'category': 'SECURITY_AUDIT_LOG', 'identifiers': idents
                    })
                elif 'record_json' in col_idx:
                    rjson = row[col_idx['record_json']]
                    rec = json.loads(rjson)
                    sys_id = row[col_idx['origin_system']] if 'origin_system' in col_idx else None
                    coll = row[col_idx['collection_name']] if 'collection_name' in col_idx else ''
                    def extract_idents_from_dict(d_obj, idents_set):
                        if isinstance(d_obj, dict):
                            for k, v in d_obj.items():
                                if isinstance(v, (dict, list)):
                                    extract_idents_from_dict(v, idents_set)
                                elif v and isinstance(v, str):
                                    norm_v = v.strip().lower()
                                    if k in ('customer_reference', 'subject_reference', 'subject_ref', 'user_id', 'email', 'phone', 'full_name', 'name', 'email_hash', 'display_name') or '@' in norm_v or norm_v.startswith('user_'):
                                        if norm_v not in ('null', 'none', ''):
                                            idents_set.add(norm_v)
                        elif isinstance(d_obj, list):
                            for item in d_obj:
                                extract_idents_from_dict(item, idents_set)
                    extract_idents_from_dict(rec, idents)
                    records.append({
                        'evidence_id': file_id, 'captured_at': captured_at,
                        'system_id': sys_id, 'resource_id': res_id,
                        'state': 'PRESENT', 'category': coll, 'identifiers': idents,
                        'raw': rec
                    })

        return records

    def _parse_txt(self, file_id, origin, captured_at, path):
        records = []
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line.startswith('-'):
                    continue
                parts = [p.strip() for p in line.lstrip('-').split('|')]
                if len(parts) >= 6:
                    ts, sys_id, res_id, cat, status, ident = parts[:6]
                    idents = {ident.lower()}
                    if status == 'NOT_FOUND':
                        state = 'ABSENT'
                    elif status in ('IDENTIFIABLE', 'ACTIVE'):
                        state = 'PRESENT'
                    elif status == 'ANONYMIZED':
                        state = 'ANONYMIZED'
                    elif status == 'REDACTED':
                        state = 'REDACTED'
                    else:
                        state = 'PRESENT'
                    records.append({
                        'evidence_id': file_id, 'captured_at': captured_at,
                        'system_id': sys_id, 'resource_id': res_id,
                        'state': state, 'category': cat, 'identifiers': idents
                    })
        return records

    def _parse_log(self, file_id, origin, captured_at, path):
        records = []
        trace_idents = {}
        parsed_entries = []

        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue

                tr = None
                kv = {}
                # Check for JSON line (e.g. 2026-09-16T08:52:49Z {...})
                json_start = line_str.find('{')
                if json_start != -1 and line_str.endswith('}'):
                    try:
                        kv = json.loads(line_str[json_start:])
                        tr = kv.get('trace_id')
                    except Exception:
                        kv = {}

                if not kv:
                    tr_m = re.search(r'trace_id=(\S+)', line_str)
                    tr = tr_m.group(1) if tr_m else None
                    matches = re.findall(r'(\w+)=(?:"([^"]*)"|(\S+))', line_str)
                    kv = {m[0]: (m[1] if m[1] != '' else m[2]) for m in matches}

                idents = set()
                for k in ('lookup_key', 'match_key', 'subject_key', 'subject_ref', 'subject_reference',
                          'correlation_key', 'customer_reference', 'user_id', 'email', 'matched_value',
                          'owner_email', 'customer_email', 'owner_phone', 'customer_phone'):
                    val = kv.get(k)
                    if val and str(val).lower() not in ('null', 'none', 'nonetype', ''):
                        idents.add(str(val).strip().lower())

                if tr and idents:
                    trace_idents.setdefault(tr, set()).update(idents)

                res_id = kv.get('resource_id')
                svc = kv.get('service') or kv.get('logger')
                if res_id and svc:
                    parsed_entries.append((tr, svc, res_id, kv, idents))

        for tr, raw_svc, res_id, kv, line_idents in parsed_entries:
            svc = raw_svc
            if svc:
                s_low = svc.lower()
                if 'support' in s_low:
                    svc = 'support_platform'
                elif 'analytic' in s_low:
                    svc = 'analytics_platform'
                elif 'integrat' in s_low or 'connector' in s_low:
                    svc = 'integration_service'
                elif 'backup' in s_low:
                    svc = 'backup_service'

            idents = set(line_idents)
            if tr and tr in trace_idents:
                idents.update(trace_idents[tr])

            rows = str(kv.get('rows', ''))
            http_status = str(kv.get('http_status', ''))
            state = 'PRESENT'
            if http_status == '404' or rows == '0' or kv.get('result') == 'miss':
                state = 'ABSENT'
            elif svc == 'integration_service' and kv.get('status') == 'active':
                state = 'ACTIVE'
            elif svc == 'backup_service' and (kv.get('restore_status') == 'enabled' or kv.get('restore_allowed') in ('true', 'True', True)):
                state = 'ACTIVE'
            elif svc == 'analytics_platform':
                # If rows == 1 or has direct identifiers -> PRESENT
                if rows == '1' or any(kv.get(k) and str(kv[k]).lower() not in ('null', 'none', '') for k in ('email', 'phone', 'customer_reference', 'email_hash')):
                    state = 'PRESENT'
                else:
                    state = 'ANONYMIZED'
            elif svc == 'support_platform':
                has_pii = any(kv.get(k) and str(kv[k]).lower() not in ('null', 'none', '') for k in ('requester_email', 'requester_phone', 'matched_value', 'customer_email'))
                marker_found = str(kv.get('marker_found', '')).lower()
                if marker_found == 'false':
                    state = 'PRESENT'
                    event_cat = 'SUPPORT_ATTACHMENT'
                elif has_pii:
                    state = 'PRESENT'
                    event_cat = 'SUPPORT_MESSAGE'
                else:
                    state = 'REDACTED'
                    event_cat = 'SUPPORT_MESSAGE'
            
            records.append({
                'evidence_id': file_id, 'captured_at': captured_at,
                'system_id': svc, 'resource_id': res_id,
                'state': state, 'category': event_cat if 'event_cat' in locals() else kv.get('event', ''), 'identifiers': idents,
                'raw': kv
            })
        return records

    def _parse_pdf(self, file_id, origin, captured_at, path):
        records = []
        reader = pypdf.PdfReader(path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        
        res_matches = re.findall(r'(analytics_\d+|tombstone_\d+|object_\d+|support_\d+|account_\d+|export_\d+|audit_record_\d+|search_\d+|marketing_\d+|data_flow_\d+|backup_\d+)', text)
        email_matches = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        user_matches = re.findall(r'user_\d+', text)
        idents = set(e.lower() for e in email_matches) | set(u.lower() for u in user_matches)

        is_attachment = ('attachment' in str(path).lower() or 'attachment' in origin.lower())
        for res_id in set(res_matches):
            svc = 'support_platform' if res_id.startswith('support_') else \
                  'account_service' if res_id.startswith('account_') else \
                  'export_service' if res_id.startswith('export_') else \
                  'security_service' if res_id.startswith('audit_record_') else 'search_service'
            cat = 'SUPPORT_ATTACHMENT' if is_attachment else ('SUPPORT_MESSAGE' if res_id.startswith('support_') else 'DOCUMENT_RECORD')
            records.append({
                'evidence_id': file_id, 'captured_at': captured_at,
                'system_id': svc, 'resource_id': res_id,
                'state': 'PRESENT', 'category': cat, 'identifiers': idents
            })
        return records

    def _parse_png(self, file_id, origin, captured_at, rel_path):
        records = []
        fname = os.path.basename(rel_path)
        lines = self.images_ocr.get(fname, [])
        
        # Map each resource occurrence to its local window identifiers
        res_to_idents = {}
        for idx, l in enumerate(lines):
            found_res = re.findall(r'(analytics_\d+|tombstone_\d+|object_\d+|support_\d+|account_\d+|export_\d+|audit_record_\d+|search_\d+|marketing_\d+|data_flow_\d+|backup_\d+)', l)
            for r_id in found_res:
                window = lines[max(0, idx-6):min(len(lines), idx+7)]
                win_text = " ".join(window)
                em_matches = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', win_text)
                u_matches = re.findall(r'user_\d+', win_text)
                local_idents = set(e.lower() for e in em_matches if not e.endswith('@northstar.shop') and not e.endswith('@company.com')) | set(u.lower() for u in u_matches)
                res_to_idents.setdefault(r_id, set()).update(local_idents)

        for res_id, idents in res_to_idents.items():
            svc = 'analytics_platform' if res_id.startswith('analytics_') else \
                  'identity_service' if res_id.startswith('tombstone_') else \
                  'object_storage' if res_id.startswith('object_') else \
                  'support_platform' if res_id.startswith('support_') else \
                  'account_service' if res_id.startswith('account_') else \
                  'export_service' if res_id.startswith('export_') else \
                  'security_service' if res_id.startswith('audit_record_') else \
                  'marketing_platform' if res_id.startswith('marketing_') else \
                  'integration_service' if res_id.startswith('data_flow_') else \
                  'backup_service' if res_id.startswith('backup_') else 'search_service'
            records.append({
                'evidence_id': file_id, 'captured_at': captured_at,
                'system_id': svc, 'resource_id': res_id,
                'state': 'PRESENT', 'category': 'IMAGE_RECORD', 'identifiers': idents
            })
        return records
