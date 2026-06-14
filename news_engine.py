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
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "") or os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")


# ============================================
# TELEGRAM КАНАЛЫ — ИСТОЧНИК ПРИОРИТЕТ 0
# ============================================

def fetch_tg_channel_posts():
    """
    Читает посты из Telegram каналов-источников.
    Требует TG_API_ID и TG_API_HASH в .env.
    Возвращает список в формате как NewsAPI articles.
    """
    try:
        from tg_scraper import get_tg_posts
        raw_posts = get_tg_posts(limit_per_channel=10)

        return raw_posts  # уже в нужном формате из tg_scraper
    except Exception as e:
        print(f"TG channel fetch error: {e}")
        return []


# ============================================
# GEMINI FALLBACK
# ============================================

def _rewrite_with_gemini(prompt):
    """Fallback rewriter using Gemini when Claude is unavailable."""
    if not GEMINI_API_KEY:
        return None
    try:
        from google import genai as google_genai
        from google.genai import types
        client = google_genai.Client(api_key=GEMINI_API_KEY)
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=700, temperature=0.5),
        )
        text = getattr(resp, "text", None) or ""
        return text.strip() or None
    except Exception as e:
        print(f"Gemini fallback error: {e}")
        return None


# ============================================
# NEWSAPI — ПОЛУЧЕНИЕ РЕАЛЬНЫХ НОВОСТЕЙ
# ============================================

NEWSAPI_QUERIES = [
    # Приоритет 1 — Сборная Узбекистана и игроки (самые важные)
    {"q": "Uzbekistan national football team 2026",      "priority": 1},
    {"q": "Uzbekistan soccer squad World Cup",           "priority": 1},
    {"q": "Shomurodov footballer 2026",                  "priority": 1},
    {"q": "Xusanov Lens defender World Cup",             "priority": 1},
    {"q": "Masharipov Uzbekistan footballer",            "priority": 1},
    # Приоритет 2 — Матчи и группа Узбекистана
    {"q": "Uzbekistan Portugal World Cup match",         "priority": 2},
    {"q": "Uzbekistan Colombia World Cup match",         "priority": 2},
    {"q": "Uzbekistan Congo World Cup Group K",          "priority": 2},
    {"q": "Group K World Cup 2026 Uzbekistan",           "priority": 2},
    # Приоритет 3 — ЧМ-2026 общее
    {"q": "FIFA World Cup 2026 news",                    "priority": 3},
    {"q": "World Cup 2026 Group K standings",            "priority": 3},
]

# Ключевые слова которые ОБЯЗАТЕЛЬНО должны быть в статье
MANDATORY_KEYWORDS = [
    "uzbekistan", "o'zbekiston", "shomurodov", "xusanov", "masharipov",
    "toshmatov", "katanec", "group k", "world cup 2026", "fifa 2026",
    "portugal", "colombia", "congo dr",
]

# Стоп-слова — статьи с ними однозначно не про нашу тему
STOP_KEYWORDS = [
    # Азартные игры — АБСОЛЮТНЫЙ ЗАПРЕТ
    "betting guide", "how to bet", "bookmaker", "1xbet", "melbet",
    "parimatch", "betway", "bet365", "mostbet", "betwinner", "casino",
    "gambling", "odds", "promo code", "букмекер", "ставк", "казино",
    "промокод", "zizobet", "leonbet", "fonbet", "winline",
    # Нерелевантные темы
    "sneakers", "shoes", "bape", "fashion", "trump", "politics",
    "socceroos", "australia vs", "canada vs bosnia", "nigeria",
    "iran vs new zealand", "brown line", "chicago reader",
    "naked capitalism", "reverse midas",
]


def fetch_newsapi(query_info, page_size=5):
    """Запрос к NewsAPI.org"""
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query_info["q"],
        "apiKey": NEWSAPI_KEY,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": page_size,
        "from": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
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
                "priority": query_info["priority"],
            })
        return articles
    except Exception as e:
        print(f"NewsAPI error [{query_info['q'][:40]}]: {e}")
        return []


def is_relevant_article(article):
    """
    Жёсткий фильтр релевантности ПЕРЕД отправкой в Claude.
    Возвращает (True, reason) или (False, reason).
    """
    text = f"{article['title']} {article['description']} {article['content']}".lower()

    # 1. Стоп-слова — сразу отклоняем
    for stop in STOP_KEYWORDS:
        if stop in text:
            return False, f"стоп-слово: '{stop}'"

    # 2. Обязательное слово — статья ДОЛЖНА быть про нашу тему
    has_mandatory = any(kw in text for kw in MANDATORY_KEYWORDS)
    if not has_mandatory:
        return False, "нет ключевых слов (Узбекистан/игроки/группа)"

    # 3. Минимальная длина контента
    content_len = len(article.get("content") or article.get("description") or "")
    if content_len < 80:
        return False, "слишком мало текста"

    # 4. Reject articles whose TITLE is purely about "Uzbekistan qualified" (old news)
    title_lower = article.get("title", "").lower()
    stale_title_signals = [
        "historic rise", "first time", "qualify", "qualified", "qualification",
        "makes history", "first world cup", "debut", "curiosit",
    ]
    uzbek_stale = any(s in title_lower for s in stale_title_signals)
    if uzbek_stale and "uzbekistan" in title_lower:
        return False, f"stale qualification headline: '{article['title'][:60]}'"

    return True, "OK"


