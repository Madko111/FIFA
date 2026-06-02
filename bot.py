import os
import json
import time
from datetime import datetime, timedelta, date
import schedule
import asyncio
import threading
from dotenv import load_dotenv
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    CallbackQueryHandler,
    ContextTypes
)
from translations import get_text

# Загружаем .env
load_dotenv()

# ============================================
# НАСТРОЙКИ
# ============================================
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
ADMIN_USER_IDS = [int(uid.strip()) for uid in os.getenv('ADMIN_USER_ID', '').split(',') if uid.strip()]
POST_INTERVAL_MINUTES = int(os.getenv('POST_INTERVAL_MINUTES', '30'))

# Файлы данных
KPI_DATA_FILE = "kpi_data.json"
USER_SETTINGS_FILE = "user_settings.json"

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
    "Houston": {"name": {"uz": "Hyuston", "ru": "Хьюстон", "en": "Houston"}, "group_link": "https://t.me/+example_houston"},
    "New York": {"name": {"uz": "Nyu-York", "ru": "Нью-Йорк", "en": "New York"}, "group_link": "https://t.me/+example_nyc"},
    "Los Angeles": {"name": {"uz": "Los-Anjeles", "ru": "Лос-Анджелес", "en": "Los Angeles"}, "group_link": "https://t.me/+example_la"},
    "Chicago": {"name": {"uz": "Chikago", "ru": "Чикаго", "en": "Chicago"}, "group_link": "https://t.me/+example_chicago"},
    "Tashkent": {"name": {"uz": "Toshkent", "ru": "Ташкент", "en": "Tashkent"}, "group_link": "https://t.me/+example_tashkent"},
}

# ============================================
# СИСТЕМА ЯЗЫКОВ
# ============================================

