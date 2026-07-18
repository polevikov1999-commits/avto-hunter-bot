import sqlite3
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DB_PATH = "av_bot.db"


def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            is_admin BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица фильтров
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS filters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            name TEXT,
            last_first_ad_id TEXT,
            last_checked TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            UNIQUE(user_id, url)
        )
    ''')
    
    # Таблица истории объявлений
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS seen_ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filter_id INTEGER NOT NULL,
            ad_id TEXT NOT NULL,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(filter_id, ad_id)
        )
    ''')
    
    # Таблица отзывов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            message TEXT NOT NULL,
            replied BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица промокодов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promo_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            days INTEGER NOT NULL,
            max_uses INTEGER DEFAULT 1,
            used_count INTEGER DEFAULT 0,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица подписок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER PRIMARY KEY,
            subscription_type TEXT DEFAULT 'free',
            expires_at TIMESTAMP,
            activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица использованных промокодов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS used_promo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            promo_code TEXT,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")


def add_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None) -> bool:
    """Добавление пользователя"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления пользователя: {e}")
        return False
    finally:
        conn.close()


def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT is_admin FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None and row[0] == 1


def add_filter(user_id: int, url: str, name: str = None, last_first_ad_id: str = None) -> Optional[int]:
    """Добавление фильтра для пользователя"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO filters (user_id, url, name, last_first_ad_id, is_active)
            VALUES (?, ?, ?, ?, 1)
        ''', (user_id, url, name, last_first_ad_id))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        logger.error(f"Ошибка добавления фильтра: {e}")
        return None
    finally:
        conn.close()


def get_user_filters(user_id: int) -> List[Dict]:
    """Получение всех активных фильтров пользователя"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, url, name, last_first_ad_id, last_checked
        FROM filters
        WHERE user_id = ? AND is_active = 1
    ''', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    return [{
        'id': row[0],
        'url': row[1],
        'name': row[2] if row[2] else f"Фильтр {row[0]}",
        'last_first_ad_id': row[3],
        'last_checked': row[4]
    } for row in rows]


def count_user_filters(user_id: int) -> int:
    """Подсчёт количества активных фильтров пользователя"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COUNT(*) FROM filters
        WHERE user_id = ? AND is_active = 1
    ''', (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count


def delete_filter(filter_id: int, user_id: int) -> bool:
    """Удаление фильтра (мягкое удаление)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE filters SET is_active = 0
        WHERE id = ? AND user_id = ?
    ''', (filter_id, user_id))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0


def update_first_ad_id(filter_id: int, first_ad_id: str):
    """Обновление ID первого объявления и времени проверки"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE filters
        SET last_first_ad_id = ?, last_checked = ?
        WHERE id = ?
    ''', (first_ad_id, datetime.now(), filter_id))
    conn.commit()
    conn.close()


def update_last_checked(filter_id: int):
    """Обновление только времени последней проверки"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE filters
        SET last_checked = ?
        WHERE id = ?
    ''', (datetime.now(), filter_id))
    conn.commit()
    conn.close()


def is_ad_seen(filter_id: int, ad_id: str) -> bool:
    """Проверка, отправляли ли уже уведомление об этом объявлении"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 1 FROM seen_ads WHERE filter_id = ? AND ad_id = ?
    ''', (filter_id, ad_id))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def mark_ad_seen(filter_id: int, ad_id: str):
    """Отметить объявление как отправленное"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO seen_ads (filter_id, ad_id)
        VALUES (?, ?)
    ''', (filter_id, ad_id))
    conn.commit()
    conn.close()


def clear_old_seen_ads(filter_id: int):
    """Очистка старых записей о просмотренных объявлениях (старше 7 дней)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        DELETE FROM seen_ads
        WHERE filter_id = ? AND first_seen < datetime('now', '-7 days')
    ''', (filter_id,))
    conn.commit()
    conn.close()


# ---------- ОТЗЫВЫ ----------
def add_feedback(user_id: int, username: str, message: str) -> bool:
    """Сохранение отзыва пользователя"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO feedback (user_id, username, message)
            VALUES (?, ?, ?)
        ''', (user_id, username, message))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения отзыва: {e}")
        return False
    finally:
        conn.close()


def mark_feedback_replied(feedback_id: int):
    """Отметить отзыв как обработанный"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE feedback SET replied = 1
        WHERE id = ?
    ''', (feedback_id,))
    conn.commit()
    conn.close()


# ---------- ПОДПИСКИ ----------
def check_premium(user_id: int) -> bool:
    """Проверка, активна ли премиум-подписка у пользователя"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT expires_at FROM subscriptions
        WHERE user_id = ? AND subscription_type = 'premium'
    ''', (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return False
    
    try:
        expires = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
        return expires > datetime.now()
    except:
        return False


def activate_premium(user_id: int, days: int) -> bool:
    """Активация премиум-подписки на N дней"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Проверяем, есть ли уже подписка
        cursor.execute('''
            SELECT expires_at FROM subscriptions WHERE user_id = ?
        ''', (user_id,))
        row = cursor.fetchone()
        
        if row and row[0]:
            try:
                expires = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
                if expires > datetime.now():
                    new_expires = expires + timedelta(days=days)
                else:
                    new_expires = datetime.now() + timedelta(days=days)
            except:
                new_expires = datetime.now() + timedelta(days=days)
        else:
            new_expires = datetime.now() + timedelta(days=days)
        
        cursor.execute('''
            INSERT OR REPLACE INTO subscriptions (user_id, subscription_type, expires_at)
            VALUES (?, 'premium', ?)
        ''', (user_id, new_expires.strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Ошибка активации премиума: {e}")
        return False
    finally:
        conn.close()