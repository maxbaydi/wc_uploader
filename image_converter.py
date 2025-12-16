#!/usr/bin/env python3
"""
Модуль для конвертации изображений в унифицированный формат.

Этот модуль предоставляет функциональность для обработки изображений в папке,
размещения их в центре шаблона с альбомным расположением (2560x1440)
с учетом качества и разрешения исходных изображений.

КЛЮЧЕВЫЕ ОСОБЕННОСТИ:
- Улучшенная логика масштабирования: contain + scale-down вместо cover
- Variance of Laplacian для оценки четкости (если доступен OpenCV)
- Ограничение апскейла по качеству изображения
- Единичный ресайз вместо двойного для лучшего качества
- Поддержка callback логирования для интеграции с GUI

АЛГОРИТМ МАСШТАБИРОВАНИЯ:
1. Анализ размера и четкости изображения
2. Вычисление масштаба "вписать целиком" (contain)
3. Ограничение апскейла в зависимости от качества
4. Центрирование на белом фоне с сохранением пропорций
5. Опциональное повышение резкости при низком качестве

ПОДДЕРЖИВАЕМЫЕ ФОРМАТЫ: JPG, JPEG, PNG, WebP, BMP, TIFF

Автор: GitHub Copilot
Дата: 16 июля 2025
Обновлено: Добавлена улучшенная логика масштабирования
"""

import sys
import logging
from pathlib import Path
from typing import Tuple, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import numpy as np
from PIL import Image, ImageFilter

# Проверяем доступность OpenCV для Variance of Laplacian
try:
    import cv2
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False


TEMPLATE_SIZE = (2560, 1440)
BACKGROUND_COLOR = (255, 255, 255)
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff'}
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
LOG_FILE = 'image_converter.log'

UPSCALE_HARD_CAP = 3.0

SHARP_THRESHOLD_CV2 = 500.0
SHARP_THRESHOLD_NO_CV2 = 3000.0
UNSHARP_THRESHOLD_CV2 = 200.0
UNSHARP_THRESHOLD_NO_CV2 = 2000.0
UNSHARP_MASK_PARAMS = {"radius": 2, "percent": 150, "threshold": 3}


def _select_threshold(cv2_value: float, fallback_value: float) -> float:
    return cv2_value if _HAS_CV2 else fallback_value


class ImageQualityAnalyzer:
    """Класс для анализа качества изображений."""
    
    @staticmethod
    def analyze_sharpness(image: Image.Image) -> float:
        """
        Оценивает четкость изображения. Предпочтительно: Variance of Laplacian (VoL),
        fallback: дисперсия после FIND_EDGES.

        Args:
            image: PIL изображение для анализа

        Returns:
            float: Показатель четкости (больше = четче)
        """
        gray = image.convert('L')
        np_gray = np.array(gray)

        if _HAS_CV2:
            # VoL — устойчивый и широко используемый фокус-метод
            # cv2.Laplacian(...).var() — численная метрика резкости
            return cv2.Laplacian(np_gray, cv2.CV_64F).var()
        else:
            # Fallback на текущую реализацию, если OpenCV недоступен
            gradient = gray.filter(ImageFilter.FIND_EDGES)
            return np.array(gradient).var()
    
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
    def get_allowed_upscale(image: Image.Image) -> float:
        """
        Determines the maximum allowed upscale factor.
        This logic is conservative: it avoids upscaling small or blurry images.
        """
        w, h = image.size
        res_quality = ImageQualityAnalyzer.analyze_resolution_quality(w, h)
        sharpness = ImageQualityAnalyzer.analyze_sharpness(image)

        sharp_threshold = _select_threshold(SHARP_THRESHOLD_CV2, SHARP_THRESHOLD_NO_CV2)
        
        high_sharpness_threshold = sharp_threshold * 2.0
        allowed = 1.0

        if sharpness >= high_sharpness_threshold:
            if res_quality == 'very_small':
                allowed = min(UPSCALE_HARD_CAP, 3.0)
            elif res_quality == 'small':
                allowed = min(UPSCALE_HARD_CAP, 1.8)
            elif res_quality == 'medium':
                allowed = 1.2
        elif sharpness >= sharp_threshold:
            if res_quality == 'very_small':
                allowed = min(UPSCALE_HARD_CAP, 2.0)
            elif res_quality == 'small':
                allowed = min(UPSCALE_HARD_CAP, 1.4)
            elif res_quality == 'medium':
                allowed = 1.1

        return allowed


