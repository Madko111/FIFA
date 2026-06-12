"""
Uzbek World Cup 2026 Bot — новый независимый экземпляр.
Новый токен: 8977052249:AAEWp-082T33-kLZIyIdEdZYkLiIRcI_lSc
Старый бот НЕ затронут.
"""

import os
import json
import time
import asyncio
import threading
from datetime import datetime, timedelta, date

import schedule
from dotenv import load_dotenv
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from translations import get_text
from news_engine import (
    fetch_all_news,
    format_news_post,
    format_countdown_post,
    is_duplicate,
    mark_published,
    get_last_countdown_time,
    get_days_until_first_match,
)

# ============================================
# НАСТРОЙКИ
# ============================================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN_NEW", "8977052249:AAEWp-082T33-kLZIyIdEdZYkLiIRcI_lSc")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@uzbekworld_test")
ADMIN_USER_IDS = [
    int(uid.strip())
    for uid in os.getenv("ADMIN_USER_ID", "5345007811,573901881,78310521").split(",")
    if uid.strip()
]
POST_INTERVAL_MINUTES = int(os.getenv("POST_INTERVAL_MINUTES", "30"))

USER_SETTINGS_FILE = "user_settings.json"
KPI_DATA_FILE = "kpi_data.json"

# ============================================
# ДАННЫЕ
# ============================================

MATCHES = [
    {"date": "2026-06-17", "opponent": {"uz": "Portugaliya", "ru": "Португалия", "en": "Portugal"}, "flag": "🇵🇹", "time": "21:00", "city": {"uz": "Hyuston", "ru": "Хьюстон", "en": "Houston"}, "stadium": "NRG Stadium"},
    {"date": "2026-06-21", "opponent": {"uz": "Kolumbiya", "ru": "Колумбия", "en": "Colombia"}, "flag": "🇨🇴", "time": "18:00", "city": {"uz": "Atlanta", "ru": "Атланта", "en": "Atlanta"}, "stadium": "Mercedes-Benz Stadium"},
    {"date": "2026-06-25", "opponent": {"uz": "Kongo (DR)", "ru": "Конго (ДР)", "en": "Congo DR"}, "flag": "🇨🇩", "time": "15:00", "city": {"uz": "Mexico-siti", "ru": "Мехико", "en": "Mexico City"}, "stadium": "Estadio Azteca"},
]

PLAYERS = [
    {"name": {"uz": "Eldor Shomurodov", "ru": "Эльдор Шомуродов", "en": "Eldor Shomurodov"}, "position": {"uz": "Hujumchi", "ru": "Нападающий", "en": "Forward"}, "club": "Roma", "number": 14, "age": 27, "emoji": "⚡️"},
    {"name": {"uz": "Abduqodir Xusanov", "ru": "Абдукодир Хусанов", "en": "Abduqodir Khusanov"}, "position": {"uz": "Himoyachi", "ru": "Защитник", "en": "Defender"}, "club": "Lens", "number": 23, "age": 20, "emoji": "🛡"},
    {"name": {"uz": "Otabek Shukurov", "ru": "Отабек Шукуров", "en": "Otabek Shukurov"}, "position": {"uz": "Yarim himoyachi", "ru": "Полузащитник", "en": "Midfielder"}, "club": "Pakhtakor", "number": 9, "age": 29, "emoji": "🎯"},
    {"name": {"uz": "Umarbek Eshmurodov", "ru": "Умарбек Эшмуродов", "en": "Umarbek Eshmurodov"}, "position": {"uz": "Darvozabon", "ru": "Вратарь", "en": "Goalkeeper"}, "club": "Pakhtakor", "number": 1, "age": 26, "emoji": "🧤"},
    {"name": {"uz": "Jasurbek Yaqshiboyev", "ru": "Жасурбек Якшибоев", "en": "Jasurbek Yakshiboyev"}, "position": {"uz": "Hujumchi", "ru": "Нападающий", "en": "Forward"}, "club": "Melbourne City", "number": 17, "age": 24, "emoji": "⚽️"},
]

