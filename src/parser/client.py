"""
Асинхронный клиент для парсинга AV.BY с поддержкой прокси
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
    """Парсер для cars.av.by с поддержкой прокси"""
    
    def __init__(self, proxy: str = None):
        """
        Args:
            proxy: URL прокси-сервера (например, http://user:pass@ip:port)
        """
        self.timeout = 30.0
        self.proxy = proxy or os.getenv("PROXY_URL")  # читаем из переменных окружения
    
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
        Получает список объявлений по URL фильтра через прокси
        """
        headers = self._get_headers()
        
        # Настройка прокси
        proxy_config = None
        if self.proxy:
            proxy_config = self.proxy
            logger.info(f"Использую прокси: {self.proxy[:20]}...")
        
        async with httpx.AsyncClient(
            follow_redirects=True,
            headers=headers,
            timeout=self.timeout,
            http2=False,
            proxies=proxy_config
        ) as client:
            try:
                # Случайная задержка перед запросом (1-4 секунды)
                delay = random.uniform(1.0, 4.0)
                logger.debug(f"Задержка перед запросом: {delay:.1f} сек")
                await asyncio.sleep(delay)
                
                logger.info(f"Запрос к AV.BY: {url[:80]}...")
                response = await client.get(url)
                
                # Если получили блокировку, пробуем ещё раз с другими заголовками
                if response.status_code == 468:
                    logger.warning(f"Получен код 468 (блокировка). Пробую с другими заголовками...")
                    await asyncio.sleep(random.uniform(3.0, 5.0))
                    headers = self._get_headers()
                    response = await client.get(url)
                
                if response.status_code != 200:
                    logger.error(f"HTTP ошибка: {response.status_code}")
                    if response.status_code == 468:
                        logger.error("AV.BY заблокировал запрос. Проверьте прокси или попробуйте другой.")
                    return []
                
                soup = BeautifulSoup(response.text, 'lxml')
                
                # Пробуем найти карточки разными способами
                items = soup.select('div.listing-item__wrap')
                if not items:
                    items = soup.select('div.listing-item')
                if not items:
                    items = soup.select('a[href*="/bmw/"], a[href*="/audi/"], a[href*="/mercedes/"]')
                
                logger.info(f"Найдено элементов для парсинга: {len(items)}")
                
                ads = []
                for item in items[:limit]:
                    ad = self._parse_item(item)
                    if ad and ad.get('id'):
                        ads.append(ad)
                
                logger.info(f"Успешно распарсено: {len(ads)}")
                
                if not ads and response.status_code == 200:
                    with open("debug_no_ads.html", "w", encoding="utf-8") as f:
                        f.write(response.text)
                    logger.warning("Не удалось распарсить объявления. HTML сохранён в debug_no_ads.html")
                
                return ads
                
            except httpx.ProxyError as e:
                logger.error(f"Ошибка прокси: {e}")
                return []
            except httpx.TimeoutException:
                logger.error(f"Таймаут при запросе к {url}")
                return []
            except Exception as e:
                logger.error(f"Ошибка при парсинге: {e}")
                return []
    
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
    """Тестовая функция для проверки парсера"""
    # Для теста можно указать прокси явно
    # parser = AVByParser(proxy="http://user:pass@ip:port")
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
        print("Проверьте файл debug_no_ads.html")


if __name__ == "__main__":
    asyncio.run(test_parser())
