#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тест автоматической загрузки настроек
"""

import tkinter as tk
import os
import json

def test_settings_load():
    """Тестирует загрузку настроек"""
    print("🧪 Тестирование автоматической загрузки настроек...")
    
    gui_settings_file = "gui_settings.json" 
    
    if os.path.exists(gui_settings_file):
        with open(gui_settings_file, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        
        print("✅ Файл gui_settings.json найден")
        print(f"📊 Всего настроек: {len(settings)}")
        
        # Проверяем наличие основных настроек
        categories = {
            "SFTP": ['sftp_host', 'sftp_port', 'sftp_username'], 
            "WooCommerce": ['wc_url', 'wc_consumer_key'],
            "AI": ['ai_api_key', 'ai_model', 'ai_language']
        }
        
        for category, keys in categories.items():
            found_keys = [key for key in keys if key in settings]
            if found_keys:
                print(f"✅ {category}: {len(found_keys)}/{len(keys)} настроек")
                for key in found_keys:
                    value = settings[key]
                    # Маскируем конфиденциальные данные
                    if 'key' in key.lower() or 'password' in key.lower() or 'secret' in key.lower():
                        masked_value = "*" * min(len(str(value)), 8) if value else "пусто"
                        print(f"   - {key}: {masked_value}")
                    else:
                        print(f"   - {key}: {value}")
            else:
                print(f"⚠️ {category}: настройки не найдены")
                
    else:
        print("❌ Файл gui_settings.json не найден")
    
    print("🎉 Тест завершен!")

if __name__ == "__main__":
    test_settings_load()
