"""Publish a Traditional Chinese listening episode every two Taipei days."""
import datetime as dt
import json
import os
import urllib.request
from pathlib import Path

DEST = Path(__file__).resolve().parents[1] / 'episodes.json'
FIRST_DAY = dt.date(2026, 11, 15)
TOPICS = ('生活科學', '學習與記憶', '數位生活', '理財基本觀念', '自然觀察', '生活中的統計')


def generate(api_key, topic, previous_titles):
    payload = {
        'model': 'gpt-5.6-terra',
        'reasoning': {'effort': 'none'},
        'max_output_tokens': 7800,
        'store': False,
        'instructions': (
            '為台灣聽眾寫繁體中文精華說書原創稿。以指定領域選一個明確題目，避開既有標題及主題。'
            '用沉穩自然的口語寫六至八章，正文約三千五百至四千八百個中文字，供約十五至三十分鐘朗讀。'
            '用不同生活例子逐步解釋，不重複句子。使用一般常識，避免即時消息、具體投資建議和醫療指示，'
            '不要假稱改編某本書，也不要引用未查證的數字或來源。首行只寫標題，其餘為正文，以空行分段，'
            '不加 Markdown、前言標籤或字數註記。'
        ),
        'input': json.dumps({'主題領域': topic, '已發布標題': previous_titles}, ensure_ascii=False),
    }
    request = urllib.request.Request(
        'https://api.openai.com/v1/responses',
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(request, timeout=150) as response:
        result = json.load(response)
    if result.get('status') != 'completed':
        raise RuntimeError('Episode generation did not complete')
    draft = '\n'.join(
        part['text']
        for item in result.get('output', []) if item.get('type') == 'message'
        for part in item.get('content', []) if part.get('type') == 'output_text'
    ).strip()
    title, _, body = draft.partition('\n')
    title, body = title.strip(), body.strip()
    if not 3 <= len(title) <= 70 or title in previous_titles or len(body) < 3000:
        raise RuntimeError('Episode draft did not pass title and length checks')
    return title, body


def publish(today):
    days = (today - FIRST_DAY).days
    if days < 0:
        return

    slot = FIRST_DAY + dt.timedelta(days=days - days % 2)
    episodes = json.loads(DEST.read_text(encoding='utf-8'))
    if any(episode.get('slot') == slot.isoformat() for episode in episodes):
        return

    previous_titles = [episode['title'] for episode in episodes]
    previous_titles.append('黃金存摺、黃金 ETF、金條，差在哪？')
    title, body = generate(os.environ['OPENAI_API_KEY'], TOPICS[(days // 2) % len(TOPICS)], previous_titles)
    episode = {
        'title': title,
        'source': f'第 {len(episodes) + 2} 集・精華說書',
        'date': today.isoformat(),
        'slot': slot.isoformat(),
        'content': body,
    }
    draft = DEST.with_suffix('.tmp')
    draft.write_text(json.dumps([episode, *episodes], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    draft.replace(DEST)


if __name__ == '__main__':
    publish(dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date())
