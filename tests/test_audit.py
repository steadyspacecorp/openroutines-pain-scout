import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_pipeline import scout


class AuditTests(unittest.TestCase):
    @patch.dict(os.environ, {'OPENROUTER_API_KEY': 'not-in-audit', 'OPENROUTINES_RUN_ID': 'run-test'})
    def audit(self):
        observation = {'id': 'stackexchange:serverfault:123', 'title': 'Backup | issue', 'text': 'My backup stopped.', 'url': 'https://serverfault.com/questions/123/'}
        self.sent = []
        def fetch(url, payload, token):
            self.sent.append(copy.deepcopy(payload))
            return {'model': 'jev-test-version', 'answers': {k: {'type': 'noul', 'noul': v} for k,v in
                    dict(firsthand=0.9, fit=0.75, excluded=0.1, seeking=0.8).items()}, 'usage': {'input_tokens': 123}}
        return scout.screen({'observations': [observation], 'coverage': {'count': 1}}, 'Original brief', 0.8, fetch)

    def test_exact_request_reconstructs_and_no_credential_is_stored(self):
        audit = self.audit()
        self.assertEqual(scout.payload(audit['request_context'], audit['results'][0]['observation']), self.sent[0])
        self.assertNotIn('not-in-audit', json.dumps(audit))
        self.assertEqual(audit['results'][0]['model'], 'jev-test-version')
        self.assertEqual(audit['results'][0]['reasons'], ['fit 0.750 < 0.800'])

    def test_threshold_review_is_offline_and_does_not_mutate(self):
        audit = self.audit()
        before = copy.deepcopy(audit)
        with patch.object(scout, 'request', side_effect=AssertionError('no network')):
            text = scout.review(audit, 0.7)
        self.assertIn('| drop | investigate |', text)
        self.assertIn('&#124;', text)
        self.assertEqual(audit, before)

    def test_ledger_roundtrip_preserves_other_state_and_is_idempotent(self):
        audit = self.audit()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'scan.md'
            path.write_text('# Scan ledger\nSeen IDs: abc\n')
            scout.append_audit(path, audit)
            first = path.read_text()
            scout.append_audit(path, audit)
            self.assertEqual(path.read_text(), first)
            self.assertIn('Seen IDs: abc', first)
            self.assertEqual(scout.read_audits(path), [audit])

    def test_usage_total_sums_reported_cost(self):
        answers = {k: {'type': 'noul', 'noul': 0.1} for k in ('firsthand', 'fit', 'excluded', 'seeking')}
        responses = iter([{'answers': answers, 'model': 'jev', 'usage': {'cost': 0.00005}},
                          {'answers': answers, 'model': 'jev', 'usage': {'cost': 0.00007}},
                          {'answers': {}}])
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test'}):
            audit = scout.screen({'observations': [{'id': 'a'}, {'id': 'b'}, {'id': 'c'}], 'coverage': {}},
                                 'brief', 0.8, lambda *args: next(responses))
        self.assertEqual(audit['usage_total'], {'calls': 3, 'answered': 2, 'cost_usd': 0.00012})
        self.assertIn('Jev calls: 3. Reported cost: $0.0001.', scout.review(audit))

    def test_question_edits_reach_request(self):
        prompts = dict(scout.QUESTIONS, fit='Does the post describe a missing completion signal?')
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test'}):
            def fetch(url, payload, token):
                self.assertTrue(payload['questions']['fit']['instructions'].startswith(prompts['fit']))
                return {'answers': {}}
            audit = scout.screen({'observations': [{'id': 'a'}], 'coverage': {}}, 'brief', 0.8, fetch, prompts)
        self.assertEqual(audit['results'][0]['route'], 'retry')
        self.assertIn('response', audit['results'][0])
        self.assertIn('| retry | retry |', scout.review(audit, 0.1))

    def test_question_schema_rejects_missing_dimensions(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'questions.json'
            path.write_text(json.dumps({'fit': 'Is it a match?'}))
            with self.assertRaises(ValueError):
                scout.load_questions(path)
