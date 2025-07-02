#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WooCommerce Product Uploader - Main Entry Point
Главная точка входа для загрузчика товаров WooCommerce
"""

import sys
import os

def check_dependencies():
    """Проверка зависимостей"""
    print("Проверка зависимостей...")
    
    required_packages = [
        'woocommerce',
        'requests', 
        'PIL',
        'pandas'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            if package == 'PIL':
                import PIL
            else:
                __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ Отсутствуют пакеты: {', '.join(missing_packages)}")
        print("Установите их командой: pip install -r requirements.txt")
        return False
    
    print("✓ Все зависимости установлены")
    return True

def main():
    """Главная функция"""
    print("=" * 60)
    print("WooCommerce Product Uploader")
    print("=" * 60)
    print()
    
    # Проверка зависимостей
    if not check_dependencies():
        input("Нажмите Enter для выхода...")
        return
    
    # Выбор режима запуска
    print("Выберите режим запуска:")
    print("1. Графический интерфейс (GUI)")
    print("2. Консольный режим")
    print()
    
    while True:
        choice = input("Ваш выбор (1/2): ").strip()
        if choice in ['1', '2']:
            break
        print("❌ Введите 1 или 2")
    
    if choice == '1':
        print("\nЗапуск графического интерфейса...")
        try:
            from gui_fixed import SimpleUploaderGUI
            app = SimpleUploaderGUI()
            app.run()
            
        except Exception as e:
            print(f"❌ Ошибка запуска GUI: {str(e)}")
            print("Попробуйте консольный режим")
            input("Нажмите Enter для выхода...")
    
    elif choice == '2':
        print("\nЗапуск консольного режима...")
        try:
            from console_uploader import ConsoleWooCommerceUploader
            uploader = ConsoleWooCommerceUploader()
            uploader.run()
            
        except Exception as e:
            print(f"❌ Критическая ошибка: {str(e)}")
            input("Нажмите Enter для выхода...")

if __name__ == "__main__":
    main()
