import os
import json
import time
from datetime import datetime, timedelta, date, time as dtime
import schedule
import asyncio
import threading
from dotenv import load_dotenv
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError, BadRequest
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    CallbackQueryHandler,
    MessageHandler,
    filters,
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
# Чат сообщества для подсчёта реальных участников (по умолчанию — канал)
COMMUNITY_CHAT_ID = os.getenv('COMMUNITY_CHAT_ID', CHANNEL_ID)
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

# Расширенный официальный состав сборной Узбекистана на ЧМ-2026
# (26 игроков, объявлены 2 июня 2026; возраст указан на 03.06.2026)
# Источник: Wikipedia — Uzbekistan national football team, Current squad.
GK = {"uz": "Darvozabon", "ru": "Вратарь", "en": "Goalkeeper"}
DF = {"uz": "Himoyachi", "ru": "Защитник", "en": "Defender"}
MF = {"uz": "Yarim himoyachi", "ru": "Полузащитник", "en": "Midfielder"}
FW = {"uz": "Hujumchi", "ru": "Нападающий", "en": "Forward"}

PLAYERS = [
    # Goalkeepers
    {"name": {"uz": "Utkir Yusupov", "ru": "Уткир Юсупов", "en": "Utkir Yusupov"}, "position": GK, "club": "Navbahor Namangan", "number": 1, "age": 35, "emoji": "🧤"},
    {"name": {"uz": "Abduvohid Nematov", "ru": "Абдувохид Нематов", "en": "Abduvohid Nematov"}, "position": GK, "club": "Nasaf", "number": 12, "age": 25, "emoji": "🧤"},
    {"name": {"uz": "Botirali Ergashev", "ru": "Ботирали Эргашев", "en": "Botirali Ergashev"}, "position": GK, "club": "Neftchi Fergana", "number": 16, "age": 30, "emoji": "🧤"},
    # Defenders
    {"name": {"uz": "Abduqodir Xusanov", "ru": "Абдукодир Хусанов", "en": "Abdukodir Khusanov"}, "position": DF, "club": "Manchester City", "number": 2, "age": 22, "emoji": "🛡"},
    {"name": {"uz": "Xojiakbar Alijonov", "ru": "Ходжиакбар Алижонов", "en": "Khojiakbar Alijonov"}, "position": DF, "club": "Pakhtakor", "number": 3, "age": 29, "emoji": "🛡"},
    {"name": {"uz": "Farrux Sayfiyev", "ru": "Фаррух Сайфиев", "en": "Farrukh Sayfiev"}, "position": DF, "club": "Neftchi Fergana", "number": 4, "age": 35, "emoji": "🛡"},
    {"name": {"uz": "Rustam Ashurmatov", "ru": "Рустам Ашурматов", "en": "Rustam Ashurmatov"}, "position": DF, "club": "Esteghlal", "number": 5, "age": 29, "emoji": "🛡"},
    {"name": {"uz": "Sherzod Nasrullayev", "ru": "Шерзод Насруллаев", "en": "Sherzod Nasrullaev"}, "position": DF, "club": "Pakhtakor", "number": 13, "age": 27, "emoji": "🛡"},
    {"name": {"uz": "Umar Eshmurodov", "ru": "Умар Эшмуродов", "en": "Umar Eshmurodov"}, "position": DF, "club": "Nasaf", "number": 15, "age": 33, "emoji": "🛡"},
    {"name": {"uz": "Abdulla Abdullayev", "ru": "Абдулла Абдуллаев", "en": "Abdulla Abdullaev"}, "position": DF, "club": "Dibba", "number": 18, "age": 28, "emoji": "🛡"},
    {"name": {"uz": "Bexruz Karimov", "ru": "Бехруз Каримов", "en": "Bekhruz Karimov"}, "position": DF, "club": "Surkhon Termiz", "number": 24, "age": 18, "emoji": "🛡"},
    {"name": {"uz": "Avazbek Ulmasaliyev", "ru": "Авазбек Улмасалиев", "en": "Avazbek Ulmasaliev"}, "position": DF, "club": "AGMK", "number": 25, "age": 26, "emoji": "🛡"},
    {"name": {"uz": "Jahongir Urozov", "ru": "Жахонгир Урозов", "en": "Jakhongir Urozov"}, "position": DF, "club": "Dinamo Samarqand", "number": 26, "age": 22, "emoji": "🛡"},
    # Midfielders
    {"name": {"uz": "Akmal Mozgovoy", "ru": "Акмаль Мозговой", "en": "Akmal Mozgovoy"}, "position": MF, "club": "Pakhtakor", "number": 6, "age": 27, "emoji": "🎯"},
    {"name": {"uz": "Otabek Shukurov", "ru": "Отабек Шукуров", "en": "Otabek Shukurov"}, "position": MF, "club": "Baniyas", "number": 7, "age": 29, "emoji": "🎯"},
    {"name": {"uz": "Jamshid Iskanderov", "ru": "Жамшид Искандеров", "en": "Jamshid Iskanderov"}, "position": MF, "club": "Neftchi Fergana", "number": 8, "age": 32, "emoji": "🎯"},
    {"name": {"uz": "Odiljon Hamrobekov", "ru": "Одильжон Хамробеков", "en": "Odiljon Hamrobekov"}, "position": MF, "club": "Tractor", "number": 9, "age": 30, "emoji": "🎯"},
    {"name": {"uz": "Jaloliddin Masharipov", "ru": "Жалолиддин Машарипов", "en": "Jaloliddin Masharipov"}, "position": MF, "club": "Esteghlal", "number": 10, "age": 32, "emoji": "🎯"},
    {"name": {"uz": "Oston Urunov", "ru": "Остон Урунов", "en": "Oston Urunov"}, "position": MF, "club": "Persepolis", "number": 11, "age": 25, "emoji": "🎯"},
    {"name": {"uz": "Dostonbek Hamdamov", "ru": "Достонбек Хамдамов", "en": "Dostonbek Khamdamov"}, "position": MF, "club": "Pakhtakor", "number": 17, "age": 29, "emoji": "🎯"},
    {"name": {"uz": "Azizjon G'aniyev", "ru": "Азизжон Ганиев", "en": "Azizjon Ganiev"}, "position": MF, "club": "Al Bataeh", "number": 19, "age": 28, "emoji": "🎯"},
    {"name": {"uz": "Abbosbek Fayzullayev", "ru": "Аббосбек Файзуллаев", "en": "Abbosbek Fayzullaev"}, "position": MF, "club": "İstanbul Başakşehir", "number": 22, "age": 22, "emoji": "🎯"},
    {"name": {"uz": "Sherzod Esanov", "ru": "Шерзод Эсанов", "en": "Sherzod Esanov"}, "position": MF, "club": "Bukhara", "number": 23, "age": 23, "emoji": "🎯"},
    # Forwards
    {"name": {"uz": "Eldor Shomurodov (K)", "ru": "Эльдор Шомуродов (К)", "en": "Eldor Shomurodov (C)"}, "position": FW, "club": "İstanbul Başakşehir", "number": 14, "age": 30, "emoji": "⚡️"},
    {"name": {"uz": "Azizbek Amonov", "ru": "Азизбек Амонов", "en": "Azizbek Amonov"}, "position": FW, "club": "Dinamo Samarqand", "number": 20, "age": 28, "emoji": "⚽️"},
    {"name": {"uz": "Igor Sergeyev", "ru": "Игорь Сергеев", "en": "Igor Sergeev"}, "position": FW, "club": "Persepolis", "number": 21, "age": 33, "emoji": "⚽️"},
]

