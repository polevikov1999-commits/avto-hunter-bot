import asyncio
import sys
import os
import logging
import json
import sqlite3
from datetime import datetime, timedelta
import pytz
import time

# Добавляем путь к модулям
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import KeyboardButton, WebAppInfo, ReplyKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import (
    init_db, add_user, add_filter, get_user_filters, delete_filter,
    count_user_filters, is_admin, check_premium, activate_premium,
    add_feedback, DB_PATH
)
from parser.client import AVByParser
from monitor.monitor import Monitor
from notifier import init_bot as init_notifier
from admin import register_admin_handlers, set_admin_id
from utils.logger import setup_logger

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "8985781891:AAF144OyAVnWey45sfflwbVyKLWzD35gWtY"  # Замените на ваш токен
ADMIN_ID = 7935728554  # Замените на ваш Telegram ID
WEBAPP_URL = "https://polevikov1999-commits.github.io/avto-hunter-webapp/"  # Ссылка на мини-приложение

# Ограничения для бесплатных пользователей
MAX_FREE_FILTERS = 3

# ==================== ВРЕМЕННАЯ ЗОНА ====================
os.environ['TZ'] = 'Europe/Minsk'
try:
    time.tzset()
except AttributeError:
    pass

def get_minsk_time():
    tz = pytz.timezone('Europe/Minsk')
    return datetime.now(tz)

def format_time(dt):
    return dt.strftime('%Y-%m-%d %H:%M:%S')

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

# Устанавливаем ID администратора
set_admin_id(ADMIN_ID)

# Создаём монитор
monitor = Monitor(check_interval=300, ads_limit=20)
logger.info("Монитор создан")

# Регистрируем административные хендлеры
register_admin_handlers(dp)
logger.info("Административные хендлеры зарегистрированы")

# ==================== WEBAPP КНОПКА ====================
web_app_button = KeyboardButton(
    text="🔍 Настроить фильтр",
    web_app=WebAppInfo(url=WEBAPP_URL)
)

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[[web_app_button]],
    resize_keyboard=True
)


# ==================== FSM ДЛЯ ДОБАВЛЕНИЯ ФИЛЬТРА ====================
class AddFilterStates(StatesGroup):
    waiting_for_url = State()
    waiting_for_name = State()


class FeedbackStates(StatesGroup):
    waiting_for_feedback = State()


# ==================== КОМАНДЫ БОТА ====================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = message.from_user
    add_user(user.id, user.username, user.first_name, user.last_name)
    
    # Если этот пользователь — администратор, обновляем флаг
    if user.id == ADMIN_ID:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('UPDATE users SET is_admin = 1 WHERE user_id = ?', (user.id,))
        conn.commit()
        conn.close()
        logger.info(f"Администратор {user.id} активирован")
    
    logger.info(f"Пользователь {user.id} (@{user.username}) запустил бота")
    
    await message.answer(
        "🚗 <b>«Авто-Хантер» — мониторинг цен на AV.BY</b>\n\n"
        "Я охочусь за новыми объявлениями на AV.BY и мгновенно приношу их вам в Telegram.\n\n"
        "📌 <b>Как пользоваться:</b>\n"
        "1️⃣ Нажмите кнопку «Настроить фильтр»\n"
        "2️⃣ Выберите марку и модель\n"
        "3️⃣ Настройте цену, год и регион\n"
        "4️⃣ Нажмите «Начать охоту» — фильтр добавится автоматически!\n\n"
        "📊 <b>Бесплатный тариф:</b> 3 фильтра, проверка раз в 30 минут\n"
        "💎 <b>Премиум:</b> безлимит фильтров, проверка раз в 5 минут\n\n"
        "<b>Команды:</b>\n"
        "/list — мои фильтры\n"
        "/untrack — удалить фильтр\n"
        "/profile — мой профиль\n"
        "/promo — активировать промокод\n"
        "/feedback — отзыв или предложение\n"
        "/help — помощь",
        reply_markup=main_keyboard,
        parse_mode="HTML"
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 <b>Помощь по «Авто-Хантеру»</b>\n\n"
        "1. <b>/track</b> — добавить фильтр вручную\n"
        "   • Отправьте ссылку с cars.av.by\n"
        "   • Введите название для фильтра\n\n"
        "2. <b>/list</b> — показать все ваши фильтры\n\n"
        "3. <b>/untrack</b> — удалить фильтр\n\n"
        "4. <b>/profile</b> — информация о вашем профиле\n\n"
        "5. <b>/promo</b> — активировать промокод\n\n"
        "6. <b>/feedback</b> — оставить отзыв\n\n"
        f"🔥 <b>Бесплатный тариф:</b> до {MAX_FREE_FILTERS} фильтров, проверка раз в 30 минут.\n\n"
        "<b>Как получить ссылку для /track:</b>\n"
        "• Зайдите на cars.av.by\n"
        "• Настройте фильтры\n"
        "• Скопируйте URL из адресной строки\n\n"
        "💡 <b>Совет:</b> Используйте кнопку «Настроить фильтр» — это проще и быстрее!",
        parse_mode="HTML"
    )


