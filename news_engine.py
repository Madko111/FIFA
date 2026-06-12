"""
NEWS ENGINE — реальный поиск и обработка новостей.
Только реальные источники. Никакой отсебятины.
"""

import os
import re
import json
import hashlib
import requests
import feedparser
from datetime import datetime, timedelta
from difflib import SequenceMatcher


# ============================================
# RSS ИСТОЧНИКИ (приоритет по порядку)
# ============================================

FEEDS = [
    # 1. Узбекистан футбол — конкретные
    {"url": "https://news.google.com/rss/search?q=Uzbekistan+national+football+team+2026&hl=en&gl=US&ceid=US:en", "priority": 1, "lang": "en"},
    {"url": "https://news.google.com/rss/search?q=O%27zbekiston+terma+jamoasi&hl=uz&gl=UZ&ceid=UZ:uz", "priority": 1, "lang": "uz"},
    {"url": "https://news.google.com/rss/search?q=%D1%81%D0%B1%D0%BE%D1%80%D0%BD%D0%B0%D1%8F+%D0%A3%D0%B7%D0%B1%D0%B5%D0%BA%D0%B8%D1%81%D1%82%D0%B0%D0%BD+%D1%84%D1%83%D1%82%D0%B1%D0%BE%D0%BB&hl=ru&gl=RU&ceid=RU:ru", "priority": 1, "lang": "ru"},

    # 2. Игроки сборной
    {"url": "https://news.google.com/rss/search?q=Shomurodov+OR+Xusanov+OR+Toshmatov+2026&hl=en&gl=US&ceid=US:en", "priority": 2, "lang": "en"},
    {"url": "https://news.google.com/rss/search?q=Shomurodov+OR+Xusanov+futbol&hl=uz&gl=UZ&ceid=UZ:uz", "priority": 2, "lang": "uz"},

    # 3. ЧМ-2026 Узбекистан
    {"url": "https://news.google.com/rss/search?q=Uzbekistan+World+Cup+2026&hl=en&gl=US&ceid=US:en", "priority": 3, "lang": "en"},
    {"url": "https://news.google.com/rss/search?q=World+Cup+2026+Group+K&hl=en&gl=US&ceid=US:en", "priority": 3, "lang": "en"},

    # 4. Соперники
    {"url": "https://news.google.com/rss/search?q=Portugal+World+Cup+2026+Group+K&hl=en&gl=US&ceid=US:en", "priority": 4, "lang": "en"},
    {"url": "https://news.google.com/rss/search?q=Colombia+Congo+World+Cup+2026+Group&hl=en&gl=US&ceid=US:en", "priority": 4, "lang": "en"},

    # 5. FIFA официальные
    {"url": "https://www.fifa.com/en/rss/articles", "priority": 5, "lang": "en"},

    # 6. AFC
    {"url": "https://www.the-afc.com/rss", "priority": 6, "lang": "en"},

    # 7. Спортивные порталы
    {"url": "https://feeds.bbci.co.uk/sport/football/rss.xml", "priority": 7, "lang": "en"},
    {"url": "https://www.goal.com/feeds/en/news", "priority": 7, "lang": "en"},
    {"url": "https://news.google.com/rss/search?q=Uzbekistan+football+FIFA&hl=en&gl=US&ceid=US:en", "priority": 7, "lang": "en"},

    # 8. Локальные узбекские
    {"url": "https://news.google.com/rss/search?q=uzreport+football&hl=uz&gl=UZ&ceid=UZ:uz", "priority": 8, "lang": "uz"},
    {"url": "https://news.google.com/rss/search?q=championat.asia+%D1%84%D1%83%D1%82%D0%B1%D0%BE%D0%BB&hl=ru&gl=RU&ceid=RU:ru", "priority": 8, "lang": "ru"},
]

# Ключевые слова для фильтрации релевантных новостей
RELEVANT_KEYWORDS = [
    "uzbekistan", "o'zbekiston", "узбекистан", "uzbek",
    "shomurodov", "шомуродов", "xusanov", "хусанов",
    "toshmatov", "ташматов", "masharipov", "машарипов",
    "world cup 2026", "fifa 2026", "wc2026",
    "group k", "группа k",
    "portugal", "colombia", "congo",
    "afc", "чм-2026", "jahon chempionati",
]

# Стоп-слова — полностью не относящиеся новости
STOP_KEYWORDS = [
    "cricket", "tennis", "basketball", "baseball", "nba", "nfl",
    "formula 1", "f1", "cycling", "swimming", "golf",
]


# ============================================
# ПАРСИНГ НОВОСТЕЙ
# ============================================

