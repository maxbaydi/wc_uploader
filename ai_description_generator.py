#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI Description Generator
Модуль для генерации описаний товаров с помощью OpenAI API
"""

import os
import json
import pandas as pd
from typing import List, Dict, Any, Optional, Callable
import time
import re
from openai import (
    OpenAI,
    APIStatusError,
    APITimeoutError,
    RateLimitError,
    APIConnectionError,
    APIError,
)


class AIDescriptionGenerator:
    """Класс для генерации описаний товаров с помощью AI"""
    
    def __init__(self, api_key: str, api_url: Optional[str] = None, model: str = "gpt-4o-mini",
                 temperature: float = 0.7, max_retries: int = 3, retry_delay: float = 2.0,
                 timeout: int = 120):
        """
        Инициализация генератора описаний
        
        Args:
            api_key: API ключ OpenAI
            api_url: Базовый URL совместимого OpenAI API (по умолчанию api.openai.com/v1)
            model: Модель для использования (по умолчанию gpt-4o-mini)
            temperature: Температура генерации (0.0-1.0)
            max_retries: Максимальное количество повторных попыток
            retry_delay: Начальная задержка между повторными попытками (сек)
            timeout: Таймаут запроса (сек)
        """
        self.api_key = api_key
        self.api_url = api_url or "https://api.openai.com/v1"
        self.base_url = self._normalize_api_url(self.api_url)
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        
        # Callbacks
        self.log_callback: Optional[Callable] = None
        self.progress_callback: Optional[Callable] = None
        
        # Флаг остановки
        self._stop_flag = False
        
        # Статистика
        self.stats = {
            'total': 0,
            'generated': 0,
            'errors': 0,
            'skipped': 0,
            'already_had_descriptions': 0,
            'batches': 0,
            'retries': 0,
            'failed_after_retries': 0
        }

        # Клиент OpenAI
        self.client = self._create_client()

    def _normalize_api_url(self, api_url: Optional[str]) -> Optional[str]:
        if not api_url:
            return None
        cleaned = api_url.strip().rstrip("/")
        if cleaned.endswith("/chat/completions"):
            cleaned = cleaned.rsplit("/chat/completions", 1)[0].rstrip("/")
        return cleaned or None

    def _create_client(self) -> OpenAI:
        client_kwargs: Dict[str, Any] = {
            "api_key": self.api_key,
            "timeout": self.timeout
        }
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        return OpenAI(**client_kwargs)

    def _get_retry_delay(self, retry: int) -> float:
        return self.retry_delay * (2 ** retry)

    def _is_retryable_status(self, status_code: Optional[int]) -> bool:
        return status_code in {429, 500, 502, 503, 504}

    def _extract_message_content(self, response: Any) -> str:
        if not response or not getattr(response, "choices", None):
            return ""
        message_content = response.choices[0].message.content
        if isinstance(message_content, str):
            return message_content.strip()
        if isinstance(message_content, list):
            parts = []
            for part in message_content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(part.get("text", ""))
                elif isinstance(part, str):
                    parts.append(part)
            return "".join(parts).strip()
        return ""
        
    def set_log_callback(self, callback: Callable[[str], None]) -> None:
        """Устанавливает callback для логирования"""
        self.log_callback = callback
        
    def set_progress_callback(self, callback: Callable[[int, int, str], None]) -> None:
        """Устанавливает callback для обновления прогресса"""
        self.progress_callback = callback
        
    def log_message(self, message: str) -> None:
        """Отправляет сообщение в лог"""
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)
            
    def update_progress(self, current: int, total: int, message: str = "") -> None:
        """Обновляет прогресс"""
        if self.progress_callback:
            self.progress_callback(current, total, message)
            
    def stop_generation(self) -> None:
        """Останавливает процесс генерации"""
        self._stop_flag = True
        
    def create_batch_prompt(self, product_names: List[str], language: str = "русский", max_length: int = 300) -> str:
        """
        Создает промт для пакетной генерации описаний
        
        Args:
            product_names: Список названий товаров
            language: Язык описаний
            max_length: Максимальная длина описания в символах
            
        Returns:
            Промт для AI модели
        """
        products_list = ""
        for i, name in enumerate(product_names, 1):
            products_list += f"ID: {i}, Название: {name}\n"
            
        prompt = f"""Ты профессиональный маркетолог, который создает описания для товаров в интернет-магазине. 