@dp.message(Command("track"))
async def cmd_track(message: types.Message, state: FSMContext):
    """Начало добавления фильтра — запрашиваем ссылку"""
    user_id = message.from_user.id
    
    # Проверяем ограничение по количеству фильтров
    current_filters = count_user_filters(user_id)
    is_premium = check_premium(user_id)
    
    if not is_premium and current_filters >= MAX_FREE_FILTERS:
        await message.answer(
            f"❌ <b>Достигнут лимит фильтров!</b>\n\n"
            f"На бесплатном тарифе можно добавить не более {MAX_FREE_FILTERS} фильтров.\n"
            f"У вас уже {current_filters} фильтр(ов).\n\n"
            f"💎 Чтобы добавить больше, активируйте премиум-доступ.\n"
            f"Введите промокод, если у вас есть: /promo КОД",
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
    is_premium = check_premium(user_id)
    max_filters = MAX_FREE_FILTERS if not is_premium else "∞"
    
    if not filters:
        await message.answer(
            f"📭 У вас нет отслеживаемых фильтров.\n\n"
            f"Добавьте первый через кнопку «Настроить фильтр» или командой /track\n"
            f"Доступно фильтров: {current_count}/{max_filters}"
        )
        return
    
    text = f"📋 <b>Ваши фильтры ({current_count}/{max_filters}):</b>\n\n"
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


# ==================== ИСПРАВЛЕННАЯ КОМАНДА /profile ====================
@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    """Профиль пользователя"""
    user_id = message.from_user.id
    filters_count = count_user_filters(user_id)
    is_premium = check_premium(user_id)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Получаем дату регистрации из БД
    cursor.execute('SELECT created_at FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    created_at = row[0] if row and row[0] else "неизвестно"
    
    # Получаем информацию о подписке
    cursor.execute('SELECT expires_at FROM subscriptions WHERE user_id = ?', (user_id,))
    sub_row = cursor.fetchone()
    conn.close()
    
    if is_premium and sub_row and sub_row[0]:
        try:
            expires = datetime.strptime(sub_row[0], '%Y-%m-%d %H:%M:%S')
            days_left = (expires - datetime.now()).days
            status = f"🟢 Премиум (осталось {days_left} дней)"
        except:
            status = "🟢 Премиум (активна)"
    else:
        status = f"🟡 Бесплатный ({MAX_FREE_FILTERS} фильтра, проверка раз в 30 минут)"
    
    await message.answer(
        f"👤 <b>Ваш профиль</b>\n\n"
        f"📊 Статус: {status}\n"
        f"🎯 Фильтров: {filters_count}/{MAX_FREE_FILTERS if not is_premium else '∞'}\n"
        f"📅 Дата регистрации: {created_at}\n"
        f"🆔 ID: {user_id}",
        parse_mode="HTML"
    )


@dp.message(Command("promo"))
async def cmd_promo(message: types.Message):
    """Активация промокода"""
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "❌ <b>Использование:</b>\n"
            "<code>/promo КОД</code>\n\n"
            "Пример: <code>/promo PREMIUM2025</code>",
            parse_mode="HTML"
        )
        return
    
    code = args[1].upper()
    user_id = message.from_user.id
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Проверяем промокод
    cursor.execute('''
        SELECT id, days, max_uses, used_count FROM promo_codes
        WHERE code = ? AND (max_uses > used_count OR max_uses = -1)
    ''', (code,))
    promo = cursor.fetchone()
    
    if not promo:
        await message.answer("❌ Промокод не найден или уже использован.")
        conn.close()
        return
    
    # Проверяем, не использовал ли пользователь этот промокод
    cursor.execute('''
        SELECT 1 FROM used_promo WHERE user_id = ? AND promo_code = ?
    ''', (user_id, code))
    if cursor.fetchone():
        await message.answer("❌ Вы уже использовали этот промокод.")
        conn.close()
        return
    
    # Активируем подписку
    promo_id, days, max_uses, used_count = promo
    activate_premium(user_id, days)
    
    # Записываем использование
    cursor.execute('''
        INSERT INTO used_promo (user_id, promo_code) VALUES (?, ?)
    ''', (user_id, code))
    
    # Увеличиваем счётчик
    cursor.execute('''
        UPDATE promo_codes SET used_count = used_count + 1 WHERE code = ?
    ''', (code,))
    
    conn.commit()
    conn.close()
    
    await message.answer(
        f"✅ <b>Промокод активирован!</b>\n\n"
        f"Вы получили {days} дней премиум-доступа.\n"
        f"Теперь у вас безлимит фильтров и проверка раз в 5 минут! 🎉",
        parse_mode="HTML"
    )


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
async def process_feedback(message: types.Message, state: FSMContext):
    """Обработка полученного отзыва"""
    user_id = message.from_user.id
    username = message.from_user.username or f"@{message.from_user.full_name}"
    feedback_text = message.text.strip()
    
    if len(feedback_text) < 3:
        await message.answer("❌ Пожалуйста, напишите более развернутый отзыв (минимум 3 символа).")
        return
    
    if add_feedback(user_id, username, feedback_text):
        await message.answer(
            "✅ <b>Спасибо за ваш отзыв!</b>\n\n"
            "Он очень важен для развития «Авто-Хантера».",
            parse_mode="HTML"
        )
        # Отправляем отзыв админу
        await bot.send_message(
            ADMIN_ID,
            f"📝 <b>Новый отзыв!</b>\n\n"
            f"👤 <b>Пользователь:</b> {username} (ID: {user_id})\n"
            f"💬 <b>Сообщение:</b>\n{feedback_text}",
            parse_mode="HTML"
        )
        logger.info(f"Новый отзыв от {user_id}: {feedback_text[:50]}...")
    else:
        await message.answer("❌ Произошла ошибка при сохранении отзыва. Попробуйте позже.")
    
    await state.clear()


# ==================== ОБРАБОТКА WEBAPP ДАННЫХ ====================
@dp.message(F.web_app_data)
async def handle_web_app_data(message: types.Message):
    """Обработка данных из мини-приложения"""
    user_id = message.from_user.id
    
    try:
        data = json.loads(message.web_app_data.data)
        url = data.get('url')
        brand = data.get('brand', '')
        model = data.get('model', '')
        
        if not url:
            await message.answer("❌ Ошибка: ссылка не получена.")
            return
        
        # Проверяем лимит фильтров
        current_filters = count_user_filters(user_id)
        is_premium = check_premium(user_id)
        
        if not is_premium and current_filters >= MAX_FREE_FILTERS:
            await message.answer(
                f"❌ <b>Достигнут лимит фильтров!</b>\n\n"
                f"На бесплатном тарифе можно добавить не более {MAX_FREE_FILTERS} фильтров.\n"
                f"У вас уже {current_filters} фильтр(ов).\n\n"
                f"💎 Чтобы добавить больше, активируйте премиум-доступ.\n"
                f"Введите промокод, если у вас есть: /promo КОД",
                parse_mode="HTML"
            )
            return
        
        # Добавляем фильтр
        name = f"{brand} {model}" if brand and model else f"Фильтр {current_filters + 1}"
        filter_id = add_filter(user_id, url, name=name)
        
        if filter_id:
            logger.info(f"Фильтр {filter_id} добавлен для пользователя {user_id} через WebApp")
            await message.answer(
                f"✅ <b>Фильтр добавлен!</b>\n\n"
                f"🚗 {name}\n"
                f"📊 Фильтров: {current_filters + 1}/{MAX_FREE_FILTERS if not is_premium else '∞'}\n\n"
                f"Я буду отслеживать новые объявления и присылать уведомления.",
                parse_mode="HTML"
            )
        else:
            await message.answer("❌ Ошибка при сохранении фильтра.")
            
    except json.JSONDecodeError:
        await message.answer("❌ Ошибка обработки данных.")
    except Exception as e:
        logger.error(f"Ошибка обработки WebApp данных: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте ещё раз.")


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
