#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль для скачивания и обработки изображений с интеграцией в GUI.
Поддерживает скачивание изображений из CSV и их преобразование в унифицированный формат.
"""

import os
import csv
import re
import requests
from urllib.parse import urlparse
import pandas as pd
from pathlib import Path
import threading
import time
from typing import Optional, Callable, Dict, Any
import logging
from PIL import Image, ImageFilter, ImageEnhance
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed


class ImageQualityAnalyzer:
    """Класс для анализа качества изображений."""
    
    @staticmethod
    def analyze_sharpness(image: Image.Image) -> float:
        """
        Анализирует четкость изображения с использованием градиентного фильтра.
        
        Args:
            image: PIL изображение для анализа
            
        Returns:
            float: Показатель четкости (больше = четче)
        """
        gray_image = image.convert('L')
        gradient = gray_image.filter(ImageFilter.FIND_EDGES)
        np_array = np.array(gradient)
        sharpness = np_array.var()
        return sharpness
    
    @staticmethod
    def analyze_resolution_quality(width: int, height: int) -> str:
        """
        Анализирует качество разрешения изображения.
        
        Args:
            width: Ширина изображения
            height: Высота изображения
            
        Returns:
            str: Категория качества ('very_small', 'small', 'medium', 'large')
        """
        total_pixels = width * height
        
        if total_pixels < 250_000:
            return 'very_small'
        elif total_pixels < 800_000:
            return 'small'
        elif total_pixels < 1_500_000:
            return 'medium'
        else:
            return 'large'
    
    @staticmethod
    def get_scale_factor(image: Image.Image) -> float:
        """
        Определяет коэффициент масштабирования для изображения.
        
        Args:
            image: PIL изображение
            
        Returns:
            float: Коэффициент масштабирования
        """
        width, height = image.size
        resolution_quality = ImageQualityAnalyzer.analyze_resolution_quality(width, height)
        sharpness = ImageQualityAnalyzer.analyze_sharpness(image)
        
        # Пороговые значения для четкости
        high_sharpness = 2500
        medium_sharpness = 2000
        low_sharpness = 1500
        
        if resolution_quality == 'very_small':
            if sharpness >= high_sharpness:
                return 1.5
            elif sharpness >= medium_sharpness:
                return 1.2
            else:
                return 1.0
                
        elif resolution_quality == 'small':
            if sharpness >= high_sharpness:
                return 2.0
            elif sharpness >= medium_sharpness:
                return 1.5
            elif sharpness >= low_sharpness:
                return 1.2
            else:
                return 1.0
                
        elif resolution_quality == 'medium':
            if sharpness >= high_sharpness:
                return 1.5
            elif sharpness >= medium_sharpness:
                return 1.2
            else:
                return 1.0
        else:  # large
            return 1.0


class ImageDownloader:
    """Класс для скачивания и обработки изображений."""
    
    def __init__(self, output_dir: str = "img"):
        """
        Инициализация загрузчика изображений.
        
        Args:
            output_dir: Папка для сохранения изображений
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Настройки шаблона для преобразования
        self.template_width = 2560
        self.template_height = 1440
        self.background_color = (255, 255, 255)  # Белый фон
        
        # Поддерживаемые форматы
        self.supported_formats = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff'}
        
        # Анализатор качества
        self.quality_analyzer = ImageQualityAnalyzer()
        
        # Callbacks
        self.progress_callback: Optional[Callable] = None
        self.log_callback: Optional[Callable] = None
        
        # Флаг остановки
        self._stop_flag = False
        
        # Статистика
        self.stats = {
            'total': 0,
            'downloaded': 0,
            'converted': 0,
            'errors': 0,
            'skipped': 0
        }
    
    def set_progress_callback(self, callback: Callable[[int, int, str], None]) -> None:
        """Устанавливает callback для обновления прогресса."""
        self.progress_callback = callback
        
    def set_log_callback(self, callback: Callable[[str], None]) -> None:
        """Устанавливает callback для логирования."""
        self.log_callback = callback
    
    def log_message(self, message: str) -> None:
        """Отправляет сообщение в лог."""
        if self.log_callback:
            self.log_callback(message)
    
    def update_progress(self, current: int, total: int, message: str = "") -> None:
        """Обновляет прогресс."""
        if self.progress_callback:
            self.progress_callback(current, total, message)
    
    def stop_download(self) -> None:
        """Останавливает процесс скачивания."""
        self._stop_flag = True
        
    def normalize_filename(self, filename: str) -> str:
        """
        Нормализует имя файла, оставляя только буквы и цифры.

        Args:
            filename: Исходное имя файла (SKU/артикул)

        Returns:
            str: Нормализованное имя файла (только буквы и цифры)
        """
        if not filename:
            return "unnamed"

        # Убираем пробелы в начале и конце
        filename = filename.strip()

        # Оставляем только буквы и цифры, удаляем все остальные символы
        normalized = re.sub(r'[^A-Za-z0-9А-Яа-яЁё]', '', filename)

        # Если после очистки ничего не осталось, используем fallback
        if not normalized:
            normalized = "unnamed"

        # Приводим к нижнему регистру
        return normalized.lower()
    
    def get_extension_from_url(self, url: str) -> str:
        """Получает расширение файла из URL."""
        path = urlparse(url).path
        ext = os.path.splitext(path)[1]
        return ext if ext else '.jpg'
    
    def get_extension_from_response(self, response: requests.Response) -> str:
        """Получает расширение файла из HTTP ответа."""
        content_type = response.headers.get('Content-Type', '')
        if 'image/' in content_type:
            return '.' + content_type.split('/')[-1].split(';')[0]
        return '.jpg'
    
    def convert_image(self, image_path: Path, convert_enabled: bool = False) -> bool:
        """
        Преобразует изображение в унифицированный формат.
        
        Args:
            image_path: Путь к изображению
            convert_enabled: Включено ли преобразование
            
        Returns:
            bool: True, если преобразование прошло успешно
        """
        if not convert_enabled:
            return True
            
        try:
            with Image.open(image_path) as image:
                # Конвертируем в RGB, если необходимо
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                # Анализируем качество
                orig_width, orig_height = image.size
                resolution_quality = self.quality_analyzer.analyze_resolution_quality(orig_width, orig_height)
                sharpness = self.quality_analyzer.analyze_sharpness(image)
                scale_factor = self.quality_analyzer.get_scale_factor(image)
                
                # Улучшаем качество при необходимости
                if sharpness < 1000:
                    enhancer = ImageEnhance.Sharpness(image)
                    image = enhancer.enhance(1.2)
                
                # Вычисляем размеры и позицию
                (new_width, new_height), (x_pos, y_pos) = self._calculate_scale_and_position(image, scale_factor)
                
                # Создаем шаблон с белым фоном
                template = Image.new('RGB', (self.template_width, self.template_height), 
                                   self.background_color)
                
                # Применяем предварительное масштабирование
                pre_scaled_width = int(orig_width * scale_factor)
                pre_scaled_height = int(orig_height * scale_factor)
                
                if scale_factor != 1.0:
                    image = image.resize((pre_scaled_width, pre_scaled_height), Image.LANCZOS)
                
                # Масштабируем до финальных размеров
                if (new_width, new_height) != image.size:
                    resized_image = image.resize((new_width, new_height), Image.LANCZOS)
                else:
                    resized_image = image
                
                # Вставляем изображение в шаблон
                template.paste(resized_image, (x_pos, y_pos))
                
                # Сохраняем преобразованное изображение
                template.save(image_path, 'JPEG', quality=100, optimize=True)
                
                self.log_message(f"🔄 Преобразовано: {image_path.name} "
                               f"(размер: {resolution_quality}, масштаб: {scale_factor}x, "
                               f"{orig_width}x{orig_height} -> {new_width}x{new_height})")
                return True
                
        except Exception as e:
            self.log_message(f"❌ Ошибка преобразования {image_path.name}: {str(e)}")
            return False
    
    def _calculate_scale_and_position(self, image: Image.Image, scale_factor: float):
        """Вычисляет масштаб и позицию для размещения изображения в шаблоне."""
        orig_width, orig_height = image.size
        
        # Применяем предварительное масштабирование
        pre_scaled_width = int(orig_width * scale_factor)
        pre_scaled_height = int(orig_height * scale_factor)
        
        # Вычисляем соотношения сторон
        image_aspect = pre_scaled_width / pre_scaled_height
        template_aspect = self.template_width / self.template_height
        
        # Определяем итоговый масштаб для вписывания в шаблон
        if image_aspect > template_aspect:
            final_scale = self.template_width / pre_scaled_width
        else:
            final_scale = self.template_height / pre_scaled_height
        
        # Вычисляем финальные размеры
        new_width = int(pre_scaled_width * final_scale)
        new_height = int(pre_scaled_height * final_scale)
        
        # Центрируем изображение
        x_position = (self.template_width - new_width) // 2
        y_position = (self.template_height - new_height) // 2
        
        return (new_width, new_height), (x_position, y_position)
    
    def download_single_image(self, img_url: str, sku: str, convert_enabled: bool = False) -> bool:
        """
        Скачивает одно изображение.
        
        Args:
            img_url: URL изображения
            sku: SKU/артикул для именования файла
            convert_enabled: Включено ли преобразование
            
        Returns:
            bool: True, если скачивание прошло успешно
        """
        if not img_url or not sku:
            return False
            
        filename = self.normalize_filename(sku)
        ext = self.get_extension_from_url(img_url)
        filepath = self.output_dir / f"{filename}{ext}"
        
        # Если файл уже существует - пропускаем
        if filepath.exists():
            self.log_message(f"⏭️ Пропущено {filepath.name} (уже существует)")
            self.stats['skipped'] += 1
            return True
            
        try:
            self.log_message(f"⬇️ Скачиваю {img_url} -> {filepath.name}")
            
            # Скачиваем файл
            response = requests.get(img_url, timeout=30)
            response.raise_for_status()
            
            # Проверяем расширение по ответу
            real_ext = self.get_extension_from_response(response)
            if real_ext != ext:
                filepath = self.output_dir / f"{filename}{real_ext}"
                
            # Сохраняем файл
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            self.stats['downloaded'] += 1
            self.log_message(f"✅ Скачано: {filepath.name}")
            
            # Преобразуем изображение если включено
            if convert_enabled:
                if self.convert_image(filepath, True):
                    self.stats['converted'] += 1
            
            return True
            
        except Exception as e:
            self.stats['errors'] += 1
            self.log_message(f"❌ Ошибка при скачивании {img_url}: {str(e)}")
            return False
    
    def download_images_from_csv(self, csv_file: str, convert_enabled: bool = False, 
                                url_column: str = 'img_url', sku_column: str = 'sku',
                                max_workers: int = 4) -> Dict[str, Any]:
        """
        Скачивает изображения из CSV файла.
        
        Args:
            csv_file: Путь к CSV файлу
            convert_enabled: Включено ли преобразование изображений
            url_column: Название колонки с URL
            sku_column: Название колонки с SKU/артикулом
            max_workers: Количество потоков для скачивания
            
        Returns:
            Dict: Статистика выполнения
        """
        self.log_message("=" * 50)
        self.log_message("🚀 НАЧАЛО СКАЧИВАНИЯ ИЗОБРАЖЕНИЙ")
        self.log_message("=" * 50)
        
        # Сбрасываем статистику
        self.stats = {
            'total': 0,
            'downloaded': 0,
            'converted': 0,
            'errors': 0,
            'skipped': 0
        }
        
        self._stop_flag = False
        
        try:
            # Читаем CSV файл
            self.log_message(f"📋 Читаю CSV файл: {os.path.basename(csv_file)}")
            
            # Пробуем разные кодировки
            try:
                df = pd.read_csv(csv_file, encoding='utf-8')
            except UnicodeDecodeError:
                try:
                    df = pd.read_csv(csv_file, encoding='cp1251')
                except UnicodeDecodeError:
                    df = pd.read_csv(csv_file, encoding='latin-1')
            
            # Проверяем наличие нужных колонок
            if url_column not in df.columns:
                raise ValueError(f"Колонка '{url_column}' не найдена в CSV файле")
            if sku_column not in df.columns:
                raise ValueError(f"Колонка '{sku_column}' не найдена в CSV файле")
            
            # Фильтруем строки с пустыми значениями
            df_filtered = df.dropna(subset=[url_column, sku_column])
            
            # Преобразуем колонки в строковый тип перед применением .str методов
            df_filtered[url_column] = df_filtered[url_column].astype(str)
            df_filtered[sku_column] = df_filtered[sku_column].astype(str)
            
            # Фильтруем пустые строки
            df_filtered = df_filtered[(df_filtered[url_column].str.strip() != '') & 
                                    (df_filtered[sku_column].str.strip() != '') &
                                    (df_filtered[url_column].str.strip() != 'nan') &
                                    (df_filtered[sku_column].str.strip() != 'nan')]
            
            self.stats['total'] = len(df_filtered)
            self.log_message(f"📊 Найдено {self.stats['total']} записей для обработки")
            
            if self.stats['total'] == 0:
                self.log_message("⚠️ Нет записей для обработки")
                return self.stats
            
            self.log_message(f"🔧 Режим преобразования: {'Включен' if convert_enabled else 'Отключен'}")
            self.log_message(f"🗂️ Папка сохранения: {self.output_dir}")
            
            # Скачиваем изображения параллельно
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                
                for index, row in df_filtered.iterrows():
                    if self._stop_flag:
                        break
                        
                    img_url = str(row[url_column]).strip()
                    sku = str(row[sku_column]).strip()
                    
                    future = executor.submit(self.download_single_image, img_url, sku, convert_enabled)
                    futures[future] = (img_url, sku)
                
                # Обрабатываем результаты
                completed = 0
                for future in as_completed(futures):
                    if self._stop_flag:
                        break
                        
                    img_url, sku = futures[future]
                    completed += 1
                    
                    try:
                        success = future.result()
                        self.update_progress(completed, self.stats['total'], 
                                           f"Обработано: {sku}")
                    except Exception as e:
                        self.stats['errors'] += 1
                        self.log_message(f"❌ Неожиданная ошибка для {sku}: {str(e)}")
                    
                    if self._stop_flag:
                        break
            
            # Итоговая статистика
            self.log_message("=" * 50)
            self.log_message("📊 РЕЗУЛЬТАТЫ СКАЧИВАНИЯ")
            self.log_message("=" * 50)
            self.log_message(f"Всего записей: {self.stats['total']}")
            self.log_message(f"Скачано: {self.stats['downloaded']}")
            self.log_message(f"Преобразовано: {self.stats['converted']}")
            self.log_message(f"Пропущено: {self.stats['skipped']}")
            self.log_message(f"Ошибки: {self.stats['errors']}")
            
            if self._stop_flag:
                self.log_message("⚠️ Процесс остановлен пользователем")
            
            return self.stats
            
        except Exception as e:
            self.log_message(f"💥 КРИТИЧЕСКАЯ ОШИБКА: {str(e)}")
            self.stats['errors'] += 1
            return self.stats