CITIES = {
    "Houston":     {"name": {"uz": "Hyuston",      "ru": "Хьюстон",       "en": "Houston"},      "group_link": "https://t.me/uzbekworld_test"},
    "New York":    {"name": {"uz": "Nyu-York",      "ru": "Нью-Йорк",      "en": "New York"},     "group_link": "https://t.me/uzbekworld_test"},
    "Los Angeles": {"name": {"uz": "Los-Anjeles",   "ru": "Лос-Анджелес",  "en": "Los Angeles"},  "group_link": "https://t.me/uzbekworld_test"},
    "Chicago":     {"name": {"uz": "Chikago",       "ru": "Чикаго",        "en": "Chicago"},      "group_link": "https://t.me/uzbekworld_test"},
    "Tashkent":    {"name": {"uz": "Toshkent",      "ru": "Ташкент",       "en": "Tashkent"},     "group_link": "https://t.me/uzbekworld_test"},
}

# ============================================
# УТИЛИТЫ
# ============================================

def load_json(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_lang(user_id):
    s = load_json(USER_SETTINGS_FILE)
    return s.get(str(user_id), {}).get("language")

def set_user_lang(user_id, lang):
    s = load_json(USER_SETTINGS_FILE)
    s.setdefault(str(user_id), {})["language"] = lang
    s[str(user_id)]["updated"] = datetime.now().isoformat()
    save_json(USER_SETTINGS_FILE, s)

def track_interaction(user_id):
    data = load_json(KPI_DATA_FILE)
    data.setdefault("interactions", {})[str(user_id)] = datetime.now().isoformat()
    save_json(KPI_DATA_FILE, data)

def is_admin(user_id):
    return int(user_id) in ADMIN_USER_IDS

# ============================================
# KPI ОТЧЁТ
# ============================================

async def build_war_room_report():
    """Строит WAR ROOM отчёт на основе реальных данных"""
    today = date.today().strftime("%d.%m.%Y")
    data = load_json(KPI_DATA_FILE)
    
    # TG Members — реальный запрос
    try:
        bot = Bot(token=BOT_TOKEN)
        members = await bot.get_chat_member_count(chat_id=CHANNEL_ID)
    except Exception:
        members = None
    
    # Active % — взаимодействия за 24ч
    now = datetime.now()
    interactions = data.get("interactions", {})
    active_24h = sum(
        1 for ts in interactions.values()
        if datetime.fromisoformat(ts) > now - timedelta(days=1)
    )
    active_pct = round(active_24h / max(members, 1) * 100, 1) if members else "N/A"
    
    def indicator(val, green, yellow):
        if val == "N/A":
            return "⚪️"
        return "🟢" if val >= green else ("🟡" if val >= yellow else "🔴")
    
    members_str = f"{members}" if members else "данные недоступны"
    
    days = get_days_until_first_match()
    priority = (
        "Активизировать рост подписчиков" if (members or 0) < 500
        else f"Готовиться к матчу с Португалией ({days} дней)"
    )
    
    report = (
        f"📊 {today} WAR ROOM\n\n"
        f"👥 TG Members: {members_str} {indicator(members or 0, 1000, 300)}\n"
        f"🔥 Active %: {active_pct}% {indicator(active_24h, 20, 5)}\n"
        f"🎉 Watch Parties: [интеграция с Airtable не подключена]\n"
        f"🏆 Founders Apps: [интеграция с Airtable не подключена]\n"
        f"🌍 Countries: [интеграция с Airtable не подключена]\n"
        f"⚠️ Red flags: {'Низкие просмотры' if (members or 0) < 100 else 'NONE'}\n"
        f"⚡️ Priority today: {priority}"
    )
    return report

async def send_war_room_to_admins():
    """Отправляет WAR ROOM всем администраторам"""
    report = await build_war_room_report()
    bot = Bot(token=BOT_TOKEN)
    for admin_id in ADMIN_USER_IDS:
        try:
            await bot.send_message(chat_id=admin_id, text=report)
            print(f"✅ WAR ROOM → admin {admin_id}")
        except Exception as e:
            print(f"❌ WAR ROOM send error ({admin_id}): {e}")

# ============================================
# АВТОПОСТИНГ — ГЛАВНАЯ ЛОГИКА
# ============================================

async def run_auto_post():
    """
    Главная функция публикации.
    Приоритет: реальные новости → countdown (1 раз/сутки) → пропуск.
    Никакой отсебятины.
    """
    print(f"\n[{datetime.now():%H:%M:%S}] 🔍 Ищем контент для публикации...")
    bot = Bot(token=BOT_TOKEN)
    
    # Загружаем новости
    articles = fetch_all_news()
    print(f"  Найдено {len(articles)} релевантных новостей")
    
    posted = False
    for article in articles:
        # Claude обязателен — если недоступен, возвращает None → пропускаем
        post_text = format_news_post(article, lang="uz")
        if not post_text:
            print(f"  ⏭ Claude недоступен: {article['title'][:50]}")
            continue

        dup, reason = is_duplicate(post_text)
        if dup:
            print(f"  ⛔ Дубликат ({reason}): {article['title'][:60]}")
            continue

        try:
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text=post_text,
                parse_mode="HTML",
                disable_web_page_preview=False,
            )
            mark_published(post_text, source_url=article.get("url", ""))
            print(f"  ✅ Опубликовано: {article['title'][:60]}")
            posted = True
            break
        except Exception as e:
            print(f"  ❌ Ошибка публикации: {e}")
    
    if not posted:
        # Countdown — только 1 раз в сутки
        last_cd = get_last_countdown_time()
        if last_cd is None or (datetime.now() - last_cd).total_seconds() > 86400:
            days = get_days_until_first_match()
            if days > 0:
                cd_post = format_countdown_post(days, lang="uz")
                dup, _ = is_duplicate(cd_post)
                if not dup:
                    try:
                        await bot.send_message(
                            chat_id=CHANNEL_ID,
                            text=cd_post,
                            parse_mode="HTML",
                        )
                        mark_published(cd_post)
                        print(f"  ✅ Countdown опубликован ({days} дней)")
                    except Exception as e:
                        print(f"  ❌ Countdown error: {e}")
                    return
        print(f"  ℹ️ Нет новых материалов. Публикация пропущена.")

