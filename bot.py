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

# Загружаем .env (override=True — .env приоритетнее системных переменных окружения)
load_dotenv(override=True)

# ============================================
# НАСТРОЙКИ
# ============================================
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
# TEMPORARY DEBUG: force test channel regardless of env var
COMMUNITY_CHAT_ID = '@uzbekworld_test'
ADMIN_USER_IDS = [int(uid.strip()) for uid in os.getenv('ADMIN_USER_ID', '').split(',') if uid.strip()]
POST_INTERVAL_MINUTES = int(os.getenv('POST_INTERVAL_MINUTES', '30'))

# AI-чат (Gemini сейчас; Claude — позже, после одобрения менеджера)
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')  # запасной провайдер
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash-lite')
CLAUDE_MODEL = os.getenv('AI_MODEL', 'claude-haiku-4-5-20251001')
# Активен AI, если задан хотя бы один ключ
AI_ENABLED = bool(GEMINI_API_KEY or ANTHROPIC_API_KEY)

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
# AI-ЧАТ (Claude)
# ============================================

# Пользователи, ожидающие ввода вопроса для AI (нажали "Ask AI" в меню)
_AI_WAITING = set()

# Ленивая инициализация клиентов
_gemini_client = None
_anthropic_client = None

def _get_gemini_client():
    """Возвращает (и кэширует) клиент Gemini, или None если ключ не задан."""
    global _gemini_client
    if not GEMINI_API_KEY:
        return None
    if _gemini_client is None:
        try:
            from google import genai
            _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        except Exception as e:
            print(f"⚠️ Gemini klient yaratilmadi: {e}")
            return None
    return _gemini_client

def _get_anthropic_client():
    """Возвращает (и кэширует) клиент Anthropic, или None если ключ не задан."""
    global _anthropic_client
    if not ANTHROPIC_API_KEY:
        return None
    if _anthropic_client is None:
        try:
            import anthropic
            _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        except Exception as e:
            print(f"⚠️ Anthropic klient yaratilmadi: {e}")
            return None
    return _anthropic_client

def _build_ai_facts():
    """Собирает актуальные факты о клубе из данных бота для системного промпта."""
    lines = []
    lines.append("MATCHES (Uzbekistan, World Cup 2026, Group K):")
    for m in MATCHES:
        lines.append(
            f"- {m['date']} {m['time']} vs {m['opponent']['en']} "
            f"in {m['city']['en']} ({m['stadium']})"
        )
    lines.append("")
    lines.append("PROGRAMS people can join (registration on the website):")
    prog_names = {
        "founders": "Founders Davra (business leaders network)",
        "stadium": "Stadium Davra (organized stadium fan sections)",
        "captain": "City Captain (lead the fan community in a city)",
        "volunteer": "Volunteer program",
        "passport": "Fan Passport",
    }
    for key in PROGRAMS:
        lines.append(f"- {prog_names.get(key, key)}")
    lines.append("")
    lines.append(f"Squad: full official 26-man Uzbekistan World Cup 2026 roster, captain Eldor Shomurodov (#14), head coach Fabio Cannavaro.")
    lines.append(f"Goal: build the largest organized Uzbek fan community for the World Cup 2026 — Uzbekistan's first-ever World Cup.")
    lines.append(f"Website: {WEBSITE_URL}")
    lines.append("")
    lines.append("LOCALIZED PROGRAM NAMES (use exactly these when answering — never invent translations):")
    lines.append("- Volunteer program → Uzbek: 'Volontyorlik' | Russian: 'Волонтёрство' | English: 'Volunteer program'")
    lines.append("- Founders Davra, Stadium Davra, City Captain, Fan Passport → keep the original names in all languages")
    return "\n".join(lines)

LANG_NAMES = {"uz": "Uzbek", "ru": "Russian", "en": "English"}