CITIES = {
    "Houston": {"name": {"uz": "Hyuston", "ru": "Хьюстон", "en": "Houston"}, "group_link": "https://t.me/+example_houston"},
    "New York": {"name": {"uz": "Nyu-York", "ru": "Нью-Йорк", "en": "New York"}, "group_link": "https://t.me/+example_nyc"},
    "Los Angeles": {"name": {"uz": "Los-Anjeles", "ru": "Лос-Анджелес", "en": "Los Angeles"}, "group_link": "https://t.me/+example_la"},
    "Chicago": {"name": {"uz": "Chikago", "ru": "Чикаго", "en": "Chicago"}, "group_link": "https://t.me/+example_chicago"},
    "Tashkent": {"name": {"uz": "Toshkent", "ru": "Ташкент", "en": "Tashkent"}, "group_link": "https://t.me/+example_tashkent"},
}

# Веб-сайт и программы
WEBSITE_URL = "https://uzbekworldclub.com"

# Каждая программа: ключ описания + ссылка на форму регистрации на сайте
PROGRAMS = {
    "founders": {"label_key": "prog_founders", "desc_key": "prog_founders_desc", "url": f"{WEBSITE_URL}/founders-davra"},
    "stadium":  {"label_key": "prog_stadium",  "desc_key": "prog_stadium_desc",  "url": f"{WEBSITE_URL}/stadium-davra"},
    "captain":  {"label_key": "prog_captain",  "desc_key": "prog_captain_desc",  "url": f"{WEBSITE_URL}/city-captain"},
    "volunteer":{"label_key": "prog_volunteer","desc_key": "prog_volunteer_desc","url": f"{WEBSITE_URL}/volunteer"},
    "passport": {"label_key": "prog_passport", "desc_key": "prog_passport_desc", "url": f"{WEBSITE_URL}/fan-passport"},
}