def auto_post_job():
    asyncio.run(run_auto_post())

def war_room_job():
    asyncio.run(send_war_room_to_admins())

# ============================================
# МЕНЮ
# ============================================

def lang_menu():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="lang_uz"),
        InlineKeyboardButton("🇷🇺 Русский",   callback_data="lang_ru"),
        InlineKeyboardButton("🇬🇧 English",   callback_data="lang_en"),
    ]])

def main_menu(lang, user_id):
    rows = [
        [InlineKeyboardButton(get_text(lang, "schedule"),   callback_data="schedule")],
        [InlineKeyboardButton(get_text(lang, "players"),    callback_data="players")],
        [InlineKeyboardButton(get_text(lang, "standings"),  callback_data="standings")],
        [InlineKeyboardButton(get_text(lang, "watchparty"), callback_data="watchparty")],
        [InlineKeyboardButton(get_text(lang, "join"),       callback_data="join_community")],
        [InlineKeyboardButton(get_text(lang, "settings"),   callback_data="settings")],
    ]
    if is_admin(user_id):
        rows.append([InlineKeyboardButton(get_text(lang, "admin_panel"), callback_data="admin_panel")])
    return InlineKeyboardMarkup(rows)

def players_menu(lang):
    rows = [
        [InlineKeyboardButton(f"{p['emoji']} {p['name'][lang]} ({p['number']})", callback_data=f"player_{p['number']}")]
        for p in PLAYERS
    ]
    rows.append([InlineKeyboardButton(get_text(lang, "back"), callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)

def cities_menu(lang):
    rows = [[InlineKeyboardButton(f"📍 {d['name'][lang]}", callback_data=f"city_{k}")] for k, d in CITIES.items()]
    rows.append([InlineKeyboardButton(get_text(lang, "back"), callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)

def settings_menu(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(lang, "change_language"), callback_data="change_language")],
        [InlineKeyboardButton(get_text(lang, "back"),            callback_data="main_menu")],
    ])

def admin_menu(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(lang, "admin_war_room"), callback_data="admin_war_room")],
        [InlineKeyboardButton(get_text(lang, "admin_stats"),    callback_data="admin_stats")],
        [InlineKeyboardButton(get_text(lang, "back"),           callback_data="main_menu")],
    ])

