"""
Асинхронный клиент для парсинга AV.BY с ротацией прокси
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
    """Парсер для cars.av.by с ротацией прокси"""
    
    def __init__(self, proxies: List[str] = None):
        """
        Args:
            proxies: Список прокси-серверов (например, ['http://user:pass@ip1:port', 'http://user:pass@ip2:port'])
        """
        self.timeout = 30.0
        
        # Загружаем прокси из переменной окружения или из аргументов
        if proxies:
            self.proxies = proxies
        else:
            proxy_list_str = os.getenv("PROXY_LIST", "")
            if proxy_list_str:
                self.proxies = [p.strip() for p in proxy_list_str.split(",") if p.strip()]
            else:
                self.proxies = []
        
        # Текущий прокси (для повторных попыток)
        self._current_proxy = None
        self._failed_proxies = set()  # Прокси, на которых была ошибка
        
        logger.info(f"Загружено прокси: {len(self.proxies)}")
        if self.proxies:
            for i, p in enumerate(self.proxies):
                # Скрываем пароль для логов
                masked = re.sub(r':[^@]+@', ':***@', p)
                logger.info(f"  Прокси {i+1}: {masked}")
    
    def _get_random_proxy(self) -> Optional[str]:
        """Возвращает случайный прокси из списка, исключая неудачные"""
        available = [p for p in self.proxies if p not in self._failed_proxies]
        if not available:
            logger.warning("Все прокси были отмечены как неудачные. Сбрасываю список.")
            self._failed_proxies.clear()
            available = self.proxies
        
        if not available:
            return None
        
        proxy = random.choice(available)
        self._current_proxy = proxy
        return proxy
    
    def _mark_proxy_failed(self, proxy: str):
        """Отмечает прокси как неудачный"""
        if proxy and proxy not in self._failed_proxies:
            self._failed_proxies.add(proxy)
            logger.warning(f"Прокси помечен как неудачный: {proxy[:20]}...")
    
    def _get_headers(self) -> Dict[str, str]:
        """Генерирует случайные заголовки для каждого запроса"""
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
        """
        Получает список объявлений по URL фильтра с ротацией прокси
        """
        # Пробуем максимум 3 разных прокси
        max_attempts = min(3, len(self.proxies)) if self.proxies else 1
        
        for attempt in range(max_attempts):
            proxy = self._get_random_proxy() if self.proxies else None
            
            # Логируем попытку
            if proxy:
                masked = re.sub(r':[^@]+@', ':***@', proxy)
                logger.info(f"Попытка {attempt+1}/{max_attempts} с прокси: {masked[:30]}...")
            else:
                logger.info(f"Попытка {attempt+1}/{max_attempts} без прокси")
            
            result = await self._fetch_single(url, limit, proxy)
            
            # Если успешно — возвращаем результат
            if result is not None:
                return result
            
            # Если прокси не сработал — помечаем его
            if proxy:
                self._mark_proxy_failed(proxy)
            
            # Ждём перед следующей попыткой
            await asyncio.sleep(random.uniform(1.0, 3.0))
        
        logger.error(f"Все попытки (макс {max_attempts}) не удались для {url}")
        return []
    
    async def _fetch_single(self, url: str, limit: int, proxy: Optional[str]) -> Optional[List[Dict[str, Any]]]:
        """
        Одиночный запрос с одним прокси
        Возвращает None при ошибке, иначе список объявлений
        """
        headers = self._get_headers()
        
        # Настройка клиента с правильным параметром "proxy" (единственное число)
        client_kwargs = {
            'follow_redirects': True,
            'headers': headers,
            'timeout': self.timeout,
            'http2': False,
        }
        
        # Добавляем прокси, если он есть
        if proxy:
            client_kwargs['proxy'] = proxy  # <-- ИСПРАВЛЕНО: proxy (единственное число)
        
        async with httpx.AsyncClient(**client_kwargs) as client:
            try:
                # Случайная задержка
                delay = random.uniform(1.0, 4.0)
                await asyncio.sleep(delay)
                
                logger.debug(f"Запрос к AV.BY: {url[:80]}...")
                response = await client.get(url)
                
                if response.status_code == 468:
                    logger.warning("Получен код 468 (блокировка)")
                    return None
                
                if response.status_code != 200:
                    logger.error(f"HTTP ошибка: {response.status_code}")
                    return None
                
                soup = BeautifulSoup(response.text, 'lxml')
                
                # Пробуем найти карточки
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
            # ----- ССЫЛКА И ID -----
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
                logger.warning(f"Подозрительно короткий ID: {ad_id} из {href}")
                return None
            
            if href.startswith('/'):
                full_url = f"https://cars.av.by{href}"
            else:
                full_url = href
            
            # ----- НАЗВАНИЕ -----
            title_tag = link_tag.select_one('.link-text')
            if not title_tag:
                title_tag = item.select_one('.listing-item__title .link-text')
            if not title_tag:
                title_tag = item.select_one('.listing-item__title')
            title = title_tag.text.strip() if title_tag else "Без названия"
            
            # ----- ЦЕНА -----
            price = None
            price_tag = item.select_one('.listing-item__price-primary')
            if not price_tag:
                price_tag = item.select_one('.price')
            if price_tag:
                price_text = price_tag.text.strip()
                digits = re.sub(r'[^\d]', '', price_text)
                if digits:
                    price = int(digits)
            
            # ----- ПРОБЕГ -----
            mileage = None
            mileage_span = item.select_one('.listing-item__params span')
            if mileage_span:
                mileage_text = mileage_span.text.strip()
                digits = re.sub(r'[^\d]', '', mileage_text)
                if digits:
                    mileage = int(digits)
            
            # ----- ГОД -----
            year = None
            year_match = re.search(r'(\d{4})', item.text if hasattr(item, 'text') else '')
            if year_match:
                year = int(year_match.group(1))
            
            # ----- ГОРОД -----
            city = None
            city_tag = item.select_one('.listing-item__location')
            if city_tag:
                city = city_tag.text.strip()
            
            # ----- ДАТА -----
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


async def test_parser():
    """Тестовая функция"""
    # Для теста можно указать прокси явно
    # parser = AVByParser(proxies=["http://user:pass@ip:port"])
    parser = AVByParser()
    
    test_url = "https://cars.av.by/filter?brands[0][brand]=8&brands[0][model]=5865&sort=4"
    
    print(f"\n🔍 Тестируем парсер AV.BY на: {test_url}\n")
    print("⏳ Пожалуйста, подождите...\n")
    
    ads = await parser.fetch_ads(test_url, limit=5)
    
    if ads:
        print(f"✅ Найдено {len(ads)} объявлений:\n")
        for ad in ads:
            print(f"ID: {ad['id']}")
            print(f"Название: {ad['title']}")
            print(f"Цена: {ad['price']} BYN")
            print(f"Год: {ad['year']}")
            print(f"Пробег: {ad['mileage']} км")
            print(f"Город: {ad['city']}")
            print(f"Дата: {ad['date']}")
            print(f"URL: {ad['url']}")
            print("-" * 50)
    else:
        print("❌ Объявления не найдены.")


if __name__ == "__main__":
    asyncio.run(test_parser())
