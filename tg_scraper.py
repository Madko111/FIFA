# -*- coding: utf-8 -*-
"""
Telegram Channel Scraper — читает посты из каналов-источников.
Использует Telethon (user account, не бот).

Каналы-источники:
  - @ZorTv_GollarTv
  - @Davron_Fayziev

Источники НЕ указываются в итоговом посте.
"""

import os
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Telethon требует API ID и API Hash от my.telegram.org
TG_API_ID   = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH = os.getenv("TG_API_HASH", "")
TG_SESSION  = "tg_session"  # имя файла сессии

# Каналы-источники
SOURCE_CHANNELS = [
    "@ZorTv_GollarTv",
    "@Davron_Fayziev",
]


async def fetch_channel_posts(channel, limit=10, hours_back=24):
    """
    Читает последние посты из канала за последние N часов.
    Возвращает список {"text": str, "date": datetime, "channel": str}
    """
    try:
        from telethon import TelegramClient
        from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

        client = TelegramClient(TG_SESSION, TG_API_ID, TG_API_HASH)
        await client.start()

        cutoff = datetime.now() - timedelta(hours=hours_back)
        posts = []

        async for msg in client.iter_messages(channel, limit=limit):
            if not msg.date:
                continue
            # Telethon возвращает UTC
            msg_date = msg.date.replace(tzinfo=None)
            if msg_date < cutoff:
                break

            text = msg.text or msg.message or ""
            text = text.strip()

            # Пропускаем слишком короткие (реклама, стикеры)
            if len(text) < 50:
                continue

            # Фото из поста (если есть)
            photo_url = None
            if hasattr(msg, "media") and isinstance(msg.media, MessageMediaPhoto):
                # Telethon не даёт прямой URL, но мы можем передать media объект
                photo_url = msg.media  # передадим как объект для скачивания

            posts.append({
                "text":    text,
                "date":    msg_date,
                "channel": channel,
                "photo":   photo_url,
                "msg_id":  msg.id,
            })

        await client.disconnect()
        return posts

    except Exception as e:
        print(f"tg_scraper error [{channel}]: {e}")
        return []


async def fetch_all_tg_posts(hours_back=12):
    """Читает посты из всех каналов-источников"""
    all_posts = []
    for channel in SOURCE_CHANNELS:
        posts = await fetch_channel_posts(channel, limit=20, hours_back=hours_back)
        all_posts.extend(posts)
        print(f"  {channel}: {len(posts)} постов")

    # Сортируем по дате (свежие первые)
    all_posts.sort(key=lambda x: x["date"], reverse=True)
    return all_posts


def get_tg_posts_sync(hours_back=12):
    """Синхронная обёртка для вызова из news_engine"""
    if not TG_API_ID or not TG_API_HASH:
        return []
    try:
        return asyncio.run(fetch_all_tg_posts(hours_back=hours_back))
    except Exception as e:
        print(f"tg_scraper sync error: {e}")
        return []
