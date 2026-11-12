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



EDITORIAL = {
    'https://www.cna.com.tw/news/ahel/202611110304.aspx': (
        '慢性阻塞性肺病會讓氣流受限。氣道發炎和痰液增加會妨礙呼吸，肺泡受損也會讓肺失去一部分彈性。'
        '因此，有些人最先注意到的是走路或爬樓梯比以前容易喘，也有人長期咳嗽、咳痰。\n\n'
        '吸菸是重要的致病因素。長期接觸二手菸、空氣污染或工作場所的粉塵，也會增加風險。'
        '已經有肺阻塞的人，呼吸道感染或空氣污染可能讓症狀突然加重。'
        '如果原本只是活動時喘，後來同樣的活動明顯更喘，或咳嗽和痰量比平時增加，就值得就醫評估。\n\n'
        '醫師會結合暴露史、症狀和肺功能檢查。肺量計會測量用力吹氣的速度與總量，'
        '幫助判斷氣流是否持續受限。治療可依個人情況包括戒菸、吸入藥物及肺部復健。',
        'https://www.who.int/en/news-room/fact-sheets/detail/chronic-obstructive-pulmonary-disease-%28copd%29',
    ),
    'https://news.pts.org.tw/article/835315': (
        '海葵白化時，體內的共生藻因環境壓力而流失，海葵的顏色也跟著變淡。'
        '小丑魚平常把海葵當作避難所，研究人員因此想知道，海葵白化會不會改變魚群的行為。\n\n'
        '研究團隊分析巴布亞紐幾內亞金貝灣在二〇二三年海洋熱浪期間的水下影片。'
        '他們分別觀察水溫升高和海葵白化時魚群的表現。'
        '這次觀察中，單看水溫上升，小丑魚的行為變化較小。'
        '海葵白化後，小丑魚更積極防守棲身的海葵，群內成員之間的攻擊也增加。\n\n'
        '同一個魚群可以同時出現兩種反應：更努力守住共同的住處，成員之間卻更常互相攻擊。'
        '這是研究團隊在特定地點和熱浪期間看到的現象。'
        '要知道其他海域的小丑魚是否也會這樣，還需要其他地點的觀察。',
        'https://www.ncl.ac.uk/press/articles/latest/2026/11/clownfishanemonebleaching/',
    ),
}


def apply_editorial(article):
    article.pop('explanation', None)
    article.pop('explanation_url', None)
    entry = EDITORIAL.get(article.get('url'))
    if entry:
        article['explanation'], article['explanation_url'] = entry


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
            apply_editorial(item)
            chosen.append(item)
            if len(chosen) >= LIMIT:
                break
        if chosen:
            sections[key] = chosen
            updated = True
        else:
            sections[key] = previous.get('sections', {}).get(key, [])
            for item in sections[key]:
                apply_editorial(item)
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
