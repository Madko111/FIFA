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
ADMIN_USER_IDS = [int(uid.strip()) for uid in os.getenv('ADMIN_USER_ID', '').split(',') if uid.strip()]

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

# All times in UZT (Tashkent, GMT+5).
# espn_date: the local match date used to query ESPN API (YYYYMMDD).
MATCHES = [
    {
        "uzt_date": "2026-06-18", "uzt_time": "07:00",
        "espn_date": "20260617",
        "opponent": {"uz": "Kolumbiya", "ru": "Колумбия", "en": "Colombia"},
        "flag": "🇨🇴",
        "city": {"uz": "Mexico-siti", "ru": "Мехико", "en": "Mexico City"},
        "stadium": "Estadio Azteca",
    },
    {
        "uzt_date": "2026-06-23", "uzt_time": "22:00",
        "espn_date": "20260623",
        "opponent": {"uz": "Portugaliya", "ru": "Португалия", "en": "Portugal"},
        "flag": "🇵🇹",
        "city": {"uz": "Hyuston", "ru": "Хьюстон", "en": "Houston"},
        "stadium": "NRG Stadium",
    },
    {
        "uzt_date": "2026-06-28", "uzt_time": "04:30",
        "espn_date": "20260627",
        "opponent": {"uz": "Kongo (DR)", "ru": "Конго (ДР)", "en": "Congo DR"},
        "flag": "🇨🇩",
        "city": {"uz": "Atlanta", "ru": "Атланта", "en": "Atlanta"},
        "stadium": "Mercedes-Benz Stadium",
    },
]


def _fetch_score_espn(espn_date: str, opponent_en: str) -> str | None:
    """Fetch live/final score from ESPN API. Returns 'X:X' or None."""
    import requests as _req
    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={espn_date}"
        resp = _req.get(url, timeout=6)
        if resp.status_code != 200:
            return None
        for event in resp.json().get('events', []):
            name = event.get('name', '').lower()
            if 'uzbekistan' not in name:
                continue
            if opponent_en.split()[0].lower() not in name:  # e.g. 'colombia', 'portugal', 'congo'
                continue
            comp = (event.get('competitions') or [{}])[0]
            status = comp.get('status', {}).get('type', {}).get('name', '')
            if status not in ('STATUS_FINAL', 'STATUS_IN_PROGRESS'):
                return None
            uz_score = opp_score = None
            for c in comp.get('competitors', []):
                team = c.get('team', {}).get('displayName', '').lower()
                s = c.get('score', '')
                if 'uzbekistan' in team:
                    uz_score = s
                else:
                    opp_score = s
            if uz_score is not None and opp_score is not None:
                suffix = ' 🔴 LIVE' if status == 'STATUS_IN_PROGRESS' else ''
                return f"{uz_score}:{opp_score}{suffix}"
    except Exception as e:
        print(f"ESPN score error: {e}")
    return None


def _days_left_label(days: int, lang: str) -> str:
    """Properly pluralized days-left string."""
    if lang == 'en':
        return f"{days} day left ⏰" if days == 1 else f"{days} days left ⏰"
    if lang == 'ru':
        if days % 100 in range(11, 20):
            word = "дней"
        elif days % 10 == 1:
            word = "день"
        elif days % 10 in (2, 3, 4):
            word = "дня"
        else:
            word = "дней"
        return f"{days} {word} ⏰"
    # Uzbek — no plural change
    return f"{days} kun qoldi ⏰"


