"""
Административные команды
"""
import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import is_admin, DB_PATH
from utils.logger import get_logger

logger = get_logger('admin')

# ID администратора
ADMIN_ID: int = None


def set_admin_id(admin_id: int):
    """Установка ID администратора"""
    global ADMIN_ID
    ADMIN_ID = admin_id
    logger.info(f"Установлен ADMIN_ID: {ADMIN_ID}")


def register_admin_handlers(dp: Dispatcher):
    """Регистрация всех административных хендлеров"""

    # ----- КОМАНДА /create_promo -----
    @dp.message(Command("create_promo"))
    async def cmd_create_promo(message: types.Message):
        if not is_admin(message.from_user.id):
            await message.answer("⛔ У вас нет прав для выполнения этой команды.")
            return
        
        args = message.text.split()
        if len(args) < 4:
            await message.answer(
                "❌ <b>Использование:</b>\n"
                "<code>/create_promo КОД ДНЕЙ МАКС_ИСПОЛЬЗОВАНИЙ</code>\n\n"
                "Пример: <code>/create_promo PREMIUM2025 30 10</code>\n"
                "Для безлимита укажите -1 в макс_использований",
                parse_mode="HTML"
            )
            return
        
        code = args[1].upper()
        days = int(args[2])
        max_uses = int(args[3])
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Проверяем, не существует ли уже такой код
        cursor.execute('SELECT 1 FROM promo_codes WHERE code = ?', (code,))
        if cursor.fetchone():
            await message.answer(f"❌ Промокод <code>{code}</code> уже существует.")
            conn.close()
            return
        
        cursor.execute('''
            INSERT INTO promo_codes (code, days, max_uses, created_by)
            VALUES (?, ?, ?, ?)
        ''', (code, days, max_uses, message.from_user.id))
        conn.commit()
        conn.close()
        
        await message.answer(
            f"✅ <b>Промокод создан!</b>\n\n"
            f"📌 Код: <code>{code}</code>\n"
            f"📅 Дней: {days}\n"
            f"👥 Использований: {max_uses if max_uses != -1 else '∞'}",
            parse_mode="HTML"
        )
        logger.info(f"Админ {message.from_user.id} создал промокод {code}")

    # ----- КОМАНДА /broadcast -----
    @dp.message(Command("broadcast"))
    async def cmd_broadcast(message: types.Message, bot: Bot):
        if not is_admin(message.from_user.id):
            await message.answer("⛔ У вас нет прав для выполнения этой команды.")
            return
        
        text = message.text.replace("/broadcast", "").strip()
        if not text:
            await message.answer(
                "❌ <b>Использование:</b>\n"
                "<code>/broadcast Текст сообщения</code>\n\n"
                "Пример: <code>/broadcast У нас новое обновление! ...</code>",
                parse_mode="HTML"
            )
            return
        
        # Получаем всех пользователей
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users')
        users = cursor.fetchall()
        conn.close()
        
        if not users:
            await message.answer("❌ Нет пользователей для рассылки.")
            return
        
        # Подтверждение
        confirm_keyboard = InlineKeyboardBuilder()
        confirm_keyboard.add(
            InlineKeyboardButton(text="✅ Да, отправить", callback_data="broadcast_confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")
        )
        confirm_keyboard.adjust(1)
        
        await message.answer(
            f"📨 <b>Подтверждение рассылки</b>\n\n"
            f"👥 Получателей: {len(users)}\n"
            f"📝 Текст:\n{text[:200]}{'...' if len(text) > 200 else ''}\n\n"
            f"Отправить?",
            reply_markup=confirm_keyboard.as_markup(),
            parse_mode="HTML"
        )
        
        # Сохраняем текст в состоянии
        dp['broadcast_text'] = text

    # Обработка подтверждения рассылки
    @dp.callback_query(F.data == "broadcast_confirm")
    async def broadcast_confirm(callback: types.CallbackQuery, bot: Bot):
        if not is_admin(callback.from_user.id):
            await callback.answer("⛔ Нет прав", show_alert=True)
            return
        
        text = dp.get('broadcast_text')
        if not text:
            await callback.message.edit_text("❌ Текст рассылки не найден.")
            return
        
        await callback.message.edit_text("⏳ Отправка рассылки...")
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users')
        users = cursor.fetchall()
        conn.close()
        
        success = 0
        fail = 0
        
        for user in users:
            try:
                await bot.send_message(user[0], text, parse_mode="HTML")
                success += 1
                await asyncio.sleep(0.1)
            except:
                fail += 1
        
        await callback.message.edit_text(
            f"✅ <b>Рассылка завершена!</b>\n\n"
            f"📨 Успешно: {success}\n"
            f"❌ Ошибок: {fail}",
            parse_mode="HTML"
        )
        await callback.answer()
        dp['broadcast_text'] = None

    @dp.callback_query(F.data == "broadcast_cancel")
    async def broadcast_cancel(callback: types.CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer("⛔ Нет прав", show_alert=True)
            return
        
        await callback.message.edit_text("❌ Рассылка отменена.")
        await callback.answer()
        dp['broadcast_text'] = None

    # ----- КОМАНДА /stats -----
    @dp.message(Command("stats"))
    async def cmd_stats(message: types.Message):
        if not is_admin(message.from_user.id):
            await message.answer("⛔ У вас нет прав для выполнения этой команды.")
            return
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM users')
        users_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM filters WHERE is_active = 1')
        filters_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM feedback')
        feedback_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM feedback WHERE replied = 0')
        unread_feedback = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM subscriptions WHERE subscription_type = "premium"')
        premium_count = cursor.fetchone()[0]
        
        conn.close()
        
        await message.answer(
            f"📊 <b>Статистика «Авто-Хантер»</b>\n\n"
            f"👤 Пользователей: {users_count}\n"
            f"🎯 Активных фильтров: {filters_count}\n"
            f"💎 Премиум-подписок: {premium_count}\n"
            f"📝 Отзывов всего: {feedback_count}\n"
            f"📩 Непрочитанных отзывов: {unread_feedback}",
            parse_mode="HTML"
        )