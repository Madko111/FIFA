# Переводы для бота на 3 языка

TRANSLATIONS = {
    'uz': {
        'welcome': """👋 Assalomu alaykum, {name}!

🇺🇿 Uzbekistan World Cup 2026 botiga xush kelibsiz!

Tilni tanlang / Choose language:""",
        'language_selected': "✅ Til tanlandi: O'zbekcha",
        'main_menu': "🏠 Asosiy menyu\n\nKerakli bo'limni tanlang:",
        'schedule': "📅 Raspisaniye",
        'players': "⚽️ O'yinchilar",
        'standings': "🏆 Jadval",
        'watchparty': "🎉 Watch Party",
        'join': "👥 Guruhga qo'shilish",
        'settings': "⚙️ Sozlamalar",
        'admin_panel': "🔐 Admin Panel",
        'back': "◀️ Orqaga",
        'schedule_title': "📅 O'YINLAR JADVALI - GURUH K",
        'vs': "vs",
        'days_left': "kun qoldi",
        'today': "BUGUN!",
        'played': "O'yin bo'lib o'tdi",
        'players_title': "⚽️ O'YINCHILAR\n\nO'yinchi tanlang:",
        'standings_title': """🏆 GURUH K JADVALI

1. 🇵🇹 Portugaliya    0-0-0  0
2. 🇨🇴 Kolumbiya      0-0-0  0
3. 🇺🇿 O'zbekiston    0-0-0  0
4. 🇨🇩 Kongo DR       0-0-0  0

📊 Jadval turnir boshlanishi bilan yangilanadi""",
        'watchparty_title': "🎉 WATCH PARTY\n\nQaysi shaharda?",
        'join_title': "👥 GURUHGA QO'SHILISH\n\nQaysi shaharda yashaysiz?",
        'settings_title': "⚙️ SOZLAMALAR",
        'change_language': "🌐 Tilni o'zgartirish",
        'admin_war_room': "📊 WAR ROOM",
        'admin_stats': "📈 Statistika",
        'no_access': "❌ Ruxsat yo'q",
        'refresh': "🔄 Yangilash",
    },
    'ru': {
        'welcome': """👋 Здравствуйте, {name}!

🇺🇿 Добро пожаловать в бот Uzbekistan World Cup 2026!

Выберите язык / Choose language:""",
        'language_selected': "✅ Язык выбран: Русский",
        'main_menu': "🏠 Главное меню\n\nВыберите раздел:",
        'schedule': "📅 Расписание",
        'players': "⚽️ Игроки",
        'standings': "🏆 Таблица",
        'watchparty': "🎉 Watch Party",
        'join': "👥 Присоединиться",
        'settings': "⚙️ Настройки",
        'admin_panel': "🔐 Админ-панель",
        'back': "◀️ Назад",
        'schedule_title': "📅 РАСПИСАНИЕ МАТЧЕЙ - ГРУППА K",
        'vs': "vs",
        'days_left': "дней осталось",
        'today': "СЕГОДНЯ!",
        'played': "Матч сыгран",
        'players_title': "⚽️ ИГРОКИ СБОРНОЙ\n\nВыберите игрока:",
        'standings_title': """🏆 ТАБЛИЦА ГРУППЫ K

1. 🇵🇹 Португалия     0-0-0  0
2. 🇨🇴 Колумбия       0-0-0  0
3. 🇺🇿 Узбекистан     0-0-0  0
4. 🇨🇩 Конго ДР       0-0-0  0

📊 Таблица обновится после начала турнира""",
        'watchparty_title': "🎉 WATCH PARTY\n\nВ каком городе?",
        'join_title': "👥 ПРИСОЕДИНИТЬСЯ К СООБЩЕСТВУ\n\nВ каком городе вы живёте?",
        'settings_title': "⚙️ НАСТРОЙКИ",
        'change_language': "🌐 Изменить язык",
        'admin_war_room': "📊 WAR ROOM",
        'admin_stats': "📈 Статистика",
        'no_access': "❌ Нет доступа",
        'refresh': "🔄 Обновить",
    },
    'en': {
        'welcome': """👋 Hello, {name}!

🇺🇿 Welcome to Uzbekistan World Cup 2026 bot!

Choose language / Tilni tanlang:""",
        'language_selected': "✅ Language selected: English",
        'main_menu': "🏠 Main Menu\n\nChoose a section:",
        'schedule': "📅 Schedule",
        'players': "⚽️ Players",
        'standings': "🏆 Standings",
        'watchparty': "🎉 Watch Party",
        'join': "👥 Join Community",
        'settings': "⚙️ Settings",
        'admin_panel': "🔐 Admin Panel",
        'back': "◀️ Back",
        'schedule_title': "📅 MATCH SCHEDULE - GROUP K",
        'vs': "vs",
        'days_left': "days left",
        'today': "TODAY!",
        'played': "Match played",
        'players_title': "⚽️ TEAM PLAYERS\n\nSelect a player:",
        'standings_title': """🏆 GROUP K STANDINGS

1. 🇵🇹 Portugal       0-0-0  0
2. 🇨🇴 Colombia       0-0-0  0
3. 🇺🇿 Uzbekistan     0-0-0  0
4. 🇨🇩 Congo DR       0-0-0  0

📊 Table will update after tournament starts""",
        'watchparty_title': "🎉 WATCH PARTY\n\nWhich city?",
        'join_title': "👥 JOIN COMMUNITY\n\nWhich city do you live in?",
        'settings_title': "⚙️ SETTINGS",
        'change_language': "🌐 Change Language",
        'admin_war_room': "📊 WAR ROOM",
        'admin_stats': "📈 Statistics",
        'no_access': "❌ No access",
        'refresh': "🔄 Refresh",
    }
}

def get_text(lang, key, **kwargs):
    """Получает переведённый текст"""
    text = TRANSLATIONS.get(lang, TRANSLATIONS['uz']).get(key, key)
    if kwargs:
        return text.format(**kwargs)
    return text
