"""
Модуль отправки уведомлений
"""
import logging
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from typing import Dict

logger = logging.getLogger(__name__)

_bot: Bot = None


def init_bot(token: str):
    global _bot
    _bot = Bot(token=token)
    logger.info("Бот для уведомлений инициализирован")


def get_bot() -> Bot:
    if _bot is None:
        raise RuntimeError("Бот не инициализирован")
    return _bot


async def send_new_ad_notification(user_id: int, ad: Dict, filter_url: str):
    """Отправка уведомления о новом объявлении"""
    bot = get_bot()
    
    text = (
        f"🚗 <b>НОВОЕ ОБЪЯВЛЕНИЕ!</b>\n\n"
        f"<b>{ad['title']}</b>\n\n"
        f"💰 <b>Цена:</b> {ad['price']:,} BYN\n"
    )
    
    if ad.get('year'):
        text += f"📅 <b>Год:</b> {ad['year']}\n"
    if ad.get('mileage'):
        text += f"📊 <b>Пробег:</b> {ad['mileage']:,} км\n"
    if ad.get('city'):
        text += f"📍 <b>Город:</b> {ad['city']}\n"
    if ad.get('date'):
        text += f"⏰ <b>Опубликовано:</b> {ad['date']}\n"
    
    text += f"\n🔗 <a href='{ad['url']}'>Ссылка на объявление</a>"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚗 Открыть объявление", url=ad['url'])]
    ])
    
    try:
        await bot.send_message(user_id, text, parse_mode="HTML", reply_markup=keyboard)
        logger.info(f"Уведомление отправлено пользователю {user_id} об объявлении {ad['id']}")
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления: {e}")