def build_schedule_text(lang: str) -> str:
    """Build schedule text — fetches live scores from ESPN."""
    headers = {
        "uz": "O'zbekiston vaqti (Toshkent, GMT+5):",
        "ru": "По времени Узбекистана (Ташкент, GMT+5):",
        "en": "Uzbekistan local time (Tashkent, GMT+5):",
    }
    titles = {
        "uz": "📅 GURUH K — O'YIN JADVALI",
        "ru": "📅 ГРУППА K — РАСПИСАНИЕ",
        "en": "📅 MATCH SCHEDULE - GROUP K",
    }
    today_labels  = {"uz": "BUGUN! 🔥",    "ru": "СЕГОДНЯ! 🔥", "en": "TODAY! 🔥"}
    played_labels = {"uz": "O'ynaldi ✅",  "ru": "Сыгран ✅",     "en": "Played ✅"}
    score_labels  = {"uz": "Natija",        "ru": "Счёт",           "en": "Score"}

    today_uzt = (datetime.utcnow() + timedelta(hours=5)).date()
    text = f"{headers.get(lang, headers['en'])}\n{titles.get(lang, titles['en'])}\n\n"

    for i, match in enumerate(MATCHES, 1):
        match_date = datetime.strptime(match['uzt_date'], '%Y-%m-%d').date()
        days_until = (match_date - today_uzt).days
        opponent = match['opponent'].get(lang, match['opponent']['en'])
        city = match['city'].get(lang, match['city']['en'])

        text += f"{i}. 🇺🇿 vs {match['flag']} {opponent}\n"
        text += f"📅 {match_date.strftime('%d.%m.%Y')} {match['uzt_time']}\n"
        text += f"📍 {city}, {match['stadium']}\n"

        if days_until > 0:
            text += f"{_days_left_label(days_until, lang)}\n"
        elif days_until == 0:
            text += f"{today_labels.get(lang, today_labels['en'])}\n"
        else:
            # Try live score from ESPN
            score = _fetch_score_espn(match['espn_date'], match['opponent']['en'])
            if score:
                text += f"{score_labels.get(lang, 'Score')}: {score}\n"
            else:
                text += f"{played_labels.get(lang, played_labels['en'])}\n"
        text += "\n"

    return text

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

# Per-user conversation history: {user_id: [{"role": "user"|"assistant", "content": str}, ...]}
_USER_HISTORY: dict[int, list[dict]] = {}
_HISTORY_MAX = 5  # keep last 5 exchanges (10 messages)


def _get_history(user_id: int) -> list[dict]:
    return _USER_HISTORY.get(user_id, [])


def _add_to_history(user_id: int, role: str, content: str):
    history = _USER_HISTORY.setdefault(user_id, [])
    history.append({"role": role, "content": content})
    # Keep only last _HISTORY_MAX exchanges (2 messages per exchange)
    if len(history) > _HISTORY_MAX * 2:
        _USER_HISTORY[user_id] = history[-(  _HISTORY_MAX * 2):]

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

def _detect_question_lang(question: str) -> str | None:
    """Detect language of the question: 'ru', 'uz', 'en' or None."""
    q = question.lower()
    # Cyrillic = Russian
    cyrillic = sum(1 for c in q if '\u0400' <= c <= '\u04ff')
    # Uzbek Latin signals
    uz_signals = ['o\'zbek', 'o\'yin', 'qancha', 'qachon', 'haqida', 'jamoasi',
                  'nechta', 'tarkibi', 'o\'yinchi', 'futbolchi', 'qo\'ychi']
    if any(s in q for s in uz_signals):
        return 'uz'
    if cyrillic > 3:
        return 'ru'
    # Default: use profile lang (None = caller decides)
    return None


def _fetch_wc2026_all_teams() -> str:
    """Fetch all WC2026 group standings and teams from ESPN."""
    import requests as _req
    lines = []
    try:
        url = "https://site.api.espn.com/apis/v2/sports/soccer/fifa.world/standings"
        resp = _req.get(url, timeout=8)
        if resp.status_code != 200:
            return "(WC2026 standings unavailable)"
        for grp in resp.json().get('children', []):
            grp_name = grp.get('name', '')
            lines.append(f"Group {grp_name}:")
            for entry in grp.get('standings', {}).get('entries', []):
                team = entry.get('team', {}).get('displayName', '')
                stats = {s['name']: s.get('value', 0) for s in entry.get('stats', [])}
                w = int(stats.get('wins', 0))
                d = int(stats.get('ties', 0))
                l = int(stats.get('losses', 0))
                pts = int(stats.get('points', 0))
                gf = int(stats.get('pointsFor', 0))
                ga = int(stats.get('pointsAgainst', 0))
                lines.append(f"  {team}: {w}W {d}D {l}L GF:{gf} GA:{ga} Pts:{pts}")
        return "\n".join(lines) if lines else "(no standings data)"
    except Exception as e:
        return f"(standings fetch error: {e})"


