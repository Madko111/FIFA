# -*- coding: utf-8 -*-
"""
Telegram Channel Scraper — читает публичные каналы через t.me/s/
Не требует авторизации. Работает с любым публичным каналом.
"""

import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup

SOURCE_CHANNELS = [
    "ZorTv_GollarTv",
    "Davron_Fayziev",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ru,en;q=0.9",
}

# ============================================================
# ЗАПРЕТ БУКМЕКЕРОВ И АЗАРТНЫХ ИГР — ФУНДАМЕНТАЛЬНЫЙ УРОВЕНЬ
# Любой пост содержащий эти слова — немедленно отклоняется.
# ============================================================
GAMBLING_STOP_WORDS = [
    "1xbet", "1хбет", "1x bet", "melbet", "мелбет", "parimatch", "париматч",
    "betway", "bet365", "mostbet", "мостбет", "betwinner", "leon bet", "leonbet",
    "olimpbet", "olimp bet", "xbet", "winline", "фонбет", "fonbet",
    "букмекер", "bukmaker", "stavka", "stavki", "ставка", "ставки",
    "koeffitsient", "koef", "коэффициент", "odds", "promo kod", "promo code",
    "промокод", "депозит", "вывод средств", "bonus", "бонус", "freebet",
    "kazino", "казино", "casino", "ruletka", "рулетка", "slot", "слот",
    "pari", "пари", "totalizator", "тотализатор", "bet ", " bet",
    "stavochnik", "ставочник", "капер", "kaper", "прогноз за деньги",
    "vip прогноз", "vip prog", "платный прогноз",
]


def fetch_channel_posts(channel_name, limit=10):
    """Парсит публичный Telegram-канал через t.me/s/"""
    url = f"https://t.me/s/{channel_name}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            print(f"  ❌ {channel_name}: HTTP {resp.status_code}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        messages = soup.find_all("div", class_="tgme_widget_message_wrap")

        posts = []
        for msg in messages[-limit:]:
            # Текст
            text_el = msg.find("div", class_="tgme_widget_message_text")
            text = text_el.get_text(separator="\n").strip() if text_el else ""
            if len(text) < 50:
                continue

            # ЗАПРЕТ БУКМЕКЕРОВ — фундаментальный уровень
            text_lower = text.lower()
            is_gambling = any(word in text_lower for word in GAMBLING_STOP_WORDS)
            if is_gambling:
                print(f"  🚫 Пост отклонён (букмекер/азарт): {text[:60]}...")
                continue

            # Фото — ищем background-image с cdn (не emoji)
            photo_url = None
            for el in msg.find_all(style=True):
                style = el.get("style", "")
                # Только реальные фото с CDN, не emoji
                if "cdn" in style and "background-image" in style and "width:" in style:
                    match = re.search(r"background-image:url\('([^']+)'\)", style)
                    if match:
                        url = match.group(1)
                        # Берём только первое (главное) фото
                        if url.startswith("https://cdn"):
                            photo_url = url
                            break

            # Дата
            date_el = msg.find("time")
            date_str = date_el.get("datetime", "") if date_el else ""
            try:
                date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                date = datetime.now()

            # Определяем приоритет по теме (не по источнику)
            text_lower_check = text.lower()
            if any(kw in text_lower_check for kw in [
                "o'zbekiston", "узбекистан", "uzbekistan", "shomurodov", "xusanov",
                "masharipov", "toshmatov", "o'zbek terma", "milliy jamoasi", "сборная узбек"
            ]):
                topic_priority = 1  # Про Узбекистан — высший приоритет
            elif any(kw in text_lower_check for kw in [
                "portugal", "colombia", "congo", "group k", "guruh k",
                "portugal", "kolumbiya", "группа k"
            ]):
                topic_priority = 2  # Про соперников/группу
            else:
                topic_priority = 3  # Общие новости ЧМ

            posts.append({"text": text, "photo": photo_url, "date": date, "priority": topic_priority})

        return posts

    except Exception as e:
        print(f"  ❌ {channel_name}: {e}")
        return []


def get_tg_posts(limit_per_channel=5):
    """Читает посты из всех каналов, возвращает в формате news_engine"""
    all_articles = []

    for channel in SOURCE_CHANNELS:
        posts = fetch_channel_posts(channel, limit=limit_per_channel)
        print(f"  @{channel}: {len(posts)} постов")

        for post in posts:
            all_articles.append({
                "title":        post["text"][:80].replace("\n", " "),
                "content":      post["text"],
                "description":  post["text"][:200],
                "url":          f"https://t.me/{channel}",
                "urlToImage":   post["photo"],
                "source":       "tg_channel",
                "published_at": post["date"].isoformat(),
                "priority":     post["priority"],  # Приоритет по теме
                "is_tg_post":   True,
            })

    all_articles.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return all_articles
