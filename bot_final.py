import os
import time
import random
import requests
import feedparser
from datetime import datetime
import schedule
import asyncio
import threading
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError
from telegram.ext import ApplicationBuilder, MessageHandler, filters

# Загружаем .env файл
load_dotenv()

# ============================================
# НАСТРОЙКИ - МЕНЯЙ ТОЛЬКО ЗДЕСЬ
# ============================================
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Для продакшена: @uzbekworldcup
ADMIN_USER_IDS = [uid.strip() for uid in os.getenv('ADMIN_USER_ID').split(',')]
POST_INTERVAL_MINUTES = int(os.getenv('POST_INTERVAL_MINUTES', '30'))

MATCHES = [
    {"date": "2026-06-17", "opponent": "🇵🇹 Португалия",  "opponent_uz": "Portugaliya",  "time": "21:00", "city": "Хьюстон",  "city_uz": "Hyuston",     "stadium": "NRG Stadium"},
    {"date": "2026-06-21", "opponent": "🇨🇴 Колумбия",   "opponent_uz": "Kolumbiya",    "time": "18:00", "city": "Атланта",  "city_uz": "Atlanta",     "stadium": "Mercedes-Benz Stadium"},
    {"date": "2026-06-25", "opponent": "🇨🇩 Конго (ДР)", "opponent_uz": "Kongo (DR)",   "time": "15:00", "city": "Мехико",   "city_uz": "Mexico-siti", "stadium": "Estadio Azteca"},
]

# База игроков сборной
PLAYERS = [
    {"name": "Эльдор Шомуродов", "position": "Нападающий", "club": "Рома", "number": 14, "age": 27, "emoji": "⚡️"},
    {"name": "Абдукодир Хусанов", "position": "Защитник", "club": "Ланс", "number": 23, "age": 20, "emoji": "🛡"},
    {"name": "Отабек Шукуров", "position": "Полузащитник", "club": "Пахтакор", "number": 9, "age": 29, "emoji": "🎯"},
    {"name": "Умарбек Эшмуродов", "position": "Вратарь", "club": "Пахтакор", "number": 1, "age": 26, "emoji": "🧤"},
    {"name": "Жасурбек Якшибоев", "position": "Нападающий", "club": "Мельбурн Сити", "number": 17, "age": 24, "emoji": "⚽️"},
    {"name": "Одил Ахмедов", "position": "Полузащитник", "club": "Шанхай СИПГ", "number": 8, "age": 36, "emoji": "🎖"},
]

# ============================================
# ПАРСИНГ РЕАЛЬНЫХ НОВОСТЕЙ
# ============================================

def get_google_news():
    """Получает реальные новости через Google News RSS"""
    try:
        queries = [
            "Uzbekistan football",
            "Uzbekistan world cup 2026",
            "Узбекистан футбол",
        ]
        
        query = random.choice(queries)
        url = f"https://news.google.com/rss/search?q={query}&hl=ru&gl=UZ&ceid=UZ:ru"
        
        feed = feedparser.parse(url)
        
        if feed.entries:
            news = random.choice(feed.entries[:5])
            return {
                "title": news.title,
                "link": news.link,
                "published": news.get("published", ""),
                "source": "Google News"
            }
    except Exception as e:
        print(f"❌ Ошибка парсинга новостей: {e}")
    
    return None

# ============================================
# ШАБЛОНЫ ПОСТОВ НА УЗБЕКСКОМ ЯЗЫКЕ
# ============================================

