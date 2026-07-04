"""
Административные команды: обратная связь, ответы на отзывы
"""
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import add_feedback, is_admin, mark_feedback_replied
from utils.logger import get_logger

logger = get_logger('admin')


# ----- FSM состояния для отзывов и ответов -----
class FeedbackStates(StatesGroup):
    waiting_for_feedback = State()
    waiting_for_reply_user = State()
    waiting_for_reply_message = State()


# ----- ID администратора (задаётся при инициализации) -----
ADMIN_ID: int = None


def set_admin_id(admin_id: int):
    """Установка ID администратора"""
    global ADMIN_ID
    ADMIN_ID = admin_id
    logger.info(f"Установлен ADMIN_ID: {ADMIN_ID}")


async def send_feedback_to_admin(bot: Bot, user_id: int, username: str, message: str):
    """Отправка отзыва администратору"""
    if ADMIN_ID is None:
        logger.error("ADMIN_ID не установлен. Отзыв не отправлен.")
        return
    
    await bot.send_message(
        ADMIN_ID,
        f"📝 <b>Новый отзыв!</b>\n\n"
        f"👤 <b>Пользователь:</b> {username} (ID: {user_id})\n"
        f"💬 <b>Сообщение:</b>\n{message}",
        parse_mode="HTML"
    )


def register_admin_handlers(dp: Dispatcher):
    """Регистрация всех административных хендлеров"""

    # ----- КОМАНДА /feedback -----
    @dp.message(Command("feedback"))
    async def cmd_feedback(message: types.Message, state: FSMContext):
        """Начало сбора отзыва"""
        await message.answer(
            "📝 <b>Поделитесь вашим мнением!</b>\n\n"
            "Напишите, что вам нравится в работе «Авто-Хантера», а что можно улучшить. "
            "Ваши отзывы помогают делать сервис лучше.\n\n"
            "💡 Если нашли ошибку, опишите шаги, как её воспроизвести.\n\n"
            "Для отмены отправьте /cancel",
            parse_mode="HTML"
        )
        await state.set_state(FeedbackStates.waiting_for_feedback)

    @dp.message(FeedbackStates.waiting_for_feedback)
    async def process_feedback(message: types.Message, state: FSMContext, bot: Bot):
        """Обработка полученного отзыва"""
        user_id = message.from_user.id
        username = message.from_user.username or f"@{message.from_user.full_name}"
        feedback_text = message.text.strip()

        if len(feedback_text) < 3:
            await message.answer("❌ Пожалуйста, напишите более развернутый отзыв (минимум 3 символа).")
            return

        # Сохраняем отзыв в БД
        if add_feedback(user_id, username, feedback_text):
            await message.answer(
                "✅ <b>Спасибо за ваш отзыв!</b>\n\n"
                "Он очень важен для развития «Авто-Хантера».",
                parse_mode="HTML"
            )
            # Отправляем отзыв админу
            await send_feedback_to_admin(bot, user_id, username, feedback_text)
            logger.info(f"Новый отзыв от {user_id}: {feedback_text[:50]}...")
        else:
            await message.answer("❌ Произошла ошибка при сохранении отзыва. Попробуйте позже.")

        await state.clear()

    # ----- КОМАНДА /reply (только для админа) -----
    @dp.message(Command("reply"))
    async def cmd_reply(message: types.Message, state: FSMContext):
        """Ответ пользователю на его отзыв (доступно только админу)"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.answer("⛔ У вас нет прав для выполнения этой команды.")
            return

        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            await message.answer(
                "❌ <b>Использование:</b> <code>/reply user_id текст ответа</code>\n\n"
                "Пример: <code>/reply 123456789 Спасибо за отзыв, мы уже работаем над этим!</code>\n\n"
                "ID пользователя можно узнать из сообщения с отзывом.",
                parse_mode="HTML"
            )
            return

        try:
            target_user_id = int(args[1])
            reply_text = args[2]
            
            # Отправляем ответ пользователю
            await bot.send_message(
                target_user_id,
                f"✉️ <b>Ответ от разработчика «Авто-Хантер»</b>\n\n"
                f"{reply_text}\n\n"
                f"💡 Если у вас остались вопросы или идеи, пишите ещё!",
                parse_mode="HTML"
            )
            
            # Помечаем последний отзыв этого пользователя как обработанный
            # (можно доработать: искать последний непрочитанный отзыв)
            await message.answer(f"✅ Ответ отправлен пользователю {target_user_id}")
            logger.info(f"Админ ответил пользователю {target_user_id}")
            
        except ValueError:
            await message.answer("❌ Неверный формат user_id. Должно быть число.")
        except Exception as e:
            await message.answer(f"❌ Ошибка при отправке: {e}")

    # ----- КОМАНДА /cancel -----
    @dp.message(Command("cancel"))
    async def cmd_cancel(message: types.Message, state: FSMContext):
        """Отмена текущей операции"""
        current_state = await state.get_state()
        if current_state is None:
            await message.answer("❌ Нет активной операции для отмены.")
            return
        
        await state.clear()
        await message.answer("✅ Операция отменена.")

    # ----- КОМАНДА /stats (админская) -----
    @dp.message(Command("stats"))
    async def cmd_stats(message: types.Message):
        """Статистика работы бота (доступно только админу)"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.answer("⛔ У вас нет прав для выполнения этой команды.")
            return
        
        import sqlite3
        from database.db import DB_PATH
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Количество пользователей
        cursor.execute('SELECT COUNT(*) FROM users')
        users_count = cursor.fetchone()[0]
        
        # Количество активных фильтров
        cursor.execute('SELECT COUNT(*) FROM filters WHERE is_active = 1')
        filters_count = cursor.fetchone()[0]
        
        # Количество отзывов
        cursor.execute('SELECT COUNT(*) FROM feedback')
        feedback_count = cursor.fetchone()[0]
        
        # Количество непрочитанных отзывов
        cursor.execute('SELECT COUNT(*) FROM feedback WHERE replied = 0')
        unread_feedback = cursor.fetchone()[0]
        
        conn.close()
        
        await message.answer(
            f"📊 <b>Статистика «Авто-Хантер»</b>\n\n"
            f"👤 Пользователей: {users_count}\n"
            f"🎯 Активных фильтров: {filters_count}\n"
            f"📝 Отзывов всего: {feedback_count}\n"
            f"📩 Непрочитанных отзывов: {unread_feedback}",
            parse_mode="HTML"
        )