def _fetch_wc2026_live_data() -> str:
    """Fetch live Group K standings + recent Uzbekistan match scores from ESPN."""
    import requests as _req
    lines = []
    try:
        # Live scores for all 3 Uzbekistan matches
        for m in MATCHES:
            score = _fetch_score_espn(m['espn_date'], m['opponent']['en'])
            opp = m['opponent']['en']
            if score:
                lines.append(f"- UZB vs {opp}: {score}")
            else:
                lines.append(f"- UZB vs {opp}: not played yet / {m['uzt_date']} {m['uzt_time']} UZT")
    except Exception as e:
        lines.append(f"(score fetch error: {e})")

    # Group K standings
    try:
        url = "https://site.api.espn.com/apis/v2/sports/soccer/fifa.world/standings"
        resp = _req.get(url, timeout=6)
        if resp.status_code == 200:
            for grp in resp.json().get('children', []):
                if grp.get('name', '').upper() in ('GROUP K', 'K'):
                    lines.append("\nGroup K standings:")
                    for entry in grp.get('standings', {}).get('entries', []):
                        team = entry.get('team', {}).get('displayName', '')
                        stats = {s['name']: s['value'] for s in entry.get('stats', [])}
                        w = int(stats.get('wins', 0))
                        d = int(stats.get('ties', 0))
                        l = int(stats.get('losses', 0))
                        pts = int(stats.get('points', 0))
                        gf = int(stats.get('pointsFor', 0))
                        ga = int(stats.get('pointsAgainst', 0))
                        lines.append(f"  {team}: {w}W {d}D {l}L | GF:{gf} GA:{ga} | {pts}pts")
    except Exception as e:
        lines.append(f"(standings fetch error: {e})")

    return "\n".join(lines) if lines else "Live data unavailable."


def _build_ai_facts():
    """Builds full fact sheet for the AI system prompt."""
    lines = []

    # --- SQUAD ---
    lines.append("=== UZBEKISTAN SQUAD (World Cup 2026, 26 players) ===")
    lines.append("Head coach: Fabio Cannavaro")
    lines.append("Captain: Eldor Shomurodov (#14, Forward, İstanbul Başakşehir)")
    lines.append("")
    pos_order = {"Goalkeeper": [], "Defender": [], "Midfielder": [], "Forward": []}
    for p in PLAYERS:
        pos = p['position']['en']
        name = p['name']['en']
        pos_order.get(pos, pos_order.setdefault(pos, [])).append(
            f"#{p['number']} {name} ({p['club']}, age {p['age']})"
        )
    for pos, players in pos_order.items():
        if players:
            lines.append(f"{pos}s: {', '.join(players)}")
    lines.append("")

    # --- MATCHES & LIVE DATA ---
    lines.append("=== MATCHES (Group K, all times UZT / Tashkent GMT+5) ===")
    for m in MATCHES:
        lines.append(
            f"- {m['uzt_date']} {m['uzt_time']} UZT: UZB vs {m['opponent']['en']} "
            f"at {m['stadium']}, {m['city']['en']}"
        )
    lines.append("")
    lines.append("=== LIVE SCORES & STANDINGS ===")
    lines.append(_fetch_wc2026_live_data())
    lines.append("")

    # --- ALL WC2026 TEAMS ---
    lines.append("=== ALL WC2026 GROUP STANDINGS (all 48 teams) ===")
    lines.append(_fetch_wc2026_all_teams())
    lines.append("")
    lines.append("NOTE: For any team's full squad/roster, use your general World Cup 2026 knowledge — rosters were announced before the tournament.")
    lines.append("")

    # --- PROGRAMS ---
    lines.append("=== PROGRAMS (join via website) ===")
    prog_names = {
        "founders": "Founders Davra (business leaders network)",
        "stadium":  "Stadium Davra (organized stadium fan sections)",
        "captain":  "City Captain (lead the fan community in a city)",
        "volunteer":"Volunteer program (Uzbek: Volontyorlik | RU: Волонтёрство)",
        "passport": "Fan Passport",
    }
    for key in PROGRAMS:
        lines.append(f"- {prog_names.get(key, key)}")
    lines.append("")
    lines.append(f"Website: {WEBSITE_URL}")
    lines.append("Goal: largest organized Uzbek fan community for WC2026 — Uzbekistan's first-ever World Cup.")
    lines.append("")
    lines.append("LOCALIZED PROGRAM NAMES: Founders Davra, Stadium Davra, City Captain, Fan Passport — keep original names in all languages.")
    return "\n".join(lines)

