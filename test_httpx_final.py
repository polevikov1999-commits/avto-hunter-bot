import httpx
import asyncio

async def test_working_url():
    # Ваша правильная ссылка
    url = "https://cars.av.by/filter?brands[0][brand]=8&brands[0][model]=5865&sort=4"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    
    async with httpx.AsyncClient(
        follow_redirects=True,
        headers=headers,
        timeout=30.0
    ) as client:
        print(f"Запрос к: {url}")
        response = await client.get(url)
        print(f"Статус код: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Успех! Страница загружена.")
            # Сохраняем HTML для анализа
            with open("avby_success.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            print("HTML сохранён в avby_success.html")
            print(f"Длина HTML: {len(response.text)} символов")
            
            # Проверяем, есть ли слово "BMW" на странице
            if "BMW" in response.text or "5 серия" in response.text:
                print("✅ Найдены упоминания BMW 5 серии")
            else:
                print("⚠️ BMW не найден в HTML. Возможно, страница не загрузилась полностью.")
        else:
            print(f"❌ Ошибка: {response.status_code}")
            with open("avby_error.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            print("HTML ошибки сохранён в avby_error.html")

if __name__ == "__main__":
    asyncio.run(test_working_url())
