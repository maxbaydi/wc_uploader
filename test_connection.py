"""
Утилита для тестирования подключения к WooCommerce API
"""

import sys
import os

# Добавляем текущую директорию в путь для импорта
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import WOOCOMMERCE_CONFIG

def test_connection():
    """Тестирование подключения к WooCommerce"""
    print("=" * 60)
    print("Тест подключения к WooCommerce API")
    print("=" * 60)
    print()
    
    try:
        from woocommerce import API
        
        # Создание API клиента
        wcapi = API(
            url=WOOCOMMERCE_CONFIG['url'],
            consumer_key=WOOCOMMERCE_CONFIG['consumer_key'],
            consumer_secret=WOOCOMMERCE_CONFIG['consumer_secret'],
            wp_api=WOOCOMMERCE_CONFIG['wp_api'],
            version=WOOCOMMERCE_CONFIG['version'],
            timeout=WOOCOMMERCE_CONFIG['timeout']
        )
        
        print(f"URL: {WOOCOMMERCE_CONFIG['url']}")
        print(f"Consumer Key: {WOOCOMMERCE_CONFIG['consumer_key'][:20]}...")
        print(f"Consumer Secret: {WOOCOMMERCE_CONFIG['consumer_secret'][:20]}...")
        print()
        
        # Тест 1: Получение информации о системе
        print("🔍 Тест 1: Получение информации о системе...")
        response = wcapi.get("system_status")
        
        if response.status_code == 200:
            system_info = response.json()
            print(f"✓ Подключение успешно!")
            print(f"  WooCommerce версия: {system_info.get('settings', {}).get('version', 'Unknown')}")
            print(f"  WordPress версия: {system_info.get('settings', {}).get('wp_version', 'Unknown')}")
        else:
            print(f"❌ Ошибка подключения: {response.status_code}")
            print(f"   Ответ: {response.text}")
            return False
            
        # Тест 2: Получение списка категорий
        print()
        print("🔍 Тест 2: Получение категорий товаров...")
        response = wcapi.get("products/categories", params={'per_page': 5})
        
        if response.status_code == 200:
            categories = response.json()
            print(f"✓ Получено категорий: {len(categories)}")
            for cat in categories[:3]:  # Показываем первые 3
                print(f"  - {cat['name']} (ID: {cat['id']})")
        else:
            print(f"❌ Ошибка получения категорий: {response.status_code}")
            
        # Тест 3: Получение товаров
        print()
        print("🔍 Тест 3: Получение товаров...")
        response = wcapi.get("products", params={'per_page': 3})
        
        if response.status_code == 200:
            products = response.json()
            print(f"✓ Получено товаров: {len(products)}")
            for product in products:
                print(f"  - {product['name']} (ID: {product['id']}, SKU: {product['sku']})")
        else:
            print(f"❌ Ошибка получения товаров: {response.status_code}")
            
        print()
        print("=" * 60)
        print("✅ Тестирование завершено успешно!")
        print("WooCommerce API готов к использованию.")
        print("=" * 60)
        
        return True
        
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        print("Установите зависимости: pip install -r requirements.txt")
        return False
        
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        print()
        print("Возможные причины:")
        print("1. Неправильные API ключи")
        print("2. WooCommerce API не включен")
        print("3. Проблемы с сетью")
        print("4. Неправильный URL сайта")
        return False

def main():
    """Главная функция"""
    if test_connection():
        input("\nНажмите Enter для выхода...")
    else:
        input("\nИсправьте ошибки и попробуйте снова. Нажмите Enter для выхода...")

if __name__ == "__main__":
    main()
