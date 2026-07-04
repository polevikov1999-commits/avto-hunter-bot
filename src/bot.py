import asyncio
import sys
import os
import logging
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.db import (
    init_db, add_user, add_filter, get_user_filters,
    delete_filter, count_user_filters, is_admin
)
from parser.client import AVByParser
from monitor.monitor import Monitor
from notifier import init_bot as init_notifier
from admin import register_admin_handlers, set_admin_id
from utils.logger import setup_logger

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "8985781891:AAF144OyAVnWey45sfflwbVyKLWzD35gWtY"          # Замените на ваш токен
ADMIN_ID = 7935728554                   # Замените на ваш Telegram ID

# Ограничения для бесплатных пользователей
MAX_FREE_FILTERS = 3

# ==================== ЛОГГЕР ====================
logger = setup_logger('av_bot', level=logging.INFO)

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
parser = AVByParser()

# База данных
init_db()
logger.info("База данных инициализирована")

# Бот для уведомлений
init_notifier(BOT_TOKEN)
logger.info("Бот для уведомлений инициализирован")

# Устанавливаем ID администратора для admin.py
set_admin_id(ADMIN_ID)

# Создаём монитор
monitor = Monitor(check_interval=300, ads_limit=20)
logger.info("Монитор создан, интервал проверки: 300 сек, лимит объявлений: 20")

# Регистрируем административные хендлеры
register_admin_handlers(dp)
logger.info("Административные хендлеры зарегистрированы")


# ==================== FSM ДЛЯ ДОБАВЛЕНИЯ ФИЛЬТРА ====================
class AddFilterStates(StatesGroup):
    waiting_for_url = State()
    waiting_for_name = State()


# ==================== КОМАНДЫ БОТА ====================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = message.from_user
    add_user(user.id, user.username, user.first_name, user.last_name)
    
    # Если этот пользователь — администратор, обновляем флаг в БД
    if user.id == ADMIN_ID:
        import sqlite3
        from database.db import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        conn.execute('UPDATE users SET is_admin = 1 WHERE user_id = ?', (user.id,))
        conn.commit()
        conn.close()
        logger.info(f"Администратор {user.id} активирован")
    
    logger.info(f"Пользователь {user.id} (@{user.username}) запустил бота")
    
    await message.answer(
        "🚗 <b>«Авто-Хантер» — мониторинг цен на AV.BY</b>\n\n"
        "Я охочусь за новыми объявлениями на AV.BY и мгновенно приношу их вам в Telegram. "
        "Больше не нужно каждые 5 минут обновлять страницу — я сделаю это за вас.\n\n"
        "<b>Как пользоваться:</b>\n"
        "1️⃣ Настройте фильтры на AV.BY (марка, модель, цена, регион)\n"
        "2️⃣ Скопируйте ссылку на страницу с результатами\n"
        "3️⃣ Отправьте команду /track и придумайте название для фильтра\n\n"
        f"🔥 <b>Бесплатный тариф:</b> до {MAX_FREE_FILTERS} фильтров, проверка раз в 30 минут.\n"
        "Скоро — больше возможностей!\n\n"
        "<b>Команды:</b>\n"
        "/track — начать охоту (добавить фильтр)\n"
        "/list — моя добыча (список фильтров)\n"
        "/untrack — забыть фильтр (удалить)\n"
        "/feedback — оставить отзыв или предложение\n"
        "/help — помощь\n\n"
        "💡 <b>Совет:</b> Используйте понятные названия для фильтров, например «BMW X5 Минск».",
        parse_mode="HTML"
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 <b>Помощь по «Авто-Хантеру»</b>\n\n"
        "1. <b>/track</b> — добавить новый фильтр\n"
        "   • Отправьте ссылку с cars.av.by\n"
        "   • Введите название для фильтра\n\n"
        "2. <b>/list</b> — показать все ваши фильтры\n\n"
        "3. <b>/untrack</b> — удалить фильтр\n\n"
        "4. <b>/feedback</b> — оставить отзыв\n\n"
        f"🔥 <b>Бесплатный тариф:</b> до {MAX_FREE_FILTERS} фильтров, проверка раз в 30 минут.\n\n"
        "<b>Как получить ссылку для /track:</b>\n"
        "• Зайдите на cars.av.by\n"
        "• Настройте фильтры (марка, модель, цена, регион)\n"
        "• Нажмите «Показать»\n"
        "• Скопируйте URL из адресной строки\n\n"
        "Бот проверяет новые объявления раз в 30 минут для бесплатного тарифа.",
        parse_mode="HTML"
    )


@dp.message(Command("track"))
async def cmd_track(message: types.Message, state: FSMContext):
    """Начало добавления фильтра — запрашиваем ссылку"""
    user_id = message.from_user.id
    
    # Проверяем ограничение по количеству фильтров
    current_filters = count_user_filters(user_id)
    if current_filters >= MAX_FREE_FILTERS:
        await message.answer(
            f"❌ <b>Достигнут лимит фильтров!</b>\n\n"
            f"На бесплатном тарифе можно добавить не более {MAX_FREE_FILTERS} фильтров.\n"
            f"У вас уже {current_filters} фильтр(ов).\n\n"
            f"Чтобы добавить новый, удалите один из существующих через /untrack.\n"
            f"Скоро будут доступны платные тарифы с безлимитом!",
            parse_mode="HTML"
        )
        return
    
    await message.answer(
        "🔗 <b>Отправьте ссылку на фильтр с AV.BY</b>\n\n"
        "Пример: <code>/track https://cars.av.by/filter?brands[0][brand]=8...</code>\n\n"
        "Для отмены отправьте /cancel",
        parse_mode="HTML"
    )
    await state.set_state(AddFilterStates.waiting_for_url)


