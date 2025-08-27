#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Простой скрипт запуска FIFU Uploader GUI
"""

import sys
import os

def main():
    """Запуск GUI приложения"""
    try:
        # Добавляем текущую директорию в путь Python
        current_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, current_dir)
        
        # Импортируем и запускаем GUI
        from gui_fifu import UploaderGUI
        
        print("🚀 Запуск WooCommerce Uploader...")
        app = UploaderGUI()
        app.run()
        
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        print("Убедитесь, что все зависимости установлены:")
        print("pip install -r requirements.txt")
        return 1
        
    except Exception as e:
        print(f"❌ Ошибка запуска: {e}")
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main()) 