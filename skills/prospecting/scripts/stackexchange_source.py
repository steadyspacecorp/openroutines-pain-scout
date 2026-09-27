from datetime import datetime, timezone
import gzip
import html
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = 'https://api.stackexchange.com/2.3/search/advanced?'


def request(url):
    req = Request(url, headers={'User-Agent': 'OpenRoutines-Pain-Scout', 'Accept-Encoding': 'gzip'})
    with urlopen(req, timeout=30) as response:
        raw = response.read()
    # The Stack Exchange API compresses every response, whatever the request asks for.
    return json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)


def collect_stackexchange(config, seen, cutoff, fetch=None):
    coverage = {'enabled': config.get('enabled', False), 'sites': [], 'queries': 0,
                'errors': [], 'truncated_searches': [], 'unique_unseen': 0, 'quota_remaining': None}
    if not coverage['enabled']:
        return {'observations': [], 'coverage': coverage}
    sites, queries = config.get('sites', []), config.get('queries', [])
    if not isinstance(sites, list) or not 1 <= len(sites) <= 10 or any(
            not isinstance(s, str) or not re.fullmatch(r'[a-z0-9.]{2,40}', s) for s in sites):
        raise ValueError('Use 1-10 Stack Exchange site names, such as serverfault')
    if not isinstance(queries, list) or not 1 <= len(queries) <= 20 or any(
            not isinstance(q, str) or not q.strip() for q in queries):
        raise ValueError('Use 1-20 nonempty Stack Exchange queries')
    pages, size = config.get('pages_per_query', 1), config.get('page_size', 50)
    if type(pages) is not int or not 1 <= pages <= 5 or type(size) is not int or not 1 <= size <= 100:
        raise ValueError('Stack Exchange pages must be 1-5; page size must be 1-100')
    sites = list(dict.fromkeys(sites))
    coverage.update(sites=sites, queries=len(queries))
    fetch = fetch or request
    key = os.environ.get('STACKEXCHANGE_KEY', '')
    observations, stopped = {}, False
    for site in sites:
        for query in queries:
            for page in range(1, pages + 1):
                if stopped:
                    break
                params = {'order': 'desc', 'sort': 'creation', 'q': query, 'site': site,
                          'fromdate': int(cutoff), 'pagesize': size, 'page': page, 'filter': 'withbody'}
                if key:
                    params['key'] = key
                try:
                    data = fetch(API + urlencode(params))
                    for item in data['items']:
                        ident = 'stackexchange:' + site + ':' + str(int(item['question_id']))
                        url = item.get('link') or ''
                        if ident in seen or not url.startswith('https://'):
                            continue
                        title = html.unescape(item.get('title') or '')
                        body = html.unescape(re.sub(r'<[^>]+>', ' ', item.get('body') or '')).strip()
                        observations[ident] = {'id': ident, 'source': 'stackexchange', 'site': site, 'url': url,
                            'title': title, 'text': (title + '\n\n' + body).strip()[:12000],
                            'author': (item.get('owner') or {}).get('display_name'), 'query': query,
                            'created_at': datetime.fromtimestamp(item['creation_date'], timezone.utc).isoformat()}
                    coverage['quota_remaining'] = data.get('quota_remaining')
                    # Stop for this scan when the API asks for a backoff or the daily quota runs out.
                    if data.get('backoff') or data.get('quota_remaining', 1) < 1:
                        coverage['errors'].append({'site': site, 'error': 'Stack Exchange asked the scout to back off; retry next scan'})
                        stopped = True
                        break
                    if not data.get('has_more'):
                        break
                    if page == pages:
                        coverage['truncated_searches'].append(site + ': ' + query)
                except (HTTPError, URLError, TimeoutError, KeyError, ValueError, TypeError, OSError):
                    coverage['errors'].append({'site': site, 'query': query, 'page': page,
                                               'error': 'Stack Exchange collection failed'})
                    break
    coverage['unique_unseen'] = len(observations)
    return {'observations': list(observations.values()), 'coverage': coverage}