def fetch_feed(feed_info, timeout=8):
    """Загружает один RSS фид"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"}
        response = requests.get(feed_info["url"], timeout=timeout, headers=headers)
        if response.status_code != 200:
            return []
        
        feed = feedparser.parse(response.content)
        articles = []
        
        for entry in feed.entries[:10]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            summary = entry.get("summary", "").strip()
            published = entry.get("published", "")
            source = entry.get("source", {}).get("title", feed.feed.get("title", "Unknown"))
            
            if not title or not link:
                continue
            
            articles.append({
                "title": title,
                "link": link,
                "summary": clean_html(summary),
                "published": published,
                "source": source,
                "priority": feed_info["priority"],
                "lang": feed_info["lang"],
            })
        
        return articles
    except Exception as e:
        print(f"Feed error [{feed_info['url'][:60]}]: {e}")
        return []


def clean_html(text):
    """Очищает HTML теги"""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&quot;', '"', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def is_relevant(article):
    """Проверяет релевантность новости"""
    text = (article["title"] + " " + article["summary"]).lower()
    
    # Стоп-слова — сразу отклоняем
    for word in STOP_KEYWORDS:
        if word in text:
            return False
    
    # Проверяем наличие хотя бы одного релевантного слова
    for keyword in RELEVANT_KEYWORDS:
        if keyword in text:
            return True
    
    return False


def fetch_all_news():
    """Загружает новости из всех источников"""
    all_articles = []
    
    for feed_info in FEEDS:
        articles = fetch_feed(feed_info)
        relevant = [a for a in articles if is_relevant(a)]
        all_articles.extend(relevant)
    
    # Сортируем по приоритету
    all_articles.sort(key=lambda x: x["priority"])
    
    # Убираем дубликаты по ссылке
    seen_links = set()
    unique_articles = []
    for article in all_articles:
        if article["link"] not in seen_links:
            seen_links.add(article["link"])
            unique_articles.append(article)
    
    return unique_articles


# ============================================
# АНТИДУБЛИКАТ СИСТЕМА
# ============================================

HISTORY_FILE = "news_history.json"


def load_history():
    """Загружает историю опубликованных постов"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"posts": [], "topics": []}
    return {"posts": [], "topics": []}


def save_history(history):
    """Сохраняет историю"""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def get_content_hash(text):
    """SHA-256 хеш для точного дубликата"""
    clean = re.sub(r'\s+', ' ', text.lower().strip())
    return hashlib.sha256(clean.encode()).hexdigest()


def extract_topic_keywords(text):
    """Извлекает ключевые слова для смысловой проверки"""
    text = text.lower()
    # Убираем стоп-слова
    stopwords = {
        'и', 'в', 'на', 'с', 'по', 'для', 'от', 'до', 'за', 'из', 'о',
        'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'is', 'are',
        'was', 'will', 'has', 'have', 'that', 'this', 'with', 'from',
        'va', 'bu', 'uchun', 'bilan', 'ga', 'da', 'ni',
    }
    words = re.findall(r'\b[a-zA-Zа-яА-ЯёЁa-zA-Z\u0400-\u04FF]{4,}\b', text)
    return set(w for w in words if w not in stopwords)


def similarity_score(text1, text2):
    """Процент похожести двух текстов (0..1)"""
    words1 = extract_topic_keywords(text1)
    words2 = extract_topic_keywords(text2)
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)


def detect_topic(text):
    """Определяет основную тему текста. Порядок приоритетов важен."""
    text_lower = text.lower()

    # Порядок от более специфичных к общим
    ordered_topics = [
        ("countdown",        ["days left", "kun qoldi", "дней осталось", "hours left", "countdown"]),
        ("press_conference", ["press conference", "presser", "matbuot anjumani", "пресс-конференция"]),
        ("transfer",         ["transfer", "signs for", "loaned", "o'tkazma", "трансфер", "перешёл"]),
        ("match_result",     ["score", "won", "lost", "draw", "natija", "счёт", "победа", "поражение"]),
        ("statistics",       ["stats", "record", "statistika", "рекорд", "статистика", "ranked"]),
        ("standings",        ["standing", "table", "points", "jadval", "турнирная", "таблица", "league table"]),
        ("interview",        ["interview", "suhbat", "интервью", "заявил", "said in"]),
        ("history",          ["history", "tarix", "first time", "биринчи", "впервые", "historic"]),
        ("watch_party",      ["watch party", "fan zone", "tomoshabin", "болельщики", "viewing"]),
        ("group_analysis",   ["group k", "guruh k", "группа k"]),
        ("match_preview",    ["vs", "preview", "forecast", "prediction", "o'yin oldi", "матч"]),
        ("player_profile",   ["shomurodov", "xusanov", "masharipov", "toshmatov", "o'yinchi", "игрок", "player profile"]),
        ("wc_news",          ["world cup", "fifa", "2026", "jahon chempionati", "чм-2026", "mundial"]),
        ("motivation",       ["support", "believe", "together", "qo'llab", "верим", "вместе"]),
    ]

    for topic, keywords in ordered_topics:
        for kw in keywords:
            if kw in text_lower:
                return topic
    return "other"


