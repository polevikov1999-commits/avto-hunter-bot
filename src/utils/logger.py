"""
Настройка логирования в файл и консоль
"""
import logging
import os
from datetime import datetime

# Создаём папку для логов, если её нет
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Имя файла лога с текущей датой
log_filename = os.path.join(LOG_DIR, f"bot_{datetime.now().strftime('%Y%m%d')}.log")


def setup_logger(name: str = None, level: int = logging.INFO) -> logging.Logger:
    """
    Настройка логгера с выводом в консоль и файл

    Args:
        name: Имя логгера (если None, возвращает root логгер)
        level: Уровень логирования

    Returns:
        Настроенный логгер
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Очищаем существующие обработчики, чтобы не дублировать
    if logger.hasHandlers():
        logger.handlers.clear()

    # Формат сообщений
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Обработчик для вывода в консоль
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Обработчик для вывода в файл
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Получить логгер по имени (создаёт с настройками по умолчанию)
    """
    return setup_logger(name)