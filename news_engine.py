# -*- coding: utf-8 -*-
"""
NEWS ENGINE v3 — NewsAPI + Claude rewrite.

Цепочка: NewsAPI (реальные тексты) → Claude (переписывает на uz/ru) → Telegram
Никакого копирования заголовков. Никакого английского в итоговом посте.
"""

import os
import re
import json
import hashlib
import requests
from datetime import datetime, timedelta


# ============================================
# API КЛЮЧИ
# ============================================

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "543701ebe5ea4056980521c43527cbb3")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")


# ============================================
# NEWSAPI — ПОЛУЧЕНИЕ РЕАЛЬНЫХ НОВОСТЕЙ
# ============================================

NEWSAPI_QUERIES = [
    "Uzbekistan national football team",
    "Uzbekistan World Cup 2026",
    "Shomurodov OR Xusanov OR Masharipov",
    "FIFA World Cup 2026 Group K",
    "World Cup 2026 Portugal Colombia Congo",
    "Portugal World Cup 2026",
    "Colombia World Cup 2026",
]


def fetch_newsapi(query, page_size=5):
    """Запрос к NewsAPI.org"""
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "apiKey": NEWSAPI_KEY,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": page_size,
        "from": (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d"),
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            print(f"NewsAPI {resp.status_code}: {resp.text[:100]}")
            return []
        data = resp.json()
        articles = []
        for item in data.get("articles", []):
            title = (item.get("title") or "").strip()
            if title in ("[Removed]", "", "None"):
                continue
            content = item.get("content") or item.get("description") or ""
            content = re.sub(r"\[\+\d+ chars\]", "", content).strip()
            articles.append({
                "title": title,
                "content": content,
                "description": (item.get("description") or "").strip(),
                "url": item.get("url", ""),
                "source": item.get("source", {}).get("name", "Unknown"),
                "published_at": item.get("publishedAt", ""),
            })
        return articles
    except Exception as e:
        print(f"NewsAPI error [{query[:40]}]: {e}")
        return []


def fetch_all_news():
    """Загружает новости из всех запросов, убирает дубликаты по URL"""
    all_articles = []
    seen_urls = set()
    for priority, query in enumerate(NEWSAPI_QUERIES, 1):
        for a in fetch_newsapi(query):
            if a["url"] not in seen_urls and a["url"]:
                seen_urls.add(a["url"])
                a["priority"] = priority
                all_articles.append(a)
    all_articles.sort(key=lambda x: x["priority"])
    return all_articles


# ============================================
# CLAUDE — ПЕРЕПИСЫВАЕТ НОВОСТЬ КАК TELEGRAM-ПОСТ
# ============================================

def rewrite_with_claude(article, lang="uz"):
    """
    Claude переписывает новость как спортивный Telegram-пост.
    Результат всегда на uz или ru — никакого английского.
    """
    if not CLAUDE_API_KEY:
        return None

    source_text = (
        f"Title: {article['title']}\n"
        f"Description: {article.get('description', '')}\n"
        f"Content: {article.get('content', '')}\n"
        f"Source: {article['source']}"
    )

    if lang == "uz":
        prompt = f"""Siz tajribali sport Telegram-muharriri siz. Quyidagi yangilikdan qisqa, ta'sirchan o'zbek tilida post yozing.

QATTIQ TALABLAR:
1. FAQAT O'ZBEK TILI — birorta inglizcha so'z bo'lmasin
2. Hajm: 150-300 belgi (2-4 qisqa abzas)
3. Format: [emoji] Sarlavha\n\nAbzas 1.\n\nAbzas 2.
4. Sarlavha: qisqa, jonli, 5-8 so'z
5. Haqiqiy faktlar va raqamlarni saqlang
6. Suvni, takrorlarni, quruq iboralarni olib tashlang
7. Hech qanday havola, sayt nomi, URL yozmang
8. "AI", "neyroset", "tarjima" so'zlarini yozmang
9. Erkin, jonli o'zbek tilida yozing — mashina tarjimasidan saqlanin

YANGILIK MATNI:
{source_text}

Faqat post matni. Boshqa hech narsa."""
    else:
        prompt = f"""Ты опытный редактор спортивного Telegram-канала. Напиши короткий живой пост на русском по этой новости.

ЖЁСТКИЕ ТРЕБОВАНИЯ:
1. ТОЛЬКО РУССКИЙ ЯЗЫК — ни слова по-английски
2. Объём: 150-300 символов (2-4 коротких абзаца)
3. Формат: [emoji] Заголовок\n\nАбзац 1.\n\nАбзац 2.
4. Заголовок: короткий, живой, 4-7 слов
5. Сохраняй реальные факты и цифры
6. Убирай воду, повторения, пустые фразы
7. Никаких ссылок, URL, названий сайтов
8. Не писать "ИИ", "нейросеть", "перевод"
9. Пиши как спортивный журналист, не переводчик

ТЕКСТ НОВОСТИ:
{source_text}

Только текст поста. Ничего лишнего."""

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": CLAUDE_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5",
                "max_tokens": 700,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=20,
        )
        if resp.status_code == 200:
            return resp.json()["content"][0]["text"].strip()
        print(f"Claude error {resp.status_code}: {resp.text[:150]}")
        return None
    except Exception as e:
        print(f"Claude request error: {e}")
        return None


