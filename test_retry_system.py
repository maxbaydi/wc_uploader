#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тест системы retry для AI генерации описаний
"""

import os
import time
from ai_description_generator import AIDescriptionGenerator

def test_retry_system():
    """Тестирует систему повторных попыток"""
    print("🧪 Тестирование системы retry для AI генерации...")
    
    # Настройки из конфигурации
    api_key = "sk-or-vv-d86ba11bb7d6309f6722e6054e8cac1517790b3604167fb960c47783943b3a0a"
    api_url = "https://api.vsegpt.ru/v1/chat/completions"
    model = "openai/gpt-5-nano"
    
    # Создаем генератор с настройками retry
    generator = AIDescriptionGenerator(
        api_key=api_key,
        api_url=api_url,
        model=model,
        temperature=0.7,
        max_retries=3,      # 3 повторные попытки
        retry_delay=1.0,    # 1 секунда начальная задержка
        timeout=30          # 30 секунд таймаут для теста
    )
    
    def log_callback(message):
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        print(f"[{timestamp}] {message}")
    
    generator.set_log_callback(log_callback)
    
    # Тестовые данные - короткие названия для быстрого тестирования
    test_names = [
        "Тестовый товар 1",
        "Тестовый товар 2", 
        "Тестовый товар 3"
    ]
    
    print(f"📦 Тестируем {len(test_names)} товаров...")
    print(f"⚙️ Настройки: {generator.max_retries} попыток, {generator.retry_delay}с задержка, {generator.timeout}с таймаут")
    print("=" * 60)
    
    # Создаем промт
    prompt = generator.create_batch_prompt(test_names, "русский", 200)
    
    # Тестируем вызов API
    start_time = time.time()
    result = generator.call_ai_api(prompt, attempt_number=1)
    end_time = time.time()
    
    print("=" * 60)
    print(f"⏱️ Время выполнения: {end_time - start_time:.2f} секунд")
    
    if result:
        print("✅ Тест успешен!")
        print(f"📊 Статистика retry:")
        print(f"   - Попыток retry: {generator.stats['retries']}")
        print(f"   - Провалено после retry: {generator.stats['failed_after_retries']}")
        
        # Проверяем структуру ответа
        if 'descriptions' in result:
            descriptions = result['descriptions']
            print(f"🎯 Получено описаний: {len(descriptions)}")
            
            for i, desc in enumerate(descriptions, 1):
                if 'id' in desc and 'name' in desc and 'description' in desc:
                    print(f"   {i}. ID: {desc['id']}, Название: {desc['name'][:30]}...")
                else:
                    print(f"   {i}. ❌ Неполная структура: {desc}")
        else:
            print("❌ Ответ не содержит 'descriptions'")
            
    else:
        print("❌ Тест провален - не удалось получить ответ от API")
        print(f"📊 Статистика retry:")
        print(f"   - Попыток retry: {generator.stats['retries']}")
        print(f"   - Провалено после retry: {generator.stats['failed_after_retries']}")
    
    print("🎉 Тест завершен!")
    
    # Демонстрируем работу с невалидным API для тестирования retry
    print("\n" + "=" * 60)
    print("🔄 Тестируем retry с невалидным API...")
    
    bad_generator = AIDescriptionGenerator(
        api_key="invalid_key",
        api_url="https://invalid.api.url/v1/chat/completions",
        model=model,
        temperature=0.7,
        max_retries=2,      # Меньше попыток для быстрого теста
        retry_delay=0.5,    # Быстрее для теста
        timeout=5           # Короткий таймаут для теста
    )
    
    bad_generator.set_log_callback(log_callback)
    
    start_time = time.time()
    bad_result = bad_generator.call_ai_api("Test prompt", attempt_number=999)
    end_time = time.time()
    
    print(f"⏱️ Время провального теста: {end_time - start_time:.2f} секунд")
    print(f"📊 Статистика провального теста:")
    print(f"   - Попыток retry: {bad_generator.stats['retries']}")
    print(f"   - Провалено после retry: {bad_generator.stats['failed_after_retries']}")
    
    if bad_result is None:
        print("✅ Retry система работает корректно - корректно обработала ошибки")
    else:
        print("❌ Неожиданный результат от невалидного API")

if __name__ == "__main__":
    test_retry_system()
