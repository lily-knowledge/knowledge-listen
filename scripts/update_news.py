"""Daily Traditional Chinese RSS news for Knowledge Listen.

Stores feed-provided summaries and full text only when a feed explicitly
provides a distinct, substantial full-text field. Never scrapes article pages.
"""
import datetime as dt
import email.utils
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'articles.json'
LIMIT = 16
MAX_AGE_DAYS = 7
MAX_FULL_CHARS = 30000
CONTENT_NS = '{http://purl.org/rss/1.0/modules/content/}encoded'
ATOM_NS = '{http://www.w3.org/2005/Atom}'
SOURCES = {
    'invest': [('中央社・產經證券', 'https://feeds.feedburner.com/rsscna/finance')],
    'health': [('中央社・生活醫藥', 'https://feeds.feedburner.com/rsscna/lifehealth')],
    'knowledge': [
        ('中央社・科技', 'https://feeds.feedburner.com/rsscna/technology'),
        ('中央社・文化', 'https://feeds.feedburner.com/rsscna/culture'),
        ('公視新聞', 'https://news.pts.org.tw/xml/newsfeed.xml'),
    ],
}
QUERIES = {
    'invest': '台股 OR 美股 OR ETF 投資 理財',
    'health': '健康 醫療 疾病預防 衛教',
    'knowledge': '科學 科技 生活知識 研究',
}


def plain(value, limit=None):
    value = re.sub(r'(?is)<(script|style)\b[^>]*>.*?</\1>', ' ', value or '')
    value = re.sub(r'(?i)<\s*br\s*/?\s*>|</\s*(?:p|div|li|h[1-6])\s*>', '\n', value)
    value = re.sub(r'<[^>]*>', ' ', value)
    value = html.unescape(value)
    value = re.sub(r'[ \t\r\f\v]+', ' ', value)
    value = re.sub(r'\n\s*\n+', '\n\n', value).strip()
    return value[:limit] if limit else value


def text(node, tag):
    child = node.find(tag)
    return ''.join(child.itertext()).strip() if child is not None else ''


def fetch_xml(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; KnowledgeListenRSS/2.1)',
        'Accept': 'application/rss+xml, application/atom+xml, application/xml, text/xml, */*',
    })
    with urllib.request.urlopen(req, timeout=20) as response:
        return ET.fromstring(response.read(2_000_000))


def parse_feed(root, source):
    results = []
    now = dt.datetime.now(dt.timezone.utc)
    items = root.findall('.//channel/item')
    if not items:
        items = root.findall('.//' + ATOM_NS + 'entry')
    for item in items:
        title = plain(text(item, 'title') or text(item, ATOM_NS + 'title'), 350)
        link = text(item, 'link')
        if not link:
            for elem in item.findall(ATOM_NS + 'link'):
                if elem.attrib.get('rel', 'alternate') == 'alternate':
                    link = elem.attrib.get('href', '')
                    break
        published = (text(item, 'pubDate') or text(item, 'published') or
                     text(item, ATOM_NS + 'published') or text(item, ATOM_NS + 'updated'))
        try:
            when = email.utils.parsedate_to_datetime(published)
        except (ValueError, TypeError, IndexError):
            try:
                when = dt.datetime.fromisoformat(published.replace('Z', '+00:00'))
            except ValueError:
                continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=dt.timezone.utc)
        if when < now - dt.timedelta(days=MAX_AGE_DAYS) or when > now + dt.timedelta(days=1):
            continue
        parsed = urllib.parse.urlparse(link)
        if not title or parsed.scheme not in ('http', 'https') or not parsed.netloc:
            continue
        raw_summary = (text(item, 'description') or text(item, 'summary') or
                       text(item, ATOM_NS + 'summary'))
        summary = plain(raw_summary, 350)
        if summary == title or len(summary) < 25:
            summary = '請點選原文連結閱讀完整報導。'
        # Only explicit full-text fields, not RSS descriptions or snippets.
        full = plain(text(item, CONTENT_NS) or text(item, ATOM_NS + 'content'), MAX_FULL_CHARS)
        # Avoid mistaking short feed excerpts for full articles.
        if len(full) < 500 or full == summary or full == title:
            full = ''
        article = {
            'title': title,
            'summary': summary,
            'url': link,
            'published': when.date().isoformat(),
            'source': source,
            '_time': when.timestamp(),
        }
        if full:
            article['content'] = full
        results.append(article)
    return results


def google_fallback(key):
    params = urllib.parse.urlencode({
        'q': QUERIES[key], 'hl': 'zh-TW', 'gl': 'TW', 'ceid': 'TW:zh-Hant'
    })
    return parse_feed(fetch_xml('https://news.google.com/rss/search?' + params), 'Google 新聞')


def main():
    previous = {}
    if DEST.exists():
        try:
            previous = json.loads(DEST.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            pass
    sections = {}
    updated = False
    for key, feeds in SOURCES.items():
        candidates = []
        for source, url in feeds:
            try:
                items = parse_feed(fetch_xml(url), source)
                candidates.extend(items)
                print(key, source, len(items), 'items')
            except Exception as exc:
                print('Feed unavailable:', source, str(exc))
        try:
            candidates.extend(google_fallback(key))
        except Exception as exc:
            print('Google news unavailable:', key, str(exc))
        candidates.sort(key=lambda x: x['_time'], reverse=True)
        seen = set()
        chosen = []
        for item in candidates:
            identity = re.sub(r'\W+', '', item['title'].lower())[:100]
            if identity in seen:
                continue
            seen.add(identity)
            item.pop('_time', None)
            chosen.append(item)
            if len(chosen) >= LIMIT:
                break
        if chosen:
            sections[key] = chosen
            updated = True
        else:
            sections[key] = previous.get('sections', {}).get(key, [])
        print(key, len(sections[key]), 'final items')
    if not updated:
        print('No feeds available; preserving previous articles.json')
        return
    result = {
        'updated_at': dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime('%Y-%m-%d %H:%M 台灣時間'),
        'sections': sections,
    }
    DEST.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Saved', DEST)


if __name__ == '__main__':
    main()
