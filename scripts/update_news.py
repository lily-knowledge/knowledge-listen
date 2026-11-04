"""Fetch public RSS metadata, preserving prior data if all feeds fail."""
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
QUERIES = {
    'invest': '台股 OR 美股 OR ETF 投資 理財',
    'health': '健康 醫療 疾病預防 衛教',
    'knowledge': '科學 科技 生活知識 研究',
}
LIMIT = 8

def plain(value):
    value = re.sub(r'<[^>]*>', ' ', value or '')
    return re.sub(r'\s+', ' ', html.unescape(value)).strip()[:350]

def get_text(item, name):
    node = item.find(name)
    return (node.text or '').strip() if node is not None else ''

def fetch(query):
    params = urllib.parse.urlencode({'q': query, 'hl': 'zh-TW', 'gl': 'TW', 'ceid': 'TW:zh-Hant'})
    url = 'https://news.google.com/rss/search?' + params
    req = urllib.request.Request(url, headers={'User-Agent': 'KnowledgeListenRSS/1.0'})
    with urllib.request.urlopen(req, timeout=25) as response:
        data = response.read(2_000_000)
    root = ET.fromstring(data)
    results = []
    seen = set()
    for item in root.findall('.//channel/item'):
        title = plain(get_text(item, 'title'))
        link = get_text(item, 'link')
        summary = plain(get_text(item, 'description'))
        published = get_text(item, 'pubDate')
        try:
            when = email.utils.parsedate_to_datetime(published)
            if when < dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7):
                continue
        except (ValueError, TypeError, OverflowError):
            continue
        parsed = urllib.parse.urlparse(link)
        if not title or parsed.scheme != 'https' or parsed.netloc != 'news.google.com' or title in seen:
            continue
        seen.add(title)
        # RSS descriptions sometimes repeat the headline or contain link lists.
        if summary == title or len(summary) < 25:
            summary = '新聞標題摘要，請點選原文連結閱讀完整內容。'
        results.append({'title': title, 'summary': summary, 'url': link, 'published': when.date().isoformat()})
        if len(results) >= LIMIT:
            break
    return results

def main():
    previous = {}
    if DEST.exists():
        try:
            previous = json.loads(DEST.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            pass
    sections = {}
    any_success = False
    for key, query in QUERIES.items():
        try:
            fresh = fetch(query)
            if not fresh:
                raise ValueError('No recent entries')
            sections[key] = fresh
            any_success = True
            print(key, len(fresh), 'items')
        except Exception as exc:
            print('Feed unavailable:', key, str(exc))
            sections[key] = previous.get('sections', {}).get(key, [])
    if not any_success:
        print('All sources unavailable; keep existing articles.json unchanged')
        return
    result = {
        'updated_at': dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime('%Y-%m-%d %H:%M 台灣時間'),
        'sections': sections,
    }
    DEST.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

if __name__ == '__main__':
    main()
