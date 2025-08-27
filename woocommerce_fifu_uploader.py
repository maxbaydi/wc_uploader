#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WooCommerce FIFU Uploader
Модуль для интеграции с плагином Featured Image from URL (FIFU) для WooCommerce
"""

import os
import requests
from woocommerce import API
import pandas as pd
import time
from csv_adapter import CSVAdapter
from sftp_uploader import SFTPImageUploader
from config import WOOCOMMERCE_CONFIG, UPLOAD_CONFIG, CSV_CONFIG, PROXY_CONFIG
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import unicodedata

# Настройка прокси для всего процесса Python
if PROXY_CONFIG["disable_proxy"]:
    # Отключаем прокси через переменные окружения
    os.environ['HTTP_PROXY'] = ''
    os.environ['HTTPS_PROXY'] = ''
    os.environ['http_proxy'] = ''
    os.environ['https_proxy'] = ''
    os.environ['NO_PROXY'] = '*'
    os.environ['no_proxy'] = '*'

def transliterate_to_latin(text):
    """
    Транслитерация текста с кириллицы на латиницу и подготовка для использования в URL
    
    Args:
        text: Исходный текст
        
    Returns:
        str: Транслитерированный текст, подготовленный для URL
    """
    if not text:
        return ""
        
    # Нормализуем Unicode символы
    text = unicodedata.normalize('NFD', text)
    
    # Словарь для транслитерации кириллических символов
    cyrillic_to_latin = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        'А': 'a', 'Б': 'b', 'В': 'v', 'Г': 'g', 'Д': 'd', 'Е': 'e', 'Ё': 'e',
        'Ж': 'zh', 'З': 'z', 'И': 'i', 'Й': 'y', 'К': 'k', 'Л': 'l', 'М': 'm',
        'Н': 'n', 'О': 'o', 'П': 'p', 'Р': 'r', 'С': 's', 'Т': 't', 'У': 'u',
        'Ф': 'f', 'Х': 'h', 'Ц': 'ts', 'Ч': 'ch', 'Ш': 'sh', 'Щ': 'sch',
        'Ъ': '', 'Ы': 'y', 'Ь': '', 'Э': 'e', 'Ю': 'yu', 'Я': 'ya'
    }
    
    # Преобразование символов
    result = ""
    for char in text:
        if char in cyrillic_to_latin:
            result += cyrillic_to_latin[char]
        elif char.isalnum() or char in ['-', '_']:
            result += char.lower()
        else:
            result += '-'
    
    # Заменяем пробелы и другие символы на дефисы
    result = re.sub(r'[^a-z0-9-_]', '-', result)
    
    # Заменяем множественные дефисы на один
    result = re.sub(r'-+', '-', result)
    
    # Удаляем дефисы в начале и конце
    result = result.strip('-')
    
    return result

class WooCommerceFIFUUploader:
    def __init__(self, wc_url, wc_consumer_key, wc_consumer_secret, ssh_config, wp_username=None, wp_app_password=None):
        """
        Инициализация загрузчика WooCommerce с поддержкой FIFU
        
        Args:
            wc_url: URL сайта WooCommerce
            wc_consumer_key: Ключ API WooCommerce
            wc_consumer_secret: Секретный ключ API WooCommerce
            ssh_config: Конфигурация для SSH подключения
            wp_username: Имя пользователя WordPress для Basic Auth
            wp_app_password: Пароль приложения WordPress для Basic Auth
        """
        self.url = wc_url
        self.consumer_key = wc_consumer_key
        self.consumer_secret = wc_consumer_secret
        self.wp_username = wp_username
        self.wp_app_password = wp_app_password
        self.ssh_config = ssh_config  # Сохраняем конфиг для воркеров
        self.wcapi = API(
            url=wc_url,
            consumer_key=wc_consumer_key,
            consumer_secret=wc_consumer_secret,
            wp_api=True,
            version="wc/v3",
            timeout=180
        )
        
        # Клиент для кастомного эндпоинта больше не нужен,
        # так как мы будем использовать requests напрямую с Basic Auth.
        
        # A separate client for the standard WP REST API, used as a fallback for brands.
        self.wp_api_v2 = API(
            url=wc_url,
            consumer_key=wc_consumer_key,
            consumer_secret=wc_consumer_secret,
            wp_api=True,
            version="wp/v2",
            timeout=60,
            query_string_auth=True # Fallback auth method
        )
        
        # Отдельный клиент для WordPress операций с Basic Auth
        self.wp_basic_auth_client = None
        if wp_username and wp_app_password:
            # Создаем отдельный клиент для WordPress операций с Basic Auth
            import requests
            self.wp_basic_auth_client = requests.Session()
            self.wp_basic_auth_client.auth = (wp_username, wp_app_password)
            
            # Настройка прокси для requests клиента
            self.wp_basic_auth_client.proxies = self._get_proxy_settings()
        
        # Создаем загрузчик изображений SFTP
        self.sftp_uploader = SFTPImageUploader(**ssh_config)
        
        # Дополнительные конфигурации
        self.upload_cfg = UPLOAD_CONFIG
        self.csv_adapter = CSVAdapter()
        
        self.progress_callback = None
        self.log_callback = None
        
        # Инициализация атрибутов класса
        self._initialize_attributes()

    def _get_proxy_settings(self):
        """Получить настройки прокси для requests"""
        if PROXY_CONFIG["disable_proxy"]:
            # Отключаем прокси
            return {
                'http': None,
                'https': None,
                'no_proxy': '*'
            }
        else:
            # Используем настройки прокси из конфигурации
            proxies = {}
            if PROXY_CONFIG["http"]:
                proxies['http'] = PROXY_CONFIG["http"]
            if PROXY_CONFIG["https"]:
                proxies['https'] = PROXY_CONFIG["https"]
            if PROXY_CONFIG["socks"]:
                proxies['http'] = PROXY_CONFIG["socks"]
                proxies['https'] = PROXY_CONFIG["socks"]
            return proxies

    def _initialize_attributes(self):
        """Инициализация атрибутов класса"""
        self.stop_requested = False
        
        # Кэш URL изображений для повторного использования
        self.image_url_cache = {}
        
        # Кэш существующих товаров для быстрого поиска
        self.existing_products_cache = {}
        self.cache_loaded = False
        
        # Placeholder image URL (если изображение не найдено)
        self.use_placeholder = False
        self.placeholder_image_path = None
        self.placeholder_image_url = None
        
        # Кэш категорий для избежания повторных запросов
        self.category_cache = {}
        
        # --- Brand Handling Rework ---
        self.brand_api_client = self.wcapi      # API client to use (wcapi or wp_api_v2)
        self.brand_endpoint = None              # API endpoint slug (e.g., 'products/brands' or 'product_brand')
        self.brand_assignment_slug = 'product_brand' # Taxonomy slug for assigning to a product
        self.brand_term_cache = {}
        self.brand_endpoint = self._find_brand_endpoint() # Discover the correct endpoint
        
        # Блокировки для избежания дублирования в параллельных потоках
        self.brand_creation_lock = threading.Lock()
        self.category_creation_lock = threading.Lock()
        
        # Предварительная загрузка категорий и брендов в кэш
        self._preload_categories_and_brands()
        
    def set_progress_callback(self, callback):
        """Установить callback для обновления прогресса"""
        self.progress_callback = callback
        self.sftp_uploader.set_log_callback(self.log)
        
    def set_log_callback(self, callback):
        """Установить callback для логирования"""
        self.log_callback = callback
        self.sftp_uploader.set_log_callback(callback)
        
    def log(self, message):
        """Логирование сообщения"""
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)
            
    def update_progress(self, current, total, message=""):
        """Обновление прогресса"""
        if self.progress_callback:
            self.progress_callback(current, total, message)
            
    def stop_upload(self):
        """Остановить загрузку"""
        self.stop_requested = True
        
    def set_placeholder_image(self, image_path, use_placeholder=True):
        """
        Установить заглушку для товаров без изображений
        
        Args:
            image_path: Путь к изображению-заглушке
            use_placeholder: Использовать ли заглушку для товаров без изображений
            
        Returns:
            bool: True если заглушка успешно загружена или отключена
        """
        self.use_placeholder = use_placeholder
        self.placeholder_image_path = image_path if use_placeholder else None
        self.placeholder_image_url = None  # Сбрасываем кэшированный URL
        
        # Если заглушка не используется, просто возвращаем True
        if not use_placeholder:
            self.log("🖼️ Заглушка для товаров без изображений отключена")
            return True
            
        # Если нет пути к заглушке, выдаем ошибку
        if not image_path:
            self.log("❌ Не указан путь к изображению-заглушке")
            self.use_placeholder = False
            return False
            
        # Если файл не существует, выдаем ошибку
        if not os.path.exists(image_path):
            self.log(f"❌ Файл изображения-заглушки не найден: {image_path}")
            self.use_placeholder = False
            return False
            
        try:
            self.log(f"🖼️ Загрузка изображения-заглушки: {image_path}")
            
            # Проверяем размер файла
            file_size = os.path.getsize(image_path)
            self.log(f"📊 Размер файла заглушки: {file_size} байт")
            
            # Загружаем изображение-заглушку на SFTP сервер (если еще не загружено)
            clean_filename = self.sftp_uploader.clean_filename(os.path.basename(image_path))
            self.log(f"📝 Очищенное имя файла: {clean_filename}")
            
            placeholder_url = self.sftp_uploader.upload_file(
                image_path, 
                'placeholders',
                rename_to=clean_filename,
                force_upload=True  # Принудительно перезаписываем заглушку
            )
            
            self.log(f"🔗 Результат upload_file: {placeholder_url}")
            
            if placeholder_url:
                self.placeholder_image_url = placeholder_url
                self.log(f"✅ Изображение-заглушка успешно загружено: {placeholder_url}")
                return True
            else:
                self.log("❌ Не удалось загрузить изображение-заглушку")
                self.use_placeholder = False
                return False
                
        except Exception as e:
            self.log(f"❌ Ошибка загрузки изображения-заглушки: {str(e)}")
            self.use_placeholder = False
            return False
        
    def create_product_data(self, row, image_url=None, use_marketing_text=True):
        """
        Creating product data for WooCommerce with FIFU support
        
        Args:
            row: Data row from CSV
            image_url: Image URL on SFTP server
            use_marketing_text: Add marketing text to product descriptions (default: True)
            
        Returns:
            dict: Product data
        """
        # Get basic data
        brand = str(row.get('Brand', '')).strip()
        name = str(row.get('Name', '')).strip()
        sku = str(row.get('SKU', '')).strip()
        category = str(row.get('Category', '')).strip()
        price = str(row.get('Price', '0')).strip()
        
        # Capitalize first letter of brand
        if brand:
            brand = brand.capitalize()
        
        # Form full product name
        full_name = f"{brand} {name}" if brand and name else (name or f"Product {sku}")
        
        # Price processing
        regular_price = ""
        if price and price != 'NaN' and str(price).strip() not in ['0', '0.0', '']:
            try:
                price_float = float(price)
                if price_float > 0:
                    regular_price = str(price_float)
            except (ValueError, TypeError):
                regular_price = ""
        
        # Generate product slug for URL from SKU or transliterated name
        if sku:
            # Use SKU directly as slug
            product_slug = sku.lower()
            slug_source = "SKU"
        else:
            # Transliterate product name for slug
            product_slug = transliterate_to_latin(full_name)
            slug_source = "транслитерированного названия"
            
        # Ensure the slug is valid for a URL (only alphanumeric and hyphens)
        product_slug = re.sub(r'[^a-z0-9-]', '-', product_slug)
        product_slug = re.sub(r'-+', '-', product_slug).strip('-')
        
        # If slug is empty after cleaning (rare case), use a fallback
        if not product_slug:
            product_slug = f"product-{int(time.time())}"
            
        # Log the slug creation
        self.log(f"🔗 URL товара сформирован из {slug_source}: {product_slug}")
        
        # Basic product data
        product_data = {
            'name': full_name,
            'type': 'simple',
            'sku': sku,
            'slug': product_slug,  # Custom slug for product URL
            'manage_stock': False,
            'in_stock': True,
            'status': 'publish',
            'catalog_visibility': 'visible',
            'featured': False,
            'virtual': False,
            'downloadable': False,
            'categories': [],
            'meta_data': []
        }
        
        # Form product description with technical specifications
        description = ""
        
        # Add title
        description += f"<h3>{full_name}</h3>\n"
        
        # Add description if available
        if 'Description' in row and pd.notna(row['Description']):
            product_desc = str(row['Description']).strip()
            description += f"<div class='product-description'><p>{product_desc}</p></div>\n"
        
        # Add marketing text to products if enabled
        if use_marketing_text:
            marketing_text = "You can buy industrial equipment at the lowest prices from us! Sale of machine tools, production lines, and special equipment with a quality guarantee. Fast worldwide delivery, assistance in selection and installation. Equipment for manufacturing, automation, and metalworking is available and customized. We reduce the costs of your business: reliable solutions without overpayments. Order now and get a discount on the commissioning!"
            description += f"<div class='marketing-text'><p>-</p><p>{marketing_text}</p></div>\n"
        
        # Add technical specifications if available
        if 'Technical Specs' in row and pd.notna(row['Technical Specs']):
            specifications = str(row['Technical Specs']).strip()
            if specifications:
                description += "<h4>Технические характеристики:</h4>\n"
                
                # Use the characteristics parser from csv_adapter
                try:
                    from csv_adapter import parse_characteristics
                    specifications_html = parse_characteristics(specifications)
                    if specifications_html:
                        description += specifications_html
                except ImportError:
                    # If parse_characteristics is not available, use simple formatting
                    description += self._simple_characteristics_format(specifications)
        
        # Add basic information
        description += "\n<div class='product-info'>\n"
        if brand:
            description += f"<p><strong>Brand:</strong> {brand}</p>\n"
        if sku:
            description += f"<p><strong>SKU:</strong> {sku}</p>\n"
        description += "</div>\n"
        
        # Set product description
        product_data['description'] = description
        
        # Short description (for product lists)
        short_desc = str(row.get('Description', ''))[:150].strip() if pd.notna(row.get('Description', '')) else f"{brand} {name}"[:150]
        product_data['short_description'] = short_desc
        
        # Add price only if it's greater than 0
        if regular_price:
            product_data['regular_price'] = regular_price
        
        # Add category
        if category:
            category_id = self.get_or_create_category(category)
            if category_id:
                product_data['categories'] = [{'id': category_id}]
                
        # --- Reworked Brand Logic ---
        if brand and self.brand_endpoint and self.brand_assignment_slug:
            brand_term_id = self._get_or_create_brand_term_id(brand)
            if brand_term_id:
                # Use the confirmed slug for assignment
                product_data[self.brand_assignment_slug] = [brand_term_id]
                # Дополнительно добавляем поле 'brands' для совместимости с плагином WooCommerce Brands
                # Используем формат объекта для brands
                product_data.setdefault('brands', [{'id': brand_term_id}])
                self.log(f"🏷️ Бренду '{brand}' присвоен ID {brand_term_id} через таксономию '{self.brand_assignment_slug}'")
                
        # FIFU image logic is now handled by a separate endpoint call after product creation/update.
            
        return product_data
        
    def _simple_characteristics_format(self, characteristics_str):
        """
        Simple formatting of characteristics into HTML table
        
        Args:
            characteristics_str: String with characteristics
            
        Returns:
            str: HTML table with characteristics
        """
        if not characteristics_str:
            return ""
            
        lines = characteristics_str.split('|')
        
        if not lines:
            return ""
            
        html = '<table class="product-specs" style="width:100%; border-collapse:collapse; margin-bottom:20px;">\n'
        html += '<tbody>\n'
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Process section headers
            if line.startswith('---') and line.endswith('---'):
                section_title = line.replace('---', '').strip()
                html += f'<tr><th colspan="2" style="background-color:#f5f5f5; padding:10px; text-align:left;">{section_title}</th></tr>\n'
                continue
                
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                
                if key and value:
                    html += f'<tr>\n'
                    html += f'  <td style="border:1px solid #ddd; padding:8px; font-weight:bold; width:40%;">{key}</td>\n'
                    html += f'  <td style="border:1px solid #ddd; padding:8px;">{value}</td>\n'
                    html += f'</tr>\n'
        
        html += '</tbody>\n'
        html += '</table>\n'
        
        return html
        
    def get_or_create_category(self, category_name):
        """
        Получить ID категории или создать новую с кэшированием
        
        Args:
            category_name: Название категории
            
        Returns:
            int: ID категории или None
        """
        if not category_name:
            return None

        # Проверяем кэш
        cache_key = category_name.strip().lower()
        if cache_key in self.category_cache:
            return self.category_cache[cache_key]

        # Используем блокировку для избежания дублирования создания категорий
        with self.category_creation_lock:
            # Повторно проверяем кэш после получения блокировки
            if cache_key in self.category_cache:
                return self.category_cache[cache_key]

            try:
                # Поиск существующей категории
                response = self.wcapi.get("products/categories", params={'search': category_name})
                
                if response.status_code == 200:
                    categories = response.json()
                    for category in categories:
                        if category['name'].lower() == category_name.lower():
                            category_id = category['id']
                            self.category_cache[cache_key] = category_id
                            return category_id
                
                # Создание новой категории
                category_data = {
                    'name': category_name,
                    'slug': category_name.lower().replace(' ', '-').replace('/', '-')
                }
                
                response = self.wcapi.post("products/categories", category_data)
                
                if response.status_code == 201:
                    category = response.json()
                    category_id = category['id']
                    self.log(f"✅ Создана категория: {category_name} (ID: {category_id})")
                    self.category_cache[cache_key] = category_id
                    return category_id
                else:
                    self.log(f"❌ Ошибка создания категории {category_name}: {response.status_code}")
                    return None
                
            except Exception as e:
                self.log(f"❌ Ошибка при создании/получении категории: {str(e)}")
                return None

    def _find_brand_endpoint(self):
        self.log("🔎 Поиск конечной точки (endpoint) и слага для брендов...")
        
        try:
            # Get all taxonomies for 'product' post type
            if self.wp_basic_auth_client:
                response = self.wp_basic_auth_client.get(f"{self.url}/wp-json/wp/v2/taxonomies", params={'type': 'product'})
            else:
                response = self.wp_api_v2.get('taxonomies', params={'type': 'product'})
                
            if not response.ok:
                self.log(f"⚠️ Не удалось получить список таксономий: {response.status_code}. Используем резервный метод.")
                return self._fallback_brand_search()

            taxonomies = response.json()
            
            # Keywords to identify a brand taxonomy
            brand_keywords = ['brand', 'brands', 'pwb', 'yith']
            
            for slug, tax_data in taxonomies.items():
                tax_name = tax_data.get('name', '').lower()
                tax_slug = tax_data.get('slug', '').lower()
                
                if any(keyword in tax_name for keyword in brand_keywords) or \
                   any(keyword in tax_slug for keyword in brand_keywords):
                    
                    rest_base = tax_data.get('rest_base')
                    if not rest_base:
                        continue # Skip if no rest_base

                    self.log(f"✅ Найдена таксономия бренда: '{tax_data.get('name')}' (слаг для API: '{rest_base}')")
                    self.brand_api_client = self.wp_api_v2
                    self.brand_assignment_slug = rest_base # This is the key for product creation
                    self.brand_endpoint = rest_base      # This is the endpoint for managing terms
                    return rest_base

        except Exception as e:
            self.log(f"❌ Исключение при поиске таксономии: {e}. Используем резервный метод.")
        
        # Fallback if the above fails
        return self._fallback_brand_search()

    def _fallback_brand_search(self):
        self.log("...используем резервный метод поиска эндпоинта")

        # 1. Prioritize WooCommerce API endpoints (wc/v3)
        self.log("...проверяем эндпоинты в WooCommerce API (wc/v3)")
        wc_endpoints = ['products/brands', 'brands']
        for endpoint in wc_endpoints:
            try:
                response = self.wcapi.get(endpoint, params={'per_page': 1})
                if response.ok:
                    self.log(f"✅ Найден эндпоинт для брендов в WC API: '{endpoint}'")
                    self.brand_api_client = self.wcapi
                    return endpoint
            except Exception:
                continue

        # 2. Fallback to standard WordPress taxonomy endpoints (wp/v2)
        self.log("...проверяем стандартные таксономии WordPress (wp/v2)")
        wp_taxonomies = ['product_brand', 'pwb-brand', 'yith_product_brand']
        for tax in wp_taxonomies:
            try:
                if self.wp_basic_auth_client:
                    response = self.wp_basic_auth_client.get(f"{self.url}/wp-json/wp/v2/{tax}", params={'per_page': 1})
                else:
                    response = self.wp_api_v2.get(tax, params={'per_page': 1})
                if response.ok:
                    self.log(f"✅ Найдена таксономия брендов в WP API: '{tax}'")
                    self.brand_api_client = self.wp_api_v2 # Switch the client
                    return tax
            except Exception:
                continue
        
        # 3. Final fallback if nothing is found
        self.log("⚠️ Не удалось автоматически определить эндпоинт. Используем 'product_brand' с WP API v2 как запасной вариант.")
        self.brand_api_client = self.wp_api_v2
        return 'product_brand'

    def _get_or_create_brand_term_id(self, brand_name):
        if not self.brand_endpoint:
            return None
            
        cache_key = brand_name.strip().lower()
        if cache_key in self.brand_term_cache:
            return self.brand_term_cache[cache_key]
            
        # Используем блокировку для избежания дублирования создания брендов
        with self.brand_creation_lock:
            # Повторно проверяем кэш после получения блокировки
            if cache_key in self.brand_term_cache:
                return self.brand_term_cache[cache_key]
                
            try:
                # Search for existing brand term using the discovered client and endpoint
                search_params = {'search': brand_name, 'per_page': 10}
                
                # Используем правильный клиент в зависимости от типа эндпоинта
                if self.brand_api_client == self.wp_api_v2:
                    # Для WordPress API используем Basic Auth
                    if self.wp_basic_auth_client:
                        response = self.wp_basic_auth_client.get(
                            f"{self.url}/wp-json/wp/v2/{self.brand_endpoint}",
                            params=search_params,
                            timeout=30
                        )
                    else:
                        self.log(f"❌ Не настроен Basic Auth клиент для WordPress операций")
                        return None
                else:
                    # Для WooCommerce API используем стандартный клиент
                    response = self.brand_api_client.get(self.brand_endpoint, params=search_params)
                
                if not response.ok:
                    self.log(f"⚠️ Ошибка поиска бренда '{brand_name}': {response.status_code} - {response.text}")
                    return None
                    
                terms = response.json()
                for term in terms:
                    if term['name'].lower() == brand_name.lower():
                        term_id = term['id']
                        self.log(f"🔍 Бренд '{brand_name}' найден, ID: {term_id}")
                        self.brand_term_cache[cache_key] = term_id
                        return term_id
                    
                self.log(f"✨ Бренд '{brand_name}' не найден, создаем новый...")
                create_data = {'name': brand_name}
                
                # Используем правильный клиент для создания
                if self.brand_api_client == self.wp_api_v2:
                    # Для WordPress API используем Basic Auth
                    if self.wp_basic_auth_client:
                        response = self.wp_basic_auth_client.post(
                            f"{self.url}/wp-json/wp/v2/{self.brand_endpoint}",
                            json=create_data,
                            timeout=30
                        )
                    else:
                        self.log(f"❌ Не настроен Basic Auth клиент для WordPress операций")
                        return None
                else:
                    # Для WooCommerce API используем стандартный клиент
                    response = self.brand_api_client.post(self.brand_endpoint, data=create_data)
                
                if response.ok:
                    new_term = response.json()
                    term_id = new_term['id']
                    self.log(f"✅ Бренд '{brand_name}' создан, ID: {term_id}")
                    self.brand_term_cache[cache_key] = term_id
                    return term_id
                else:
                    # Если бренд уже существует (ошибка 400 term_exists), попробуем найти его
                    if response.status_code == 400 and "term_exists" in response.text:
                        try:
                            error_data = response.json()
                            if 'additional_data' in error_data and error_data['additional_data']:
                                term_id = error_data['additional_data'][0]  # Первый ID из списка
                                self.log(f"🔍 Бренд '{brand_name}' уже существует, ID: {term_id}")
                                self.brand_term_cache[cache_key] = term_id
                                return term_id
                        except:
                            pass
                    
                    self.log(f"❌ Не удалось создать бренд '{brand_name}': {response.status_code} {response.text}")
                    return None

            except Exception as e:
                self.log(f"❌ Исключение при работе с брендом '{brand_name}': {str(e)}")
                return None
            
    def load_all_existing_products(self, brand_filters=None):
        """
        Загрузка всех существующих товаров с сайта для кэширования.
        
        Returns:
            bool: True если загрузка успешна
        """
        if self.cache_loaded:
            self.log("📋 Кэш товаров уже загружен")
            return True
            
        try:
            self.log("📋 Загружаем все существующие товары в кэш...")
            self.existing_products_cache = {}
            
            # Параллельная загрузка страниц с per_page=100
            per_page = 100
            total_loaded = 0
            # Загрузка первой страницы для определения числа страниц
            response = self.wcapi.get("products", params={
                "page": 1,
                "per_page": per_page,
                "status": "any",
                "_fields": "id,sku,attributes"
            })
            if response.status_code != 200:
                self.log(f"❌ Ошибка получения товаров: {response.status_code}")
                return False
            first_products = response.json()
            total_pages = int(response.headers.get('X-WP-TotalPages', 1))
            self.log(f"✅ Загрузка страницы 1/{total_pages} завершена ({len(first_products)} товаров)")
            # Собираем все страницы
            pages = {1: first_products}
            errors_occurred = False
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {
                    executor.submit(
                        lambda pg: (pg, self.wcapi.get("products", params={
                            "page": pg,
                            "per_page": per_page,
                            "status": "any",
                            "_fields": "id,sku,attributes"
                        }).json()),
                        page_num
                    ): page_num
                    for page_num in range(2, total_pages + 1)
                }
                for future in as_completed(futures):
                    pg = futures[future]
                    try:
                        _, products = future.result()
                        pages[pg] = products
                        self.log(f"✅ Загрузка страницы {pg}/{total_pages} завершена ({len(products)} товаров)")
                    except Exception as e:
                        self.log(f"❌ Ошибка загрузки страницы {pg}: {e}")
                        errors_occurred = True
            
            if errors_occurred:
                self.log("❌ Обнаружены ошибки при постраничной загрузке товаров. Кэш может быть неполным.")
                return False

            # Фильтрация и заполнение кэша
            for products in pages.values():
                for product in products:
                    sku = product.get('sku', '').strip().lower()
                    if not sku:
                        continue
                    if brand_filters:
                        product_brand = None
                        for attr in product.get('attributes', []):
                            if attr.get('name', '').lower() == 'brand' and attr.get('options'):
                                product_brand = str(attr['options'][0]).strip().lower()
                                break
                        if product_brand is None or product_brand not in brand_filters:
                            continue
                    self.existing_products_cache[sku] = product
                    total_loaded += 1
            
            self.cache_loaded = True
            self.log(f"✅ Кэш загружен: {total_loaded} товаров")
            return True
            
        except Exception as e:
            self.log(f"❌ Ошибка загрузки кэша товаров: {str(e)}")
            return False

    def find_existing_product_by_sku(self, sku, use_cache=False):
        """
        Проверяет наличие товара с данным SKU
        
        Args:
            sku: Артикул товара
            use_cache: Использовать кэш для поиска
            
        Returns:
            dict: Данные товара или None
        """
        if not sku:
            return None
            
        if use_cache and self.cache_loaded:
            # Поиск в кэше
            return self.existing_products_cache.get(sku.strip().lower())
        
        # Поиск через API
        try:
            resp = self.wcapi.get("products", params={"sku": sku})
            if resp.status_code == 200:
                products = resp.json()
                if products:
                    return products[0]
        except Exception:
            pass
        return None
        
    def get_product_detailed_info(self, product_id=None, sku=None):
        """
        Получить полную информацию о товаре по ID или SKU
        
        Args:
            product_id: ID товара
            sku: Артикул товара (используется, если не указан ID)
            
        Returns:
            dict: Полная информация о товаре или None
        """
        try:
            if not product_id and not sku:
                self.log("❌ Необходимо указать ID или SKU товара")
                return None
                
            # Если передан SKU, сначала найдем ID
            if not product_id and sku:
                existing = self.find_existing_product_by_sku(sku)
                if existing:
                    product_id = existing['id']
                else:
                    self.log(f"❌ Товар с артикулом {sku} не найден")
                    return None
            
            # Получаем полную информацию о товаре по ID
            response = self.wcapi.get(f"products/{product_id}")
            
            if response.status_code == 200:
                product = response.json()
                
                # Получаем URL внешнего изображения из мета-данных
                external_image_url = None
                for meta in product.get('meta_data', []):
                    if meta.get('key') == '_external_image_url': # Изменено с 'fifu_image_url'
                        external_image_url = meta.get('value')
                        break
                        
                # Добавим информацию о внешнем изображении в основной объект
                product['external_image_url'] = external_image_url # Изменено с 'fifu_image_url'
                
                return product
            else:
                self.log(f"❌ Ошибка получения информации о товаре: {response.status_code}")
                return None
                
        except Exception as e:
            self.log(f"❌ Ошибка при получении информации о товаре: {str(e)}")
            return None
        
    def upload_products(self, csv_file, images_folder, max_count=None, selected_fields=None, 
                        skip_existing=True, update_mode='all', use_marketing_text=True,
                        use_placeholder=False, placeholder_image=None):
        """
        Upload products from CSV file
        
        Args:
            csv_file: Path to CSV file
            images_folder: Folder with images
            max_count: Maximum number of products (None for all)
            selected_fields: List of selected fields
            skip_existing: Skip existing products (default: True)
            update_mode: Update mode ('all', 'images', 'description', 'missing')
            use_marketing_text: Add marketing text to product descriptions (default: True)
            use_placeholder: Use placeholder image for products without images
            placeholder_image: Path to placeholder image file
            
        Returns:
            dict: Upload result
        """
        try:
            self.log("📊 Reading CSV file...")
            
            # Log marketing text setting
            if use_marketing_text:
                self.log("✅ Добавление маркетингового текста в описание включено")
            else:
                self.log("ℹ️ Добавление маркетингового текста в описание отключено")
                
            # Configure placeholder image if enabled
            if use_placeholder and placeholder_image:
                self.log("🖼️ Настройка заглушки для товаров без изображений...")
                if not self.set_placeholder_image(placeholder_image, use_placeholder=True):
                    self.log("⚠️ Заглушка не будет использована из-за ошибки")
            else:
                # Disable placeholder if not requested
                self.set_placeholder_image(None, use_placeholder=False)
            
            # Connect to SFTP server
            if not self.sftp_uploader.connect():
                self.log("❌ Failed to connect to SFTP server, upload impossible")
                return {
                    'success': False,
                    'uploaded': 0,
                    'errors': 0,
                    'total': 0,
                    'message': 'SFTP connection error'
                }
            
            # Read CSV with encoding settings
            encodings = [CSV_CONFIG.get('encoding', 'utf-8'), CSV_CONFIG.get('fallback_encoding', 'cp1251'), 'windows-1251', 'iso-8859-1']
            df = None
            for enc in encodings:
                try:
                    df = pd.read_csv(csv_file, encoding=enc)
                    break
                except UnicodeDecodeError:
                    continue
            if df is None:
                raise ValueError("Could not read CSV with specified encodings")

            # Keep only selected columns (if specified)
            if selected_fields is not None:
                cols_to_keep = [c for c in df.columns if c in selected_fields]
                if not cols_to_keep:
                    raise ValueError("None of the selected columns found in CSV")
                df = df[cols_to_keep]

            # Adapt DataFrame to standard columns
            adapted_df, mapping = self.csv_adapter.adapt_dataframe(df)
            if adapted_df is None:
                self.log("Failed to adapt CSV – missing required-fields")
                self.sftp_uploader.disconnect()
                return {
                    'success': False,
                    'uploaded': 0,
                    'errors': 1,
                    'total': 0,
                    'message': 'CSV adaptation error',
                }

            df = adapted_df
            
            # Limit number of products
            total_products = len(df)
            self.log(f"📦 Found {total_products} products in file")
            
            if max_count and max_count < total_products:
                df = df.head(max_count)
                self.log(f"🔢 Limited to {max_count} products")
            
            # Используем пакетную обработку для обоих режимов
            self.log("📦 Переходим к пакетной обработке товаров...")
            
            return self.batch_process_products(
                df,
                images_folder,
                skip_existing=skip_existing,
                update_mode=update_mode,
                batch_size=100,
                use_marketing_text=use_marketing_text
            )
            
        except Exception as e:
            self.log(f"❌ Critical error: {str(e)}")
            # Disconnect from SFTP
            if hasattr(self, 'sftp_uploader'):
                self.sftp_uploader.disconnect()
                
            return {
                'success': False,
                'uploaded': 0,
                'errors': 1,
                'total': 0,
                'message': str(e)
            }
            
    def clean_sku_for_image(self, sku):
        """
        Очистка SKU для поиска изображения
        
        Args:
            sku: Исходный SKU
            
        Returns:
            str: Очищенный SKU для поиска изображения
        """
        if not sku:
            return ""
            
        # Очищаем SKU от специальных символов
        clean_sku = str(sku).strip()
        
        # Удаляем все символы, кроме букв, цифр и дефисов
        clean_sku = re.sub(r'[^a-zA-Z0-9\-]', '', clean_sku)
        
        return clean_sku
        
    def find_product_image(self, sku, images_folder):
        """
        Поиск изображения товара по SKU
        
        Args:
            sku: SKU товара (очищенный)
            images_folder: Папка с изображениями
            
        Returns:
            str: Путь к изображению или None, если не найдено
        """
        if not sku or not images_folder:
            return None
            
        # Проверяем существование папки
        if not os.path.isdir(images_folder):
            self.log(f"❌ Папка с изображениями не найдена: {images_folder}")
            return None
            
        # Ищем изображение по точному совпадению SKU
        extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
        
        for ext in extensions:
            image_path = os.path.join(images_folder, f"{sku}{ext}")
            if os.path.exists(image_path):
                return image_path
                
        # Если не нашли по точному совпадению, ищем по началу имени файла
        for filename in os.listdir(images_folder):
            file_path = os.path.join(images_folder, filename)
            if os.path.isfile(file_path) and filename.lower().startswith(sku.lower()):
                _, ext = os.path.splitext(filename)
                if ext.lower() in extensions:
                    return file_path
                    
        return None

    def batch_process_products(self, df, images_folder, skip_existing=True, update_mode='all', batch_size=100, use_marketing_text=True):
        """
        Разделяет DataFrame на пакеты и обрабатывает их последовательно
        """
        total_products = len(df)
        processed_count = 0
        new_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        self.log(f"📦 Начинаем пакетную обработку {total_products} товаров")
        self.log(f"📏 Размер пакета: {batch_size}")
        
        # Ensure cache is loaded only for 'skip' mode
        if skip_existing:
            if not self.cache_loaded:
                brand_filters = None
                if 'Brand' in df.columns:
                    brand_filters = set(df['Brand'].dropna().str.strip().str.lower())
                if brand_filters:
                    self.log(f"🔄 Загружаем кэш товаров для брендов: {', '.join(sorted(brand_filters))}")
                else:
                    self.log("🔄 Загружаем кэш товаров (все бренды)")
                
                cache_load_success = self.load_all_existing_products(brand_filters=brand_filters)
                
                # If cache fails in skip mode, it's a fatal error
                if not cache_load_success:
                    self.log("❌ Не удалось загрузить кэш существующих товаров. Пропуск дубликатов невозможен. Прерывание.")
                    self.sftp_uploader.disconnect()
                    return {
                        'success': False,
                        'uploaded': 0,
                        'errors': 1,
                        'total': total_products,
                        'message': 'Ошибка загрузки кэша товаров для режима пропуска дубликатов.'
                    }
        else:  # This is update mode
            self.log("ℹ️ Режим обновления: кэширование отключено. Товары будут созданы или обновлены по результатам ответа API.")
            self.existing_products_cache.clear()  # Ensure cache is empty
            self.cache_loaded = True  # Prevent accidental reloading
        
        # Разбиваем DataFrame на пакеты
        for batch_start in range(0, total_products, batch_size):
            if self.stop_requested:
                self.log("⛔ Обработка остановлена пользователем")
                break
                
            batch_end = min(batch_start + batch_size, total_products)
            batch_df = df.iloc[batch_start:batch_end]
            
            self.log(f"\n📦 Обработка пакета {batch_start + 1}-{batch_end} из {total_products}")
            
            try:
                # Обрабатываем пакет
                batch_result = self.process_batch(
                    batch_df, 
                    images_folder, 
                    skip_existing=skip_existing,
                    update_mode=update_mode,
                    use_marketing_text=use_marketing_text
                )
                
                # Обновляем статистику
                processed_count += batch_result['processed']
                new_count += batch_result['new']
                updated_count += batch_result['updated'] 
                skipped_count += batch_result['skipped']
                error_count += batch_result['errors']
                
                self.log(f"✅ Пакет обработан: +{batch_result['processed']} товаров")
                
            except Exception as e:
                self.log(f"❌ Ошибка обработки пакета: {str(e)}")
                error_count += len(batch_df)
                
            # Обновляем прогресс
            if self.progress_callback:
                self.progress_callback(batch_end, total_products, f"Обработано: {processed_count}")
                
            # Пауза между пакетами
            if batch_end < total_products:
                self.log("⏳ Пауза между пакетами...")
                time.sleep(2.0)
        
        # Итоговая статистика
        self.log(f"\n{'='*50}")
        self.log(f"📊 ИТОГИ ПАКЕТНОЙ ОБРАБОТКИ:")
        self.log(f"   📦 Всего товаров: {total_products}")
        self.log(f"   ✅ Обработано: {processed_count}")
        self.log(f"   🆕 Новых: {new_count}")
        self.log(f"   🔄 Обновлено: {updated_count}")
        self.log(f"   ⏭️ Пропущено: {skipped_count}")
        self.log(f"   ❌ Ошибок: {error_count}")
        self.log(f"{'='*50}")
        
        return {
            'success': error_count == 0,
            'uploaded': processed_count,
            'new': new_count,
            'updated': updated_count,
            'skipped': skipped_count,
            'errors': error_count,
            'total': total_products,
            'message': f'Обработано {processed_count} из {total_products} товаров'
        }

    def _upload_image_task(self, sku, clean_sku, images_folder):
        """
        Worker task to upload a single image. Creates its own SFTP connection to be thread-safe.
        """
        image_path = self.find_product_image(clean_sku, images_folder)
        
        # Если изображение не найдено и включена заглушка, используем ее URL
        if not image_path and self.use_placeholder and self.placeholder_image_url:
            self.log(f"🖼️ Для товара {sku} не найдено изображение, используем заглушку")
            return sku, self.placeholder_image_url
            
        # Если изображение не найдено и заглушка не включена или не загружена
        if not image_path:
            return sku, None

        thread_uploader = None
        try:
            # Create a thread-local SFTP uploader
            thread_uploader = SFTPImageUploader(**self.ssh_config)
            thread_uploader.set_log_callback(self.log) # The logger is thread-safe as it uses a queue

            image_url = None
            if thread_uploader.connect():
                original_filename = os.path.basename(image_path)
                clean_filename = thread_uploader.clean_filename(original_filename)
                
                image_url = thread_uploader.upload_file(
                    image_path, 
                    'products', 
                    rename_to=clean_filename
                )

            return sku, image_url
        except Exception as e:
            self.log(f"❌ Error during image upload for SKU {sku} in worker thread: {str(e)}")
            return sku, None
        finally:
            if thread_uploader and thread_uploader.connected:
                thread_uploader.disconnect()

    def _prepare_product_data_task(self, row, images_urls, use_marketing_text=True):
        """Worker task to prepare a single product's data."""
        try:
            sku = str(row.get('SKU', '')).strip()
            if not sku:
                # Returning a tuple with status, so we can filter it later.
                return 'error', "Строка без SKU."
                
            image_url = images_urls.get(sku)
            product_data = self.create_product_data(row, image_url, use_marketing_text)
            return 'success', product_data
        except Exception as e:
            sku_val = row.get('SKU', 'N/A')
            error_message = f"Ошибка подготовки товара {sku_val}: {str(e)}"
            # The error is logged here to provide immediate feedback in the console
            self.log(f"❌ {error_message}")
            # The error is returned to be counted in the final statistics
            return 'error', error_message

    def process_batch(self, batch_df, images_folder, skip_existing=True, update_mode='all', use_marketing_text=True):
        """
        Обработка одного пакета товаров.
        Логика разделена для режимов "пропуск" и "обновление".
        """
        # --- Параллельная загрузка изображений ---
        images_urls = {}
        self.log("🖼️ Параллельная загрузка изображений для пакета...")

        tasks = []
        unique_skus = set()
        for _, row in batch_df.iterrows():
            sku = str(row.get('SKU', '')).strip()
            if sku and sku not in unique_skus:
                unique_skus.add(sku)
                clean_sku = self.clean_sku_for_image(sku)
                tasks.append((sku, clean_sku))

        if tasks:
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_sku = {executor.submit(self._upload_image_task, sku, clean_sku, images_folder): sku for sku, clean_sku in tasks}
                for future in as_completed(future_to_sku):
                    try:
                        sku_result, image_url = future.result()
                        if image_url:
                            images_urls[sku_result] = image_url
                            self.log(f"✅ URL изображения для {sku_result} получен после загрузки.")
                    except Exception as exc:
                        sku_task = future_to_sku[future]
                        self.log(f"❌ Worker для SKU {sku_task} сгенерировал исключение: {exc}")

        self.log("✅ Параллельная загрузка изображений для пакета завершена.")

        # --- Разделение логики по режимам ---
        
        # РЕЖИМ: ПРОПУСК СУЩЕСТВУЮЩИХ (использует кэш)
        if skip_existing:
            self.log("🔍 Анализ пакета в режиме 'Пропуск'...")
            
            rows_to_process = []
            skipped_count = 0
            error_count = 0
            
            # Предварительная фильтрация товаров, которые уже существуют
            for _, row in batch_df.iterrows():
                try:
                    sku = str(row['SKU']).strip()
                    if not sku:
                        self.log("⚠️ Пропущена строка без SKU.")
                        error_count += 1
                        continue

                    if self.existing_products_cache.get(sku.lower()):
                        self.log(f"⏭️ Пропускаем: {sku} (уже существует в кэше)")
                        skipped_count += 1
                        continue
                    
                    rows_to_process.append(row)
                except KeyError:
                    self.log("❌ В CSV файле отсутствует обязательная колонка 'SKU'.")
                    error_count += 1

            self.log(f"⚙️ {len(rows_to_process)} товаров будут подготовлены к созданию (асинхронно)...")
            products_to_create = []

            # Асинхронная подготовка данных
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_row = {executor.submit(self._prepare_product_data_task, row, images_urls, use_marketing_text): row for row in rows_to_process}
                for future in as_completed(future_to_row):
                    try:
                        status, data = future.result()
                        if status == 'success':
                            products_to_create.append(data)
                        else:
                            error_count += 1
                    except Exception as exc:
                        row = future_to_row[future]
                        sku = row.get('SKU', 'N/A')
                        self.log(f"❌ Worker для SKU {sku} сгенерировал исключение при подготовке данных: {exc}")
                        error_count += 1
            
            self.log(f"✅ Асинхронная подготовка завершена. {len(products_to_create)} товаров готово к созданию.")
            
            newly_created_products = self.batch_create_products(products_to_create)
            new_count = len(newly_created_products)
            
            # After creation, set external images via the custom endpoint
            if newly_created_products:
                self._set_external_images_in_parallel(newly_created_products, images_urls)
            
            return {
                'processed': new_count,
                'new': new_count,
                'updated': 0,
                'skipped': skipped_count,
                'errors': error_count + (len(products_to_create) - len(newly_created_products))
            }

        # РЕЖИМ: ОБНОВЛЕНИЕ СУЩЕСТВУЮЩИХ
        else:
            self.log("🔍 Асинхронная подготовка данных для пакета в режиме 'Обновление'...")
            products_to_process = []
            initial_error_count = 0

            # 1. Асинхронная подготовка данных для всех товаров в пакете
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_row = {executor.submit(self._prepare_product_data_task, row, images_urls, use_marketing_text): row for _, row in batch_df.iterrows()}
                for future in as_completed(future_to_row):
                    try:
                        status, data = future.result()
                        if status == 'success':
                            products_to_process.append(data)
                        else:
                            initial_error_count += 1
                    except Exception as exc:
                        row = future_to_row[future]
                        sku = row.get('SKU', 'N/A')
                        self.log(f"❌ Worker для SKU {sku} сгенерировал исключение: {exc}")
                        initial_error_count += 1
            
            self.log("✅ Асинхронная подготовка данных завершена.")
            
            if not products_to_process:
                self.log("ℹ️ В пакете нет товаров для обработки.")
                return {'processed': 0, 'new': 0, 'updated': 0, 'skipped': 0, 'errors': initial_error_count}

            # 2. Попытка создать все товары, с разделением на "новые" и "к обновлению"
            self.log(f"📤 Попытка пакетного создания/обновления {len(products_to_process)} товаров...")
            
            newly_created_products = []
            products_to_update_data = []
            api_errors_count = 0
            
            # Обработка пакетами по 25
            chunk_size = 25
            for i in range(0, len(products_to_process), chunk_size):
                chunk_to_create = products_to_process[i:i + chunk_size]
                
                try:
                    response = self.wcapi.post("products/batch", {'create': chunk_to_create})
                    
                    if response.ok:
                        results = response.json().get('create', [])
                        for original_data, result in zip(chunk_to_create, results):
                            if 'id' in result and result.get('id'):
                                newly_created_products.append(result)
                            elif 'error' in result:
                                error_code = result['error'].get('code', '')
                                error_msg = result['error'].get('message', '')
                                
                                # The error message "already present in the lookup table" indicates a duplicate.
                                # The standard WooCommerce error code is 'woocommerce_rest_product_sku_already_exists'.
                                # We check for both to be safe.
                                if error_code in ('woocommerce_rest_product_sku_already_exists', 'product_invalid_sku') or 'already present in the lookup table' in error_msg or 'Product SKU already exists' in error_msg:
                                    # This product exists, add it to the list to be updated.
                                    products_to_update_data.append(original_data)
                                else:
                                    # This is a different, unexpected error.
                                    sku = original_data.get('sku', 'N/A')
                                    self.log(f"❌ Ошибка API при создании товара {sku}: {error_msg} (Code: {error_code})")
                                    api_errors_count += 1
                            else:
                                sku = original_data.get('sku', 'N/A')
                                self.log(f"❌ Неизвестный ответ от API для товара {sku}")
                                api_errors_count += 1
                    else:
                        self.log(f"❌ HTTP ошибка при создании пакета: {response.status_code} - {response.text[:200]}...")
                        api_errors_count += len(chunk_to_create)
                
                except requests.exceptions.ReadTimeout:
                    self.log(f"    - ❌ Тайм-аут при создании пакета. Сервер не ответил в течение {self.wcapi.timeout}с.")
                    api_errors_count += len(chunk_to_create)
                except Exception as e:
                    self.log(f"❌ Исключение при создании пакета: {str(e)}")
                    api_errors_count += len(chunk_to_create)

            # 3. Устанавливаем изображения для только что созданных товаров
            if newly_created_products:
                self.log(f"✨ Создано {len(newly_created_products)} новых товаров.")
                self._set_external_images_in_parallel(newly_created_products, images_urls)
            
            # 4. Обновление товаров, которые уже существуют
            updated_products = []
            if products_to_update_data:
                self.log(f"🔄 {len(products_to_update_data)} товаров уже существуют. Получаем ID и обновляем...")
                
                products_for_batch_update = []
                # Получаем ID для товаров, которые нужно обновить
                with ThreadPoolExecutor(max_workers=5) as executor:
                    future_to_sku = {executor.submit(self.find_existing_product_by_sku, p['sku']): p for p in products_to_update_data}
                    for future in as_completed(future_to_sku):
                        original_data = future_to_sku[future]
                        try:
                            existing_product = future.result()
                            if existing_product and 'id' in existing_product:
                                # Добавляем ID в данные для обновления
                                update_data = original_data
                                update_data['id'] = existing_product['id']
                                products_for_batch_update.append(update_data)
                            else:
                                self.log(f"👻 Обнаружен 'призрачный' SKU: {original_data['sku']}. Товар не найден для обновления, но его создание блокируется. Рекомендуется очистить таблицы поиска товаров в WooCommerce (WooCommerce > Status > Tools).")
                                api_errors_count += 1
                        except Exception as e:
                            self.log(f"❌ Ошибка получения ID для SKU {original_data['sku']}: {e}")
                            api_errors_count += 1
                
                if products_for_batch_update:
                    self.log(f"📤 Отправка {len(products_for_batch_update)} товаров на пакетное обновление...")
                    updated_products = self.batch_update_products(products_for_batch_update)
                    if updated_products:
                        self._set_external_images_in_parallel(updated_products, images_urls)

            # 5. Финальный подсчет
            newly_created_count = len(newly_created_products)
            updated_count = len(updated_products)
            total_processed = newly_created_count + updated_count
            total_errors = initial_error_count + api_errors_count + (len(products_to_update_data) - updated_count)

            return {
                'processed': total_processed,
                'new': newly_created_count,
                'updated': updated_count,
                'skipped': 0,
                'errors': total_errors
            }
        
    def batch_create_products(self, products_data):
        """
        Пакетное создание новых товаров с разделением на под-пакеты по 25 штук
        
        Args:
            products_data: Список данных товаров для создания
            
        Returns:
            list: Список успешно созданных товаров (с ID, SKU, name)
        """
        if not products_data:
            return []

        total_to_create = len(products_data)
        successful_creations = []
        chunk_size = 25  # Обрабатываем по 25 товаров за раз, чтобы избежать тайм-аутов
        
        self.log(f"📦 Начинается пакетное создание {total_to_create} товаров (пакеты по {chunk_size})...")

        for i in range(0, total_to_create, chunk_size):
            chunk_data = products_data[i:i + chunk_size]
            current_chunk_num = (i // chunk_size) + 1
            total_chunks = (total_to_create + chunk_size - 1) // chunk_size
            
            self.log(f"  - Обработка пакета {current_chunk_num}/{total_chunks} ({len(chunk_data)} товаров)...")

            try:
                batch_data = {'create': chunk_data}
                
                response = self.wcapi.post("products/batch", batch_data)
                
                if response.status_code == 200:
                    result = response.json()
                    created_items = result.get('create', [])
                    
                    for idx, product_result in enumerate(created_items):
                        if 'id' in product_result and product_result.get('id'):
                            successful_creations.append(product_result)
                            # Log success with URL information
                            product_id = product_result.get('id')
                            product_slug = product_result.get('slug', '')
                            product_sku = product_result.get('sku', '')
                            product_url = f"{self.url}/product/{product_slug}" if product_slug else f"{self.url}/?p={product_id}"
                            self.log(f"    - ✅ Товар создан: ID={product_id}, SKU={product_sku}, URL={product_url}")
                        elif 'error' in product_result:
                            sku = chunk_data[idx].get('sku', 'Unknown SKU')
                            error_msg = product_result['error'].get('message', 'Unknown error')
                            self.log(f"    - ❌ Ошибка создания товара {sku}: {error_msg}")
                    
                    self.log(f"    - ✅ Успешно создано: {len([p for p in created_items if p.get('id')])}/{len(chunk_data)}")
                else:
                    self.log(f"    - ❌ Ошибка HTTP для пакета {current_chunk_num}: {response.status_code} - {response.text[:200]}...")

            except requests.exceptions.ReadTimeout:
                self.log(f"    - ❌ Тайм-аут при создании пакета {current_chunk_num}. Сервер не ответил в течение {self.wcapi.timeout}с.")
                self.log("    - ℹ️ Возможно, стоит уменьшить размер пакета или увеличить таймаут в `__init__`.")
            except Exception as e:
                self.log(f"    - ❌ Неизвестное исключение при создании пакета {current_chunk_num}: {str(e)}")

        self.log(f"📊 Пакетное создание завершено. Всего создано: {len(successful_creations)}/{total_to_create}")
        return successful_creations
    
    def batch_update_products(self, products_data):
        """
        Пакетное обновление существующих товаров с улучшенным логированием и обработкой ошибок.
        
        Args:
            products_data: Список данных товаров для обновления (с id)
            
        Returns:
            list: Список успешно обновленных товаров
        """
        if not products_data:
            return []

        total_to_update = len(products_data)
        successful_updates = []
        chunk_size = 25  # Обрабатываем по 25 товаров за раз, чтобы избежать тайм-аутов
        
        self.log(f"📦 Начинается пакетное обновление {total_to_update} товаров (пакеты по {chunk_size})...")

        for i in range(0, total_to_update, chunk_size):
            chunk_data = products_data[i:i + chunk_size]
            current_chunk_num = (i // chunk_size) + 1
            total_chunks = (total_to_update + chunk_size - 1) // chunk_size
            
            self.log(f"  - Обработка пакета {current_chunk_num}/{total_chunks} ({len(chunk_data)} товаров)...")

            try:
                for item in chunk_data:
                    item.pop('sku', None)
                batch_data = {'update': chunk_data}
                
                response = self.wcapi.post("products/batch", batch_data)
                
                if response.status_code == 200:
                    result = response.json()
                    updated_items = result.get('update', [])
                    
                    for product_result in updated_items:
                        if 'error' in product_result:
                            product_id = product_result.get('id', 'Unknown ID')
                            error_msg = product_result['error'].get('message', 'Unknown error')
                            self.log(f"    - ❌ Ошибка обновления товара ID {product_id}: {error_msg}")
                        else:
                            successful_updates.append(product_result)
                            # Log success with URL information
                            product_id = product_result.get('id')
                            product_slug = product_result.get('slug', '')
                            product_url = f"{self.url}/product/{product_slug}" if product_slug else f"{self.url}/?p={product_id}"
                            self.log(f"    - ✅ Товар обновлен: ID={product_id}, URL={product_url}")
                    
                    self.log(f"    - ✅ Успешно обновлено: {len([p for p in updated_items if 'error' not in p])}/{len(chunk_data)}")
                else:
                    self.log(f"    - ❌ Ошибка HTTP для пакета {current_chunk_num}: {response.status_code} - {response.text[:200]}...")

            except requests.exceptions.ReadTimeout:
                self.log(f"    - ❌ Тайм-аут при обновлении пакета {current_chunk_num}. Сервер не ответил в течение {self.wcapi.timeout}с.")
                self.log("    - ℹ️ Возможно, стоит уменьшить размер пакета или увеличить таймаут в `__init__`.")
            except Exception as e:
                self.log(f"    - ❌ Неизвестное исключение при обновлении пакета {current_chunk_num}: {str(e)}")

        self.log(f"📊 Пакетное обновление завершено. Всего обновлено: {len(successful_updates)}/{total_to_update}")
        return successful_updates

    def set_external_image(self, product_id, image_url, product_name):
        """Устанавливает внешнее изображение для товара, используя кастомный эндпоинт с Basic Auth."""
        if not image_url:
            return False, "No image URL provided."

        if not self.wp_username or not self.wp_app_password:
            error_message = f"Невозможно установить изображение для товара ID {product_id}. Не задан wp_username или wp_app_password."
            self.log(f"❌ {error_message}")
            return False, error_message
        
        # Логируем URL для диагностики
        self.log(f"🔗 Установка изображения для товара ID {product_id}: {image_url}")
        
        data = { 'image_url': image_url }
        url = f"{self.url}/wp-json/my-images/v1/set-url/{product_id}"

        try:
            # Используем requests напрямую для Basic Auth с настройками прокси
            response = requests.post(
                url,
                auth=(self.wp_username, self.wp_app_password),
                json=data,
                timeout=30,
                proxies=self._get_proxy_settings()
            )
            
            if response.status_code == 200:
                self.log(f"✅ Изображение успешно установлено для товара ID {product_id}")
                return True, "Success"
            else:
                try:
                    error_details = response.json()
                except Exception:
                    error_details = response.text
                error_message = f"Failed to set external image for product ID {product_id}. Status: {response.status_code}, Response: {str(error_details)[:200]}"
                self.log(f"❌ {error_message}")
                return False, error_message
        except Exception as e:
            error_message = f"Exception when calling custom image endpoint for product ID {product_id}: {str(e)}"
            self.log(f"❌ {error_message}")
            return False, error_message

    def _set_external_images_in_parallel(self, processed_products, images_urls):
        """
        Takes a list of successfully created/updated products from the batch response
        and sets their external images in parallel using our custom endpoint.
        """
        if not processed_products:
            return
            
        self.log(f"📸 Запуск параллельной установки {len(processed_products)} внешних изображений...")
        success_count = 0
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_product = {}
            for product in processed_products:
                product_id = product.get('id')
                sku = product.get('sku')
                name = product.get('name')
                image_url = images_urls.get(sku)

                if product_id and sku and image_url:
                    future = executor.submit(self.set_external_image, product_id, image_url, name)
                    future_to_product[future] = product_id
            
            for future in as_completed(future_to_product):
                try:
                    success, _ = future.result()
                    if success:
                        success_count += 1
                except Exception as e:
                    product_id = future_to_product[future]
                    self.log(f"❌ Исключение при установке внешнего изображения для ID {product_id}: {e}")

        self.log(f"📸 Установка внешних изображений завершена. Успешно: {success_count}/{len(processed_products)}")

    def _preload_categories_and_brands(self):
        """
        Предварительная загрузка всех категорий и брендов в кэш для избежания повторных запросов
        """
        try:
            self.log("📋 Предварительная загрузка категорий и брендов в кэш...")
            
            # Загрузка всех категорий
            try:
                response = self.wcapi.get("products/categories", params={'per_page': 100})
                if response.status_code == 200:
                    categories = response.json()
                    for category in categories:
                        cache_key = category['name'].strip().lower()
                        self.category_cache[cache_key] = category['id']
                    self.log(f"✅ Загружено {len(categories)} категорий в кэш")
                else:
                    self.log(f"⚠️ Не удалось загрузить категории: {response.status_code}")
            except Exception as e:
                self.log(f"⚠️ Ошибка загрузки категорий: {str(e)}")
            
            # Загрузка всех брендов (если эндпоинт найден)
            if self.brand_endpoint and self.brand_api_client:
                try:
                    if self.brand_api_client == self.wp_api_v2 and self.wp_basic_auth_client:
                        response = self.wp_basic_auth_client.get(
                            f"{self.url}/wp-json/wp/v2/{self.brand_endpoint}",
                            params={'per_page': 100},
                            timeout=30
                        )
                    else:
                        response = self.brand_api_client.get(self.brand_endpoint, params={'per_page': 100})
                    
                    if response.ok:
                        brands = response.json()
                        for brand in brands:
                            cache_key = brand['name'].strip().lower()
                            self.brand_term_cache[cache_key] = brand['id']
                        self.log(f"✅ Загружено {len(brands)} брендов в кэш")
                    else:
                        self.log(f"⚠️ Не удалось загрузить бренды: {response.status_code}")
                except Exception as e:
                    self.log(f"⚠️ Ошибка загрузки брендов: {str(e)}")
            
        except Exception as e:
            self.log(f"❌ Ошибка предварительной загрузки: {str(e)}")

# Пример использования
if __name__ == "__main__":
    # Настройки WooCommerce
    wc_config = {
        'wc_url': WOOCOMMERCE_CONFIG['url'],
        'wc_consumer_key': WOOCOMMERCE_CONFIG['consumer_key'],
        'wc_consumer_secret': WOOCOMMERCE_CONFIG['consumer_secret'],
        'wp_username': WOOCOMMERCE_CONFIG.get('wp_username'),
        'wp_app_password': WOOCOMMERCE_CONFIG.get('wp_app_password')
    }
    
    # Настройки SSH
    ssh_config = {
        'host': 'bf6baca11842.vps.myjino.ru',
        'port': 49181,
        'username': 'root',
        'password': 'dKX-wGM-RYw-jDH',
        'remote_base_path': '/images'
    }
    
    # Создаем апплоадер
    uploader = WooCommerceFIFUUploader(**wc_config, ssh_config=ssh_config)
    
    # Загружаем товары
    results = uploader.upload_products('products.csv', 'images')
    
    print(f"Загрузка завершена: {results['uploaded']}/{results['total']} товаров загружено")