def _build_ai_system_prompt(lang, is_admin=False):
    """Системный промпт: тема, тон, язык, отказ от офтопа."""
    lang_name = LANG_NAMES.get(lang, "English")
    facts = _build_ai_facts()
    admin_note = ""
    if is_admin:
        data = load_kpi_data()
        total_users = len(data.get('user_interactions', {}))
        active_24h = len([
            u for u, t in data.get('user_interactions', {}).items()
            if datetime.fromisoformat(t) > datetime.now() - timedelta(days=1)
        ])
        admin_note = (
            "\n\nADMIN MODE: This user is an admin. You may also answer questions about "
            f"internal community stats. Current bot stats: total tracked users = {total_users}, "
            f"active in last 24h = {active_24h}. Targets: 10,000 Telegram members, 100+ watch "
            "parties, 50 city captains, 100 Founders Davra, 20 volunteers."
        )
    return (
        "You are the AI assistant for 'Uzbek World Club', the official Uzbek fan community "
        "for the FIFA World Cup 2026.\n\n"
        "STRICT SCOPE: You may ONLY answer questions about (1) Uzbek World Club itself, "
        "(2) the FIFA World Cup in general, and (3) the FIFA World Cup 2026 (teams, matches, "
        "schedule, host cities, Uzbekistan's national team). If a question is outside these "
        "topics, do NOT answer it — instead reply with exactly this sentence (translated to the "
        f"user's language): 'Sorry, my knowledge base only covers Uzbek World Club, the World "
        "Cup, and World Cup 2026.'\n\n"
        f"ALWAYS answer in {lang_name}.\n"
        "Keep answers SHORT, CLEAR and CONCISE — 1-3 sentences, no fluff.\n"
        "Use the facts below when relevant. If you don't know a specific fact, say so briefly.\n"
        "WEBSITE LINK RULE: Whenever you mention our website, registration, joining a program, "
        "or anything that points users to our site, render the URL as a Telegram Markdown link "
        f"using this exact format: [Uzbek World Club]({WEBSITE_URL}). Never paste the raw URL "
        "as plain text and never use any other anchor text.\n\n"
        f"FACTS:\n{facts}"
        f"{admin_note}"
    )

# Темо-фильтр для пассивного триггера в группах (грубая проверка ключевых слов)
AI_TOPIC_KEYWORDS = [
    "world cup", "worldcup", "fifa", "uzbek", "o'zbek", "узбек", "uzbekistan",
    "chempionat", "чемпионат", "jch", "чм", "watch party", "davra", "captain",
    "shomurodov", "cannavaro", "portugal", "colombia", "congo", "match", "matn",
    "o'yin", "матч", "stadium", "stadion", "стадион", "founders", "volunteer",
    "volontyor", "волонтёр", "passport", "passportt", "qachon", "когда", "when",
]

def _looks_on_topic(text):
    """Грубая эвристика: похоже ли сообщение на наш топик."""
    t = (text or "").lower()
    return any(k in t for k in AI_TOPIC_KEYWORDS)

async def _ask_gemini(question, system_prompt):
    """Запрос к Gemini. Возвращает текст или None."""
    client = _get_gemini_client()
    if client is None:
        return None
    try:
        from google.genai import types
        def _call():
            return client.models.generate_content(
                model=GEMINI_MODEL,
                contents=question,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=400,
                    temperature=0.4,
                ),
            )
        resp = await asyncio.to_thread(_call)
        answer = (getattr(resp, "text", None) or "").strip()
        return answer or None
    except Exception as e:
        print(f"⚠️ Gemini xatosi: {e}")
        return None

async def _ask_claude(question, system_prompt):
    """Запрос к Claude. Возвращает текст или None."""
    client = _get_anthropic_client()
    if client is None:
        return None
    try:
        def _call():
            return client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=400,
                system=system_prompt,
                messages=[{"role": "user", "content": question}],
            )
        resp = await asyncio.to_thread(_call)
        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        answer = "".join(parts).strip()
        return answer or None
    except Exception as e:
        print(f"⚠️ Claude xatosi: {e}")
        return None