# Цели из graphify (War Room Dashboard стандарт)
WAR_ROOM_TARGETS = {
    "telegram": 10000,    # Telegram Target 10K
    "watch": "100+",      # Watch Parties 100+
    "captains": 50,       # City Captains 50
    "founders": 100,      # Founders Davra 100
    "volunteers": 20,     # Volunteers 20
    "visitors": "50K+",   # Website Visitors 50K+
}

# Фаза проекта (по таймлайну graphify)
PROJECT_PHASE = "🟢 LAUNCH"

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
    """Главное меню: короткие пункты в 2 столбца, длинные — на всю ширину."""
    keyboard = [
        [
            InlineKeyboardButton(get_text(lang, 'players'), callback_data="players"),
            InlineKeyboardButton(get_text(lang, 'standings'), callback_data="standings"),
        ],
        [
            InlineKeyboardButton(get_text(lang, 'watchparty'), callback_data="watchparty"),
            InlineKeyboardButton(get_text(lang, 'programs'), callback_data="programs"),
        ],
        # Длинные подписи — отдельными строками, чтобы текст не обрезался
        [InlineKeyboardButton(get_text(lang, 'schedule'), callback_data="schedule")],
        [InlineKeyboardButton(get_text(lang, 'join'), callback_data="join_community")],
        [InlineKeyboardButton(get_text(lang, 'settings'), callback_data="settings")],
    ]
    
    if is_admin:
        keyboard.append([InlineKeyboardButton(get_text(lang, 'admin_panel'), callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(keyboard)

def _chunk_rows(buttons, per_row=2):
    """Группирует кнопки в строки по per_row штук."""
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]

def get_players_menu(lang):
    """Меню игроков: по одному в строке — длинные имена не обрезаются."""
    keyboard = [
        [InlineKeyboardButton(
            f"{player['emoji']} #{player['number']} {player['name'][lang]}",
            callback_data=f"player_{player['number']}"
        )]
        for player in PLAYERS
    ]
    keyboard.append([InlineKeyboardButton(get_text(lang, 'back'), callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_cities_menu(lang):
    """Меню городов (2 столбца)"""
    buttons = [
        InlineKeyboardButton(
            f"📍 {city_data['name'][lang]}",
            callback_data=f"city_{city_en}"
        )
        for city_en, city_data in CITIES.items()
    ]
    keyboard = _chunk_rows(buttons, 2)
    keyboard.append([InlineKeyboardButton(get_text(lang, 'back'), callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_programs_menu(lang):
    """Меню программ: по одному в строке — подписи не обрезаются."""
    keyboard = [
        [InlineKeyboardButton(
            get_text(lang, prog['label_key']),
            callback_data=f"prog_{key}"
        )]
        for key, prog in PROGRAMS.items()
    ]
    keyboard.append([InlineKeyboardButton(get_text(lang, 'back'), callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_program_detail_menu(lang, key):
    """Меню деталей программы: регистрация + назад"""
    prog = PROGRAMS[key]
    keyboard = [
        [InlineKeyboardButton(get_text(lang, 'register'), url=prog['url'])],
        [InlineKeyboardButton(get_text(lang, 'back'), callback_data="programs")],
    ]
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
            reply_markup=get_main_menu(lang, is_admin),
            parse_mode="Markdown"
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
    
    try:
        await _handle_button(query)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise

async def _handle_button(query):
    """Внутренний обработчик кнопок."""
    user_id = query.from_user.id
    track_user_interaction(user_id)
    
    # Выбор языка — сразу показываем главное меню без экрана "язык выбран"
    if query.data.startswith("lang_"):
        lang = query.data.split("_")[1]
        set_user_language(user_id, lang)
        
        is_admin = user_id in ADMIN_USER_IDS
        
        await query.edit_message_text(
            get_text(lang, 'main_menu'),
            reply_markup=get_main_menu(lang, is_admin),
            parse_mode="Markdown"
        )
        return
    
    # Получаем язык пользователя
    lang = get_user_language(user_id) or 'uz'
    is_admin = user_id in ADMIN_USER_IDS
    
    # Главное меню
    if query.data == "main_menu":
        await query.edit_message_text(
            get_text(lang, 'main_menu'),
            reply_markup=get_main_menu(lang, is_admin),
            parse_mode="Markdown"
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
    
    # Программы (список)
    elif query.data == "programs":
        await query.edit_message_text(
            get_text(lang, 'programs_title'),
            reply_markup=get_programs_menu(lang)
        )
    
    # Программа (детали)
    elif query.data.startswith("prog_"):
        key = query.data.split("_", 1)[1]
        prog = PROGRAMS.get(key)
        if prog:
            await query.edit_message_text(
                get_text(lang, prog['desc_key']),
                reply_markup=get_program_detail_menu(lang, key)
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
        
        await query.edit_message_text(
            await build_war_room(lang, query.get_bot()),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(lang, 'refresh'), callback_data="admin_war_room")],
                [InlineKeyboardButton(get_text(lang, 'back'), callback_data="admin_panel")]
            ]),
            parse_mode="Markdown"
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
# ПРИВЕТСТВИЕ НОВЫХ УЧАСТНИКОВ
# ============================================

async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствует новых участников группы/канала на 3 языках."""
    if not update.message or not update.message.new_chat_members:
        return

    bot_username = context.bot.username
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        name = member.first_name or "friend"
        # Многоязычное приветствие (uz / ru / en вместе)
        text = (
            f"{get_text('uz', 'new_member', name=name, bot_username=bot_username)}\n\n"
            f"────────\n\n"
            f"{get_text('ru', 'new_member', name=name, bot_username=bot_username)}\n\n"
            f"────────\n\n"
            f"{get_text('en', 'new_member', name=name, bot_username=bot_username)}"
        )
        try:
            await update.message.reply_text(text)
        except TelegramError as e:
            print(f"⚠️ Не удалось отправить приветствие: {e}")

# ============================================
# АВТОПОСТИНГ (JobQueue)
# ============================================

def days_until_first_match():
    """Сколько дней до первого матча."""
    first = datetime.strptime(MATCHES[0]['date'], '%Y-%m-%d')
    return (first - datetime.now()).days

# ============================================
# WAR ROOM (стандарт graphify)
# ============================================

def today_priority(lang, days):
    """Приоритет дня по фазе обратного отсчёта."""
    priorities = {
        'uz': {
            'far': "Telegram o'sishi va kontent mashinasi",
            'mid': "Watch Party va shahar kapitanlari faollashtirish",
            'near': "Match day tayyorgarligi va Stadium Davra",
        },
        'ru': {
            'far': "Рост Telegram и контент-машина",
            'mid': "Активация Watch Party и капитанов городов",
            'near': "Подготовка к матчу и Stadium Davra",
        },
        'en': {
            'far': "Telegram growth and content machine",
            'mid': "Activate Watch Parties and City Captains",
            'near': "Match-day prep and Stadium Davra",
        },
    }
    p = priorities.get(lang, priorities['en'])
    if days > 10:
        return p['far']
    elif days > 3:
        return p['mid']
    return p['near']

async def get_community_member_count(bot):
    """Возвращает реальное число участников чата сообщества (или None)."""
    try:
        return await bot.get_chat_member_count(COMMUNITY_CHAT_ID)
    except TelegramError as e:
        print(f"⚠️ Не удалось получить число участников сообщества: {e}")
        return None

async def build_war_room(lang, bot=None):
    """Собирает War Room по стандарту graphify: live-данные + цели."""
    data = load_kpi_data()
    interactions = data.get('user_interactions', {})
    active_24h = len([
        u for u, t in interactions.items()
        if datetime.fromisoformat(t) > datetime.now() - timedelta(days=1)
    ])
    days = days_until_first_match()
    manual = get_text(lang, 'wr_manual')

    # Реальное число участников Telegram-сообщества
    members = await get_community_member_count(bot) if bot is not None else None
    members_str = f"{members:,}" if members is not None else "—"

    lines = [
        f"*{get_text(lang, 'wr_title')}* — {date.today().strftime('%d.%m.%Y')}",
        "",
        f"⏱ {get_text(lang, 'wr_days')}: *{max(days, 0)}* {get_text(lang, 'wr_days_unit')}",
        f"📍 {get_text(lang, 'wr_phase')}: {PROJECT_PHASE}",
        "",
        f"👥 {get_text(lang, 'wr_telegram')}: *{members_str}* / {WAR_ROOM_TARGETS['telegram']:,}",
        f"🔥 {get_text(lang, 'wr_active')}: *{active_24h}*",
        f"🎉 {get_text(lang, 'wr_watch')}: 0 / {WAR_ROOM_TARGETS['watch']} _({manual})_",
        f"🧭 {get_text(lang, 'wr_captains')}: 0 / {WAR_ROOM_TARGETS['captains']} _({manual})_",
        f"👑 {get_text(lang, 'wr_founders')}: 0 / {WAR_ROOM_TARGETS['founders']} _({manual})_",
        f"🤝 {get_text(lang, 'wr_volunteers')}: 0 / {WAR_ROOM_TARGETS['volunteers']} _({manual})_",
        f"🌐 {get_text(lang, 'wr_visitors')}: — / {WAR_ROOM_TARGETS['visitors']} _({manual})_",
        "",
        f"⚠️ {get_text(lang, 'wr_redflags')}: {get_text(lang, 'wr_none')}",
        f"⚡️ {get_text(lang, 'wr_priority')}: {today_priority(lang, days)}",
    ]
    return "\n".join(lines)

async def post_countdown(context: ContextTypes.DEFAULT_TYPE):
    """Публикует обратный отсчёт в канал (на 3 языках)."""
    days = days_until_first_match()
    if days < 0:
        return  # турнир начался

    channel_handle = CHANNEL_ID.lstrip('@')
    text = (
        f"{get_text('uz', 'countdown_post', days=days, channel=channel_handle)}\n\n"
        f"────────\n\n"
        f"{get_text('ru', 'countdown_post', days=days, channel=channel_handle)}\n\n"
        f"────────\n\n"
        f"{get_text('en', 'countdown_post', days=days, channel=channel_handle)}"
    )
    try:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=text)
        print(f"📢 Countdown posted: {days} days left")
    except TelegramError as e:
        print(f"⚠️ Не удалось опубликовать пост в канал: {e}")

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
    
    # Приветствие новых участников
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))
    
    # Автопостинг: ежедневный обратный отсчёт в канал
    job_queue = app.job_queue
    if job_queue is not None:
        # Каждый день в 10:00 по серверному времени
        job_queue.run_daily(post_countdown, time=dtime(hour=10, minute=0))
        print("⏰ Avtoposting yoqildi (har kuni 10:00 da countdown)")
    else:
        print("⚠️ JobQueue mavjud emas — avtoposting o'chirilgan")
    
    print("✅ Bot ishga tushdi!\n")
    
    # Запуск
    app.run_polling()

if __name__ == "__main__":
    main()