def load_user_settings():
    """Загружает настройки пользователей"""
    if os.path.exists(USER_SETTINGS_FILE):
        try:
            with open(USER_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_user_settings(settings):
    """Сохраняет настройки пользователей"""
    with open(USER_SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

def get_user_language(user_id):
    """Получает язык пользователя"""
    settings = load_user_settings()
    return settings.get(str(user_id), {}).get('language', None)

def set_user_language(user_id, language):
    """Устанавливает язык пользователя"""
    settings = load_user_settings()
    if str(user_id) not in settings:
        settings[str(user_id)] = {}
    settings[str(user_id)]['language'] = language
    settings[str(user_id)]['last_updated'] = datetime.now().isoformat()
    save_user_settings(settings)

# ============================================
# KPI СИСТЕМА
# ============================================

def load_kpi_data():
    """Загружает KPI данные"""
    if os.path.exists(KPI_DATA_FILE):
        try:
            with open(KPI_DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {"daily_stats": {}, "user_interactions": {}}
    return {"daily_stats": {}, "user_interactions": {}}

def save_kpi_data(data):
    """Сохраняет KPI данные"""
    with open(KPI_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def track_user_interaction(user_id):
    """Отслеживает взаимодействие"""
    data = load_kpi_data()
    data['user_interactions'][str(user_id)] = datetime.now().isoformat()
    save_kpi_data(data)

# ============================================
# МЕНЮ
# ============================================

def get_language_menu():
    """Меню выбора языка"""
    keyboard = [
        [InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="lang_uz")],
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_main_menu(lang, is_admin=False):
    """Главное меню"""
    keyboard = [
        [InlineKeyboardButton(get_text(lang, 'schedule'), callback_data="schedule")],
        [InlineKeyboardButton(get_text(lang, 'players'), callback_data="players")],
        [InlineKeyboardButton(get_text(lang, 'standings'), callback_data="standings")],
        [InlineKeyboardButton(get_text(lang, 'watchparty'), callback_data="watchparty")],
        [InlineKeyboardButton(get_text(lang, 'join'), callback_data="join_community")],
        [InlineKeyboardButton(get_text(lang, 'settings'), callback_data="settings")],
    ]
    
    if is_admin:
        keyboard.append([InlineKeyboardButton(get_text(lang, 'admin_panel'), callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(keyboard)

def get_players_menu(lang):
    """Меню игроков"""
    keyboard = []
    for player in PLAYERS:
        keyboard.append([InlineKeyboardButton(
            f"{player['emoji']} {player['name'][lang]} ({player['number']})",
            callback_data=f"player_{player['number']}"
        )])
    keyboard.append([InlineKeyboardButton(get_text(lang, 'back'), callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_cities_menu(lang):
    """Меню городов"""
    keyboard = []
    for city_en, city_data in CITIES.items():
        keyboard.append([InlineKeyboardButton(
            f"📍 {city_data['name'][lang]}",
            callback_data=f"city_{city_en}"
        )])
    keyboard.append([InlineKeyboardButton(get_text(lang, 'back'), callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_settings_menu(lang):
    """Меню настроек"""
    keyboard = [
        [InlineKeyboardButton(get_text(lang, 'change_language'), callback_data="change_language")],
        [InlineKeyboardButton(get_text(lang, 'back'), callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_menu(lang):
    """Админ-панель"""
    keyboard = [
        [InlineKeyboardButton(get_text(lang, 'admin_war_room'), callback_data="admin_war_room")],
        [InlineKeyboardButton(get_text(lang, 'admin_stats'), callback_data="admin_stats")],
        [InlineKeyboardButton(get_text(lang, 'back'), callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

# ============================================
# КОМАНДЫ
# ============================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    user_id = user.id
    
    track_user_interaction(user_id)
    
    # Проверяем, выбран ли язык
    lang = get_user_language(user_id)
    
    if not lang:
        # Первый запуск - выбор языка
        await update.message.reply_text(
            get_text('uz', 'welcome', name=user.first_name),
            reply_markup=get_language_menu()
        )
    else:
        # Язык уже выбран - показываем меню
        is_admin = user_id in ADMIN_USER_IDS
        await update.message.reply_text(
            get_text(lang, 'main_menu'),
            reply_markup=get_main_menu(lang, is_admin)
        )

async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Расписание"""
    user_id = update.effective_user.id
    track_user_interaction(user_id)
    lang = get_user_language(user_id) or 'uz'
    
    schedule_text = get_text(lang, 'schedule_title') + "\n\n"
    
    for i, match in enumerate(MATCHES, 1):
        match_date = datetime.strptime(match['date'], '%Y-%m-%d')
        days_until = (match_date - datetime.now()).days
        
        schedule_text += f"{i}. 🇺🇿 {get_text(lang, 'vs')} {match['flag']} {match['opponent'][lang]}\n"
        schedule_text += f"   📅 {match_date.strftime('%d.%m.%Y')} {match['time']}\n"
        schedule_text += f"   📍 {match['city'][lang]}\n"
        
        if days_until > 0:
            schedule_text += f"   ⏰ {days_until} {get_text(lang, 'days_left')}\n\n"
        elif days_until == 0:
            schedule_text += f"   🔥 {get_text(lang, 'today')}\n\n"
        else:
            schedule_text += f"   ✅ {get_text(lang, 'played')}\n\n"
    
    await update.message.reply_text(schedule_text)

# ============================================
# CALLBACK HANDLERS
# ============================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    track_user_interaction(user_id)
    
    # Выбор языка
    if query.data.startswith("lang_"):
        lang = query.data.split("_")[1]
        set_user_language(user_id, lang)
        
        is_admin = user_id in ADMIN_USER_IDS
        
        await query.edit_message_text(
            f"{get_text(lang, 'language_selected')}\n\n{get_text(lang, 'main_menu')}",
            reply_markup=get_main_menu(lang, is_admin)
        )
        return
    
    # Получаем язык пользователя
    lang = get_user_language(user_id) or 'uz'
    is_admin = user_id in ADMIN_USER_IDS
    
    # Главное меню
    if query.data == "main_menu":
        await query.edit_message_text(
            get_text(lang, 'main_menu'),
            reply_markup=get_main_menu(lang, is_admin)
        )
    
    # Расписание
    elif query.data == "schedule":
        schedule_text = get_text(lang, 'schedule_title') + "\n\n"
        for i, match in enumerate(MATCHES, 1):
            match_date = datetime.strptime(match['date'], '%Y-%m-%d')
            days_until = (match_date - datetime.now()).days
            
            schedule_text += f"{i}. 🇺🇿 {get_text(lang, 'vs')} {match['flag']} {match['opponent'][lang]}\n"
            schedule_text += f"📅 {match_date.strftime('%d.%m.%Y')} {match['time']}\n"
            schedule_text += f"📍 {match['city'][lang]}\n"
            if days_until > 0:
                schedule_text += f"⏰ {days_until} {get_text(lang, 'days_left')}\n\n"
        
        await query.edit_message_text(
            schedule_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(get_text(lang, 'back'), callback_data="main_menu")]])
        )
    
    # Игроки
    elif query.data == "players":
        await query.edit_message_text(
            get_text(lang, 'players_title'),
            reply_markup=get_players_menu(lang)
        )
    
    # Игрок
    elif query.data.startswith("player_"):
        player_number = int(query.data.split("_")[1])
        player = next((p for p in PLAYERS if p['number'] == player_number), None)
        
        if player:
            player_text = f"{player['emoji']} {player['name'][lang].upper()}\n\n"
            player_text += f"🔢 #{player['number']}\n"
            player_text += f"📍 {player['position'][lang]}\n"
            player_text += f"⚽️ {player['club']}\n"
            player_text += f"🎂 {player['age']}\n"
            
            await query.edit_message_text(
                player_text,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(get_text(lang, 'back'), callback_data="players")]])
            )
    
    # Таблица
    elif query.data == "standings":
        await query.edit_message_text(
            get_text(lang, 'standings_title'),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(get_text(lang, 'back'), callback_data="main_menu")]])
        )
    
    # Watch Party
    elif query.data == "watchparty":
        await query.edit_message_text(
            get_text(lang, 'watchparty_title'),
            reply_markup=get_cities_menu(lang)
        )
    
    # Город
    elif query.data.startswith("city_"):
        city_en = query.data.split("_")[1]
        city_data = CITIES.get(city_en, {})
        
        city_text = f"📍 {city_data['name'][lang]}\n\n"
        city_text += f"🎉 Watch Party info coming soon!\n\n"
        city_text += f"Group: {city_data.get('group_link', 'Coming soon')}"
        
        await query.edit_message_text(
            city_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(get_text(lang, 'back'), callback_data="watchparty")]])
        )
    
    # Join Community
    elif query.data == "join_community":
        await query.edit_message_text(
            get_text(lang, 'join_title'),
            reply_markup=get_cities_menu(lang)
        )
    
    # Настройки
    elif query.data == "settings":
        await query.edit_message_text(
            get_text(lang, 'settings_title'),
            reply_markup=get_settings_menu(lang)
        )
    
    # Смена языка
    elif query.data == "change_language":
        await query.edit_message_text(
            "🌐 Choose language / Tilni tanlang / Выберите язык:",
            reply_markup=get_language_menu()
        )
    
    # Админ-панель
    elif query.data == "admin_panel":
        if user_id not in ADMIN_USER_IDS:
            await query.answer(get_text(lang, 'no_access'), show_alert=True)
            return
        
        await query.edit_message_text(
            f"🔐 {get_text(lang, 'admin_panel')}",
            reply_markup=get_admin_menu(lang)
        )
    
    # WAR ROOM
    elif query.data == "admin_war_room":
        if user_id not in ADMIN_USER_IDS:
            await query.answer(get_text(lang, 'no_access'), show_alert=True)
            return
        
        war_room_text = f"""📊 {date.today().strftime('%d.%m.%Y')} WAR ROOM

👥 TG Members: [Данные собираются]
🔥 Active %: [Данные собираются]
🎉 Watch Parties: [Требуется Airtable]
🏆 Founders Apps: [Требуется Airtable]
🌍 Countries: [Требуется Airtable]
⚠️ Red flags: NONE
⚡️ Priority today: Подготовка к матчу"""
        
        await query.edit_message_text(
            war_room_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(lang, 'refresh'), callback_data="admin_war_room")],
                [InlineKeyboardButton(get_text(lang, 'back'), callback_data="admin_panel")]
            ])
        )
    
    # Статистика
    elif query.data == "admin_stats":
        if user_id not in ADMIN_USER_IDS:
            await query.answer(get_text(lang, 'no_access'), show_alert=True)
            return
        
        data = load_kpi_data()
        stats_text = f"""📈 {get_text(lang, 'admin_stats')}

👥 Total users: {len(data['user_interactions'])}
📊 Active (24h): {len([u for u, t in data['user_interactions'].items() if datetime.fromisoformat(t) > datetime.now() - timedelta(days=1)])}"""
        
        await query.edit_message_text(
            stats_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(get_text(lang, 'back'), callback_data="admin_panel")]])
        )

# ============================================
# ЗАПУСК
# ============================================

def main():
    """Главная функция"""
    print("🚀 Bot ishga tushmoqda...")
    print(f"📢 Kanal: {CHANNEL_ID}")
    print(f"👥 Adminlar: {len(ADMIN_USER_IDS)}")
    print(f"🌐 Tillar: O'zbekcha, Русский, English\n")
    
    # Создаем приложение
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("schedule", schedule_command))
    
    # Кнопки
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("✅ Bot ishga tushdi!\n")
    
    # Запуск
    app.run_polling()

if __name__ == "__main__":
    main()