async def ask_ai(question, lang, is_admin=False):
    """Короткий тематический ответ. Сначала Claude, при отсутствии — Gemini.

    Возвращает текст или None при ошибке.
    """
    system_prompt = _build_ai_system_prompt(lang, is_admin)
    # Приоритет — Claude
    if ANTHROPIC_API_KEY:
        answer = await _ask_claude(question, system_prompt)
        if answer:
            return answer
    # Запасной — Gemini
    if GEMINI_API_KEY:
        return await _ask_gemini(question, system_prompt)
    return None

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
        [InlineKeyboardButton(get_text(lang, 'ask_ai'), callback_data="ask_ai")],
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

async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /ask <вопрос> — разовый AI-вопрос."""
    user_id = update.effective_user.id
    track_user_interaction(user_id)
    lang = get_user_language(user_id) or 'uz'
    is_admin = user_id in ADMIN_USER_IDS

    question = " ".join(context.args).strip() if context.args else ""
    if not question:
        await update.message.reply_text(get_text(lang, 'ask_ai_usage'))
        return

    await _answer_with_ai(update.message, question, lang, is_admin)

async def _answer_with_ai(message, question, lang, is_admin):
    """Общий обработчик: показывает 'думаю', спрашивает AI, шлёт ответ или отказ."""
    if not AI_ENABLED:
        await message.reply_text(get_text(lang, 'ask_ai_error'))
        return

    thinking = await message.reply_text(get_text(lang, 'ask_ai_thinking'))
    answer = await ask_ai(question, lang, is_admin)
    final = answer or get_text(lang, 'ask_ai_error')
    # Сначала пробуем Markdown (ради ссылок [текст](url)). При ошибке парсинга — без форматирования.
    try:
        await thinking.edit_text(final, parse_mode='Markdown', disable_web_page_preview=True)
    except BadRequest:
        try:
            await thinking.edit_text(final)
        except BadRequest:
            await message.reply_text(final)

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Свободный текст: AI-чат.

    Срабатывает если:
    - пользователь нажал "Ask AI" в меню (режим ожидания), ИЛИ
    - в личке написал текст, ИЛИ
    - в группе ответил на сообщение бота, ИЛИ
    - в группе написал явно на нашу тему (по ключевым словам).
    """
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    if not text or text.startswith("/"):
        return

    user_id = update.effective_user.id
    lang = get_user_language(user_id) or 'uz'
    is_admin = user_id in ADMIN_USER_IDS
    chat_type = update.message.chat.type
    is_private = chat_type == "private"

    waiting = user_id in _AI_WAITING
    bot_username = context.bot.username
    replied_to_bot = (
        update.message.reply_to_message is not None
        and update.message.reply_to_message.from_user is not None
        and update.message.reply_to_message.from_user.is_bot
    )
    mentioned = bool(bot_username) and (f"@{bot_username}".lower() in text.lower())

    # Решаем, отвечать ли
    if is_private:
        should = waiting or True  # в личке любой текст считаем вопросом
    else:
        # В группе — только если позвали бота или похоже на нашу тему
        should = waiting or replied_to_bot or mentioned or _looks_on_topic(text)

    if not should:
        return

    # Снимаем режим ожидания после первого вопроса
    _AI_WAITING.discard(user_id)
    track_user_interaction(user_id)

    # Убираем упоминание бота из вопроса
    if mentioned and bot_username:
        text = text.replace(f"@{bot_username}", "").strip()

    await _answer_with_ai(update.message, text, lang, is_admin)

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
        _AI_WAITING.discard(user_id)
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
    
    # AI-чат: включаем режим ожидания вопроса
    elif query.data == "ask_ai":
        _AI_WAITING.add(user_id)
        await query.edit_message_text(
            get_text(lang, 'ask_ai_prompt'),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(get_text(lang, 'back'), callback_data="main_menu")]]),
            parse_mode="Markdown"
        )

    # Настройки
    elif query.data == "settings":
        _AI_WAITING.discard(user_id)
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

# ============================================
# НОВОСТНОЙ АВТОПОСТИНГ
# ============================================

NEWS_FEEDS = [
    "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "https://www.espn.com/espn/rss/soccer/news",
    "https://www.theguardian.com/football/rss",
    "https://rss.app/feeds/tFoNgcWzS8EMflrJ.xml",  # FIFA World Cup 2026 news aggregator
]