class ImageConverter:
    """Основной класс для конвертации изображений."""
    
    def __init__(self, source_dir: str, output_dir: str = "img_result", log_callback=None):
        """
        Инициализация конвертера изображений.

        Args:
            source_dir: Путь к папке с исходными изображениями
            output_dir: Путь к папке для сохранения результатов
            log_callback: Функция обратного вызова для логирования (опционально)
        """
        self.source_dir = Path(source_dir)
        self.output_dir = Path(output_dir)
        self.template_width, self.template_height = TEMPLATE_SIZE
        self.background_color = BACKGROUND_COLOR
        self.log_callback = log_callback  # Callback функция для внешнего логирования
        self.supported_formats = SUPPORTED_FORMATS
        self.unsharp_threshold = _select_threshold(UNSHARP_THRESHOLD_CV2, UNSHARP_THRESHOLD_NO_CV2)

        # Настройка логирования
        self._setup_logging()

        # Создаем папку для результатов
        self.output_dir.mkdir(exist_ok=True)

        # Инициализируем анализатор качества
        self.quality_analyzer = ImageQualityAnalyzer()
    
    def _setup_logging(self) -> None:
        """Настройка системы логирования."""
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout)
        ])
        self.logger = logging.getLogger(__name__)

    def _log(self, message: str, level: str = 'info') -> None:
        """
        Универсальный метод логирования с поддержкой callback.

        Args:
            message: Сообщение для логирования
            level: Уровень логирования ('info', 'error', 'warning')
        """
        if self.log_callback:
            # Используем callback для внешнего логирования
            self.log_callback(message)
        else:
            # Используем стандартный логгер
            if level == 'info':
                self.logger.info(message)
            elif level == 'error':
                self.logger.error(message)
            elif level == 'warning':
                self.logger.warning(message)
    
    def _get_image_files(self) -> List[Path]:
        """
        Получает список всех поддерживаемых изображений в папке.
        
        Returns:
            List[Path]: Список путей к файлам изображений
        """
        image_files = []
        
        if not self.source_dir.exists():
            self._log(f"Папка {self.source_dir} не существует", 'error')
            return image_files

        for file_path in self.source_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in self.supported_formats:
                image_files.append(file_path)

        self._log(f"Найдено {len(image_files)} изображений для обработки")
        return image_files
    

    def _calculate_scale_and_position(self, image: Image.Image) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """
        Calculates the final size and position of the image on the template.
        It respects the quality limits and includes a hard cap on upscaling.
        """
        orig_width, orig_height = image.size
        contain_scale = min(self.template_width / orig_width, self.template_height / orig_height)
        quality_limited_upscale = self.quality_analyzer.get_allowed_upscale(image)

        if contain_scale > UPSCALE_HARD_CAP:
            final_scale = min(quality_limited_upscale, UPSCALE_HARD_CAP)
        elif contain_scale > 1.0:
            final_scale = min(contain_scale, quality_limited_upscale, UPSCALE_HARD_CAP)
        else:
            final_scale = contain_scale

        new_width = max(1, int(round(orig_width * final_scale)))
        new_height = max(1, int(round(orig_height * final_scale)))

        x_position = (self.template_width - new_width) // 2
        y_position = (self.template_height - new_height) // 2

        return (new_width, new_height), (x_position, y_position)
    
    def _build_template(self) -> Image.Image:
        return Image.new('RGB', (self.template_width, self.template_height), self.background_color)

    @staticmethod
    def _ensure_rgb(image: Image.Image) -> Image.Image:
        return image if image.mode == 'RGB' else image.convert('RGB')

    @staticmethod
    def _resize_image(image: Image.Image, size: Tuple[int, int]) -> Image.Image:
        return image if image.size == size else image.resize(size, Image.LANCZOS)

    def _should_apply_unsharp_mask(self, sharpness: float) -> bool:
        return sharpness < self.unsharp_threshold

    def _collect_image_stats(self, image: Image.Image) -> Tuple[str, float, Tuple[int, int]]:
        width, height = image.size
        resolution_quality = self.quality_analyzer.analyze_resolution_quality(width, height)
        sharpness = self.quality_analyzer.analyze_sharpness(image)
        return resolution_quality, sharpness, (width, height)

    @staticmethod
    def _apply_unsharp_mask(image: Image.Image) -> Image.Image:
        return image.filter(ImageFilter.UnsharpMask(**UNSHARP_MASK_PARAMS))
    
    def _process_single_image(self, image_path: Path) -> bool:
        """
        Обрабатывает одно изображение.

        Args:
            image_path: Путь к изображению

        Returns:
            bool: True, если обработка прошла успешно
        """
        try:
            with Image.open(image_path) as image:
                image = self._ensure_rgb(image)
                resolution_quality, sharpness, (orig_width, orig_height) = self._collect_image_stats(image)
                (new_width, new_height), (x_pos, y_pos) = self._calculate_scale_and_position(image)

                template = self._build_template()
                resized_image = self._resize_image(image, (new_width, new_height))

                if self._should_apply_unsharp_mask(sharpness):
                    resized_image = self._apply_unsharp_mask(resized_image)

                template.paste(resized_image, (x_pos, y_pos))

                output_path = self.output_dir / image_path.name
                template.save(output_path, 'JPEG', quality=100, optimize=True)

                self._log(
                    f"✓ Обработано: {image_path.name} -> {output_path.name} "
                    f"(размер: {resolution_quality}, четкость: {sharpness:.1f}, "
                    f"{orig_width}x{orig_height} -> {new_width}x{new_height})"
                )
                return True
        except Exception as e:
            self._log(f"✗ Ошибка при обработке {image_path.name}: {str(e)}", 'error')
            return False
    
    def convert_images(self, max_workers: int = 4) -> None:
        """
        Конвертирует все изображения в папке.
        
        Args:
            max_workers: Максимальное количество потоков для параллельной обработки
        """
        start_time = datetime.now()
        self._log("=" * 60)
        self._log("НАЧАЛО ОБРАБОТКИ ИЗОБРАЖЕНИЙ")
        self._log("=" * 60)

        # Получаем список файлов
        image_files = self._get_image_files()

        if not image_files:
            self._log("Не найдено изображений для обработки", 'warning')
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
                    self._log(f"Неожиданная ошибка для {image_path.name}: {str(e)}", 'error')
                    failed_count += 1

        # Итоговая статистика
        end_time = datetime.now()
        processing_time = end_time - start_time

        self._log("=" * 60)
        self._log("РЕЗУЛЬТАТЫ ОБРАБОТКИ")
        self._log("=" * 60)
        self._log(f"Всего изображений: {len(image_files)}")
        self._log(f"Успешно обработано: {successful_count}")
        self._log(f"Ошибки: {failed_count}")
        self._log(f"Время обработки: {processing_time}")
        self._log(f"Результаты сохранены в: {self.output_dir}")

        if failed_count > 0:
            self._log(f"Внимание: {failed_count} изображений не удалось обработать", 'warning')

