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

            # Фото
            photo_url = None
            photo_el = msg.find("a", class_="tgme_widget_message_photo_wrap")
            if photo_el:
                style = photo_el.get("style", "")
                match = re.search(r"url\('?([^')]+)'?\)", style)
                if match:
                    photo_url = match.group(1)

            # Дата
            date_el = msg.find("time")
            date_str = date_el.get("datetime", "") if date_el else ""
            try:
                date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                date = datetime.now()

            posts.append({"text": text, "photo": photo_url, "date": date})

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
                "priority":     0,
                "is_tg_post":   True,
            })

    all_articles.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return all_articles
