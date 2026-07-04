#!/bin/bash
echo "📦 Установка Chromium для Playwright..."
playwright install chromium
echo "🚀 Запуск бота..."
python src/bot.py
