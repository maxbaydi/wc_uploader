#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Утилиты для работы с именами файлов.
Общие функции нормализации для использования во всех модулях проекта.
"""

import re

def normalize_sku_for_filename(sku: str) -> str:
    """
    Нормализует SKU для безопасного использования в именах файлов.
    Оставляет только буквы и цифры.
    
    Эта функция используется для:
    1. Сохранения изображений при скачивании
    2. Поиска изображений при загрузке товаров
    
    Args:
        sku: Исходный SKU/артикул
        
    Returns:
        str: Нормализованный SKU (только буквы и цифры)
    """
    if not sku:
        return "unnamed"
        
    # Убираем пробелы в начале и конце
    sku = sku.strip()
    
    # Оставляем только буквы и цифры, удаляем все остальные символы
    normalized = re.sub(r'[^A-Za-z0-9А-Яа-яЁё]', '', sku)
    
    # Если после очистки ничего не осталось, используем fallback
    if not normalized:
        normalized = "unnamed"
    
    # Приводим к нижнему регистру
    return normalized.lower()


def get_possible_image_names(sku: str, extensions: list = None) -> list:
    """
    Возвращает список возможных имен файлов для данного SKU.
    
    Args:
        sku: Исходный SKU/артикул
        extensions: Список расширений (по умолчанию стандартные изображения)
        
    Returns:
        list: Список возможных имен файлов
    """
    if extensions is None:
        extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
    
    # Нормализуем SKU
    normalized_sku = normalize_sku_for_filename(sku)
    
    # Создаем список возможных имен
    possible_names = []
    for ext in extensions:
        possible_names.append(f"{normalized_sku}{ext}")
    
    return possible_names


def should_filename_match_sku(filename: str, sku: str) -> bool:
    """
    Проверяет, соответствует ли имя файла данному SKU.
    
    Args:
        filename: Имя файла (без пути)
        sku: Исходный SKU
        
    Returns:
        bool: True, если файл соответствует SKU
    """
    # Нормализуем SKU
    normalized_sku = normalize_sku_for_filename(sku)
    
    # Убираем расширение из имени файла и приводим к нижнему регистру
    filename_without_ext = filename.lower()
    if '.' in filename_without_ext:
        filename_without_ext = '.'.join(filename_without_ext.split('.')[:-1])
    
    # Проверяем точное совпадение или начало
    return (filename_without_ext == normalized_sku or 
            filename_without_ext.startswith(normalized_sku))