@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    """Отмена текущей операции"""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("❌ Нет активной операции для отмены.")
        return
    
    await state.clear()
    await message.answer("✅ Операция отменена.")


@dp.message(AddFilterStates.waiting_for_url)
async def process_filter_url(message: types.Message, state: FSMContext):
    """Обработка полученной ссылки"""
    user_id = message.from_user.id
    url = message.text.strip()
    
    if "cars.av.by" not in url:
        await message.answer("❌ Пожалуйста, отправьте ссылку с cars.av.by\n\nДля отмены отправьте /cancel")
        return
    
    status_msg = await message.answer("🔍 Проверяю ссылку...")
    
    ads = await parser.fetch_ads(url, limit=20)
    
    if not ads:
        await status_msg.edit_text("❌ Не удалось получить объявления по этой ссылке. Проверьте её правильность.")
        await state.clear()
        return
    
    await state.update_data(url=url, first_ad_id=ads[0]['id'])
    
    await status_msg.edit_text(
        f"✅ Ссылка работает!\n\n"
        f"📌 <b>Первое объявление в выдаче:</b>\n"
        f"{ads[0]['title'][:100]}...\n\n"
        f"📝 <b>Теперь введите название для этого фильтра</b>\n"
        f"(например, «BMW X5 Минск»)\n\n"
        f"Для отмены отправьте /cancel",
        parse_mode="HTML"
    )
    await state.set_state(AddFilterStates.waiting_for_name)


@dp.message(AddFilterStates.waiting_for_name)
async def process_filter_name(message: types.Message, state: FSMContext):
    """Обработка названия фильтра и сохранение"""
    user_id = message.from_user.id
    name = message.text.strip()
    
    if len(name) < 3:
        await message.answer("❌ Название должно содержать хотя бы 3 символа. Попробуйте ещё раз.\n\nДля отмены отправьте /cancel")
        return
    
    if len(name) > 50:
        await message.answer("❌ Название слишком длинное (максимум 50 символов). Попробуйте ещё раз.\n\nДля отмены отправьте /cancel")
        return
    
    data = await state.get_data()
    url = data['url']
    first_ad_id = data['first_ad_id']
    
    filter_id = add_filter(user_id, url, name=name, last_first_ad_id=first_ad_id)
    
    if filter_id:
        logger.info(f"Фильтр {filter_id} '{name}' добавлен для пользователя {user_id}")
        await message.answer(
            f"✅ <b>Фильтр добавлен!</b>\n\n"
            f"📌 <b>Название:</b> {name}\n"
            f"🆔 <b>Первый ID:</b> {first_ad_id}\n\n"
            f"Я буду отслеживать новые объявления и присылать уведомления.",
            parse_mode="HTML"
        )
    else:
        logger.error(f"Ошибка сохранения фильтра для пользователя {user_id}")
        await message.answer("❌ Ошибка при сохранении фильтра.")
    
    await state.clear()


@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    """Показывает все фильтры пользователя"""
    user_id = message.from_user.id
    filters = get_user_filters(user_id)
    current_count = len(filters)
    
    if not filters:
        await message.answer(
            f"📭 У вас нет отслеживаемых фильтров.\n\n"
            f"Добавьте первый командой /track\n"
            f"Доступно фильтров: {current_count}/{MAX_FREE_FILTERS}"
        )
        return
    
    text = f"📋 <b>Ваши фильтры ({current_count}/{MAX_FREE_FILTERS}):</b>\n\n"
    for f in filters:
        text += f"🆔 <b>{f['id']}</b> — <b>{f['name']}</b>\n"
        text += f"🕐 Последняя проверка: {f['last_checked'] or 'ещё не проверялся'}\n\n"
    
    await message.answer(text, parse_mode="HTML")


@dp.message(Command("untrack"))
async def cmd_untrack(message: types.Message):
    """Начало удаления фильтра"""
    user_id = message.from_user.id
    filters = get_user_filters(user_id)
    
    if not filters:
        await message.answer("📭 У вас нет отслеживаемых фильтров.")
        return
    
    keyboard = InlineKeyboardBuilder()
    for f in filters:
        name = f['name'] if f['name'] else f"Фильтр {f['id']}"
        name = name[:40] if len(name) > 40 else name
        keyboard.add(InlineKeyboardButton(
            text=f"❌ {name}",
            callback_data=f"delete_filter_{f['id']}"
        ))
    keyboard.adjust(1)
    
    await message.answer(
        "🗑️ <b>Выберите фильтр для удаления:</b>",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("delete_filter_"))
async def callback_delete_filter(callback: types.CallbackQuery):
    filter_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    if delete_filter(filter_id, user_id):
        logger.info(f"Пользователь {user_id} удалил фильтр {filter_id}")
        await callback.answer("Фильтр удалён")
        await callback.message.edit_text("✅ Фильтр удалён.")
    else:
        logger.error(f"Ошибка удаления фильтра {filter_id} для пользователя {user_id}")
        await callback.answer("Ошибка при удалении", show_alert=True)


# ==================== ЗАПУСК ====================
async def main():
    logger.info("🚀 «Авто-Хантер» запускается...")
    
    # Запускаем монитор в фоне
    asyncio.create_task(monitor.run())
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        logger.info("«Авто-Хантер» остановлен")


if __name__ == "__main__":
    asyncio.run(main())