POST_TEMPLATES = {
    "countdown": [
        "⏰ Birinchi o'yingacha {days} kun qoldi!\n\n🇺🇿 O'zbekiston tarixda birinchi marta Jahon chempionatiga chiqdi. Birinchi raqib — Yevropa chempioni Portugaliya.\n\n17-iyun kuni Xyustonda o'zbek futbolining yangi sahifasi boshlanadi. Butun dunyo bo'ylab millionlab muxlislar bu tarixiy lahzaga tayyorgarlik ko'rmoqda.\n\n📅 Birinchi o'yin: 17-iyun, 21:00\n🏟 NRG Stadium, Xyuston\n\n👉 @uzbekworld_test\n\n#UzbekWorldCup #JCH2026",
        
        "🔥 TARIXGACHA {days} KUN!\n\nO'zbekiston mustaqillik tarixida birinchi marta Jahon chempionatiga yo'llanma oldi. Bu federatsiya, murabbiylar va o'yinchilarning ko'p yillik mehnatining natijasidir.\n\nPortugaliyaga qarshi birinchi o'yin o'zbek futboli tarixidagi eng muhim uchrashuv bo'ladi. Butun mamlakat har bir daqiqani kuzatib boradi.\n\n🇺🇿 O'zbekiston vs 🇵🇹 Portugaliya\n📅 17-iyun, 21:00 (Xyuston)\n\n👉 @uzbekworld_test\n\n#Ozbekiston #WorldCup2026",
    ],
    
    "player_spotlight": [
        "{emoji} O'YINCHI PROFILI: {name}\n\n{name} ({number}) — O'zbekiston terma jamoasining {position}i. {age} yoshida u {club}da o'ynaydi va yaqinlashib kelayotgan Jahon chempionatida jamoaning asosiy o'yinchilaridan biridir.\n\nUning tajribasi va mahorati Portugaliya, Kolumbiya va Kongoga qarshi o'yinlarda juda muhim bo'ladi. Muxlislar uning o'yiniga katta umidlar bog'lashmoqda.\n\n⚽️ Klub: {club}\n🔢 Raqam: {number}\n🎂 Yosh: {age}\n\n👉 @uzbekworld_test\n\n#UzbekWorldCup #Ozbekiston",
    ],
    
    "match_reminder": [
        "📢 O'YIN HAQIDA ESLATMA\n\n🇺🇿 O'zbekiston {opponent}ga qarshi {date} kuni soat {time}da o'ynaydi. O'yin {city} shahridagi {stadium} stadionida bo'lib o'tadi.\n\nBu jamoa pley-offga chiqishi uchun muhim bo'lgan uchta guruh o'yinidan biridir. Har bir ochko oltin qiymatga ega.\n\nTerma jamoamizni qo'llab-quvvatlaylik! Qayerda bo'lsangiz ham — o'yinni biz bilan birga tomosha qiling.\n\n🏟 {stadium}, {city}\n📅 {date}, {time}\n\n👉 @uzbekworld_test\n\n#WorldCup2026 #Ozbekiston",
    ],
    
    "motivation": [
        "💪 BIRGALIKDA BIZ KUCHLIMIZ!\n\nO'zbekistondagi 33 million va butun dunyo bo'ylab millionlab o'zbeklar bitta maqsad atrofida birlashmoqda — tarixdagi birinchi Jahon chempionatida terma jamoani qo'llab-quvvatlash.\n\nBu shunchaki futbol emas. Bu o'nlab yillar davomida esda qoladigan milliy g'urur lahzasidir. Har birimiz bu tarixning bir qismimiz.\n\nDunyoga o'zbek futboli hurmatga loyiqligini ko'rsatamiz!\n\n🇺🇿 👉 @uzbekworld_test\n\n#UzbekWorldCup #Ozbekiston",
        
        "🏆 JAMOAMIZGA ISHONAMIZ!\n\nO'zbekiston turnirning eng qiyin guruhlaridan biriga tushdi: Portugaliya, Kolumbiya, Kongo DR. Lekin aynan bunday o'yinlarda afsonalar tug'iladi.\n\nTerma jamoamiz saralash bosqichida o'z kuchini isbotlab, guruhda birinchi o'rinni egalladi. Endi jahon arenasida o'zimizni ko'rsatish vaqti keldi.\n\nBiz g'alabaga ishonamiz! Kim biz bilan?\n\n⚡️ 👉 @uzbekworld_test\n\n#WorldCup2026 #Ozbekiston",
    ],
    
    "facts": [
        "📊 TARIXIY FAKT\n\nO'zbekiston 1998-yildan beri Jahon chempionatiga yo'llanma olgan Markaziy Osiyoning birinchi jamoasi bo'ldi.\n\nSaralash bosqichida terma jamoa 14 ta o'yin o'tkazib, 10 ta g'alaba qozondi va guruhda birinchi o'rinni egalladi. Bu o'zbek futboli tarixidagi eng yaxshi natija.\n\nEndi jamoa jahon arenasida o'z kuchini ko'rsatishga tayyorlanmoqda.\n\n👉 @uzbekworld_test\n\n#UzbekWorldCup #Tarix",
        
        "⚽️ BILASIZMI?\n\nO'zbekiston terma jamoasi saralash bosqichida 28 ta gol urdi — bu Osiyo zonasidagi barcha jamoalar orasida eng yaxshi ko'rsatkich.\n\nJamoa faqat 8 ta gol o'tkazib yubordi, bu hujum va himoyada muvozanatli o'yindan dalolat beradi. Bunday statistika turnir boshlanishidan oldin optimizm uyg'otadi.\n\n🎯 28 ta gol urildi\n🛡 8 ta gol o'tkazib yuborildi\n\n👉 @uzbekworld_test\n\n#Ozbekiston #JCH2026",
    ],
    
    "community": [
        "🌍 BUTUN DUNYO O'ZBEKLAR BIRLASHMOQDA!\n\nXyuston, Toronto, Mexiko, Dubay, Moskva, Toshkent — hamma joyda terma jamoa o'yinlarini tomosha qilish uchun watch party'lar tashkil etilmoqda.\n\nBu vatandoshlar bilan uchrashish, his-tuyg'ularni bo'lishish va jamoani birgalikda qo'llab-quvvatlash uchun noyob imkoniyat. Qayerda bo'lsangiz ham — siz bu harakatning bir qismisiz.\n\nJamiyatimizga qo'shiling!\n\n👉 @uzbekworld_test\n\n#UzbekWorldClub #Community",
    ],
    
    "group_info": [
        "📋 K GURUH — TARKIB\n\nO'zbekiston K guruhda uchta kuchli jamoaga qarshi o'ynaydi:\n\n🇵🇹 Portugaliya — UEFA Nations League chempioni, Ronaldo jamoasi\n🇨🇴 Kolumbiya — Janubiy Amerika futbolining kuchli vakili\n🇨🇩 Kongo DR — Afrika chempionati sobiq g'olibi\n\nO'yinlar:\n📅 17-iyun — Portugaliyaga qarshi (Xyuston)\n📅 21-iyun — Kolumbiyaga qarshi (Atlanta)\n📅 25-iyun — Kongoga qarshi (Mexiko)\n\nHar bir o'yin pley-offga chiqish uchun hal qiluvchi bo'ladi.\n\n👉 @uzbekworld_test\n\n#WorldCup2026 #KGuruh",
    ],
    
    "engagement": [
        "🌍 Qaysi shaharda o'yinni tomosha qilasiz?\n\nO'zingizning shahringizni yozing 👇\n\n#UzbekWorldCup #WatchParty",
        "⚽️ Birinchi o'yinda necha gol bo'ladi?\n\n🎯 0:0 — Durang\n1️⃣ 1:0 — O'zbekiston g'alabasi\n2️⃣ 2:1 — Barakali g'alaba\n🔴 0:1 — Yutqazib qo'yamiz\n\nJavobingizni yozing 👇\n\n#JCH2026 #Ozbekiston",
        "🙋 Watch party uyushtirmoqchimisiz?\n\n✅ Ha, tayyor!\n📺 Yo'q, uyda ko'raman\n✈️ Stadiondan ko'raman\n\n#UzbekWorldClub #WatchParty",
        "🇺🇿 Bu tarixiy lahzani kim bilan birga tomosha qilasiz?\n\nOila bilan 👨‍👩‍👧‍👦\nDo'stlar bilan 👥\nYolg'iz 😅\nStadionda 🏟\n\n#WorldCup2026 #Ozbekiston",
        "⭐️ Sizning eng sevimli o'yinchingiz kim?\n\n👇 Ismini yozing va sababini aytib bering!\n\n#Uzbekistan #JCH2026",
        "📍 Qaysi davlatdan bizni kuzatyapsiz?\n\nBayroq emoji bilan javob bering! 🌍\n\n#UzbekWorldClub #GlobalUzbeks",
        "💬 Jamoaga bitta xabar yozing!\n\n🇺🇿 Terma jamoamizga nima demoqchisiz?\nQuyida qoldiring 👇\n\n#Ozbekiston #WorldCup2026",
        "🏆 O'zbekiston guruh bosqichidan o'tadimi?\n\n✅ Ha, albatta!\n🤞 Umid qilamiz\n😬 Qiyin bo'ladi\n\n#JCH2026 #UzbekWorldCup",
        "📺 O'yinni qanday tomosha qilasiz?\n\n📡 Televideniye orqali\n📱 Telefonda\n🏟 Stadiondan\n🎉 Watch party'da\n\n#WorldCup2026",
        "🌟 Bu jamoada kim eng ko'p gol uradi?\n\nFikringizni yozing 👇\n\n#UzbekWorldCup #Ozbekiston",
    ],
}

