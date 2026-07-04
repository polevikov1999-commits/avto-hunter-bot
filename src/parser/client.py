"""
Асинхронный клиент для парсинга AV.BY
"""
import asyncio
import re
import sys
import os
from typing import List, Optional, Dict, Any

import httpx
from bs4 import BeautifulSoup

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import get_logger

logger = get_logger('parser')


class AVByParser:
    """Парсер для cars.av.by"""

    def __init__(self, user_agent: str = None):
        self.user_agent = user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        self.timeout = 30.0

    async def fetch_ads(self, url: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Получает список объявлений по URL фильтра
        """
        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }

        async with httpx.AsyncClient(follow_redirects=True, headers=headers, timeout=self.timeout) as client:
            try:
                await asyncio.sleep(0.5)
                logger.info(f"Запрос к AV.BY: {url}")
                response = await client.get(url)

                if response.status_code != 200:
                    logger.error(f"HTTP ошибка: {response.status_code}")
                    return []

                soup = BeautifulSoup(response.text, 'lxml')

                # Пробуем найти карточки разными способами
                items = soup.select('div.listing-item__wrap')
                if not items:
                    items = soup.select('div.listing-item')

                logger.info(f"Найдено карточек: {len(items)}")

                ads = []
                for item in items[:limit]:
                    ad = self._parse_item(item)
                    if ad and ad.get('id'):
                        ads.append(ad)
                    else:
                        logger.debug(f"Не удалось распарсить карточку")

                logger.info(f"Успешно распарсено: {len(ads)}")

                # Если ничего не распарсили, сохраняем полный HTML
                if not ads:
                    with open("debug_no_ads.html", "w", encoding="utf-8") as f:
                        f.write(response.text)
                    logger.warning("Не удалось распарсить объявления. HTML сохранён в debug_no_ads.html")

                return ads

            except Exception as e:
                logger.error(f"Ошибка при парсинге: {e}")
                return []

    def _parse_item(self, item) -> Optional[Dict[str, Any]]:
        """Парсит одну карточку объявления"""
        try:
            # ----- ССЫЛКА И ID (БЕРЁМ ПОСЛЕДНЮЮ ГРУППУ ЦИФР) -----
            link_tag = item.select_one('a.listing-item__link')
            if not link_tag:
                link_tag = item.select_one('a')
            if not link_tag:
                return None

            href = link_tag.get('href', '')
            if not href:
                return None

            # Находим ВСЕ группы цифр в ссылке и берём ПОСЛЕДНЮЮ
            numbers = re.findall(r'\d+', href)
            if not numbers:
                logger.debug(f"Нет цифр в ссылке: {href}")
                return None

            # ID объявления — это ПОСЛЕДНЯЯ группа цифр
            ad_id = numbers[-1]

            # Проверяем, что ID похож на реальный (минимум 5 цифр)
            if len(ad_id) < 5:
                logger.warning(f"Подозрительно короткий ID: {ad_id} из {href}")
                return None

            # Полный URL
            if href.startswith('/'):
                full_url = f"https://cars.av.by{href}"
            else:
                full_url = href

            # ----- НАЗВАНИЕ -----
            title_tag = item.select_one('.listing-item__title .link-text')
            if not title_tag:
                title_tag = item.select_one('.listing-item__title')
            title = title_tag.text.strip() if title_tag else "Без названия"

            # ----- ЦЕНА -----
            price = None
            price_tag = item.select_one('.listing-item__price-primary')
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
            year_match = re.search(r'(\d{4})', item.text)
            if year_match:
                year = int(year_match.group(1))

            # ----- ГОРОД -----
            city = None
            city_tag = item.select_one('.listing-item__location')
            if city_tag:
                city = city_tag.text.strip()

            # ----- ДАТА ПУБЛИКАЦИИ -----
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
    parser = AVByParser()

    # Тестируем Peugeot 607
    test_url = "https://cars.av.by/filter?brands[0][brand]=989&brands[0][model]=1006&sort=4"

    print(f"\n🔍 Тестируем парсер Peugeot 607 на: {test_url}\n")
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
        print("❌ Объявления не найдены")
        print("\nПроверьте файл debug_no_ads.html")


if __name__ == "__main__":
    asyncio.run(test_parser())