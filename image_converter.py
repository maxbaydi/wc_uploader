#!/usr/bin/env python3
"""
Модуль для конвертации изображений в унифицированный формат.

Этот модуль предоставляет функциональность для обработки изображений в папке,
размещения их в центре шаблона с альбомным расположением (2560x1440) 
с учетом качества и разрешения исходных изображений.

Автор: GitHub Copilot
Дата: 16 июля 2025
"""

import os
import sys
from pathlib import Path
from typing import Tuple, Optional, List
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageFilter, ImageEnhance
import numpy as np
from datetime import datetime


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
        # Конвертируем в градации серого для анализа
        gray_image = image.convert('L')
        
        # Применяем фильтр для вычисления градиента
        gradient = gray_image.filter(ImageFilter.FIND_EDGES)
        
        # Вычисляем дисперсию как показатель четкости
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
        
        # Более точные пороговые значения для классификации качества
        if total_pixels < 250_000:  # Менее 250K пикселей (например, 500x500)
            return 'very_small'
        elif total_pixels < 800_000:  # Менее 800K пикселей (например, 900x900)
            return 'small'
        elif total_pixels < 1_500_000:  # Менее 1.5M пикселей (например, 1200x1200)
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
            float: Коэффициент масштабирования (1.0, 1.2, 1.5, 2.0)
        """
        width, height = image.size
        total_pixels = width * height
        
        # Анализируем качество разрешения
        resolution_quality = ImageQualityAnalyzer.analyze_resolution_quality(width, height)
        
        # Анализируем четкость
        sharpness = ImageQualityAnalyzer.analyze_sharpness(image)
        
        # Пороговые значения для четкости
        very_low_sharpness = 1000   # Очень низкое качество четкости
        low_sharpness = 1500        # Низкое качество четкости
        medium_sharpness = 2000     # Среднее качество четкости
        high_sharpness = 2500       # Высокое качество четкости
        
        # Улучшенная логика масштабирования
        if resolution_quality == 'very_small':
            # Очень маленькие изображения (как adp0150bnc.jpg: 500x298)
            # Такие изображения лучше не увеличивать сильно
            if sharpness >= high_sharpness:
                return 1.5  # Только если очень четкое
            elif sharpness >= medium_sharpness:
                return 1.2  # Небольшое увеличение
            else:
                return 1.0  # Не увеличиваем совсем
                
        elif resolution_quality == 'small':
            # Маленькие изображения
            if sharpness >= high_sharpness:
                return 2.0  # Можно увеличить в 2 раза
            elif sharpness >= medium_sharpness:
                return 1.5  # Увеличиваем в 1.5 раза
            elif sharpness >= low_sharpness:
                return 1.2  # Небольшое увеличение
            else:
                return 1.0  # Не увеличиваем
                
        elif resolution_quality == 'medium':
            # Средние изображения
            if sharpness >= high_sharpness:
                return 1.5  # Увеличиваем в 1.5 раза
            elif sharpness >= medium_sharpness:
                return 1.2  # Небольшое увеличение
            else:
                return 1.0  # Не увеличиваем
                
        else:  # large
            # Большие изображения не увеличиваем
            return 1.0


class ImageConverter:
    """Основной класс для конвертации изображений."""
    
    def __init__(self, source_dir: str, output_dir: str = "img_result"):
        """
        Инициализация конвертера изображений.
        
        Args:
            source_dir: Путь к папке с исходными изображениями
            output_dir: Путь к папке для сохранения результатов
        """
        self.source_dir = Path(source_dir)
        self.output_dir = Path(output_dir)
        self.template_width = 2560
        self.template_height = 1440
        self.background_color = (255, 255, 255)  # Белый фон
        
        # Поддерживаемые форматы
        self.supported_formats = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff'}
        
        # Настройка логирования
        self._setup_logging()
        
        # Создаем папку для результатов
        self.output_dir.mkdir(exist_ok=True)
        
        # Инициализируем анализатор качества
        self.quality_analyzer = ImageQualityAnalyzer()
    
    def _setup_logging(self) -> None:
        """Настройка системы логирования."""
        log_format = '%(asctime)s - %(levelname)s - %(message)s'
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.FileHandler('image_converter.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def _get_image_files(self) -> List[Path]:
        """
        Получает список всех поддерживаемых изображений в папке.
        
        Returns:
            List[Path]: Список путей к файлам изображений
        """
        image_files = []
        
        if not self.source_dir.exists():
            self.logger.error(f"Папка {self.source_dir} не существует")
            return image_files
        
        for file_path in self.source_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in self.supported_formats:
                image_files.append(file_path)
        
        self.logger.info(f"Найдено {len(image_files)} изображений для обработки")
        return image_files
    
    def _calculate_scale_and_position(self, image: Image.Image) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """
        Вычисляет масштаб и позицию для размещения изображения в шаблоне.
        
        Args:
            image: PIL изображение
            
        Returns:
            Tuple: ((new_width, new_height), (x_position, y_position))
        """
        orig_width, orig_height = image.size
        
        # Получаем коэффициент предварительного масштабирования
        scale_factor = self.quality_analyzer.get_scale_factor(image)
        
        # Применяем предварительное масштабирование
        pre_scaled_width = int(orig_width * scale_factor)
        pre_scaled_height = int(orig_height * scale_factor)
        
        # Вычисляем соотношения сторон
        image_aspect = pre_scaled_width / pre_scaled_height
        template_aspect = self.template_width / self.template_height
        
        # Определяем итоговый масштаб для вписывания в шаблон
        if image_aspect > template_aspect:
            # Изображение шире шаблона - масштабируем по ширине
            final_scale = self.template_width / pre_scaled_width
        else:
            # Изображение выше шаблона - масштабируем по высоте
            final_scale = self.template_height / pre_scaled_height
        
        # Вычисляем финальные размеры
        new_width = int(pre_scaled_width * final_scale)
        new_height = int(pre_scaled_height * final_scale)
        
        # Центрируем изображение
        x_position = (self.template_width - new_width) // 2
        y_position = (self.template_height - new_height) // 2
        
        return (new_width, new_height), (x_position, y_position)
    
    def _enhance_image_quality(self, image: Image.Image) -> Image.Image:
        """
        Улучшает качество изображения при необходимости.
        
        Args:
            image: Исходное изображение
            
        Returns:
            Image.Image: Улучшенное изображение
        """
        # Анализируем четкость
        sharpness = self.quality_analyzer.analyze_sharpness(image)
        
        # Если изображение недостаточно четкое, применяем фильтр повышения резкости
        if sharpness < 1000:  # Пороговое значение
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(1.2)  # Небольшое повышение резкости
        
        return image
    
    def _process_single_image(self, image_path: Path) -> bool:
        """
        Обрабатывает одно изображение.
        
        Args:
            image_path: Путь к изображению
            
        Returns:
            bool: True, если обработка прошла успешно
        """
        try:
            # Открываем изображение
            with Image.open(image_path) as image:
                # Конвертируем в RGB, если необходимо
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                # Анализируем качество для логирования
                orig_width, orig_height = image.size
                resolution_quality = self.quality_analyzer.analyze_resolution_quality(orig_width, orig_height)
                sharpness = self.quality_analyzer.analyze_sharpness(image)
                scale_factor = self.quality_analyzer.get_scale_factor(image)
                
                # Улучшаем качество при необходимости
                image = self._enhance_image_quality(image)
                
                # Вычисляем размеры и позицию с новой логикой
                (new_width, new_height), (x_pos, y_pos) = self._calculate_scale_and_position(image)
                
                # Создаем шаблон с белым фоном
                template = Image.new('RGB', (self.template_width, self.template_height), 
                                   self.background_color)
                
                # Применяем предварительное масштабирование
                pre_scaled_width = int(orig_width * scale_factor)
                pre_scaled_height = int(orig_height * scale_factor)
                
                # Сначала применяем предварительное масштабирование
                if scale_factor != 1.0:
                    image = image.resize((pre_scaled_width, pre_scaled_height), Image.LANCZOS)
                
                # Затем масштабируем до финальных размеров
                if (new_width, new_height) != image.size:
                    resized_image = image.resize((new_width, new_height), Image.LANCZOS)
                else:
                    resized_image = image
                
                # Вставляем изображение в шаблон
                template.paste(resized_image, (x_pos, y_pos))
                
                # Сохраняем результат с оригинальным именем
                output_path = self.output_dir / f"{image_path.name}"
                template.save(output_path, 'JPEG', quality=100, optimize=True)
                
                # Логируем с подробной информацией
                self.logger.info(f"✓ Обработано: {image_path.name} -> {output_path.name} "
                               f"(размер: {resolution_quality}, четкость: {sharpness:.0f}, "
                               f"масштаб: {scale_factor}x, {orig_width}x{orig_height} -> {new_width}x{new_height})")
                return True
                
        except Exception as e:
            self.logger.error(f"✗ Ошибка при обработке {image_path.name}: {str(e)}")
            return False
    
    def convert_images(self, max_workers: int = 4) -> None:
        """
        Конвертирует все изображения в папке.
        
        Args:
            max_workers: Максимальное количество потоков для параллельной обработки
        """
        start_time = datetime.now()
        self.logger.info("=" * 60)
        self.logger.info("НАЧАЛО ОБРАБОТКИ ИЗОБРАЖЕНИЙ")
        self.logger.info("=" * 60)
        
        # Получаем список файлов
        image_files = self._get_image_files()
        
        if not image_files:
            self.logger.warning("Не найдено изображений для обработки")
            return
        
        # Статистика обработки
        successful_count = 0
        failed_count = 0
        
        # Обрабатываем изображения параллельно
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Запускаем задачи
            future_to_path = {
                executor.submit(self._process_single_image, image_path): image_path
                for image_path in image_files
            }
            
            # Собираем результаты
            for future in as_completed(future_to_path):
                image_path = future_to_path[future]
                try:
                    success = future.result()
                    if success:
                        successful_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    self.logger.error(f"Неожиданная ошибка для {image_path.name}: {str(e)}")
                    failed_count += 1
        
        # Итоговая статистика
        end_time = datetime.now()
        processing_time = end_time - start_time
        
        self.logger.info("=" * 60)
        self.logger.info("РЕЗУЛЬТАТЫ ОБРАБОТКИ")
        self.logger.info("=" * 60)
        self.logger.info(f"Всего изображений: {len(image_files)}")
        self.logger.info(f"Успешно обработано: {successful_count}")
        self.logger.info(f"Ошибки: {failed_count}")
        self.logger.info(f"Время обработки: {processing_time}")
        self.logger.info(f"Результаты сохранены в: {self.output_dir}")
        
        if failed_count > 0:
            self.logger.warning(f"Внимание: {failed_count} изображений не удалось обработать")


def main():
    """Главная функция для запуска конвертации."""
    # Пути к папкам
    source_directory = "/home/max-bay/Рабочий стол/Projects/temp_parse/img"
    output_directory = "/home/max-bay/Рабочий стол/Projects/temp_parse/img_result"
    
    # Создаем конвертер
    converter = ImageConverter(source_directory, output_directory)
    
    # Запускаем конвертацию
    converter.convert_images(max_workers=4)


if __name__ == "__main__":
    main()
