"""
Конфигурация проекта
"""
import os
from dotenv import load_dotenv
from pathlib import Path

# Загружаем .env файл
BASE_DIR = Path(__file__).parent.parent.parent
env_file = BASE_DIR / ".env"
if env_file.exists():
    load_dotenv(env_file)

# Telegram Bot
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env файле")

# База данных
DATABASE_PATH = BASE_DIR / "av_bot.db"

# Парсер
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
