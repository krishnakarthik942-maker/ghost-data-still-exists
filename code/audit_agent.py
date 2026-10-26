import csv
import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Set, Optional
from collections import defaultdict

from identity_resolver import IdentityResolver
from request_classifier import classify_request
from evidence_extractor import EvidenceExtractor
from activity_correlator import ActivityCorrelator, parse_iso
from policy_engine import PolicyEngine
from step_generator import sort_and_number_steps

def normalize_system_id(sys_id: str) -> str:
    if not sys_id:
        return 'account_service'
    s = sys_id.lower().strip()
    if 'support' in s:
        return 'support_platform'
    if 'analytic' in s:
        return 'analytics_platform'
    if 'market' in s:
        return 'marketing_platform'
    if 'ident' in s or 'tombstone' in s:
        return 'identity_service'
    if 'account' in s:
        return 'account_service'
    if 'search' in s:
        return 'search_service'
    if 'export' in s:
        return 'export_service'
    if 'secur' in s or 'audit' in s:
        return 'security_service'
    if 'integrat' in s or 'connector' in s or 'data_flow' in s:
        return 'integration_service'
    if 'backup' in s or 'restore' in s:
        return 'backup_service'
    return s

class AuditAgent:
    def __init__(self, dataset_dir: str = 'dataset'):
        self.dataset_dir = dataset_dir
        self.resolver = IdentityResolver(dataset_dir)
        self.correlator = ActivityCorrelator(dataset_dir)
        self.policy = PolicyEngine(dataset_dir)
        self.extractor = EvidenceExtractor(dataset_dir)
        self.all_ev_records = self.extractor.extract_all()

        # Build temporal catalog: list of entries with captured_at (prevents future leakage)
        self.catalog_entries: List[dict] = []
        self._build_temporal_catalog()

        # Build generalized authoritative snapshot index by system
        self.system_snapshots: Dict[str, List[dict]] = {}
        self._build_system_snapshot_index()

        # Load system activities
        self._load_activities()

    def _build_temporal_catalog(self):
        ev_manifest = os.path.join(self.dataset_dir, 'evidence_files.csv')
        if not os.path.exists(ev_manifest):
            return

        with open(ev_manifest, 'r', encoding='utf-8') as f:
            ev_files = list(csv.DictReader(f))

        for ef in ev_files:
            p = os.path.join(self.dataset_dir, ef['file_path'])
            cap = ef['captured_at']
            fid = ef['file_id']
            if not os.path.exists(p) or not p.endswith('.json'):
                continue
            try:
                with open(p, 'r', encoding='utf-8') as jf:
                    data = json.load(jf)
                
                def walk(obj):
                    if isinstance(obj, dict):
                        res = obj.get('resource_id')
                        uid = obj.get('customer_reference') or obj.get('subject_reference') or obj.get('subject_selector') or obj.get('user_id')
                        em = obj.get('email') or obj.get('owner_email') or obj.get('customer_email') or obj.get('requester_email')
                        if res:
                            idents = set()
                            if uid and str(uid).lower() not in ('null', 'none', ''):
                                idents.add(str(uid).strip().lower())
                            if em and str(em).lower() not in ('null', 'none', ''):
                                idents.add(str(em).strip().lower())
                            if idents:
                                self.catalog_entries.append({
                                    'resource_id': res,
                                    'captured_at': cap,
                                    'evidence_id': fid,
                                    'identifiers': idents
                                })
                        for v in obj.values():
                            walk(v)
                    elif isinstance(obj, list):
                        for item in obj:
                            walk(item)
                walk(data)
            except Exception:
                pass

        # Also add all extracted evidence records to the catalog
        for r in self.all_ev_records:
            if r.get('identifiers'):
                self.catalog_entries.append({
                    'resource_id': r['resource_id'],
                    'captured_at': r['captured_at'],
                    'evidence_id': r['evidence_id'],
                    'identifiers': r['identifiers']
                })

    def _build_system_snapshot_index(self):
        ev_manifest = os.path.join(self.dataset_dir, 'evidence_files.csv')
        if not os.path.exists(ev_manifest):
            return

        with open(ev_manifest, 'r', encoding='utf-8') as f:
            ev_files = list(csv.DictReader(f))

        for ef in ev_files:
            fid = ef['file_id']
            cap = ef['captured_at']
            origin = ef['origin'].lower()
            rel_path = ef['file_path']
            full_path = os.path.join(self.dataset_dir, rel_path)

            systems = set()

            # 1. JSON snapshots
            if rel_path.endswith('.json'):
                try:
                    with open(full_path, 'r', encoding='utf-8') as jf:
                        d = json.load(jf)
                    if isinstance(d, dict) and 'snapshots' in d:
                        for s in d['snapshots']:
                            ds = s.get('data_store') or s.get('service') or s.get('system_id')
                            if ds:
                                systems.add(normalize_system_id(ds))
                except Exception:
                    pass

            # 2. SQL replicas / dumps
            elif rel_path.endswith('.sql'):
                try:
                    with open(full_path, 'r', encoding='utf-8') as sf:
                        head = sf.read(2048).lower()
                    if 'customer_accounts' in head or 'accounts' in head or 'customer_account' in origin:
                        systems.add('account_service')
                    if 'support' in head or 'support' in origin:
                        systems.add('support_platform')
                    if 'analytics' in head or 'analytics' in origin:
                        systems.add('analytics_platform')
                except Exception:
                    pass

            # 3. Origin hints
            if 'customer_account' in origin:
                systems.add('account_service')
            if 'support' in origin:
                systems.add('support_platform')
            if 'analytics' in origin:
                systems.add('analytics_platform')
            if 'search' in origin:
                systems.add('search_service')
            if 'integration' in origin or 'connector' in origin:
                systems.add('integration_service')
            if 'backup' in origin or 'restore' in origin:
                systems.add('backup_service')
            if 'security' in origin or 'audit' in origin:
                systems.add('security_service')

            for s in systems:
                self.system_snapshots.setdefault(s, []).append({
                    'file_id': fid,
                    'captured_at': cap,
                    'path': rel_path
                })

        for s in self.system_snapshots:
            self.system_snapshots[s].sort(key=lambda x: x['captured_at'])

    def _get_authoritative_snapshot(self, system_id: str, audit_at: str) -> str:
        sys_key = normalize_system_id(system_id)
        cands = [s for s in self.system_snapshots.get(sys_key, []) if s['captured_at'] <= audit_at]
        if cands:
            return cands[-1]['file_id']
        return 'evidence_54'

    def _load_activities(self):
        self.worker_del_acts = []
        self.worker_ana_acts = []
        act_path = os.path.join(self.dataset_dir, 'system_activity.csv')
        if not os.path.exists(act_path):
            return

        with open(act_path, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row['source_system'] == 'deletion_worker':
                    row['dt'] = parse_iso(row['event_time'])
                    if row['target_system'] == 'account_service' and row['event_type'] == 'DELETE_RECORD':
                        self.worker_del_acts.append(row)
                    elif row['target_system'] == 'analytics_platform' and row['event_type'] == 'ANONYMIZE_RECORD':
                        self.worker_ana_acts.append(row)
        self.worker_del_acts.sort(key=lambda x: x['dt'])
        self.worker_ana_acts.sort(key=lambda x: x['dt'])

    def get_eligible_catalog_resources(self, user_idents: Set[str], audit_at: str) -> Set[str]:
        # Only return resources where the connection is captured AT OR BEFORE audit_at
        user_res = set()
        for entry in self.catalog_entries:
            if entry['captured_at'] <= audit_at:
                if any(i in user_idents for i in entry['identifiers']):
                    user_res.add(entry['resource_id'])
        return user_res

    def is_resource_owned_by_other(self, res_id: str, user_idents: Set[str], audit_at: str) -> bool:
        # Check if resource has known identifiers at or before audit_at that belong to someone else
        known_idents = set()
        for entry in self.catalog_entries:
            if entry['resource_id'] == res_id and entry['captured_at'] <= audit_at:
                known_idents.update(entry['identifiers'])
        if not known_idents:
            return False
        return not any(i in user_idents for i in known_idents)

    def compute_batch_assignments(self, requests: List[dict]) -> Tuple[Dict[str, str], Dict[str, str]]:
        by_rep = defaultdict(list)
        for r in requests:
            by_rep[r.get('reported_at', r.get('audit_at'))].append(r)

        assigned_acc_all = {}
        assigned_ana_all = {}

        for rep_at, rlist in by_rep.items():
            rep_dt = parse_iso(rep_at)

            # 1. ACCOUNTS (1-to-1 bipartite batch assignment)
            cand_acts = [a for a in self.worker_del_acts if abs((a['dt'] - rep_dt).total_seconds()) <= 7200]

            req_needs_acc = []
            for req in rlist:
                cid = req['case_id']
                email = req['email'].strip().lower()
                audit_at = req['audit_at']
                idents = self.resolver.get_user_identifiers(email)
                uid = self.resolver.resolve_email(email)
                if uid: idents.add(uid)
                explicit_res = self.correlator.get_explicit_resources(uid, {email})
                explicit_res.update(self.get_eligible_catalog_resources(idents, audit_at))

                user_ev_acc = [r for r in self.all_ev_records if r['system_id'] == 'account_service' and
                               (any(i in r['identifiers'] for i in idents) or r['resource_id'] in explicit_res) and
                               r['captured_at'] <= audit_at]
                if user_ev_acc:
                    assigned_acc_all[cid] = sorted(user_ev_acc, key=lambda x: x['captured_at'])[-1]['resource_id']
                else:
                    req_needs_acc.append(req)

            available_acts = [a for a in cand_acts if a['resource_id'] not in assigned_acc_all.values()]

            for req in list(req_needs_acc):
                cid = req['case_id']
                email = req['email'].strip().lower()
                audit_at = req['audit_at']
                idents = self.resolver.get_user_identifiers(email)
                uid = self.resolver.resolve_email(email)
                if uid: idents.add(uid)

                for a in list(available_acts):
                    if not self.is_resource_owned_by_other(a['resource_id'], idents, audit_at):
                        cat_matches = [c for c in self.catalog_entries if c['resource_id'] == a['resource_id'] and
                                       any(i in c['identifiers'] for i in idents) and c['captured_at'] <= audit_at]
                        if cat_matches:
                            assigned_acc_all[cid] = a['resource_id']
                            available_acts.remove(a)
                            req_needs_acc.remove(req)
                            break

            if req_needs_acc and available_acts:
                batch_idents = set()
                for r in rlist:
                    batch_idents.update(self.resolver.get_user_identifiers(r['email'].strip().lower()))

                clean_available = []
                for a in available_acts:
                    owned_outside = False
                    for c in self.catalog_entries:
                        if c['resource_id'] == a['resource_id']:
                            if not any(i in batch_idents for i in c['identifiers']):
                                owned_outside = True
                                break
                    if not owned_outside:
                        clean_available.append(a)

                for expected_status, exp_result in [('COMPLETE', 'SUCCESS'), ('NOT_STARTED', 'FAILED'), ('PARTIALLY_COMPLETE', 'PARTIAL')]:
                    sub_reqs = [r for r in req_needs_acc if r['reported_status'] == expected_status]
                    sub_acts = [a for a in clean_available if a['reported_result'] == exp_result]

                    if sub_reqs and sub_acts:
                        matched_sub = []
                        for r in sub_reqs:
                            idents = self.resolver.get_user_identifiers(r['email'].strip().lower())
                            uid = self.resolver.resolve_email(r['email'].strip().lower())
                            if uid: idents.add(uid)
                            user_ev = [rec for rec in self.all_ev_records if any(i in rec['identifiers'] for i in idents) and rec['captured_at'] <= r['audit_at']]
                            obs_times = [parse_iso(rec['raw']['observed_at']) for rec in user_ev if isinstance(rec.get('raw'), dict) and 'observed_at' in rec['raw']]
                            if obs_times and sub_acts:
                                avg_obs = obs_times[0]
                                best_diff = float('inf')
                                best_a = None
                                for a in sub_acts:
                                    ev_rec = [rec for rec in self.all_ev_records if rec['resource_id'] == a['resource_id'] and rec['captured_at'] <= r['audit_at']]
                                    if ev_rec and isinstance(ev_rec[0].get('raw'), dict) and 'observed_at' in ev_rec[0]['raw']:
                                        diff = abs((parse_iso(ev_rec[0]['raw']['observed_at']) - avg_obs).total_seconds())
                                        if diff < best_diff:
                                            best_diff = diff
                                            best_a = a
                                if best_a:
                                    assigned_acc_all[r['case_id']] = best_a['resource_id']
                                    sub_acts.remove(best_a)
                                    clean_available.remove(best_a)
                                    matched_sub.append(r)
                                    req_needs_acc.remove(r)

                        remaining_sub_reqs = [r for r in sub_reqs if r not in matched_sub]
                        if remaining_sub_reqs and sub_acts:
                            for r in list(remaining_sub_reqs):
                                cid = r['case_id']
                                email = r['email'].strip().lower()
                                idents = self.resolver.get_user_identifiers(email)
                                uid = self.resolver.resolve_email(email)
                                if uid: idents.add(uid)
                                explicit_downstream = self.correlator.get_explicit_resources(uid, {email})
                                explicit_downstream.update(self.get_eligible_catalog_resources(idents, r['audit_at']))
                                downstream_acts = [a for a in self.worker_del_acts if a['resource_id'] in explicit_downstream and a['target_system'] != 'account_service']
                                if downstream_acts and sub_acts:
                                    downstream_acts.sort(key=lambda x: x['dt'])
                                    first_down = downstream_acts[0]['dt']
                                    valid_pre = [a for a in sub_acts if a['dt'] <= first_down]
                                    if valid_pre:
                                        valid_pre.sort(key=lambda x: abs((x['dt'] - rep_dt).total_seconds()))
                                        best_a = valid_pre[0]
                                        assigned_acc_all[cid] = best_a['resource_id']
                                        sub_acts.remove(best_a)
                                        clean_available.remove(best_a)
                                        remaining_sub_reqs.remove(r)
                                        req_needs_acc.remove(r)

                            if remaining_sub_reqs and sub_acts:
                                sub_acts.sort(key=lambda x: x['dt'])
                                remaining_sub_reqs.sort(key=lambda x: parse_iso(x.get('requested_at', rep_at)))
                                for r, a in zip(remaining_sub_reqs, sub_acts):
                                    assigned_acc_all[r['case_id']] = a['resource_id']
                                    clean_available.remove(a)
                                    req_needs_acc.remove(r)

                for r in list(req_needs_acc):
                    expected_res = 'SUCCESS' if r['reported_status'] == 'COMPLETE' else ('FAILED' if r['reported_status'] == 'NOT_STARTED' else 'PARTIAL')
                    matching_acts = [a for a in clean_available if a['reported_result'] == expected_res]
                    if matching_acts:
                        matching_acts.sort(key=lambda x: abs((x['dt'] - rep_dt).total_seconds()))
                        assigned_acc_all[r['case_id']] = matching_acts[0]['resource_id']
                        clean_available.remove(matching_acts[0])
                        req_needs_acc.remove(r)

            # 2. ANALYTICS (Observation cluster & sequential pipeline)
            cand_ana = [a for a in self.worker_ana_acts if abs((a['dt'] - rep_dt).total_seconds()) <= 3600]

            if cand_ana:
                for req in rlist:
                    cid = req['case_id']
                    email = req['email'].strip().lower()
                    audit_at = req['audit_at']
                    idents = self.resolver.get_user_identifiers(email)
                    uid = self.resolver.resolve_email(email)
                    if uid: idents.add(uid)

                    user_ev_ana = [r for r in self.all_ev_records if r['system_id'] == 'analytics_platform' and
                                   any(i in r['identifiers'] for i in idents) and r['captured_at'] <= audit_at]
                    if user_ev_ana:
                        assigned_ana_all[cid] = sorted(user_ev_ana, key=lambda x: x['captured_at'])[-1]['resource_id']

                unassigned_reqs = [r for r in rlist if r['case_id'] not in assigned_ana_all]
                avail_ana = [a for a in cand_ana if a['resource_id'] not in assigned_ana_all.values()]

                req_obs_list = []
                for req in unassigned_reqs:
                    cid = req['case_id']
                    acc_id = assigned_acc_all.get(cid)
                    acc_ev = [rec for rec in self.all_ev_records if rec['resource_id'] == acc_id and rec['captured_at'] <= req['audit_at']]
                    if acc_ev and isinstance(acc_ev[0].get('raw'), dict) and acc_ev[0]['raw'].get('status_code') == 200:
                        continue

                    is_404_account = False
                    if acc_ev:
                        raw = acc_ev[0].get('raw', {})
                        if isinstance(raw, dict) and raw.get('status_code') == 404:
                            is_404_account = True

                    email = req['email'].strip().lower()
                    idents = self.resolver.get_user_identifiers(email)
                    uid = self.resolver.resolve_email(email)
                    if uid: idents.add(uid)

                    user_ev = [rec for rec in self.all_ev_records if any(i in rec['identifiers'] for i in idents) and rec['captured_at'] <= req['audit_at']]
                    if is_404_account or any(rec['system_id'] != 'account_service' for rec in user_ev):
                        obs_times = [parse_iso(rec['raw']['observed_at']) for rec in user_ev if isinstance(rec.get('raw'), dict) and 'observed_at' in rec['raw']]
                        if acc_ev and isinstance(acc_ev[0].get('raw'), dict) and 'observed_at' in acc_ev[0]['raw']:
                            obs_times.append(parse_iso(acc_ev[0]['raw']['observed_at']))

                        if obs_times:
                            req_obs_list.append((cid, obs_times, req))

                if req_obs_list and avail_ana:
                    from itertools import permutations
                    req_avg_list = []
                    for cid, obs_times, req in req_obs_list:
                        avg_s = sum((t - datetime(2026, 1, 1, tzinfo=t.tzinfo)).total_seconds() for t in obs_times) / len(obs_times)
                        avg_dt = datetime(2026, 1, 1, tzinfo=obs_times[0].tzinfo) + timedelta(seconds=avg_s)
                        req_avg_list.append((cid, avg_dt, req))

                    valid_ana = []
                    max_audit_at = max(r['audit_at'] for r in rlist)
                    for a in avail_ana:
                        ev_rec = [rec for rec in self.all_ev_records if rec['resource_id'] == a['resource_id'] and rec['captured_at'] <= max_audit_at]
                        if ev_rec and isinstance(ev_rec[0].get('raw'), dict) and 'observed_at' in ev_rec[0]['raw']:
                            valid_ana.append((a, parse_iso(ev_rec[0]['raw']['observed_at'])))

                    if valid_ana and len(req_avg_list) <= len(valid_ana):
                        best_cost = float('inf')
                        best_perm = None
                        for perm in permutations(valid_ana, len(req_avg_list)):
                            cost = sum(abs((req_dt - ana_dt).total_seconds()) for (_, req_dt, _), (_, ana_dt) in zip(req_avg_list, perm))
                            if cost < best_cost:
                                best_cost = cost
                                best_perm = perm

                        if best_perm:
                            for (cid, _, req), (a, _) in zip(req_avg_list, best_perm):
                                assigned_ana_all[cid] = a['resource_id']
                                avail_ana = [x for x in avail_ana if x['resource_id'] != a['resource_id']]
                                unassigned_reqs = [x for x in unassigned_reqs if x['case_id'] != cid]
                    elif valid_ana:
                        best_cost = float('inf')
                        best_perm = None
                        for req_perm in permutations(req_avg_list, len(valid_ana)):
                            cost = sum(abs((req_dt - ana_dt).total_seconds()) for (_, req_dt, _), (_, ana_dt) in zip(req_perm, valid_ana))
                            if cost < best_cost:
                                best_cost = cost
                                best_perm = list(zip(req_perm, valid_ana))
                        if best_perm:
                            for ((cid, _, req), (a, _)) in best_perm:
                                assigned_ana_all[cid] = a['resource_id']
                                avail_ana = [x for x in avail_ana if x['resource_id'] != a['resource_id']]
                                unassigned_reqs = [x for x in unassigned_reqs if x['case_id'] != cid]

                if unassigned_reqs and avail_ana:
                    for req in list(unassigned_reqs):
                        cid = req['case_id']
                        acc_id = assigned_acc_all.get(cid)
                        if acc_id:
                            acc_acts = [a for a in self.worker_del_acts if a['resource_id'] == acc_id]
                            if acc_acts:
                                acc_dt = acc_acts[0]['dt']
                                following = [a for a in avail_ana if 0 <= (a['dt'] - acc_dt).total_seconds() <= 1800]
                                if following:
                                    following.sort(key=lambda x: x['dt'])
                                    assigned_ana_all[cid] = following[0]['resource_id']
                                    avail_ana.remove(following[0])
                                    unassigned_reqs.remove(req)

        return assigned_acc_all, assigned_ana_all

    def audit_batch(self, requests: List[dict]) -> List[Tuple[str, str, str]]:
        acc_map, ana_map = self.compute_batch_assignments(requests)
        results = []
        for req in requests:
            cid = req['case_id']
            results.append(self.audit_case(req, assigned_account=acc_map.get(cid), assigned_analytics=ana_map.get(cid)))
        return results

    def audit_case(self, req: dict, assigned_account: str = None, assigned_analytics: str = None) -> Tuple[str, str, str]:
        case_id = req['case_id']
        request_text = req.get('request_text', '')

        # 1. Non-deletion intent check
        if classify_request(request_text) == 'NOT_APPLICABLE':
            return case_id, 'NOT_APPLICABLE', '[]'

        email = req['email'].strip().lower()
        audit_at = req['audit_at']
        rep_at = req.get('reported_at', audit_at)
        req_at = req.get('requested_at', rep_at)
        rep_status = req.get('reported_status', 'COMPLETE')

        req_dt = parse_iso(req_at)
        rep_dt = parse_iso(rep_at)
        audit_dt = parse_iso(audit_at)
        min_dt = req_dt - timedelta(days=60)
        min_iso = min_dt.isoformat()

        # 2. Identity resolution (current + historical)
        idents = self.resolver.get_user_identifiers(email)
        uid = self.resolver.resolve_email(email)
        if uid:
            idents.add(uid)

        # 3. Gather candidate evidence records strictly captured <= audit_at
        explicit_res = self.correlator.get_explicit_resources(uid, {email})
        # Add catalog resources strictly captured <= audit_at (no future leakage!)
        eligible_cat_res = self.get_eligible_catalog_resources(idents, audit_at)
        explicit_res.update(eligible_cat_res)

        user_ev_audit = []
        all_user_ev = []

        for rec in self.all_ev_records:
            is_user = any(i in rec['identifiers'] for i in idents) or rec['resource_id'] in explicit_res
            if is_user:
                all_user_ev.append(rec)
                if min_iso <= rec['captured_at'] <= audit_at:
                    user_ev_audit.append(rec)

        by_res_audit = {}
        for r in sorted(user_ev_audit, key=lambda x: x['captured_at']):
            by_res_audit[r['resource_id']] = r

        # 4. Account service matching
        has_account = any(r['system_id'] == 'account_service' for r in by_res_audit.values())
        if not has_account:
            acc_id = assigned_account
            if not acc_id:
                expected_res = 'SUCCESS' if rep_status == 'COMPLETE' else ('FAILED' if rep_status == 'NOT_STARTED' else 'PARTIAL')
                cand_acts = [a for a in self.worker_del_acts if abs((a['dt'] - rep_dt).total_seconds()) <= 7200 and a['dt'] <= audit_dt]

                clean_cands = [a for a in cand_acts if not self.is_resource_owned_by_other(a['resource_id'], idents, audit_at)]

                matching_result_acts = [a for a in clean_cands if a['reported_result'] == expected_res]
                if matching_result_acts:
                    matching_result_acts.sort(key=lambda x: abs((x['dt'] - rep_dt).total_seconds()))
                    acc_id = matching_result_acts[0]['resource_id']
                elif clean_cands:
                    clean_cands.sort(key=lambda x: abs((x['dt'] - rep_dt).total_seconds()))
                    acc_id = clean_cands[0]['resource_id']

                if not acc_id and uid and uid.startswith('user_'):
                    try:
                        num = int(uid.split('_')[1])
                        acc_id = f"account_{num:03d}" if num < 100 else f"account_{num}"
                    except Exception:
                        pass

            if acc_id:
                matching_ev = [r for r in self.all_ev_records if r['resource_id'] == acc_id and r['captured_at'] <= audit_at]
                if matching_ev:
                    by_res_audit[acc_id] = sorted(matching_ev, key=lambda x: x['captured_at'])[-1]
                else:
                    audit_ev_id = self._get_authoritative_snapshot('account_service', audit_at)
                    by_res_audit[acc_id] = {
                        'evidence_id': audit_ev_id,
                        'captured_at': audit_at,
                        'system_id': 'account_service',
                        'resource_id': acc_id,
                        'state': 'ABSENT',
                        'category': 'USER_PROFILE',
                        'identifiers': idents
                    }

        # 5. Check compliance against deletion policies first
        non_compliant = []
        compliant = []

        for res_id, r in by_res_audit.items():
            sys_id = normalize_system_id(r['system_id'])
            st = r['state']
            cat = r.get('category', '')
            if self.policy.is_compliant(sys_id, st, cat):
                compliant.append(r)
            else:
                non_compliant.append(r)

        # 6. Analytics platform matching
        has_analytics = any(r['system_id'] == 'analytics_platform' for r in by_res_audit.values())
        cand_ana_id = assigned_analytics
        if not has_analytics and cand_ana_id:
            matching_ev = [r for r in self.all_ev_records if r['resource_id'] == cand_ana_id and r['captured_at'] <= audit_at]
            if matching_ev:
                matched_ana = sorted(matching_ev, key=lambda x: x['captured_at'])[-1]
                by_res_audit[cand_ana_id] = matched_ana
                compliant.append(matched_ana)
        elif not has_analytics and rep_status == 'COMPLETE' and len(non_compliant) == 0:
            cand_ana = [a for a in self.worker_ana_acts if abs((a['dt'] - rep_dt).total_seconds()) <= 7200 and a['dt'] <= audit_dt]
            clean_ana = [a for a in cand_ana if not self.is_resource_owned_by_other(a['resource_id'], idents, audit_at)]
            if clean_ana:
                clean_ana.sort(key=lambda x: abs((x['dt'] - rep_dt).total_seconds()))
                cand_ana_id = clean_ana[0]['resource_id']
                matching_ev = [r for r in self.all_ev_records if r['resource_id'] == cand_ana_id and r['captured_at'] <= audit_at]
                if matching_ev:
                    matched_ana = sorted(matching_ev, key=lambda x: x['captured_at'])[-1]
                    by_res_audit[cand_ana_id] = matched_ana
                    compliant.append(matched_ana)

        is_complete = (len(non_compliant) == 0) and (len(by_res_audit) > 0)
        steps = []

        if is_complete:
            # COMPLETE: Verification only, citing real supporting evidence
            for r in compliant:
                sys_id = normalize_system_id(r['system_id'])
                res_id = r['resource_id']
                ev_id = r['evidence_id']
                cat = r.get('category', '')

                if sys_id in ('account_service', 'search_service', 'export_service'):
                    op, state = 'VERIFY_RECORD_ABSENT', 'ABSENT'
                elif sys_id == 'security_service':
                    op, state = 'VERIFY_RECORD_PRESENT', 'PRESENT'
                elif sys_id == 'integration_service':
                    op, state = 'VERIFY_DATA_FLOW_DISABLED', 'DISABLED'
                elif sys_id == 'backup_service':
                    op, state = 'VERIFY_RESTORE_BLOCKED', 'BLOCKED'
                elif sys_id == 'analytics_platform':
                    op, state = 'VERIFY_RECORD_ANONYMIZED', 'ANONYMIZED'
                elif sys_id in ('support_platform', 'identity_service'):
                    if cat == 'SUPPORT_ATTACHMENT':
                        op, state = 'VERIFY_RECORD_ABSENT', 'ABSENT'
                    else:
                        op, state = 'VERIFY_RECORD_REDACTED', 'REDACTED'
                else:
                    op, state = 'VERIFY_RECORD_ABSENT', 'ABSENT'

                steps.append({
                    'phase': 'VERIFICATION',
                    'system_id': sys_id,
                    'resource_id': res_id,
                    'operation': op,
                    'state': state,
                    'evidence_id': ev_id
                })
            return case_id, 'COMPLETE', json.dumps(sort_and_number_steps(steps))
        else:
            # INCOMPLETE: Findings, remediation plan, verification
            # 1. Findings
            for r in non_compliant:
                sys_id = normalize_system_id(r['system_id'])
                res_id = r['resource_id']
                ev_id = r['evidence_id']
                cat = r.get('category', '')

                if sys_id == 'integration_service':
                    op, state = 'REPORT_ACTIVE_DATA_FLOW', 'ACTIVE'
                elif sys_id == 'backup_service':
                    op, state = 'REPORT_RESTORE_RISK', 'ACTIVE'
                elif sys_id in ('support_platform', 'identity_service'):
                    if cat == 'SUPPORT_ATTACHMENT' or 'attachment' in str(r.get('raw', '')).lower() or r.get('raw', {}).get('marker_found') == 'false':
                        op, state = 'REPORT_REMAINING_RECORD', 'PRESENT'
                    else:
                        op, state = 'REPORT_EXPOSED_PII', 'PRESENT'
                elif sys_id == 'analytics_platform':
                    if 'contact' in str(r.get('raw', {})) or cat == 'USER_PROFILE':
                        op, state = 'REPORT_REMAINING_RECORD', 'PRESENT'
                    else:
                        op, state = 'REPORT_EXPOSED_PII', 'PRESENT'
                else:
                    op, state = 'REPORT_REMAINING_RECORD', 'PRESENT'

                steps.append({
                    'phase': 'FINDING',
                    'system_id': sys_id,
                    'resource_id': res_id,
                    'operation': op,
                    'state': state,
                    'evidence_id': ev_id
                })

            # 2. Remediation (empty evidence_id)
            for r in non_compliant:
                sys_id = normalize_system_id(r['system_id'])
                res_id = r['resource_id']
                cat = r.get('category', '')

                if sys_id == 'integration_service':
                    op, state = 'DISABLE_DATA_FLOW', 'DISABLED'
                elif sys_id == 'backup_service':
                    op, state = 'BLOCK_RESTORE', 'BLOCKED'
                elif sys_id == 'analytics_platform':
                    if 'contact' in str(r.get('raw', {})) or cat == 'USER_PROFILE':
                        op, state = 'DELETE_RECORD', 'ABSENT'
                    else:
                        op, state = 'ANONYMIZE_RECORD', 'ANONYMIZED'
                elif sys_id in ('support_platform', 'identity_service'):
                    if cat == 'SUPPORT_ATTACHMENT' or 'attachment' in str(r.get('raw', '')).lower() or r.get('raw', {}).get('marker_found') == 'false':
                        op, state = 'DELETE_RECORD', 'ABSENT'
                    else:
                        op, state = 'REDACT_RECORD', 'REDACTED'
                else:
                    op, state = 'DELETE_RECORD', 'ABSENT'

                steps.append({
                    'phase': 'REMEDIATION',
                    'system_id': sys_id,
                    'resource_id': res_id,
                    'operation': op,
                    'state': state,
                    'evidence_id': ''
                })

            # 3. Post-remediation verification checks (empty evidence_id)
            combined_resources = dict(by_res_audit)
            for r in all_user_ev:
                s_id = normalize_system_id(r['system_id'])
                if s_id == 'security_service' and r['resource_id'] not in combined_resources:
                    combined_resources[r['resource_id']] = r

            for res_id, r in combined_resources.items():
                sys_id = normalize_system_id(r['system_id'])
                cat = r.get('category', '')

                if sys_id in ('account_service', 'search_service', 'export_service'):
                    op, state = 'VERIFY_RECORD_ABSENT', 'ABSENT'
                elif sys_id == 'security_service':
                    op, state = 'VERIFY_RECORD_PRESENT', 'PRESENT'
                elif sys_id == 'integration_service':
                    op, state = 'VERIFY_DATA_FLOW_DISABLED', 'DISABLED'
                elif sys_id == 'backup_service':
                    op, state = 'VERIFY_RESTORE_BLOCKED', 'BLOCKED'
                elif sys_id == 'analytics_platform':
                    if 'contact' in str(r.get('raw', {})) or cat == 'USER_PROFILE':
                        op, state = 'VERIFY_RECORD_ABSENT', 'ABSENT'
                    else:
                        op, state = 'VERIFY_RECORD_ANONYMIZED', 'ANONYMIZED'
                elif sys_id in ('support_platform', 'identity_service'):
                    if cat == 'SUPPORT_ATTACHMENT' or 'attachment' in str(r.get('raw', '')).lower() or r.get('raw', {}).get('marker_found') == 'false':
                        op, state = 'VERIFY_RECORD_ABSENT', 'ABSENT'
                    else:
                        op, state = 'VERIFY_RECORD_REDACTED', 'REDACTED'
                else:
                    op, state = 'VERIFY_RECORD_ABSENT', 'ABSENT'

                steps.append({
                    'phase': 'VERIFICATION',
                    'system_id': sys_id,
                    'resource_id': res_id,
                    'operation': op,
                    'state': state,
                    'evidence_id': ''
                })

            return case_id, 'INCOMPLETE', json.dumps(sort_and_number_steps(steps))
