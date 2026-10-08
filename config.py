import os
import time

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

OWNER_RAW = os.getenv("OWNER_ID") or os.getenv("ADMIN_ID") or ""
try:
    OWNER_ID = int(OWNER_RAW)
except ValueError:
    OWNER_ID = None

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

PORT = int(os.getenv("PORT", "8080"))

BOT_START_TIME = time.time()

ANIMALS = [
    {"emoji": "🐶", "slug": "dog", "name": "Собака"},
    {"emoji": "🐱", "slug": "cat", "name": "Кошка"},
    {"emoji": "🐭", "slug": "mouse", "name": "Мышь"},
    {"emoji": "🐹", "slug": "hamster", "name": "Хомяк"},
    {"emoji": "🐰", "slug": "rabbit", "name": "Кролик"},
    {"emoji": "🦊", "slug": "fox", "name": "Лиса"},
    {"emoji": "🐻", "slug": "bear", "name": "Медведь"},
    {"emoji": "🐼", "slug": "panda", "name": "Панда"},
    {"emoji": "🐨", "slug": "koala", "name": "Коала"},
    {"emoji": "🐯", "slug": "tiger", "name": "Тигр"},
    {"emoji": "🦁", "slug": "lion", "name": "Лев"},
    {"emoji": "🐮", "slug": "cow", "name": "Корова"},
    {"emoji": "🐷", "slug": "pig", "name": "Свинья"},
    {"emoji": "🐸", "slug": "frog", "name": "Лягушка"},
    {"emoji": "🐵", "slug": "monkey", "name": "Обезьяна"},
    {"emoji": "🐔", "slug": "chicken", "name": "Курица"},
    {"emoji": "🐧", "slug": "penguin", "name": "Пингвин"},
    {"emoji": "🦄", "slug": "unicorn", "name": "Единорог"},
    {"emoji": "🐴", "slug": "horse", "name": "Лошадь"},
    {"emoji": "🐢", "slug": "turtle", "name": "Черепаха"},
    {"emoji": "🐍", "slug": "snake", "name": "Змея"},
    {"emoji": "🦋", "slug": "butterfly", "name": "Бабочка"},
    {"emoji": "🐠", "slug": "fish", "name": "Рыба"},
    {"emoji": "🐘", "slug": "elephant", "name": "Слон"},
]

CONTENT_TITLES = {
    "text": "Текст",
    "photo": "Фото",
    "voice": "Голосовое сообщение",
    "video_note": "Кружок",
    "sticker": "Стикер",
    "video": "Видео",
    "audio": "Аудио",
    "document": "Документ",
    "animation": "GIF/Анимация",
    "contact": "Контакт",
    "location": "Локация",
    "poll": "Опрос",
    "invoice": "Инвойс",
    "successful_payment": "Платёж",
}