def back_btn(lang, target="main_menu"):
    return InlineKeyboardMarkup([[InlineKeyboardButton(get_text(lang, "back"), callback_data=target)]])

# ============================================
# КОМАНДЫ
# ============================================

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    track_interaction(user.id)
    lang = get_user_lang(user.id)
    
    if not lang:
        await update.message.reply_text(
            f"👋 {user.first_name}!\n\n🇺🇿 Uzbekistan World Cup 2026\n\nTilni tanlang / Выберите язык:",
            reply_markup=lang_menu()
        )
    else:
        await update.message.reply_text(
            get_text(lang, "main_menu"),
            reply_markup=main_menu(lang, user.id)
        )

async def cmd_schedule(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    track_interaction(user_id)
    lang = get_user_lang(user_id) or "uz"
    
    text = get_text(lang, "schedule_title") + "\n\n"
    for i, m in enumerate(MATCHES, 1):
        dt = datetime.strptime(m["date"], "%Y-%m-%d")
        days = (dt - datetime.now()).days
        text += f"{i}. 🇺🇿 {get_text(lang,'vs')} {m['flag']} {m['opponent'][lang]}\n"
        text += f"   📅 {dt.strftime('%d.%m.%Y')} {m['time']}\n"
        text += f"   📍 {m['city'][lang]}\n"
        if days > 0:
            text += f"   ⏰ {days} {get_text(lang,'days_left')}\n\n"
        elif days == 0:
            text += f"   🔥 {get_text(lang,'today')}\n\n"
        else:
            text += f"   ✅ {get_text(lang,'played')}\n\n"
    
    await update.message.reply_text(text)

# ============================================
# КНОПКИ
# ============================================

async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    track_interaction(uid)
    
    data = q.data
    
    # Выбор языка
    if data.startswith("lang_"):
        lang = data[5:]
        set_user_lang(uid, lang)
        await q.edit_message_text(
            f"{get_text(lang,'language_selected')}\n\n{get_text(lang,'main_menu')}",
            reply_markup=main_menu(lang, uid)
        )
        return
    
    lang = get_user_lang(uid) or "uz"
    
    if data == "main_menu":
        await q.edit_message_text(get_text(lang, "main_menu"), reply_markup=main_menu(lang, uid))
    
    elif data == "schedule":
        text = get_text(lang, "schedule_title") + "\n\n"
        for i, m in enumerate(MATCHES, 1):
            dt = datetime.strptime(m["date"], "%Y-%m-%d")
            days = (dt - datetime.now()).days
            text += f"{i}. 🇺🇿 {get_text(lang,'vs')} {m['flag']} {m['opponent'][lang]}\n"
            text += f"📅 {dt.strftime('%d.%m.%Y')} {m['time']}  📍 {m['city'][lang]}\n"
            suffix = f"⏰ {days} {get_text(lang,'days_left')}" if days > 0 else (f"🔥 {get_text(lang,'today')}" if days == 0 else f"✅ {get_text(lang,'played')}")
            text += f"{suffix}\n\n"
        await q.edit_message_text(text, reply_markup=back_btn(lang))
    
    elif data == "players":
        await q.edit_message_text(get_text(lang, "players_title"), reply_markup=players_menu(lang))
    
    elif data.startswith("player_"):
        num = int(data.split("_")[1])
        p = next((x for x in PLAYERS if x["number"] == num), None)
        if p:
            text = (
                f"{p['emoji']} {p['name'][lang].upper()}\n\n"
                f"🔢 #{p['number']}  |  {p['position'][lang]}\n"
                f"⚽️ {p['club']}  |  🎂 {p['age']} {'yosh' if lang=='uz' else 'лет' if lang=='ru' else 'y.o.'}"
            )
            await q.edit_message_text(text, reply_markup=back_btn(lang, "players"))
    
    elif data == "standings":
        await q.edit_message_text(get_text(lang, "standings_title"), reply_markup=back_btn(lang))
    
    elif data == "watchparty":
        await q.edit_message_text(get_text(lang, "watchparty_title"), reply_markup=cities_menu(lang))
    
    elif data == "join_community":
        await q.edit_message_text(get_text(lang, "join_title"), reply_markup=cities_menu(lang))
    
    elif data.startswith("city_"):
        city_key = "_".join(data.split("_")[1:])
        city = CITIES.get(city_key, {})
        text = f"📍 {city.get('name',{}).get(lang, city_key)}\n\nGroup: {city.get('group_link','—')}"
        await q.edit_message_text(text, reply_markup=back_btn(lang, "watchparty"))
    
    elif data == "settings":
        await q.edit_message_text(get_text(lang, "settings_title"), reply_markup=settings_menu(lang))
    
    elif data == "change_language":
        await q.edit_message_text("🌐 Choose language:", reply_markup=lang_menu())
    
    # ---- ADMIN ONLY ----
    elif data == "admin_panel":
        if not is_admin(uid):
            await q.answer(get_text(lang, "no_access"), show_alert=True)
            return
        await q.edit_message_text(f"🔐 {get_text(lang,'admin_panel')}", reply_markup=admin_menu(lang))
    
    elif data == "admin_war_room":
        if not is_admin(uid):
            await q.answer(get_text(lang, "no_access"), show_alert=True)
            return
        report = await build_war_room_report()
        await q.edit_message_text(
            report,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(lang, "refresh"), callback_data="admin_war_room")],
                [InlineKeyboardButton(get_text(lang, "back"), callback_data="admin_panel")],
            ])
        )
    
    elif data == "admin_stats":
        if not is_admin(uid):
            await q.answer(get_text(lang, "no_access"), show_alert=True)
            return
        kpi = load_json(KPI_DATA_FILE)
        interactions = kpi.get("interactions", {})
        total = len(interactions)
        now = datetime.now()
        active_24 = sum(1 for ts in interactions.values() if datetime.fromisoformat(ts) > now - timedelta(days=1))
        text = (
            f"📈 {get_text(lang,'admin_stats')}\n\n"
            f"👥 Всего пользователей: {total}\n"
            f"📊 Активны за 24ч: {active_24}\n"
            f"📅 Дата: {datetime.now():%d.%m.%Y %H:%M}"
        )
        await q.edit_message_text(text, reply_markup=back_btn(lang, "admin_panel"))

# ============================================
# ПЛАНИРОВЩИК
# ============================================

def run_scheduler():
    # Публикация каждые N минут
    schedule.every(POST_INTERVAL_MINUTES).minutes.do(auto_post_job)
    # WAR ROOM каждый день в 09:00
    schedule.every().day.at("09:00").do(war_room_job)
    print(f"⏰ Scheduler: post every {POST_INTERVAL_MINUTES}min, WAR ROOM at 09:00")
    while True:
        schedule.run_pending()
        time.sleep(1)

# ============================================
# ЗАПУСК
# ============================================

def main():
    print("🚀 UzbekWorldCup Bot (new instance) starting...")
    print(f"📢 Channel : {CHANNEL_ID}")
    print(f"🔑 Token   : {BOT_TOKEN[:20]}...")
    print(f"👥 Admins  : {ADMIN_USER_IDS}")
    print(f"🌐 Languages: uz / ru / en\n")
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("schedule", cmd_schedule))
    app.add_handler(CallbackQueryHandler(on_button))
    
    threading.Thread(target=run_scheduler, daemon=True).start()
    
    print("✅ Bot is running!\n")
    app.run_polling()

if __name__ == "__main__":
    main()