NEWS_KEYWORDS = [
    "uzbekistan", "uzbek", "world cup 2026", "fifa 2026", "2026 world cup",
    "wc2026", "shomurodov", "cannavaro", "group k", "host city", "host cities",
    "метчо\"26", "чм 2026", "чемпионат мира 2026", "o'zbekiston", "o'zbek",
]

# In-memory fallback for posted URLs when DB not available
_posted_news_urls: set = set()


def _is_news_posted(url: str) -> bool:
    """Check if article URL was already posted (DB or memory)."""
    try:
        import db as _db
        pool = _db._get_pool()
        if pool:
            with pool.connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT 1 FROM posted_news WHERE url = %s", (url,))
                return cur.fetchone() is not None
    except Exception:
        pass
    return url in _posted_news_urls


def _mark_news_posted(url: str, title: str) -> None:
    """Mark article as posted."""
    _posted_news_urls.add(url)
    try:
        import db as _db
        pool = _db._get_pool()
        if pool:
            with pool.connection() as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO posted_news (url, title, posted_at) VALUES (%s, %s, NOW()) ON CONFLICT DO NOTHING",
                    (url, title[:500]),
                )
                conn.commit()
    except Exception:
        pass


def _fetch_news_articles() -> list[dict]:
    """Fetch fresh articles from RSS feeds, filter for WC2026/Uzbekistan relevance."""
    import feedparser
    articles = []
    for feed_url in NEWS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in (feed.entries or [])[:10]:
                title = getattr(entry, 'title', '') or ''
                summary = getattr(entry, 'summary', '') or ''
                link = getattr(entry, 'link', '') or ''
                combined = (title + ' ' + summary).lower()
                if any(k in combined for k in NEWS_KEYWORDS):
                    articles.append({
                        'title': title,
                        'summary': summary[:500],
                        'url': link,
                        'source': feed.feed.get('title', feed_url),
                    })
        except Exception as e:
            print(f"⚠️ News feed error ({feed_url}): {e}")
    return articles


async def _format_news_post(article: dict) -> str | None:
    """Use AI to create an Uzbek-first Telegram post from article data."""
    channel = CHANNEL_ID if CHANNEL_ID.startswith('@') else f"@{CHANNEL_ID}"
    prompt = (
        f"You are a content editor for 'Uzbek World Club' — the official Uzbek fan community for FIFA World Cup 2026.\n\n"
        f"Write a Telegram channel post in UZBEK based on this news article.\n"
        f"Title: {article['title']}\n"
        f"Summary: {article['summary']}\n\n"
        f"STRICT FORMAT RULES — follow exactly:\n"
        f"1. Start with ONE bold headline in CAPS with a relevant emoji (e.g. ⚽ **SARLAVHA**)\n"
        f"2. Body: 2-4 short factual sentences. No fluff. Only facts from the article.\n"
        f"3. If about Uzbekistan/Uzbek team: add genuine enthusiasm 🇺🇿\n"
        f"4. End with exactly these two lines (no changes):\n"
        f"   👉 {channel}\n"
        f"   #UzbekWorldCup #JCH2026\n\n"
        f"STYLE: Sharp sports journalism. Short factual sentences. No fluff. Use emojis naturally.\n"
        f"LANGUAGE: Uzbek only. No Russian. No English. No source URL.\n"
        f"OUTPUT: Only the post text. Nothing else. Plain text, no markdown symbols."
    )
    try:
        # Try Gemini first (Claude has no credits)
        if GEMINI_API_KEY:
            client = _get_gemini_client()
            if client:
                from google.genai import types
                def _gcall():
                    return client.models.generate_content(
                        model=GEMINI_MODEL,
                        contents=prompt,
                        config=types.GenerateContentConfig(max_output_tokens=800, temperature=0.5),
                    )
                resp = await asyncio.to_thread(_gcall)
                return (getattr(resp, 'text', None) or '').strip() or None
        # Fallback to Claude if Gemini fails
        if ANTHROPIC_API_KEY:
            client = _get_anthropic_client()
            if client:
                def _call():
                    return client.messages.create(
                        model=CLAUDE_MODEL,
                        max_tokens=800,
                        messages=[{"role": "user", "content": prompt}],
                    )
                resp = await asyncio.to_thread(_call)
                parts = [b.text for b in resp.content if getattr(b, 'type', None) == 'text']
                return "".join(parts).strip() or None
    except Exception as e:
        print(f"⚠️ AI news format error: {e}")
    return None


