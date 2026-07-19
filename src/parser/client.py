"""
Асинхронный клиент для парсинга AV.BY с поддержкой списка прокси
"""
import asyncio
import re
import sys
import os
import random
from typing import List, Optional, Dict, Any

import httpx
from bs4 import BeautifulSoup

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import get_logger

logger = get_logger('parser')


class AVByParser:
    """Парсер для cars.av.by с поддержкой списка прокси"""
    
    def __init__(self, proxy_list: str = None):
        self.timeout = 30.0
        
        # Загружаем список прокси
        proxy_str = proxy_list or os.getenv("PROXY_LIST") or os.getenv("PROXY_URL")
        
        if proxy_str:
            # Разделяем по запятой и очищаем
            self.proxies = [p.strip() for p in proxy_str.split(',') if p.strip()]
            logger.info(f"📋 Загружено прокси: {len(self.proxies)}")
            if self.proxies:
                # Маскируем пароль в логах
                masked = [re.sub(r':[^@]+@', ':***@', p) for p in self.proxies[:3]]
                logger.info(f"   {', '.join(masked)}...")
        else:
            self.proxies = []
        
        # Для отслеживания неудачных прокси
        self._failed_proxies = set()
    
    def _get_random_proxy(self) -> Optional[str]:
        """Возвращает случайный прокси из списка, исключая неудачные"""
        available = [p for p in self.proxies if p not in self._failed_proxies]
        if not available:
            # Сбрасываем список неудачных, если все прокси сгорели
            if self._failed_proxies:
                logger.warning("⚠️ Все прокси отмечены как неудачные. Сбрасываю список.")
                self._failed_proxies.clear()
                available = self.proxies
            else:
                return None
        
        return random.choice(available)
    
    def _mark_proxy_failed(self, proxy: str):
        """Отмечает прокси как неудачный"""
        if proxy and proxy not in self._failed_proxies:
            self._failed_proxies.add(proxy)
            masked = re.sub(r':[^@]+@', ':***@', proxy)
            logger.warning(f"⚠️ Прокси помечен как неудачный: {masked[:40]}...")
    
    def _get_headers(self) -> Dict[str, str]:
        """Генерирует случайные заголовки"""
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/122.0',
        ]
        
        return {
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'sec-ch-ua': '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
        }
    
    async def fetch_ads(self, url: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Получает список объявлений по URL фильтра с ротацией прокси"""
        # Пробуем максимум 3 разных прокси
        max_attempts = min(3, len(self.proxies)) if self.proxies else 1
        
        for attempt in range(max_attempts):
            proxy = self._get_random_proxy() if self.proxies else None
            
            if proxy:
                masked = re.sub(r':[^@]+@', ':***@', proxy)
                logger.debug(f"Попытка {attempt+1}/{max_attempts} с прокси: {masked[:40]}...")
            
            result = await self._fetch_single(url, limit, proxy)
            
            if result is not None:
                return result
            
            # Если прокси не сработал — помечаем его
            if proxy:
                self._mark_proxy_failed(proxy)
            
            await asyncio.sleep(random.uniform(1.0, 3.0))
        
        logger.error(f"Все попытки ({max_attempts}) не удались для {url[:80]}...")
        return []
    
    async def _fetch_single(self, url: str, limit: int, proxy: Optional[str]) -> Optional[List[Dict[str, Any]]]:
        """Одиночный запрос с одним прокси"""
        headers = self._get_headers()
        
        async with httpx.AsyncClient(
            follow_redirects=True,
            headers=headers,
            timeout=self.timeout,
            http2=False,
            proxy=proxy
        ) as client:
            try:
                delay = random.uniform(1.0, 3.0)
                await asyncio.sleep(delay)
                
                logger.info(f"Запрос к AV.BY: {url[:80]}...")
                response = await client.get(url)
                
                if response.status_code == 468:
                    logger.warning("Получен код 468 (блокировка)")
                    return None
                
                if response.status_code != 200:
                    logger.error(f"HTTP ошибка: {response.status_code}")
                    return None
                
                soup = BeautifulSoup(response.text, 'lxml')
                
                items = soup.select('div.listing-item__wrap')
                if not items:
                    items = soup.select('div.listing-item')
                if not items:
                    items = soup.select('a[href*="/bmw/"], a[href*="/audi/"], a[href*="/mercedes/"]')
                
                logger.info(f"Найдено элементов: {len(items)}")
                
                ads = []
                for item in items[:limit]:
                    ad = self._parse_item(item)
                    if ad and ad.get('id'):
                        ads.append(ad)
                
                logger.info(f"Успешно распарсено: {len(ads)}")
                
                if not ads and response.status_code == 200:
                    with open("debug_no_ads.html", "w", encoding="utf-8") as f:
                        f.write(response.text)
                    logger.warning("Не удалось распарсить объявления. HTML сохранён.")
                
                return ads
                
            except httpx.ProxyError as e:
                logger.error(f"Ошибка прокси: {e}")
                return None
            except httpx.TimeoutException:
                logger.error("Таймаут")
                return None
            except Exception as e:
                logger.error(f"Ошибка: {e}")
                return None
    
    def _parse_item(self, item) -> Optional[Dict[str, Any]]:
        """Парсит одну карточку объявления"""
        try:
            if item.name == 'a':
                link_tag = item
            else:
                link_tag = item.select_one('a.listing-item__link')
                if not link_tag:
                    link_tag = item.select_one('a')
            
            if not link_tag:
                return None
            
            href = link_tag.get('href', '')
            if not href:
                return None
            
            numbers = re.findall(r'\d+', href)
            if not numbers:
                return None
            
            ad_id = numbers[-1]
            if len(ad_id) < 5:
                return None
            
            if href.startswith('/'):
                full_url = f"https://cars.av.by{href}"
            else:
                full_url = href
            
            title_tag = link_tag.select_one('.link-text')
            if not title_tag:
                title_tag = item.select_one('.listing-item__title .link-text')
            if not title_tag:
                title_tag = item.select_one('.listing-item__title')
            title = title_tag.text.strip() if title_tag else "Без названия"
            
            price = None
            price_tag = item.select_one('.listing-item__price-primary')
            if not price_tag:
                price_tag = item.select_one('.price')
            if price_tag:
                price_text = price_tag.text.strip()
                digits = re.sub(r'[^\d]', '', price_text)
                if digits:
                    price = int(digits)
            
            mileage = None
            mileage_span = item.select_one('.listing-item__params span')
            if mileage_span:
                mileage_text = mileage_span.text.strip()
                digits = re.sub(r'[^\d]', '', mileage_text)
                if digits:
                    mileage = int(digits)
            
            year = None
            year_match = re.search(r'(\d{4})', item.text if hasattr(item, 'text') else '')
            if year_match:
                year = int(year_match.group(1))
            
            city = None
            city_tag = item.select_one('.listing-item__location')
            if city_tag:
                city = city_tag.text.strip()
            
            date = None
            date_tag = item.select_one('.listing-item__date')
            if date_tag:
                date = date_tag.text.strip()
            
            return {
                'id': ad_id,
                'url': full_url,
                'title': title,
                'price': price,
                'year': year,
                'mileage': mileage,
                'city': city,
                'date': date,
            }
        except Exception as e:
            logger.error(f"Ошибка парсинга карточки: {e}")
            return None