# ============================================
# ФУНКЦИИ ГЕНЕРАЦИИ КОНТЕНТА
# ============================================

def get_days_until_first_match():
    """Считает дни до первого матча (17 июня vs Португалия)"""
    first_match = datetime.strptime("2026-06-17", "%Y-%m-%d")
    today = datetime.now()
    delta = first_match - today
    return max(0, delta.days)

def generate_countdown_post():
    """Генерирует пост с обратным отсчетом"""
    days = get_days_until_first_match()
    template = random.choice(POST_TEMPLATES["countdown"])
    return template.format(days=days)

def generate_player_post():
    """Генерирует пост об игроке"""
    player = random.choice(PLAYERS)
    template = random.choice(POST_TEMPLATES["player_spotlight"])
    return template.format(
        name=player["name"],
        position=player["position"],
        club=player["club"],
        number=player["number"],
        age=player["age"],
        emoji=player["emoji"]
    )

def generate_match_reminder():
    """Генерирует напоминание о матче"""
    match = random.choice(MATCHES)
    template = random.choice(POST_TEMPLATES["match_reminder"])
    return template.format(
        opponent=match["opponent"],
        date=match["date"],
        time=match["time"],
        city=match["city"],
        stadium=match["stadium"]
    )

def generate_motivation_post():
    """Генерирует мотивационный пост"""
    return random.choice(POST_TEMPLATES["motivation"])

