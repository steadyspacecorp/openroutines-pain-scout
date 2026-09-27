import json
import os
from unittest.mock import patch, MagicMock
import unittest
from urllib.error import HTTPError
from test_pipeline import scout
from reddit_source import RedditClient, collect_reddit


class RedditTests(unittest.TestCase):
    def config(self, **extra):
        return dict(enabled=True, subreddits=['selfhosted'], pages_per_subreddit=2, posts_per_page=25, **extra)

    def post(self, name='t3_abc', created=900, **extra):
        data = dict(name=name, created_utc=created, title='Missed backups', selftext='It stopped running', author='example')
        data.update(extra)
        return {'kind': 't3', 'data': data}

    def test_disabled_never_fetches(self):
        result = collect_reddit({'enabled': False}, set(), 100, lambda u: self.fail('unexpected request'))
        self.assertEqual(result['observations'], [])

    def test_missing_credentials_are_visible(self):
        with patch.dict(os.environ, {}, clear=True):
            result = collect_reddit(self.config(), set(), 100)
        self.assertTrue(result['coverage']['errors'])

    def test_pagination_seen_removed_and_cutoff(self):
        calls = []
        def fetch(url):
            calls.append(url)
            if len(calls) == 1:
                return {'data': {'children': [self.post(), self.post('t3_def', selftext='[removed]')], 'after': 't3_abc'}}
            return {'data': {'children': [self.post('t3_ghi'), self.post('t3_old', 50)], 'after': 't3_old'}}
        result = collect_reddit(self.config(), {'reddit:t3_abc'}, 100, fetch)
        self.assertEqual([p['id'] for p in result['observations']], ['reddit:t3_ghi'])
        self.assertIn('after=t3_abc', calls[1])
        self.assertEqual(result['coverage']['truncated_subreddits'], [])

    def test_title_only_post_and_page_limit(self):
        config = self.config()
        config['pages_per_subreddit'] = 1
        result = collect_reddit(config, set(), 100, lambda u: {'data': {'children': [self.post(selftext='')], 'after': 'more'}})
        self.assertEqual(result['observations'][0]['text'], 'Missed backups')
        self.assertEqual(result['coverage']['truncated_subreddits'], ['selfhosted'])

    def test_failure_preserves_other_community(self):
        config = self.config()
        config['subreddits'] = ['selfhosted', 'devops']
        def fetch(url):
            if '/selfhosted/' in url:
                raise HTTPError(url, 403, 'forbidden', {}, None)
            return {'data': {'children': [self.post()], 'after': None}}
        result = collect_reddit(config, set(), 100, fetch)
        self.assertEqual(len(result['observations']), 1)
        self.assertEqual(result['coverage']['errors'][0]['subreddit'], 'selfhosted')

    def test_invalid_name_rejected_before_request(self):
        config = self.config()
        config['subreddits'] = ['../api/me']
        with self.assertRaises(ValueError):
            collect_reddit(config, set(), 100, lambda u: self.fail('unexpected request'))

    def test_combined_budget_includes_both_sources(self):
        config = dict(queries=['backup'], lookback_hours=1, pages_per_query=1, max_items=2, reddit=self.config())
        hn = lambda u: {'hits': [{'objectID': str(i), 'comment_text': 'backup failure'} for i in range(1, 4)], 'nbPages': 1}
        reddit = lambda u: {'data': {'children': [self.post(created=9900)], 'after': None}}
        result = scout.collect(config, set(), hn, 10000, reddit)
        self.assertEqual([p['id'] for p in result['observations']], ['1', 'reddit:t3_abc'])
        self.assertEqual(result['coverage']['deferred_by_cap'], 2)

    @patch.dict(os.environ, {'REDDIT_CLIENT_ID': 'client', 'REDDIT_CLIENT_SECRET': 'secret'})
    def test_oauth_and_bearer_headers(self):
        token_response = MagicMock()
        token_response.__enter__.return_value.read.return_value = json.dumps({'access_token': 'access'}).encode()
        api_response = MagicMock()
        api_response.__enter__.return_value.read.return_value = b'{"data": {"children": []}}'
        api_response.__enter__.return_value.headers = {'X-Ratelimit-Remaining': '0'}
        with patch('reddit_source.urlopen', side_effect=[token_response, api_response]) as opener:
            client = RedditClient('script:pain-scout:v1 (by /u/test)')
            client.get('https://oauth.reddit.com/r/selfhosted/new')
            token_request = opener.call_args_list[0].args[0]
            self.assertEqual(token_request.data, b'grant_type=client_credentials')
            self.assertTrue(token_request.get_header('Authorization').startswith('Basic '))
            api_request = opener.call_args_list[1].args[0]
            self.assertEqual(api_request.get_header('Authorization'), 'Bearer access')
            with self.assertRaises(ValueError):
                client.get('https://oauth.reddit.com/r/devops/new')
            self.assertEqual(opener.call_count, 2)
