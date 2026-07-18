"""
Настройка логирования в файл и консоль
"""
import logging
import os
from datetime import datetime

# Устанавливаем временную зону
os.environ['TZ'] = 'Europe/Minsk'
try:
    import time
    time.tzset()
except AttributeError:
    pass

# Создаём папку для логов
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

log_filename = os.path.join(LOG_DIR, f"bot_{datetime.now().strftime('%Y%m%d')}.log")


def setup_logger(name: str = None, level: int = logging.INFO) -> logging.Logger:
    """
    Настройка логгера с выводом в консоль и файл
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    if logger.hasHandlers():
        logger.handlers.clear()
    
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """Получить логгер по имени"""
    return setup_logger(name)