LANG_NAMES = {"uz": "Uzbek", "ru": "Russian", "en": "English"}

def _build_ai_system_prompt(lang, is_admin=False, question: str = ""):
    """Системный промпт: тема, тон, язык, отказ от офтопа."""
    # Override lang with detected language from the question itself
    detected = _detect_question_lang(question)
    if detected:
        lang = detected
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
        f"You are a knowledgeable football assistant for 'Uzbek World Club' — the official Uzbek fan community for FIFA World Cup 2026.\n\n"
        f"LANGUAGE: Detect the language of the user's question and ALWAYS reply in that SAME language. "
        f"Russian question → Russian answer. Uzbek question → Uzbek answer. English → English. Profile language ({lang_name}) is only a fallback.\n\n"
        "SCOPE: Answer freely about FIFA World Cup 2026 — ANY team (Colombia, Portugal, Brazil, etc.), "
        "ANY player, squads, rosters, group standings, match results, statistics, host cities. "
        "You have full football knowledge. Also answer about Uzbek World Club programs and community. "
        "Refuse ONLY questions completely unrelated to football or the World Cup.\n\n"
        "RULES:\n"
        "- Be direct. Give the actual answer immediately — no apologies, no disclaimers.\n"
        "- NEVER say 'check official FIFA' or 'I don't have details' if you know the answer — just answer.\n"
        "- NEVER repeat scope disclaimers. If you already said it once, don't say it again.\n"
        "- For squad/roster questions: list the players directly in bullet points.\n"
        "- Use live data below when available. Use your training knowledge for the rest.\n"
        "- Max 8 sentences for detailed questions, 1-2 for simple ones.\n\n"
        "WEBSITE LINK: When mentioning registration or programs use Telegram Markdown: "
        f"[Uzbek World Club]({WEBSITE_URL})\n\n"
        f"LIVE DATA (ESPN, updated each call):\n{facts}"
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

async def _ask_gemini(question, system_prompt, history: list):
    """Запрос к Gemini с историей диалога. Возвращает текст или None."""
    client = _get_gemini_client()
    if client is None:
        return None
    try:
        from google.genai import types
        # Build contents from history + current question
        contents = []
        for msg in history:
            contents.append(types.Content(
                role="user" if msg["role"] == "user" else "model",
                parts=[types.Part(text=msg["content"])]
            ))
        contents.append(types.Content(role="user", parts=[types.Part(text=question)]))
        def _call():
            return client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=800,
                    temperature=0.5,
                ),
            )
        resp = await asyncio.to_thread(_call)
        answer = (getattr(resp, "text", None) or "").strip()
        return answer or None
    except Exception as e:
        print(f"⚠️ Gemini xatosi: {e}")
        return None

async def _ask_claude(question, system_prompt, history: list):
    """Запрос к Claude с историей диалога. Возвращает текст или None."""
    client = _get_anthropic_client()
    if client is None:
        return None
    try:
        messages = list(history) + [{"role": "user", "content": question}]
        def _call():
            return client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=800,
                system=system_prompt,
                messages=messages,
            )
        resp = await asyncio.to_thread(_call)
        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        answer = "".join(parts).strip()
        return answer or None
    except Exception as e:
        print(f"⚠️ Claude xatosi: {e}")
        return None