def is_duplicate(new_content, history_limit=50):
    """
    Возвращает (True, reason) если пост — дубликат.
    Проверяет:
      1. Точный хеш
      2. Схожесть > 40%
      3. Та же тема в последних 5 постах
    """
    history = load_history()
    recent_posts = history["posts"][-history_limit:]
    
    # 1. Точный хеш
    new_hash = get_content_hash(new_content)
    for post in recent_posts:
        if post.get("hash") == new_hash:
            return True, "exact_duplicate"
    
    # 2. Смысловая похожесть > 40%
    for post in recent_posts:
        sim = similarity_score(new_content, post.get("content", ""))
        if sim > 0.40:
            return True, f"semantic_duplicate (sim={sim:.2f})"
    
    # 3. Та же тема в последних 5 постах
    new_topic = detect_topic(new_content)
    if new_topic not in ("other", "wc_news"):  # wc_news — общее, разрешаем
        recent_topics = [p.get("topic") for p in recent_posts[-5:]]
        if recent_topics.count(new_topic) >= 2:
            return True, f"topic_overload ({new_topic})"
    
    # 4. Спам-фразы — мотивация/поддержка
    spam_phrases = [
        "мы верим", "мы готовы", "вперёд узбекистан", "узбеки объединяются",
        "поддержим сборную", "biz tayyormiz", "biz ishonamiz", "birgalikda",
        "oldinga o'zbekiston", "qo'llab-quvvatlaylik",
    ]
    content_lower = new_content.lower()
    for phrase in spam_phrases:
        if phrase in content_lower:
            # Разрешаем, если последние 24 часа не было подобного
            cutoff = datetime.now() - timedelta(hours=24)
            for post in recent_posts:
                ts = post.get("timestamp", "")
                try:
                    if datetime.fromisoformat(ts) > cutoff:
                        post_lower = post.get("content", "").lower()
                        if any(p in post_lower for p in spam_phrases):
                            return True, "motivation_spam_within_24h"
                except:
                    pass
            break
    
    return False, None


def mark_published(content, source_url=""):
    """Записывает пост в историю"""
    history = load_history()
    
    entry = {
        "hash": get_content_hash(content),
        "content": content[:300],  # Первые 300 символов для сравнения
        "topic": detect_topic(content),
        "timestamp": datetime.now().isoformat(),
        "source_url": source_url,
    }
    
    history["posts"].append(entry)
    
    # Храним только последние 200 постов
    if len(history["posts"]) > 200:
        history["posts"] = history["posts"][-200:]
    
    save_history(history)


def get_last_countdown_time():
    """Возвращает время последнего countdown поста"""
    history = load_history()
    for post in reversed(history["posts"]):
        if post.get("topic") == "countdown":
            try:
                return datetime.fromisoformat(post["timestamp"])
            except:
                pass
    return None


# ============================================
# ФОРМАТИРОВАНИЕ ПОСТОВ
# ============================================

def format_news_post(article, lang="uz"):
    """
    Форматирует новость в пост для Telegram.
    Только реальный контент — никакой отсебятины.
    """
    title = article["title"].strip()
    summary = article["summary"].strip()
    link = article["link"].strip()
    source = article["source"].strip()
    
    # Убираем слишком короткие описания
    if len(summary) < 50:
        summary = ""
    
    # Лимит описания — 400 символов
    if len(summary) > 400:
        summary = summary[:400].rstrip() + "..."
    
    # Определяем эмодзи по теме
    topic = detect_topic(title + " " + summary)
    emoji_map = {
        "player_profile": "⚽️",
        "match_preview": "🔮",
        "match_result": "🏆",
        "standings": "📊",
        "transfer": "🔄",
        "interview": "🎙",
        "statistics": "📈",
        "history": "📜",
        "press_conference": "📢",
        "watch_party": "🎉",
        "group_analysis": "🗂",
        "wc_news": "🌍",
        "countdown": "⏰",
        "motivation": "💪",
    }
    emoji = emoji_map.get(topic, "📰")
    
    # Строим пост
    lines = [f"{emoji} {title}"]
    
    if summary:
        lines.append("")
        lines.append(summary)
    
    lines.append("")
    lines.append(f"🔗 {link}")
    lines.append(f"📰 {source}")
    
    return "\n".join(lines)


def format_countdown_post(days, lang="uz"):
    """
    Пост с обратным отсчётом. Только 1 раз в сутки.
    """
    match_info = {
        "uz": f"O'zbekiston vs 🇵🇹 Portugaliya — {days} kun qoldi!\n\n17-iyun, 21:00 | NRG Stadium, Hyuston",
        "ru": f"Узбекистан vs 🇵🇹 Португалия — {days} дней!\n\n17 июня, 21:00 | NRG Stadium, Хьюстон",
        "en": f"Uzbekistan vs 🇵🇹 Portugal — {days} days left!\n\nJune 17, 21:00 | NRG Stadium, Houston",
    }
    return f"⏰ {match_info.get(lang, match_info['uz'])}"


def get_days_until_first_match():
    """Дней до первого матча"""
    first_match = datetime(2026, 6, 17)
    delta = first_match - datetime.now()
    return max(0, delta.days)
