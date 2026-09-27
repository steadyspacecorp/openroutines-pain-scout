import base64
from datetime import datetime, timezone
import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class RedditClient:
    def __init__(self, user_agent):
        self.user_agent = user_agent
        self.token = None
        self.exhausted = False

    def get(self, url):
        if self.exhausted:
            raise ValueError('Reddit rate limit reached; retry next scan')
        if self.token is None:
            pair = os.environ['REDDIT_CLIENT_ID'] + ':' + os.environ['REDDIT_CLIENT_SECRET']
            req = Request('https://www.reddit.com/api/v1/access_token',
                          data=urlencode({'grant_type': 'client_credentials'}).encode(),
                          headers={'Authorization': 'Basic ' + base64.b64encode(pair.encode()).decode(),
                                   'User-Agent': self.user_agent,
                                   'Content-Type': 'application/x-www-form-urlencoded'})
            with urlopen(req, timeout=30) as response:
                self.token = json.load(response)['access_token']
            if not isinstance(self.token, str) or not self.token:
                raise ValueError('Missing Reddit access token')
        req = Request(url, headers={'Authorization': 'Bearer ' + self.token,
                                    'User-Agent': self.user_agent})
        try:
            with urlopen(req, timeout=30) as response:
                remaining = response.headers.get('X-Ratelimit-Remaining')
                if remaining is not None and float(remaining) < 1:
                    self.exhausted = True
                return json.load(response)
        except HTTPError as error:
            if error.code == 429:
                self.exhausted = True
            raise


def collect_reddit(config, seen, cutoff, fetch=None):
    coverage = {'enabled': config.get('enabled', False), 'subreddits': [],
                'errors': [], 'truncated_subreddits': [], 'unique_unseen': 0}
    if not coverage['enabled']:
        return {'observations': [], 'coverage': coverage}
    names = config.get('subreddits', [])
    if not isinstance(names, list) or any(not isinstance(n, str) or not re.fullmatch(r'[A-Za-z0-9_]{2,21}', n) for n in names):
        raise ValueError('Use bare subreddit names, such as selfhosted')
    names = list(dict.fromkeys(n.lower() for n in names))
    pages = config.get('pages_per_subreddit', 1)
    limit = config.get('posts_per_page', 25)
    if type(pages) is not int or not 1 <= pages <= 10 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Reddit pages must be 1-10; posts per page must be 1-100')
    if len(names) > 20:
        raise ValueError('Configure at most 20 subreddits per scout')
    coverage['subreddits'] = names
    user_agent = config.get('user_agent', '')
    if fetch is None:
        if not user_agent or 'YOUR_USERNAME' in user_agent or not all(os.environ.get(k) for k in ('REDDIT_CLIENT_ID', 'REDDIT_CLIENT_SECRET')):
            coverage['errors'].append({'error': 'Reddit credentials or identifying user_agent are not configured'})
            return {'observations': [], 'coverage': coverage}
        client = RedditClient(user_agent)
        fetch = client.get
    observations = {}
    for name in names:
        after = None
        for page in range(pages):
            params = {'limit': limit, 'raw_json': 1}
            if after:
                params['after'] = after
            try:
                data = fetch('https://oauth.reddit.com/r/' + name + '/new?' + urlencode(params))['data']
                reached_cutoff = False
                for child in data['children']:
                    if child.get('kind') != 't3':
                        continue
                    post = child['data']
                    created = float(post['created_utc'])
                    if created < cutoff:
                        if not post.get('stickied'):
                            reached_cutoff = True
                        continue
                    ident = post['name']
                    if not re.fullmatch(r't3_[a-z0-9]+', ident):
                        continue
                    ident = 'reddit:' + ident
                    body = post.get('selftext') or ''
                    title = post.get('title') or ''
                    if ident in seen or body in ('[removed]', '[deleted]') or post.get('removed_by_category') or post.get('author') in (None, '[deleted]'):
                        continue
                    observations[ident] = {'id': ident, 'source': 'reddit', 'subreddit': name,
                        'url': 'https://www.reddit.com/comments/' + post['name'][3:] + '/',
                        'title': title, 'text': (title + '\n\n' + body).strip()[:12000],
                        'author': post['author'], 'created_at': datetime.fromtimestamp(created, timezone.utc).isoformat()}
                after = data.get('after')
                if reached_cutoff or not after:
                    break
                if page + 1 == pages:
                    coverage['truncated_subreddits'].append(name)
            except (HTTPError, URLError, TimeoutError, KeyError, ValueError, TypeError):
                coverage['errors'].append({'subreddit': name, 'page': page, 'error': 'Reddit collection failed; check access or rate limits'})
                break
    coverage['unique_unseen'] = len(observations)
    return {'observations': list(observations.values()), 'coverage': coverage}