async def ask_ai(question, lang, is_admin=False, user_id: int = 0):
    """Returns AI answer with per-user conversation context (last 5 exchanges)."""
    system_prompt = _build_ai_system_prompt(lang, is_admin, question=question)
    history = _get_history(user_id) if user_id else []
    if ANTHROPIC_API_KEY:
        answer = await _ask_claude(question, system_prompt, history)
        if answer:
            return answer
    if GEMINI_API_KEY:
        return await _ask_gemini(question, system_prompt, history)
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
    await update.message.reply_text(build_schedule_text(lang))

async def matches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Alias for /schedule"""
    await schedule_command(update, context)

async def watchparty_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show watch party / cities menu"""
    user_id = update.effective_user.id
    track_user_interaction(user_id)
    lang = get_user_language(user_id) or 'uz'
    await update.message.reply_text(
        get_text(lang, 'watchparty_title'),
        reply_markup=get_cities_menu(lang)
    )

async def players_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show players menu"""
    user_id = update.effective_user.id
    track_user_interaction(user_id)
    lang = get_user_language(user_id) or 'uz'
    await update.message.reply_text(
        get_text(lang, 'players_title'),
        reply_markup=get_players_menu(lang)
    )

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

def _md_to_html(text: str) -> str:
    """Convert AI markdown output to Telegram HTML."""
    import re
    # Remove markdown headings (# ## ###) -> plain bold line
    text = re.sub(r'^#{1,6}\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    # Bold **text** or __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)
    # Italic *text* or _text_ (but not inside words)
    text = re.sub(r'(?<!\w)\*(.+?)\*(?!\w)', r'<i>\1</i>', text)
    text = re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'<i>\1</i>', text)
    # Inline code `text`
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    # Markdown links [text](url) -> HTML
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    return text.strip()


async def _answer_with_ai(message, question, lang, is_admin):
    """Общий обработчик: показывает 'думаю', спрашивает AI, шлёт ответ или отказ."""
    if not AI_ENABLED:
        await message.reply_text(get_text(lang, 'ask_ai_error'))
        return

    # Use detected language from question for the thinking message too
    detected = _detect_question_lang(question)
    reply_lang = detected or lang

    # Infer user_id from message
    uid = message.from_user.id if message.from_user else 0
    thinking = await message.reply_text(get_text(reply_lang, 'ask_ai_thinking'))
    answer = await ask_ai(question, lang, is_admin, user_id=uid)
    if answer:
        # Save exchange to history
        _add_to_history(uid, "user", question)
        _add_to_history(uid, "assistant", answer)
    final = _md_to_html(answer) if answer else get_text(reply_lang, 'ask_ai_error')
    try:
        await thinking.edit_text(final, parse_mode='HTML', disable_web_page_preview=True)
    except BadRequest:
        try:
            await thinking.edit_text(answer or get_text(reply_lang, 'ask_ai_error'))
        except BadRequest:
            await message.reply_text(answer or get_text(reply_lang, 'ask_ai_error'))

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
    except Exception as e:
        err = str(e)
        print(f"⚠️ button_callback error [{query.data}]: {err}")
        if "Message is not modified" not in err:
            try:
                await query.edit_message_text(f"⚠️ Xatolik: {err[:200]}")
            except Exception:
                pass

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
        await query.edit_message_text(
            build_schedule_text(lang),
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
    """Возвращает число участников текущего чата (или None)."""
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
# ЗАПУСК
# ============================================

def main():
    """Главная функция"""
    print("🚀 Bot ishga tushmoqda...")
    print(f"💬 Bot yoqildi")
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
    app.add_handler(CommandHandler("matches", matches_command))
    app.add_handler(CommandHandler("watchparty", watchparty_command))
    app.add_handler(CommandHandler("players", players_command))
    app.add_handler(CommandHandler("ask", ask_command))
    
    # Кнопки
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # AI-чат: свободный текст (не команды). Регистрируем последним.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    
    print("✅ Bot ishga tushdi!\n")
    
    # Запуск
    app.run_polling(allowed_updates=["message", "callback_query", "my_chat_member"])

if __name__ == "__main__":
    main()