async def post_news(context: ContextTypes.DEFAULT_TYPE):
    """Fetch latest WC2026/Uzbekistan news and post to channel. Falls back to countdown if no new articles."""
    # Try to find a fresh unposted article
    articles = await asyncio.to_thread(_fetch_news_articles)
    for article in articles:
        if not article.get('url') or _is_news_posted(article['url']):
            continue
        # Format with AI
        text = await _format_news_post(article)
        if not text:
            continue
        try:
            await context.bot.send_message(
                chat_id=COMMUNITY_CHAT_ID,
                text=text,
                disable_web_page_preview=True,
            )
            _mark_news_posted(article['url'], article['title'])
            print(f"📰 News posted: {article['title'][:60]}")
            return
        except TelegramError as e:
            print(f"⚠️ Failed to post news: {e}")
            # Try without Markdown in case of parse error
            try:
                await context.bot.send_message(chat_id=COMMUNITY_CHAT_ID, text=text)
                _mark_news_posted(article['url'], article['title'])
                return
            except TelegramError:
                continue

    # No new articles — fall back to countdown
    days = days_until_first_match()
    if days < 0:
        return
    channel_handle = CHANNEL_ID.lstrip('@') if CHANNEL_ID else 'uzbekworld'
    text = (
        f"{get_text('uz', 'countdown_post', days=days, channel=channel_handle)}\n\n"
        f"────────\n\n"
        f"{get_text('ru', 'countdown_post', days=days, channel=channel_handle)}\n\n"
        f"────────\n\n"
        f"{get_text('en', 'countdown_post', days=days, channel=channel_handle)}"
    )
    try:
        await context.bot.send_message(chat_id=COMMUNITY_CHAT_ID, text=text)
        print(f"📢 No new news — countdown posted: {days} days left")
    except TelegramError as e:
        print(f"⚠️ Countdown post failed: {e}")

# ============================================
# ЗАПУСК
# ============================================

def main():
    """Главная функция"""
    print("🚀 Bot ishga tushmoqda...")
    print(f"� Komunita chati: {COMMUNITY_CHAT_ID}")
    print(f"👥 Adminlar: {len(ADMIN_USER_IDS)}")
    print(f"🌐 Tillar: O'zbekcha, Русский, English")
    if ANTHROPIC_API_KEY:
        ai_status = "yoqilgan (Claude, fallback: Gemini)" if GEMINI_API_KEY else "yoqilgan (Claude)"
    elif GEMINI_API_KEY:
        ai_status = "yoqilgan (Gemini)"
    else:
        ai_status = "o'chirilgan (API kalit yo'q)"
    print(f"🤖 AI-chat: {ai_status}\n")
    
    # Создаем приложение
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("schedule", schedule_command))
    app.add_handler(CommandHandler("ask", ask_command))
    
    # Кнопки
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # Приветствие новых участников
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))

    # AI-чат: свободный текст (не команды). Регистрируем последним.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    
    # Автопостинг: непрерывный обратный отсчёт в канал (24/7).
    # Интервал — POST_INTERVAL_MINUTES (по умолчанию 30 мин). Первый пост через 30 сек после старта.
    job_queue = app.job_queue
    if job_queue is not None:
        interval_sec = max(1, POST_INTERVAL_MINUTES) * 60
        job_queue.run_repeating(post_news, interval=interval_sec, first=30)
        print(f"📰 News autopost yoqildi — har {POST_INTERVAL_MINUTES} daqiqada WC2026 yangiliklari (24/7)")
    else:
        print("⚠️ JobQueue mavjud emas — avtoposting o'chirilgan")
    
    print("✅ Bot ishga tushdi!\n")
    
    # Запуск
    app.run_polling()

if __name__ == "__main__":
    main()
