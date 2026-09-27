import gzip
import json
import os
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from test_pipeline import scout
from stackexchange_source import collect_stackexchange, request


class StackExchangeTests(unittest.TestCase):
    def config(self, **extra):
        return dict(enabled=True, sites=['serverfault'], queries=['cron'], pages_per_query=2, page_size=50, **extra)

    def question(self, ident=1, **extra):
        data = dict(question_id=ident, title='Cron job &amp; backups', body='<p>My backup <b>stopped</b></p>',
                    link='https://serverfault.com/questions/%d/x' % ident, creation_date=900,
                    owner={'display_name': 'example'})
        data.update(extra)
        return data

    def test_disabled_never_fetches(self):
        result = collect_stackexchange({'enabled': False}, set(), 100, lambda u: self.fail('unexpected request'))
        self.assertEqual(result['observations'], [])

    def test_parses_questions_skips_seen_and_follows_pages(self):
        calls = []
        def fetch(url):
            calls.append(parse_qs(urlparse(url).query))
            if len(calls) == 1:
                return {'items': [self.question(1), self.question(2)], 'has_more': True, 'quota_remaining': 290}
            return {'items': [self.question(3)], 'has_more': False, 'quota_remaining': 289}
        result = collect_stackexchange(self.config(), {'stackexchange:serverfault:1'}, 100, fetch)
        self.assertEqual([o['id'] for o in result['observations']],
                         ['stackexchange:serverfault:2', 'stackexchange:serverfault:3'])
        first = result['observations'][0]
        self.assertEqual(first['text'], 'Cron job & backups\n\nMy backup  stopped')
        self.assertEqual(first['author'], 'example')
        self.assertEqual(calls[0]['fromdate'], ['100'])
        self.assertEqual(calls[1]['page'], ['2'])
        self.assertEqual(result['coverage']['quota_remaining'], 289)
        self.assertEqual(result['coverage']['truncated_searches'], [])

    def test_page_limit_is_reported(self):
        config = self.config()
        config['pages_per_query'] = 1
        result = collect_stackexchange(config, set(), 100, lambda u: {'items': [self.question()], 'has_more': True})
        self.assertEqual(result['coverage']['truncated_searches'], ['serverfault: cron'])

    def test_backoff_stops_the_scan(self):
        config = self.config()
        config['sites'] = ['serverfault', 'devops']
        calls = []
        def fetch(url):
            calls.append(url)
            return {'items': [self.question()], 'has_more': True, 'backoff': 10}
        result = collect_stackexchange(config, set(), 100, fetch)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(result['observations']), 1)
        self.assertIn('back off', result['coverage']['errors'][0]['error'])

    def test_failure_preserves_other_site(self):
        config = self.config()
        config['sites'] = ['serverfault', 'devops']
        def fetch(url):
            if 'site=serverfault' in url:
                raise HTTPError(url, 400, 'bad request', {}, None)
            return {'items': [self.question(link='https://devops.stackexchange.com/questions/1/x')], 'has_more': False}
        result = collect_stackexchange(config, set(), 100, fetch)
        self.assertEqual([o['id'] for o in result['observations']], ['stackexchange:devops:1'])
        self.assertEqual(result['coverage']['errors'][0]['site'], 'serverfault')

    def test_invalid_site_rejected_before_request(self):
        config = self.config()
        config['sites'] = ['../users']
        with self.assertRaises(ValueError):
            collect_stackexchange(config, set(), 100, lambda u: self.fail('unexpected request'))

    @patch.dict(os.environ, {'STACKEXCHANGE_KEY': 'public-key'})
    def test_key_is_sent_when_configured(self):
        urls = []
        collect_stackexchange(self.config(), set(), 100, lambda u: urls.append(u) or {'items': [], 'has_more': False})
        self.assertEqual(parse_qs(urlparse(urls[0]).query)['key'], ['public-key'])

    def test_request_decompresses_gzip(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = gzip.compress(json.dumps({'items': []}).encode())
        with patch('stackexchange_source.urlopen', return_value=response):
            self.assertEqual(request('https://api.stackexchange.com/2.3/search/advanced?q=cron'), {'items': []})

    def test_combined_budget_includes_all_sources(self):
        config = dict(queries=['backup'], lookback_hours=1, pages_per_query=1, max_items=3,
                      stackexchange=self.config())
        hn = lambda u: {'hits': [{'objectID': str(i), 'comment_text': 'backup failure'} for i in range(1, 4)], 'nbPages': 1}
        se = lambda u: {'items': [self.question(7, creation_date=9900)], 'has_more': False}
        result = scout.collect(config, set(), hn, 10000, se)
        self.assertEqual([o['id'] for o in result['observations']], ['1', 'stackexchange:serverfault:7', '2'])
        self.assertEqual(result['coverage']['sources']['stackexchange']['unique_unseen'], 1)
        self.assertEqual(result['coverage']['deferred_by_cap'], 1)
