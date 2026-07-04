"""
Фоновый мониторинг новых объявлений (по позиции в выдаче)
"""
import asyncio
import sqlite3
import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parser.client import AVByParser
from notifier import send_new_ad_notification
from database.db import (
    update_first_ad_id, update_last_checked,
    is_ad_seen, mark_ad_seen, clear_old_seen_ads
)
from utils.logger import get_logger

logger = get_logger('monitor')


class Monitor:
    """Класс для фонового мониторинга (по позиции объявления в выдаче)"""
    
    def __init__(self, check_interval: int = 300, ads_limit: int = 20):
        self.check_interval = check_interval
        self.ads_limit = ads_limit
        self.parser = AVByParser()
        self.running = True
        self.db_path = "av_bot.db"
    
    def _get_all_active_filters(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, user_id, url, last_first_ad_id, name
            FROM filters
            WHERE is_active = 1
        ''')
        rows = cursor.fetchall()
        conn.close()
        
        return [{
            'id': row[0],
            'user_id': row[1],
            'url': row[2],
            'last_first_ad_id': row[3],
            'name': row[4]
        } for row in rows]
    
    async def check_all_filters(self):
        logger.info("🔄 Начинаю проверку всех фильтров...")
        
        filters = self._get_all_active_filters()
        logger.info(f"📋 Найдено активных фильтров: {len(filters)}")
        
        for filter_info in filters:
            try:
                await self._check_filter(
                    filter_info['id'],
                    filter_info['user_id'],
                    filter_info['url'],
                    filter_info['last_first_ad_id']
                )
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Ошибка проверки фильтра {filter_info['id']}: {e}")
        
        logger.info("✅ Проверка всех фильтров завершена")
    
    async def _check_filter(self, filter_id: int, user_id: int, url: str, last_first_ad_id: str):
        logger.info(f"🔍 Проверяю фильтр {filter_id} для пользователя {user_id}")
        
        ads = await self.parser.fetch_ads(url, limit=self.ads_limit)
        
        if not ads:
            logger.warning(f"Не удалось получить объявления для фильтра {filter_id}")
            return
        
        # Всегда обновляем время проверки
        update_last_checked(filter_id)
        
        # Первый запуск (нет сохранённого ID)
        if not last_first_ad_id:
            first_ad_id = ads[0]['id']
            update_first_ad_id(filter_id, first_ad_id)
            logger.info(f"Фильтр {filter_id}: первый запуск, сохранён first_ad_id = {first_ad_id}")
            return
        
        # Ищем сохранённый ID в текущей выдаче
        found_position = None
        for i, ad in enumerate(ads):
            if ad['id'] == last_first_ad_id:
                found_position = i
                break
        
        # Случай 1: сохранённый ID не найден
        if found_position is None:
            logger.info(f"Фильтр {filter_id}: предыдущее первое объявление {last_first_ad_id} не найдено, синхронизируюсь")
            clear_old_seen_ads(filter_id)
            new_first_ad_id = ads[0]['id']
            update_first_ad_id(filter_id, new_first_ad_id)
            logger.info(f"Фильтр {filter_id}: синхронизирован, новый first_ad_id = {new_first_ad_id}")
            return
        
        # Случай 2: сохранённый ID на первой позиции — новых нет
        if found_position == 0:
            logger.info(f"Фильтр {filter_id}: новых объявлений нет (первое объявление {last_first_ad_id} на месте)")
            return
        
        # Случай 3: есть новые объявления!
        new_ads = ads[:found_position]
        
        unseen_new_ads = []
        for ad in new_ads:
            if not is_ad_seen(filter_id, ad['id']):
                unseen_new_ads.append(ad)
        
        if unseen_new_ads:
            logger.info(f"🎉 Фильтр {filter_id}: найдено {len(unseen_new_ads)} новых объявлений")
            
            for ad in reversed(unseen_new_ads):
                await send_new_ad_notification(user_id, ad, url)
                mark_ad_seen(filter_id, ad['id'])
                await asyncio.sleep(1)
            
            new_first_ad_id = ads[0]['id']
            update_first_ad_id(filter_id, new_first_ad_id)
            logger.info(f"Фильтр {filter_id}: обновлён first_ad_id с {last_first_ad_id} на {new_first_ad_id}")
        else:
            new_first_ad_id = ads[0]['id']
            if new_first_ad_id != last_first_ad_id:
                update_first_ad_id(filter_id, new_first_ad_id)
                logger.info(f"Фильтр {filter_id}: синхронизирован first_ad_id (новые уже были отправлены)")
            else:
                logger.info(f"Фильтр {filter_id}: нет непрочитанных новых объявлений")
    
    async def run(self):
        logger.info(f"🟢 Монитор запущен. Интервал проверки: {self.check_interval} сек. Лимит объявлений: {self.ads_limit}")
        
        while self.running:
            try:
                await self.check_all_filters()
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}")
            
            await asyncio.sleep(self.check_interval)
    
    def stop(self):
        self.running = False
        logger.info("🔴 Монитор остановлен")
