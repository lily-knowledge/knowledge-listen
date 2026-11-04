"""Daily Traditional Chinese RSS headlines for Knowledge Listen.
Only stores short feed-provided metadata and original links, never full articles.
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
SOURCES = {
    'invest': [
        ('中央社・產經證券', 'https://feeds.feedburner.com/rsscna/finance'),
    ],
    'health': [
        ('中央社・生活醫藥', 'https://feeds.feedburner.com/rsscna/lifehealth'),
    ],
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


def plain(value):
    value = re.sub(r'<[^>]*>', ' ', value or '')
    return re.sub(r'\s+', ' ', html.unescape(value)).strip()[:350]


def text(node, tag):
    child = node.find(tag)
    return ''.join(child.itertext()).strip() if child is not None else ''


def fetch_xml(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; KnowledgeListenRSS/2.0)',
        'Accept': 'application/rss+xml, application/atom+xml, application/xml, text/xml, */*',
    })
    with urllib.request.urlopen(req, timeout=20) as response:
        return ET.fromstring(response.read(2_000_000))


def parse_feed(root, source):
    results = []
    now = dt.datetime.now(dt.timezone.utc)
    items = root.findall('.//channel/item')
    if not items:
        items = root.findall('.//{http://www.w3.org/2005/Atom}entry')
    for item in items:
        title = plain(text(item, 'title') or text(item, '{http://www.w3.org/2005/Atom}title'))
        link = text(item, 'link')
        if not link:
            for elem in item.findall('{http://www.w3.org/2005/Atom}link'):
                if elem.attrib.get('rel', 'alternate') == 'alternate':
                    link = elem.attrib.get('href', '')
                    break
        published = (text(item, 'pubDate') or text(item, 'published') or
                     text(item, '{http://www.w3.org/2005/Atom}published') or
                     text(item, '{http://www.w3.org/2005/Atom}updated'))
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
        summary = plain(text(item, 'description') or text(item, 'summary') or
                        text(item, '{http://www.w3.org/2005/Atom}summary'))
        if summary == title or len(summary) < 25:
            summary = '請點選原文連結閱讀完整報導。'
        results.append({
            'title': title,
            'summary': summary,
            'url': link,
            'published': when.date().isoformat(),
            'source': source,
            '_time': when.timestamp(),
        })
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