Создай краткие и привлекательные описания для следующих товаров на {language} языке:

{products_list}

ТРЕБОВАНИЯ:
- Каждое описание должно быть не более {max_length} символов
- Описания должны быть информативными и привлекательными для покупателей
- Используй ключевые слова для SEO
- Подчеркни основные преимущества и применение товара
- Избегай технических терминов, если они не важны для покупателя
- ОБЯЗАТЕЛЬНО возвращай ID товара для точного сопоставления

ФОРМАТ ОТВЕТА (строго JSON):
{{
  "descriptions": [
    {{"id": 1, "name": "название товара 1 (переведенное на {language} при необходимости)", "description": "описание товара 1"}},
    {{"id": 2, "name": "название товара 2 (переведенное на {language} при необходимости)", "description": "описание товара 2"}},
    ...
  ]
}}

ВАЖНО: Обязательно включай поле "id" для каждого товара! Это критично для правильного сопоставления.

Верни только JSON, без дополнительных комментариев."""

        return prompt
        
    def call_ai_api(self, prompt: str, attempt_number: int = 1) -> Optional[Dict[str, Any]]:
        """
        Вызов AI API для генерации описаний с поддержкой retry
        
        Args:
            prompt: Промт для модели
            attempt_number: Номер попытки (для логирования)
            
        Returns:
            Ответ от API в виде словаря или None при ошибке
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Ты профессиональный маркетолог и копирайтер."},
                {"role": "user", "content": prompt}
            ],
            "temperature": self.temperature,
            "response_format": {"type": "json_object"}
        }
        
        # Retry логика с экспоненциальной задержкой
        for retry in range(self.max_retries + 1):
            try:
                if retry == 0:
                    self.log_message(f"🤖 Отправка запроса к OpenAI (модель: {self.model}, температура: {self.temperature})")
                else:
                    self.stats['retries'] += 1
                    self.log_message(f"🔄 Повторная попытка #{retry} для пакета {attempt_number}")
                
                response = self.client.chat.completions.create(**payload, timeout=self.timeout)
                content = self._extract_message_content(response)

                if not content:
                    self.log_message(f"❌ Пустой ответ от OpenAI (попытка {retry + 1})")
                    if retry < self.max_retries:
                        continue
                    else:
                        break

                # Улучшенный парсинг JSON с обработкой неполных ответов
                try:
                    descriptions_data = json.loads(content)
                    if retry > 0:
                        self.log_message(f"✅ Успешно восстановлено после {retry} попыток")
                    return descriptions_data
                except json.JSONDecodeError as e:
                    self.log_message(f"❌ Ошибка парсинга JSON (попытка {retry + 1}): {e}")
                    if "Unterminated string" in str(e) or "Expecting" in str(e):
                        try:
                            if content.count('{') > content.count('}'):
                                fixed_content = content + '"}]}'
                                descriptions_data = json.loads(fixed_content)
                                self.log_message(f"✅ JSON восстановлен автоматически")
                                return descriptions_data
                        except Exception:
                            pass
                    
                    if retry == self.max_retries:
                        self.log_message(f"Содержимое ответа: {content[:500]}...")
                    
                    if retry < self.max_retries:
                        continue
                    else:
                        break
                            
            except (APITimeoutError, RateLimitError, APIConnectionError) as e:
                self.log_message(f"⚠️ Временная ошибка OpenAI (попытка {retry + 1}): {e}")
                if retry < self.max_retries:
                    delay = self._get_retry_delay(retry)
                    self.log_message(f"⏳ Ожидание {delay:.1f} сек. перед повтором...")
                    time.sleep(delay)
                    continue
                else:
                    break
            except APIStatusError as e:
                status_code = getattr(e, "status_code", None)
                self.log_message(f"⚠️ Ошибка OpenAI: HTTP {status_code} (попытка {retry + 1})")
                if self._is_retryable_status(status_code) and retry < self.max_retries:
                    delay = self._get_retry_delay(retry)
                    self.log_message(f"⏳ Ожидание {delay:.1f} сек. перед повтором...")
                    time.sleep(delay)
                    continue
                else:
                    return None
            except APIError as e:
                self.log_message(f"❌ Критическая ошибка OpenAI: {e}")
                return None
            except Exception as e:
                self.log_message(f"💥 Неожиданная ошибка (попытка {retry + 1}): {e}")
                if retry < self.max_retries:
                    delay = self._get_retry_delay(retry)
                    self.log_message(f"⏳ Ожидание {delay:.1f} сек. перед повтором...")
                    time.sleep(delay)
                    continue
                else:
                    break
        
        # Если дошли сюда, значит все попытки исчерпаны
        self.stats['failed_after_retries'] += 1
        return None
            
    def process_ai_response(self, ai_response: Dict[str, Any], original_names: List[str]) -> Dict[str, Dict[str, str]]:
        """
        Обрабатывает ответ от AI и сопоставляет описания с названиями по ID
        
        Args:
            ai_response: Ответ от AI API
            original_names: Оригинальные названия товаров
            
        Returns:
            Словарь {оригинальное_название: {'name': переведенное_название, 'description': описание}}
        """
        result = {}
        
        if 'descriptions' not in ai_response:
            self.log_message("❌ В ответе AI отсутствует поле 'descriptions'")
            return result
            
        descriptions = ai_response['descriptions']
        
        if not isinstance(descriptions, list):
            self.log_message("❌ Поле 'descriptions' не является списком")
            return result
            
        # Сопоставляем описания с оригинальными названиями по ID
        for desc_item in descriptions:
            if not isinstance(desc_item, dict):
                continue
                
            # Проверяем наличие обязательных полей
            required_fields = ['id', 'description']
            if not all(field in desc_item for field in required_fields):
                self.log_message(f"⚠️ Пропущен товар из-за отсутствующих полей: {desc_item}")
                continue
                
            try:
                product_id = int(desc_item['id'])
                ai_name = desc_item.get('name', 'неизвестно').strip()
                description = desc_item['description'].strip()
                
                # Проверяем валидность ID (должен быть от 1 до количества товаров)
                if 1 <= product_id <= len(original_names):
                    original_name = original_names[product_id - 1]  # ID начинается с 1
                    result[original_name] = {
                        'name': ai_name,
                        'description': description
                    }
                    self.log_message(f"✓ ID {product_id}: '{original_name}' -> '{ai_name}' -> описание {len(description)} символов")
                else:
                    self.log_message(f"❌ Некорректный ID {product_id} для товара '{ai_name}' (должен быть 1-{len(original_names)})")
                    
            except (ValueError, TypeError) as e:
                self.log_message(f"❌ Ошибка обработки ID для товара {desc_item}: {e}")
                continue
                
        return result
        
    def calculate_similarity(self, str1: str, str2: str) -> float:
        """
        Вычисляет простую меру схожести строк
        
        Args:
            str1, str2: Строки для сравнения
            
        Returns:
            Значение схожести от 0 до 1
        """
        if str1 == str2:
            return 1.0
            
        # Простая метрика: количество общих слов
        words1 = set(re.findall(r'\w+', str1.lower()))
        words2 = set(re.findall(r'\w+', str2.lower()))
        
        if not words1 or not words2:
            return 0.0
            
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)
        
    def generate_descriptions_from_csv(
        self, 
        csv_file: str, 
        name_column: str = "product_name",
        language: str = "русский",
        max_length: int = 300,
        batch_size: int = 5,
        delay_between_batches: float = 1.0,
        translate_names: bool = True
    ) -> Dict[str, Any]:
        """
        Генерирует описания для товаров из CSV файла
        
        Args:
            csv_file: Путь к CSV файлу
            name_column: Название колонки с названиями товаров  
            language: Язык описаний
            max_length: Максимальная длина описания
            batch_size: Размер пакета для обработки
            delay_between_batches: Задержка между пакетами в секундах
            translate_names: Переводить ли названия товаров на язык описаний
            
        Returns:
            Статистика обработки
        """
        self.log_message("=" * 50)
        self.log_message("🤖 НАЧАЛО ГЕНЕРАЦИИ AI ОПИСАНИЙ")
        self.log_message("🔍 Режим: обработка товаров без описаний")
        self.log_message("=" * 50)
        
        try:
            # Читаем CSV файл
            self.log_message(f"📋 Читаю CSV файл: {os.path.basename(csv_file)}")
            
            try:
                df = pd.read_csv(csv_file, encoding='utf-8')
            except UnicodeDecodeError:
                try:
                    df = pd.read_csv(csv_file, encoding='cp1251')
                except UnicodeDecodeError:
                    df = pd.read_csv(csv_file, encoding='latin-1')
                    
            # Проверяем наличие нужной колонки
            if name_column not in df.columns:
                raise ValueError(f"Колонка '{name_column}' не найдена в CSV файле")
                
            # Фильтруем строки с пустыми названиями
            df_filtered = df.dropna(subset=[name_column])
            df_filtered[name_column] = df_filtered[name_column].astype(str)
            df_filtered = df_filtered[df_filtered[name_column].str.strip() != '']

            # Проверяем наличие столбца description и фильтруем товары без описаний
            if 'description' in df.columns:
                self.log_message("🔍 Найден столбец 'description', проверяю товары без описаний...")

                # Определяем товары без описаний (пустые, NaN или только пробелы)
                mask_no_description = (
                    df_filtered['description'].isna() |
                    (df_filtered['description'].astype(str).str.strip() == '')
                )

                products_without_descriptions = df_filtered[mask_no_description]

                if len(products_without_descriptions) > 0:
                    products_with_descriptions = len(df_filtered) - len(products_without_descriptions)
                    self.stats['already_had_descriptions'] = products_with_descriptions
                    self.log_message(f"📝 Найдено {len(products_without_descriptions)} товаров без описаний из {len(df_filtered)}")
                    self.log_message(f"✅ Товаров с существующими описаниями: {products_with_descriptions}")
                    df_filtered = products_without_descriptions
                else:
                    self.log_message("✅ Все товары уже имеют описания!")
                    self.stats['total'] = 0
                    self.stats['already_had_descriptions'] = len(df_filtered)
                    return self.stats
            else:
                self.log_message("📝 Столбец 'description' не найден, будет создан новый")

            product_names = df_filtered[name_column].tolist()
            self.stats['total'] = len(product_names)
            
            self.log_message(f"📊 Найдено {self.stats['total']} товаров для генерации описаний")
            self.log_message(f"🔧 Настройки: язык={language}, макс.длина={max_length}, размер пакета={batch_size}")
            
            if self.stats['total'] == 0:
                self.log_message("⚠️ Нет товаров для обработки")
                return self.stats
                
            # Создаем колонку для описаний если ее нет
            if 'description' not in df.columns:
                df['description'] = ''
                self.log_message("📝 Создана новая колонка 'description'")
            else:
                self.log_message("📝 Используется существующая колонка 'description'")
                
            # Обрабатываем товары пакетами
            all_product_data = {}  # Теперь храним и названия, и описания
            total_batches = (len(product_names) + batch_size - 1) // batch_size
            
            for batch_idx in range(0, len(product_names), batch_size):
                if self._stop_flag:
                    self.log_message("⚠️ Процесс остановлен пользователем")
                    break
                    
                batch_names = product_names[batch_idx:batch_idx + batch_size]
                current_batch = (batch_idx // batch_size) + 1
                
                self.log_message(f"\n🔄 Обработка пакета {current_batch}/{total_batches} ({len(batch_names)} товаров)")
                
                # Создаем промт для пакета
                prompt = self.create_batch_prompt(batch_names, language, max_length)
                
                # Вызываем AI API с номером пакета для лучшего логирования
                ai_response = self.call_ai_api(prompt, attempt_number=current_batch)
                
                if ai_response:
                    # Обрабатываем ответ
                    batch_product_data = self.process_ai_response(ai_response, batch_names)
                    all_product_data.update(batch_product_data)
                    
                    self.stats['generated'] += len(batch_product_data)
                    self.stats['batches'] += 1
                    
                    self.log_message(f"✅ Успешно сгенерировано {len(batch_product_data)} описаний")
                    
                else:
                    self.stats['errors'] += len(batch_names)
                    self.log_message(f"❌ Ошибка генерации для пакета {current_batch}")
                    
                # Обновляем прогресс
                self.update_progress(
                    min(batch_idx + batch_size, len(product_names)),
                    len(product_names),
                    f"Обработано пакетов: {current_batch}/{total_batches}"
                )
                
                # Задержка между пакетами
                if current_batch < total_batches and delay_between_batches > 0:
                    self.log_message(f"⏳ Ожидание {delay_between_batches} сек. перед следующим пакетом...")
                    time.sleep(delay_between_batches)
                    
            # Добавляем описания и обновляем названия в DataFrame
            for idx, row in df.iterrows():
                product_name = str(row[name_column]).strip()
                if product_name in all_product_data:
                    product_data = all_product_data[product_name]
                    
                    # Обновляем описание
                    df.at[idx, 'description'] = product_data['description']
                    
                    # Обновляем название товара, если нужно перевести и язык не русский
                    if translate_names and language.lower() != "русский":
                        df.at[idx, name_column] = product_data['name']
                        self.log_message(f"🔄 Название обновлено: '{product_name}' -> '{product_data['name']}'")
                    
                elif pd.isna(row.get('description', '')) or row.get('description', '').strip() == '':
                    # Если столбец description существовал изначально, то пустые описания означают,
                    # что товар не был обработан (например, ошибка генерации)
                    if 'description' in df.columns:
                        self.stats['errors'] += 1
                    else:
                        self.stats['skipped'] += 1
                    
            # Сохраняем обновленный CSV
            output_file = csv_file
            df.to_csv(output_file, index=False, encoding='utf-8')
            self.log_message(f"💾 Обновленный CSV сохранен: {os.path.basename(output_file)}")
            
            # Итоговая статистика
            self.log_message("\n" + "=" * 50) 
            self.log_message("📊 РЕЗУЛЬТАТЫ ГЕНЕРАЦИИ ОПИСАНИЙ")
            self.log_message("=" * 50)
            total_products_in_file = self.stats['total'] + self.stats['already_had_descriptions']
            self.log_message(f"Всего товаров в файле: {total_products_in_file}")
            self.log_message(f"Товаров без описаний: {self.stats['total']}")
            self.log_message(f"Товаров с существующими описаниями: {self.stats['already_had_descriptions']}")
            self.log_message(f"Сгенерировано описаний: {self.stats['generated']}")
            self.log_message(f"Пропущено: {self.stats['skipped']}")
            self.log_message(f"Ошибки: {self.stats['errors']}")
            self.log_message(f"Обработано пакетов: {self.stats['batches']}")
            
            # Новая статистика retry
            if self.stats['retries'] > 0 or self.stats['failed_after_retries'] > 0:
                self.log_message("=" * 50)
                self.log_message("🔄 СТАТИСТИКА ПОВТОРНЫХ ПОПЫТОК")
                self.log_message(f"Всего retry попыток: {self.stats['retries']}")
                self.log_message(f"Восстановлено после retry: {self.stats['retries'] - self.stats['failed_after_retries']}")
                self.log_message(f"Провалено даже после retry: {self.stats['failed_after_retries']}")
                if self.stats['retries'] > 0:
                    retry_success_rate = ((self.stats['retries'] - self.stats['failed_after_retries']) / self.stats['retries']) * 100
                    self.log_message(f"Эффективность retry: {retry_success_rate:.1f}%")
            
            if self.stats['total'] > 0:
                success_rate = (self.stats['generated'] / self.stats['total']) * 100
                self.log_message(f"\n✅ Успешность генерации: {success_rate:.1f}% ({self.stats['generated']} из {self.stats['total']} товаров без описаний)")

                # Расчет экономии благодаря retry
                if self.stats['retries'] > 0:
                    saved_products = self.stats['retries'] - self.stats['failed_after_retries']
                    if saved_products > 0:
                        self.log_message(f"💰 Спасено товаров благодаря retry: {saved_products}")
                        old_success_rate = ((self.stats['generated'] - saved_products) / self.stats['total']) * 100
                        improvement = success_rate - old_success_rate
                        self.log_message(f"📈 Улучшение на: {improvement:.1f}% (с {old_success_rate:.1f}% до {success_rate:.1f}%)")
                
            return self.stats
            
        except Exception as e:
            self.log_message(f"💥 КРИТИЧЕСКАЯ ОШИБКА: {str(e)}")
            raise e