def fetch_all_news():
    """
    Загружает новости из всех источников:
    1. Telegram каналы (приоритет 0 — самый высокий)
    2. NewsAPI (приоритет 1-3)
    Фильтрует нерелевантные, сортирует по приоритету.
    """
    all_articles = []
    seen_texts = set()

    # Источник 0: Telegram каналы (если настроены)
    tg_posts = fetch_tg_channel_posts()
    for a in tg_posts:
        key = a["content"][:100]
        if key not in seen_texts:
            seen_texts.add(key)
            all_articles.append(a)

    # Источник 1+: NewsAPI
    seen_urls = set()
    for query_info in NEWSAPI_QUERIES:
        for a in fetch_newsapi(query_info):
            if a["url"] in seen_urls or not a["url"]:
                continue
            seen_urls.add(a["url"])

            relevant, reason = is_relevant_article(a)
            if not relevant:
                continue

            all_articles.append(a)

    # Сортируем: сначала по приоритету, потом по свежести
    all_articles.sort(key=lambda x: (x["priority"], x.get("published_at", "")))
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

    # TG-посты уже на uz/ru — просто редактируем, не переводим
    is_tg = article.get("is_tg_post", False)

    source_text = (
        f"Title: {article['title']}\n"
        f"Description: {article.get('description', '')}\n"
        f"Content: {article.get('content', '')}\n"
        f"Source: {article['source']}"
    )

    if is_tg:
        # Для TG-постов: редактируем, не переводим
        prompt = f"""Sen sport Telegram-kanal muharriri siz. Quyidagi postni qayta ishlang.

VAZIFA:
- Matnni to'g'ri formatlang (sarlavha + 1-2 qisqa abzas)
- Manbaga havola, sayt nomi, kanal nomi — olib tashlang
- Keraksiz takrorlarni olib tashlang
- Hajm: 200-350 belgi
- Til: original tilida qoldiring (o'zbek yoki rus)
- Hech qanday URL, @ va havola bo'lmasin

FORMAT:
[emoji] Sarlavha

Abzas 1.

Abzas 2.

ORIGINAL POST:
{article['content']}

Faqat tayyor post."""
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
                    "max_tokens": 500,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=20,
            )
            if resp.status_code == 200:
                return resp.json()["content"][0]["text"].strip()
        except Exception as e:
            print(f"Claude TG error: {e}")
        return None

    if lang == "uz":
        prompt = f"""Sen O'zbekiston futboli haqidagi Telegram-kanal muharririsiz. Quyidagi inglizcha manbadan o'zbek tilidagi yangilik post yoz.

SEN JURNALISTSIZ, TARJIMON EMASSAN:
- Matnni so'zma-so'z tarjima qilma
- Avval asosiy fikrni tushun, keyin o'zbek tilida o'z so'zingda yoz
- Tabiiy, jonli o'zbek tili ishlatilsin
- Ingliz tilining konstruksiyalarini nusxalama

FORMAT (qat'iy):
[1 ta emoji] Qisqa sarlavha (maqola sarlavhasini ko'chirma, yangi yoz)

Birinchi abzas — eng muhim ma'lumot.

Ikkinchi abzas — qo'shimcha detal.

(Kerak bo'lsa uchinchi abzas)

QOIDALAR:
- Hajm: 200-350 ta belgi (sarlavhasiz)
- Takrorlanuvchi fikrlarni, kirish so'zlarni va keraksiz jumlalarni olib tashla
- FAQAT O'ZBEK TILI — inglizcha so'z bo'lmasin
- Hech qanday URL, havola, sayt nomi yozma
- Pafosdan saqlaning: "tarixiy lahza", "butun dunyo kutmoqda" — taqiqlangan
- Faqat haqiqiy faktlar
- Oddiy, tushinarli til — sport xabari sifatida

TAQIQLANGAN IBORALAR: "tarixiy lahza", "afsonaviy", "dunyoning eng muhim", "barcha ko'zlar",
"birinchi marta Jahon Kubogiga", "uzoq kutilgan", "yangi sahifa ochdi", "yangi davr"

MUHIM KONTEKST: Bugun 15-iyun 2026. O'zbekiston ALLAQACHON Jahon Kubogiga chiqqan (bu eski yangilik).
Birinchi o'yin — 17-iyun, Portugaliya bilan. Faqat BUGUNGI yoki ERTANGI yangiliklar haqida yoz.
Qvalifikatsiya haqida yozma — bu o'tgan yilgi gap.

YANGILIK MATNI:
{source_text}

Faqat tayyor post matni. Izoh yozma."""
    else:
        prompt = f"""Ты редактор Telegram-канала про сборную Узбекистана. Напиши пост на русском по этой новости.

ТЫ ЖУРНАЛИСТ, НЕ ПЕРЕВОДЧИК:
- Не переводи слово в слово
- Сначала пойми смысл, потом напиши своими словами
- Пиши как русскоязычный спортивный журналист

ФОРМАТ (строго):
[1 эмодзи] Короткий заголовок (придумай новый, не копируй из статьи)

Первый абзац — самое важное.

Второй абзац — детали.

(Третий если нужен)

ПРАВИЛА:
- Объём: 200-350 символов (без заголовка)
- Убирай повторяющиеся мысли, лишние вводные, очевидные фразы без фактов
- ТОЛЬКО РУССКИЙ ЯЗЫК
- Никаких URL, ссылок, названий сайтов
- Без пафоса: "исторический момент", "весь мир следит" — запрещено
- Только реальные факты
- Естественный язык

ЗАПРЕЩЁННЫЕ ФРАЗЫ: "исторический момент", "легендарное противостояние", "весь мир замер", "эпохальный"

ТЕКСТ НОВОСТИ:
{source_text}

Только текст поста. Никаких пояснений."""

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
        # Fallback to Gemini
        return _rewrite_with_gemini(prompt)
    except Exception as e:
        print(f"Claude request error: {e} — trying Gemini fallback")
        return _rewrite_with_gemini(prompt)