def format_news_post(article, lang="uz"):
    """
    Формирует Telegram-пост через Claude.
    Если Claude недоступен — возвращает None (пост не публикуется).
    """
    rewritten = rewrite_with_claude(article, lang=lang)

    if rewritten and len(rewritten) > 80:
        post = validate_post(rewritten.strip())
        if not post:
            return None
        # Только ссылка на наш канал — источник скрыт
        post += '\n\n👉 <a href="https://t.me/uzbekworld_test">Uzbek World Cup</a>'
        return post

    return None


def validate_post(text):
    """
    Валидирует пост перед публикацией.
    Возвращает очищенный текст или None если пост не подходит.
    """
    if not text:
        return None

    # Удаляем случайные URL
    text = re.sub(r'https?://\S+', '', text)

    # Удаляем HTML-теги которые Claude не должен был писать
    # (кроме тех что мы сами добавляем: <b>, <a>)
    text = re.sub(r'<(?!/?b>|a |/a>)[^>]+>', '', text)

    # Убираем строки с сайтами/источниками которые Claude мог добавить
    bad_patterns = [
        r'(?i)(manba|источник|source)\s*[:：].*',
        r'(?i)www\.\S+',
        r'(?i)\.(com|uz|ru|net|org|io)\b[^\n]*',
    ]
    for pattern in bad_patterns:
        text = re.sub(pattern, '', text)

    # Убираем лишние пустые строки (больше 2 подряд)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()

    # Минимальная длина
    if len(text) < 80:
        return None

    return text


# ============================================
# АНТИДУБЛИКАТ
# ============================================

HISTORY_FILE = "news_history.json"


def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"posts": []}


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def get_content_hash(text):
    return hashlib.sha256(re.sub(r"\s+", " ", text.lower().strip()).encode()).hexdigest()


def extract_keywords(text):
    stopwords = {
        "и","в","на","с","по","для","от","до","за","из","о",
        "the","a","an","in","on","at","to","for","of","is","are",
        "va","bu","uchun","bilan","ga","da","ni","was","will",
    }
    words = re.findall(r"\b[a-zA-Zа-яА-ЯёЁ\u0400-\u04FF]{4,}\b", text.lower())
    return set(w for w in words if w not in stopwords)


def similarity_score(t1, t2):
    w1, w2 = extract_keywords(t1), extract_keywords(t2)
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / len(w1 | w2)


def detect_topic(text):
    tl = text.lower()
    topics = [
        ("countdown",        ["days left", "kun qoldi", "дней осталось"]),
        ("press_conference", ["press conference", "пресс-конференция"]),
        ("transfer",         ["transfer", "трансфер", "перешёл"]),
        ("match_result",     ["score", "won", "lost", "draw", "счёт", "g'alaba"]),
        ("statistics",       ["stats", "record", "рекорд", "statistika"]),
        ("standings",        ["standing", "table", "таблица", "jadval"]),
        ("interview",        ["interview", "высказался", "заявил", "suhbat"]),
        ("history",          ["history", "впервые", "birinchi marta"]),
        ("watch_party",      ["watch party", "болельщики", "muxlis"]),
        ("team_news",        ["arrived", "training camp", "тренировочный"]),
        ("group_analysis",   ["group k", "guruh k", "группа k"]),
        ("match_preview",    ["vs", "preview", "forecast", "prediction", "матч"]),
        ("player_profile",   ["shomurodov", "xusanov", "masharipov"]),
        ("wc_news",          ["world cup", "fifa", "2026", "jahon chempionati"]),
        ("general_football", ["football", "futbol", "soccer"]),
    ]
    for topic, keywords in topics:
        for kw in keywords:
            if kw in tl:
                return topic
    return "other"


def is_duplicate(new_content, limit=50):
    if not new_content:
        return True, "empty_content"
    recent = load_history()["posts"][-limit:]
    new_hash = get_content_hash(new_content)

    for post in recent:
        if post.get("hash") == new_hash:
            return True, "exact_duplicate"
        if similarity_score(new_content, post.get("content", "")) > 0.42:
            return True, "semantic_duplicate"

    spam = ["biz tayyormiz", "biz ishonamiz", "oldinga o'zbekiston",
            "мы верим", "мы готовы", "вперёд узбекистан"]
    if any(p in new_content.lower() for p in spam):
        cutoff = datetime.now() - timedelta(hours=24)
        for post in recent:
            try:
                if datetime.fromisoformat(post["timestamp"]) > cutoff:
                    if any(p in post.get("content", "").lower() for p in spam):
                        return True, "motivation_spam_24h"
            except:
                pass

    return False, None


def mark_published(content, source_url=""):
    history = load_history()
    history["posts"].append({
        "hash": get_content_hash(content),
        "content": content[:300],
        "topic": detect_topic(content),
        "timestamp": datetime.now().isoformat(),
        "source_url": source_url,
    })
    if len(history["posts"]) > 200:
        history["posts"] = history["posts"][-200:]
    save_history(history)


def get_last_countdown_time():
    for post in reversed(load_history()["posts"]):
        if post.get("topic") == "countdown":
            try:
                return datetime.fromisoformat(post["timestamp"])
            except:
                pass
    return None


def get_days_until_first_match():
    return max(0, (datetime(2026, 6, 17) - datetime.now()).days)


def format_countdown_post(days, lang="uz"):
    if lang == "uz":
        return f"⏰ O'zbekiston vs 🇵🇹 Portugaliya — <b>{days} kun qoldi!</b>\n\n17-iyun, 21:00 | NRG Stadium, Hyuston\n\n#UzbekWorldCup"
    return f"⏰ Узбекистан vs 🇵🇹 Португалия — <b>{days} дней!</b>\n\n17 июня, 21:00 | NRG Stadium, Хьюстон\n\n#UzbekWorldCup"