def generate_fact_post():
    """Генерирует пост с фактом"""
    return random.choice(POST_TEMPLATES["facts"])

def generate_community_post():
    """Генерирует пост о сообществе"""
    return random.choice(POST_TEMPLATES["community"])

def generate_group_info_post():
    """Генерирует пост о группе"""
    return random.choice(POST_TEMPLATES["group_info"])

def generate_engagement_post():
    """Генерирует вовлекающий пост (вопрос/опрос)"""
    return random.choice(POST_TEMPLATES["engagement"])

def generate_news_post():
    """Генерирует пост на основе реальной новости"""
    news = get_google_news()
    
    if news:
        post = f"📰 YANGILIK\n\n{news['title']}\n\nBu yangilik O'zbekiston terma jamoasi va Jahon chempionatiga tayyorgarlik haqida muhim ma'lumot beradi.\n\n🔗 To'liq o'qish: {news['link']}\n\n👉 @uzbekworld_test\n\n#UzbekWorldCup #Yangiliklar"
        return post
    else:
        return generate_fact_post()

# ============================================
# ФУНКЦИЯ ПУБЛИКАЦИИ (ASYNC)
# ============================================

async def post_to_telegram_async(message):
    """Отправляет сообщение в Telegram канал (асинхронно)"""
    try:
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(chat_id=CHANNEL_ID, text=message, disable_web_page_preview=True)
        print(f"✅ Пост опубликован: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📝 Превью: {message[:100]}...")
        return True
    except TelegramError as e:
        print(f"❌ Ошибка публикации: {e}")
        return False

def post_to_telegram(message):
    """Синхронная обертка для асинхронной функции"""
    # Заменяем хардкод канала на значение из .env
    message = message.replace('@uzbekworld_test', CHANNEL_ID)
    return asyncio.run(post_to_telegram_async(message))

# ============================================
# ОСНОВНАЯ ЛОГИКА ПОСТИНГА
# ============================================

