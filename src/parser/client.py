"""
Парсер AV.BY через Playwright (обходит ошибку 468)
"""
import asyncio
import re
import sys
import os
from typing import List, Optional, Dict, Any

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import get_logger

logger = get_logger('parser')


class AVByParser:
    """Парсер для cars.av.by (Playwright)"""
    
    def __init__(self):
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    async def fetch_ads(self, url: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Получает список объявлений по URL фильтра через Playwright
        Обходит ошибку 468 (блокировка ботов)
        """
        async with async_playwright() as p:
            # Запускаем браузер в фоновом режиме
            browser = await p.chromium.launch(headless=True)
            
            # Создаём контекст с параметрами реального браузера
            context = await browser.new_context(
                user_agent=self.user_agent,
                viewport={'width': 1920, 'height': 1080},
                locale='ru-RU'
            )
            
            # Добавляем скрипт для скрытия признаков автоматизации
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['ru-RU', 'ru', 'en']
                });
                window.chrome = { runtime: {} };
            """)
            
            page = await context.new_page()
            
            try:
                logger.info(f"Запрос к AV.BY (Playwright): {url}")
                
                # Переходим по ссылке, ждём загрузки контента
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                
                # Имитация поведения человека: небольшой скролл и пауза
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
                await asyncio.sleep(0.5)
                
                # Ждём появления карточек объявлений
                try:
                    await page.wait_for_selector('div.listing-item__wrap', timeout=15000)
                except:
                    try:
                        await page.wait_for_selector('div.listing-item', timeout=10000)
                    except:
                        logger.warning("Карточки объявлений не найдены на странице")
                
                # Получаем HTML страницы для парсинга
                html = await page.content()
                soup = BeautifulSoup(html, 'lxml')
                
                # Ищем карточки объявлений
                items = soup.select('div.listing-item__wrap')
                if not items:
                    items = soup.select('div.listing-item')
                
                logger.info(f"Найдено карточек: {len(items)}")
                
                # Парсим каждую карточку
                ads = []
                for item in items[:limit]:
                    ad = self._parse_item(item)
                    if ad and ad.get('id'):
                        ads.append(ad)
                    else:
                        logger.debug(f"Не удалось распарсить карточку")
                
                logger.info(f"Успешно распарсено: {len(ads)}")
                
                # Если объявления не найдены, сохраняем HTML для отладки
                if not ads:
                    with open("debug_no_ads.html", "w", encoding="utf-8") as f:
                        f.write(html)
                    logger.warning("Не удалось распарсить объявления. HTML сохранён в debug_no_ads.html")
                
                await browser.close()
                return ads
                
            except Exception as e:
                logger.error(f"Ошибка при парсинге: {e}")
                # Сохраняем скриншот для отладки
                try:
                    await page.screenshot(path="playwright_error.png")
                    logger.info("Скриншот ошибки сохранён в playwright_error.png")
                except:
                    pass
                await browser.close()
                return []
    
    def _parse_item(self, item) -> Optional[Dict[str, Any]]:
        """Парсит одну карточку объявления"""
        try:
            # ----- ССЫЛКА И ID (берём последнюю группу цифр) -----
            link_tag = item.select_one('a.listing-item__link')
            if not link_tag:
                link_tag = item.select_one('a')
            if not link_tag:
                return None
            
            href = link_tag.get('href', '')
            if not href:
                return None
            
            # Находим все группы цифр в ссылке и берём последнюю
            numbers = re.findall(r'\d+', href)
            if not numbers:
                logger.debug(f"Нет цифр в ссылке: {href}")
                return None
            
            ad_id = numbers[-1]
            
            # Проверяем, что ID похож на реальный (минимум 5 цифр)
            if len(ad_id) < 5:
                logger.warning(f"Подозрительно короткий ID: {ad_id} из {href}")
                return None
            
            # Полный URL объявления
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


# ==================== ТЕСТОВАЯ ФУНКЦИЯ ====================
async def test_parser():
    """Тестовая функция для проверки парсера"""
    parser = AVByParser()
    
    # Тестовая ссылка (BMW 5 серия, сначала новые)
    test_url = "https://cars.av.by/filter?brands[0][brand]=8&brands[0][model]=5865&sort=4"
    
    print(f"\n🔍 Тестируем парсер AV.BY (Playwright) на: {test_url}\n")
    print("⏳ Пожалуйста, подождите... (парсинг через браузер может занять 5-10 секунд)\n")
    
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
        print("Возможные причины:")
        print("  - AV.BY изменил структуру страницы")
        print("  - Ошибка при загрузке страницы (проверьте playwright_error.png)")
        print("  - Ссылка неактивна")


if __name__ == "__main__":
    asyncio.run(test_parser())