def extract_image_url(article):
    """
    Извлекает изображение статьи.
    Приоритет: urlToImage из NewsAPI → og:image из страницы.
    Фильтрует логотипы, баннеры, иконки.
    """
    # 1. NewsAPI сам возвращает urlToImage
    img = article.get("urlToImage") or article.get("image_url") or ""
    if img and _is_valid_image(img):
        return img

    # 2. Пытаемся вытащить og:image из страницы статьи
    url = article.get("url", "")
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=6, headers={
            "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1)"
        })
        if resp.status_code != 200:
            return None
        # Ищем og:image
        match = re.search(
            r'<meta[^>]+(?:property=["\']og:image["\']|name=["\']og:image["\'])[^>]+content=["\']([^"\']+)["\']',
            resp.text, re.IGNORECASE
        )
        if not match:
            match = re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property=["\']og:image["\'])',
                resp.text, re.IGNORECASE
            )
        if match:
            img_url = match.group(1).strip()
            if _is_valid_image(img_url):
                return img_url
    except Exception:
        pass

    return None


def _is_valid_image(url):
    """Проверяет, подходит ли изображение для публикации"""
    if not url or len(url) < 10:
        return False

    url_lower = url.lower()

    # Фильтруем явно плохие
    bad_patterns = [
        "logo", "icon", "favicon", "banner", "ad_", "ads_", "advert",
        "pixel.gif", "1x1", "tracking", "beacon", "placeholder",
        "avatar", "profile_pic", "spinner", "loading",
    ]
    for bad in bad_patterns:
        if bad in url_lower:
            return False

    # Должен быть обычный изображение-URL
    if not any(ext in url_lower for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
        # Разрешаем URL без расширения (CDN часто так делают)
        if "image" not in url_lower and "photo" not in url_lower and "media" not in url_lower:
            return True  # Даём шанс — проверим по размеру при отправке
    return True


def format_news_post(article, lang="uz"):
    """
    Формирует Telegram-пост через Claude.
    Возвращает dict {"text": str, "image": str|None} или None.
    """
    rewritten = rewrite_with_claude(article, lang=lang)

    if rewritten and len(rewritten) > 80:
        post = validate_post(rewritten.strip())
        if not post:
            return None

        post += '\n\n👉 <a href="https://t.me/uzbekworld_test">Uzbek World Cup</a>'

        # Ищем изображение
        image_url = extract_image_url(article)

        return {"text": post, "image": image_url}

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
        if similarity_score(new_content, post.get("content", "")) > 0.28:
            return True, "semantic_duplicate"

    spam = ["biz tayyormiz", "biz ishonamiz", "oldinga o'zbekiston",
            "мы верим", "мы готовы", "вперёд узбекистан",
            "birinchi marta jahon kubogiga", "birinchi marta chiqdi",
            "uzoq kutilgan orzu", "yangi sahifa ochdi", "yangi davr boshlandi",
            "uzoq kutilgan", "yangi bosqich", "tarixiy yutuq",
            "birinchi marta kvalifikatsiya", "впервые вышел", "исторический выход"]
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