def create_and_post():
    """Создает и публикует случайный пост"""
    
    # Выбираем случайный тип поста с весами
    post_types = [
        (generate_countdown_post, 12),
        (generate_player_post, 18),
        (generate_match_reminder, 10),
        (generate_motivation_post, 15),
        (generate_fact_post, 12),
        (generate_community_post, 10),
        (generate_group_info_post, 8),
        (generate_news_post, 10),
        (generate_engagement_post, 15),
    ]
    
    functions, weights = zip(*post_types)
    post_function = random.choices(functions, weights=weights)[0]
    
    content = post_function()
    
    post_to_telegram(content)

# ============================================
# РАСПИСАНИЕ ПОСТОВ
# ============================================

def setup_schedule():
    """Настраивает расписание постов"""
    
    schedule.every(POST_INTERVAL_MINUTES).minutes.do(create_and_post)
    
    posts_per_day = int(24 * 60 / POST_INTERVAL_MINUTES)
    
    print("🚀 Бот запущен!")
    print(f"📢 Канал: {CHANNEL_ID}")
    print(f"⏰ Интервал: каждые {POST_INTERVAL_MINUTES} минут(ы)")
    print(f"📊 Примерно {posts_per_day} постов в день")
    print(f"📅 Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏳ До первого матча: {get_days_until_first_match()} дней")
    print("\n⏳ Ожидание следующего поста...\n")

# ============================================
# ЗАПУСК БОТА
# ============================================

WELCOME_MESSAGE = """👋 Xush kelibsiz, {name}!

🇺🇿 Uzbek World Club'ga qo'shilganingiz uchun rahmat!

Biz O'zbekistonning Jahon chempionatidagi tarixiy ishtirokini birga kuzatamiz.

📅 Birinchi o'yin: 17-iyun — 🇵🇹 Portugaliyaga qarshi (Xyuston)
📅 Ikkinchi o'yin: 21-iyun — 🇨🇴 Kolumbiyaga qarshi (Atlanta)
📅 Uchinchi o'yin: 25-iyun — 🇨🇩 Kongoga qarshi (Mexiko)

✅ Watch party tashkil etmoqchimisiz? Adminga yozing.
✅ City Captain bo'lmoqchimisiz? Adminga yozing.

🌍 Qaysi shahardansiz?"""

async def welcome_new_member(update, context):
    """Отправляет приветственное сообщение новым участникам группы"""
    try:
        for member in update.message.new_chat_members:
            if not member.is_bot:
                name = member.first_name or member.username or "Do'stim"
                msg = WELCOME_MESSAGE.format(name=name)
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=msg
                )
    except Exception as e:
        print(f"❌ Welcome error: {e}")


def _run_polling_in_thread():
    """Запускает polling в отдельном потоке с собственным event loop"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    loop.run_until_complete(app.initialize())
    loop.run_until_complete(app.start())
    loop.run_until_complete(app.updater.start_polling())
    print("✅ Welcome handler started (new member greeting active)")
    loop.run_forever()


def start_welcome_handler():
    """Запускает Telegram polling для нового участника"""
    try:
        thread = threading.Thread(target=_run_polling_in_thread, daemon=True)
        thread.start()
    except Exception as e:
        print(f"❌ Failed to start welcome handler: {e}")

if __name__ == "__main__":

    print("🧪 Test postini yuborish...")
    test_message = f"🚀 UZBEK WORLD CUP BOTI ISHGA TUSHDI!\n\n✅ Avtomatik postlar faollashtirildi\n⏰ Interval: har {POST_INTERVAL_MINUTES} daqiqada\n⏳ Birinchi o'yingacha: {get_days_until_first_match()} kun\n\n📅 17-iyun — 🇵🇹 Portugaliya (Xyuston)\n📅 21-iyun — 🇨🇴 Kolumbiya (Atlanta)\n📅 25-iyun — 🇨🇩 Kongo DR (Mexiko)\n\nO'zbekiston terma jamoasi yangiliklarini kuzatib boring!\n\n👉 @uzbekworld_test\n\n#UzbekWorldCup"
    post_to_telegram(test_message)
    
    start_welcome_handler()
    setup_schedule()
    
    while True:
        schedule.run_pending()
        time.sleep(1)
