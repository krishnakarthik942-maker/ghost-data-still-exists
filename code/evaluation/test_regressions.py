import unittest
import csv
import json
import os
import sys

# Add code directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from audit_agent import AuditAgent
from identity_resolver import IdentityResolver
from evidence_extractor import EvidenceExtractor
from policy_engine import PolicyEngine

class TestComplianceAuditRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = AuditAgent('dataset')

    def test_future_evidence_leakage_prevented(self):
        """
        Verify that relationships or resources appearing ONLY in evidence captured
        after audit_at are strictly invisible to an earlier audit.
        """
        user_idents = {'test.user@example.com', 'user_9999'}
        # Simulate a future evidence entry
        future_entry = {
            'resource_id': 'account_future_test_999',
            'captured_at': '2026-09-25T12:00:00Z',
            'evidence_id': 'evidence_future_mock',
            'identifiers': user_idents
        }
        self.agent.catalog_entries.append(future_entry)

        # Audit cutoff prior to future evidence
        earlier_audit_at = '2026-09-10T12:00:00Z'
        discovered_earlier = self.agent.get_eligible_catalog_resources(user_idents, earlier_audit_at)
        self.assertNotIn('account_future_test_999', discovered_earlier,
                         "CRITICAL: Future evidence leaked into an audit prior to its capture date!")

        # Audit cutoff after future evidence
        later_audit_at = '2026-09-30T12:00:00Z'
        discovered_later = self.agent.get_eligible_catalog_resources(user_idents, later_audit_at)
        self.assertIn('account_future_test_999', discovered_later,
                      "Resource should be discovered when audit_at is after capture date.")

        # Clean up mock entry
        self.agent.catalog_entries.remove(future_entry)

    def test_concurrent_worker_isolation(self):
        """
        Verify that concurrent deletion tasks within the same window
        cannot attribute another person's resource to the current user.
        """
        user_a_idents = {'alice@example.com', 'user_101'}
        # Mark resource account_9988 as belonging to Bob
        bob_idents = {'bob@example.com', 'user_102'}
        self.agent.catalog_entries.append({
            'resource_id': 'account_9988',
            'captured_at': '2026-09-01T00:00:00Z',
            'evidence_id': 'mock_evidence',
            'identifiers': bob_idents
        })

        is_owned_by_other = self.agent.is_resource_owned_by_other('account_9988', user_a_idents, '2026-09-15T00:00:00Z')
        self.assertTrue(is_owned_by_other, "Resource owned by Bob must be flagged as owned by other for Alice.")

    def test_support_attachment_vs_message_classification(self):
        """
        Verify that support attachments require complete removal (DELETE_RECORD),
        whereas support conversation messages require redaction (REDACT_RECORD).
        """
        policy = self.agent.policy
        # Rule 06: Support attachments containing PII require complete deletion
        attachment_compliant = policy.is_compliant('support_platform', 'REDACTED', 'SUPPORT_ATTACHMENT')
        self.assertFalse(attachment_compliant, "SUPPORT_ATTACHMENT cannot remain as REDACTED; it must be ABSENT.")

        # Rule 04: Support messages with PII redacted are compliant
        message_compliant = policy.is_compliant('support_platform', 'REDACTED', 'SUPPORT_MESSAGE')
        self.assertTrue(message_compliant, "SUPPORT_MESSAGE is compliant once direct PII is REDACTED.")

    def test_security_audit_retention_preserved(self):
        """
        Verify that security audit records are retained under Rule 07 and never deleted.
        """
        policy = self.agent.policy
        # Security audit log must be PRESENT
        self.assertTrue(policy.is_compliant('security_service', 'PRESENT', 'SECURITY_AUDIT_LOG'),
                        "Security audit log must be retained as PRESENT.")
        self.assertFalse(policy.is_compliant('security_service', 'ABSENT', 'SECURITY_AUDIT_LOG'),
                         "Security audit log cannot be deleted.")

    def test_account_tombstone_compliance(self):
        """
        Verify that account tombstones must have prohibited identifiers redacted
        while preserving the internal tombstone record under Rule 05.
        """
        policy = self.agent.policy
        self.assertTrue(policy.is_compliant('identity_service', 'REDACTED', 'ACCOUNT_TOMBSTONE'),
                        "ACCOUNT_TOMBSTONE is compliant when direct PII is REDACTED.")
        self.assertFalse(policy.is_compliant('identity_service', 'PRESENT', 'ACCOUNT_TOMBSTONE'),
                         "ACCOUNT_TOMBSTONE cannot remain with unredacted PII (PRESENT).")

    def test_zero_false_complete_safety_invariant(self):
        """
        Verify that an unredacted support record or active sync connector strictly outputs INCOMPLETE.
        """
        # Test case with active connector
        mock_req = {
            'case_id': 'test_safety_gate',
            'email': 'lucia-garcia@proton.me',
            'requested_at': '2026-03-25T10:00:00Z',
            'reported_status': 'COMPLETE', # Worker falsely claims complete
            'reported_at': '2026-03-28T10:00:00Z',
            'audit_at': '2026-03-30T10:00:00Z',
            'request_text': 'Please delete all my personal data.'
        }
        cid, status, steps_json = self.agent.audit_case(mock_req)
        self.assertEqual(status, 'INCOMPLETE',
                         "CRITICAL SAFETY VIOLATION: Case with surviving unredacted records was marked COMPLETE!")
        steps = json.loads(steps_json)
        self.assertTrue(len(steps) > 0, "INCOMPLETE cases must have remediation steps.")
        # Future remediation and verification steps must have empty evidence_id
        for s in steps:
            if s['phase'] == 'REMEDIATION':
                self.assertEqual(s['evidence_id'], '', "Remediation step must have empty evidence_id.")
    def test_strict_temporal_cutoff_boundary(self):
        """
        Verify that evidence captured even 1 second after audit_at is strictly excluded,
        and cannot be selected as an authoritative snapshot or evidence source.
        """
        cutoff_time = '2026-08-15T12:00:00Z'
        # Snapshot at exactly audit_at vs 1 second later
        valid_ev = {
            'file_id': 'evidence_mock_on_time',
            'origin': 'customer_data_inventory',
            'captured_at': '2026-08-15T12:00:00Z'
        }
        leaked_ev = {
            'file_id': 'evidence_mock_leaked',
            'origin': 'customer_data_inventory',
            'captured_at': '2026-08-15T12:00:01Z'
        }
        test_entries = [
            {'resource_id': 'res_on_time', 'captured_at': valid_ev['captured_at'], 'identifiers': {'user_boundary@example.com'}},
            {'resource_id': 'res_leaked', 'captured_at': leaked_ev['captured_at'], 'identifiers': {'user_boundary@example.com'}}
        ]
        self.agent.catalog_entries.extend(test_entries)

        discovered = self.agent.get_eligible_catalog_resources({'user_boundary@example.com'}, cutoff_time)
        self.assertIn('res_on_time', discovered, "On-time evidence must be discovered.")
        self.assertNotIn('res_leaked', discovered, "Evidence captured 1s after cutoff must NOT be discovered.")

        for e in test_entries:
            self.agent.catalog_entries.remove(e)

    def test_cross_user_batch_attribution_collision(self):
        """
        Verify that when two users share an activity burst window, resources belonging
        to User B are strictly prevented from being attributed to User A.
        """
        user_a = {'user_a@example.com', 'user_111'}
        user_b = {'user_b@example.com', 'user_222'}

        # Resource belonging to User B
        self.agent.catalog_entries.append({
            'resource_id': 'account_user_b_res',
            'captured_at': '2026-07-01T00:00:00Z',
            'identifiers': user_b
        })

        is_owned_by_b = self.agent.is_resource_owned_by_other('account_user_b_res', user_a, '2026-07-15T00:00:00Z')
        self.assertTrue(is_owned_by_b, "Resource of User B must be flagged as owned by other when auditing User A.")

        # Clean up
        self.agent.catalog_entries.pop()

    def test_active_sync_connector_and_restore_hazard(self):
        """
        Verify that active data flows or unblocked backups force an INCOMPLETE status,
        prescribe DISABLE_DATA_FLOW / BLOCK_RESTORE remediation, and verify them afterward.
        """
        policy = self.agent.policy
        # Rule 10: Active connector configurations must be disabled
        self.assertFalse(policy.is_compliant('integration_service', 'ACTIVE', 'CONNECTOR_CONFIGURATION'))
        self.assertTrue(policy.is_compliant('integration_service', 'DISABLED', 'CONNECTOR_CONFIGURATION'))

        # Rule 11: Surviving restore capability must be blocked
        self.assertFalse(policy.is_compliant('backup_service', 'ACTIVE', 'BACKUP_RECORD'))
        self.assertTrue(policy.is_compliant('backup_service', 'BLOCKED', 'BACKUP_RECORD'))

    def test_batch_bipartite_assignment_overlapping_windows(self):
        """
        Verify that bipartite batch matching solves 1-to-1 assignments across concurrent
        requests sharing the same reported_at window without colliding or attributing
        conflicting accounts.
        """
        # Create two synthetic requests in the same reported_at window
        req_1 = {
            'case_id': 'synth_case_1',
            'email': 'synth1@example.com',
            'reported_status': 'COMPLETE',
            'reported_at': '2026-09-06T12:00:00Z',
            'audit_at': '2026-09-15T12:00:00Z',
            'request_text': 'Please delete all my personal data.'
        }
        req_2 = {
            'case_id': 'synth_case_2',
            'email': 'synth2@example.com',
            'reported_status': 'COMPLETE',
            'reported_at': '2026-09-06T12:00:00Z',
            'audit_at': '2026-09-15T12:00:00Z',
            'request_text': 'I request account deletion.'
        }
        acc_map, ana_map = self.agent.compute_batch_assignments([req_1, req_2])
        # Verify 1-to-1 disjoint allocation: no two requests get the same resource
        allocated_accs = [acc for acc in acc_map.values() if acc]
        self.assertEqual(len(allocated_accs), len(set(allocated_accs)),
                         "Bipartite matching must never assign the same account to multiple concurrent requests.")

    def test_observation_clustering_and_200_exclusion(self):
        """
        Verify that active profiles with status_code: 200 are excluded from anonymized
        analytics attribution, preserving strict isolation for deleted profiles.
        """
        # Account with status 200 (active profile)
        acc_200 = 'account_5334'
        ev_200 = [rec for rec in self.agent.all_ev_records if rec['resource_id'] == acc_200 and rec['captured_at'] <= '2026-09-15T12:00:00Z']
        self.assertTrue(any(r.get('raw', {}).get('status_code') == 200 for r in ev_200),
                        "account_5334 must have status_code 200 in evidence.")

        # Test request using account_5334
        req = {
            'case_id': 'test_200_case',
            'email': 'keiko.nakamura@gmail.com',
            'reported_status': 'NOT_STARTED',
            'reported_at': '2026-09-02T12:00:00Z',
            'audit_at': '2026-09-15T12:00:00Z',
            'request_text': 'Delete my account.'
        }
        acc_map, ana_map = self.agent.compute_batch_assignments([req])
        self.assertNotIn('test_200_case', ana_map,
                         "A request associated with an active status_code: 200 profile must NOT be assigned an anonymized analytics profile.")

    def test_request_order_invariance(self):
        """
        Verify that reordering requests in a concurrent batch produces identical
        deterministic assignments and preserves 1-to-1 disjoint allocations.
        """
        req_a = {
            'case_id': 'req_a',
            'email': 'ananya.k5892@outlook.com',
            'requested_at': '2026-08-30T10:00:00Z',
            'reported_status': 'NOT_STARTED',
            'reported_at': '2026-09-02T12:00:00Z',
            'audit_at': '2026-09-15T12:00:00Z',
            'request_text': 'Delete my account.'
        }
        req_b = {
            'case_id': 'req_b',
            'email': 's.jang78@yahoo.com',
            'requested_at': '2026-08-31T10:00:00Z',
            'reported_status': 'NOT_STARTED',
            'reported_at': '2026-09-02T12:00:00Z',
            'audit_at': '2026-09-15T12:00:00Z',
            'request_text': 'Delete my account.'
        }
        map_ab, _ = self.agent.compute_batch_assignments([req_a, req_b])
        map_ba, _ = self.agent.compute_batch_assignments([req_b, req_a])
        self.assertEqual(map_ab.get('req_a'), map_ba.get('req_a'), "Assignment for req_a must be invariant to batch input order.")
        self.assertEqual(map_ab.get('req_b'), map_ba.get('req_b'), "Assignment for req_b must be invariant to batch input order.")

    def test_ungrounded_audit_records_never_fabricated(self):
        """
        Verify that the agent never invents or cites non-existent security audit records
        (such as audit_record_6645 or audit_record_5569) without participant evidence.
        """
        for ef in self.agent.extractor.evidence_files:
            self.assertNotEqual(ef['file_id'], 'audit_record_6645')
            self.assertNotEqual(ef['file_id'], 'audit_record_5569')

        # Run sample case 18 and case 20 through agent
        req_18 = next(r for r in csv.DictReader(open('dataset/sample_deletion_requests.csv', encoding='utf-8')) if r['case_id'] == 'case_18')
        req_20 = next(r for r in csv.DictReader(open('dataset/sample_deletion_requests.csv', encoding='utf-8')) if r['case_id'] == 'case_20')
        _, _, steps_18_str = self.agent.audit_case(req_18)
        _, _, steps_20_str = self.agent.audit_case(req_20)

        steps_18 = json.loads(steps_18_str)
        steps_20 = json.loads(steps_20_str)

        self.assertFalse(any(s.get('resource_id') == 'audit_record_6645' for s in steps_18),
                         "audit_record_6645 must never be fabricated for case_18.")
        self.assertFalse(any(s.get('resource_id') == 'audit_record_5569' for s in steps_20),
                         "audit_record_5569 must never be fabricated for case_20.")

if __name__ == '__main__':
    unittest.main()


