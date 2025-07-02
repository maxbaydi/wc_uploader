import pandas as pd
import os
import requests
from woocommerce import API
import time
from PIL import Image
import base64
import mimetypes
from config import WOOCOMMERCE_CONFIG, UPLOAD_CONFIG, CSV_CONFIG


class WooCommerceUploader:
    def __init__(self, url, consumer_key, consumer_secret):
        """
        Инициализация загрузчика WooCommerce
        
        Args:
            url: URL сайта WooCommerce
            consumer_key: Ключ API
            consumer_secret: Секретный ключ API
        """
        self.url = url
        self.wcapi = API(
            url=url,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            wp_api=True,
            version="wc/v3",
            timeout=30
        )
        
        self.progress_callback = None
        self.log_callback = None
        self.stop_requested = False
        
    def set_progress_callback(self, callback):
        """Установить callback для обновления прогресса"""
        self.progress_callback = callback
        
    def set_log_callback(self, callback):
        """Установить callback для логирования"""
        self.log_callback = callback
        
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
        
    def parse_characteristics(self, characteristics_str):
        """
        Парсинг характеристик из строки и создание HTML таблицы
        
        Args:
            characteristics_str: Строка с характеристиками
            
        Returns:
            str: HTML таблица с характеристиками
        """
        if not characteristics_str or pd.isna(characteristics_str):
            return ""
            
        # Разделение на секции
        sections = characteristics_str.split('|||')
        
        html = '<div class="product-specifications">'
        
        for section in sections:
            section = section.strip()
            if not section:
                continue
                
            # Извлечение заголовка секции
            if section.startswith('---') and section.endswith('---'):
                # Это заголовок секции
                title = section.replace('---', '').strip()
                html += f'<h4 style="margin-top: 20px; margin-bottom: 10px; color: #333; border-bottom: 2px solid #0073aa; padding-bottom: 5px;">{title}</h4>'
                continue
                
            # Обработка параметров
            lines = section.split('|')
            if len(lines) > 1:
                html += '<table style="width: 100%; border-collapse: collapse; margin-bottom: 15px;">'
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                        
                    # Разделение на ключ и значение
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        if key and value:
                            html += f'''
                            <tr>
                                <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold; width: 40%;">{key}</td>
                                <td style="padding: 8px; border: 1px solid #ddd;">{value}</td>
                            </tr>
                            '''
                
                html += '</table>'
                
        html += '</div>'
        return html
        
    def upload_image(self, image_path, product_sku):
        """
        Загрузка изображения в WordPress Media Library
        
        Args:
            image_path: Путь к изображению
            product_sku: Артикул товара
            
        Returns:
            dict: Информация о загруженном изображении или None
        """
        try:
            if not os.path.exists(image_path):
                self.log(f"Изображение не найдено: {image_path}")
                return None
                
            # Проверка размера файла (максимум 10MB)
            file_size = os.path.getsize(image_path)
            if file_size > 10 * 1024 * 1024:
                self.log(f"Изображение слишком большое ({file_size} bytes): {image_path}")
                return None
                
            # Определение MIME типа
            mime_type, _ = mimetypes.guess_type(image_path)
            if not mime_type or not mime_type.startswith('image/'):
                self.log(f"Неподдерживаемый тип файла: {image_path}")
                return None
                
            # Чтение изображения
            with open(image_path, 'rb') as f:
                image_data = f.read()
                
            # Кодирование в base64
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            # Подготовка данных для загрузки
            filename = os.path.basename(image_path)
            data = {
                'title': f'Product Image - {product_sku}',
                'alt_text': f'Product {product_sku}',
                'caption': f'Product image for {product_sku}',
                'media_type': 'image',
                'mime_type': mime_type,
                'post_content': image_base64
            }
            
            # Загрузка через WordPress API
            response = self.wcapi.post("media", data)
            
            if response.status_code == 201:
                media_data = response.json()
                self.log(f"Изображение загружено: {filename} (ID: {media_data['id']})")
                return media_data
            else:
                self.log(f"Ошибка загрузки изображения: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            self.log(f"Ошибка при загрузке изображения {image_path}: {str(e)}")
            return None
            
    def get_or_create_brand(self, brand_name):
        """
        Gets or creates a brand via taxonomy and returns its ID.
        Получает или создает бренд через таксономию и возвращает его ID.
        """
        if not brand_name or pd.isna(brand_name) or str(brand_name).strip() == '':
            return None

        brand_name = str(brand_name).strip().capitalize()
        self.log(f"🔍 Processing brand: '{brand_name}'")

        try:
            # 1. Search for an existing brand
            response = self.wcapi.get("products/brands", params={"search": brand_name})
            response.raise_for_status()
            brands = response.json()

            for brand in brands:
                if brand['name'].lower() == brand_name.lower():
                    brand_id = brand['id']
                    self.log(f"✅ Found brand '{brand_name}' with ID: {brand_id}")
                    return brand_id

            # 2. Create a new brand if not found
            self.log(f"🔧 Brand '{brand_name}' not found, creating a new one...")
            data = {"name": brand_name}
            response = self.wcapi.post("products/brands", data)
            response.raise_for_status()
            new_brand = response.json()
            brand_id = new_brand['id']
            self.log(f"✅ Created brand '{brand_name}' with ID: {brand_id}")
            return brand_id

        except Exception as e:
            self.log(f"❌ Error managing brand '{brand_name}': {e}")
            if hasattr(e, 'response') and e.response.status_code == 404:
                self.log("⚠️  The 'products/brands' endpoint was not found. Please ensure a brand plugin is installed and active.")
            return None

    def find_product_image(self, sku, image_folder):
        """
        Улучшенный поиск изображения по артикулу
        
        Args:
            sku: Артикул товара
            image_folder: Папка с изображениями
            
        Returns:
            str: Путь к найденному изображению или None
        """
        if not sku or not image_folder or not os.path.exists(image_folder):
            return None
            
        # Очистка SKU от лишних символов
        sku_clean = str(sku).strip()
        
        # Убираем ".0" в конце, если есть (pandas иногда добавляет это к числам)
        if sku_clean.endswith('.0'):
            sku_clean = sku_clean[:-2]
        
        # Расширения файлов для поиска
        extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.JPG', '.JPEG', '.PNG', '.GIF', '.WEBP']
        
        # Варианты имен файлов для поиска
        search_variants = [
            sku_clean,                             # Очищенный артикул
            sku_clean.upper(),                     # В верхнем регистре
            sku_clean.lower(),                     # В нижнем регистре
            sku_clean.replace(' ', ''),            # Без пробелов
            sku_clean.replace(' ', '_'),           # Пробелы заменены на подчеркивания
            sku_clean.replace(' ', '-'),           # Пробелы заменены на дефисы
            sku_clean.replace('-', ''),            # Без дефисов
            sku_clean.replace('_', ''),            # Без подчеркиваний
            str(sku).strip(),                      # Оригинальный артикул как есть
        ]
        
        self.log(f"🔍 Searching image for SKU: {sku} (cleaned: {sku_clean})")
        
        # Перебираем все варианты названий и расширений
        for variant in search_variants:
            for ext in extensions:
                image_path = os.path.join(image_folder, f"{variant}{ext}")
                if os.path.exists(image_path):
                    self.log(f"✅ Found image: {variant}{ext}")
                    return image_path
        
        # Дополнительный поиск с подстановочными знаками
        try:
            import glob
            for variant in search_variants[:3]:  # Ограничиваем поиск основными вариантами
                pattern = os.path.join(image_folder, f"{variant}.*")
                matches = glob.glob(pattern, recursive=False)
                for match in matches:
                    file_ext = os.path.splitext(match)[1].lower()
                    if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                        self.log(f"✅ Found image via glob: {os.path.basename(match)}")
                        return match
        except Exception as e:
            self.log(f"⚠️  Glob search error: {str(e)}")
        
        self.log(f"❌ No image found for SKU: {sku}")
        return None
        
    def create_product_data(self, row, image_id=None):
        """
        Создание данных товара для WooCommerce
        
        Args:
            row: Строка данных из CSV
            image_id: ID загруженного изображения
            
        Returns:
            dict: Данные товара
        """
        # Получаем основные данные
        brand = str(row.get('Бренд', '')).strip()
        name = str(row.get('Название', '')).strip()
        sku = str(row.get('Артикул', '')).strip()
        category = str(row.get('Категория', '')).strip()
        price = str(row.get('Цена', '0')).strip()
        
        # Делаем первую букву бренда заглавной
        if brand:
            brand = brand.capitalize()
        
        # Формируем полное название товара
        full_name = f"{brand} {name}" if brand and name else (name or f"Product {sku}")
        
        # Создаем описание с характеристиками
        description = self.format_product_description(row)
        short_description = name[:100] if name else f"Product {brand}"
        
        # Обработка цены - игнорируем если 0 или пустая
        regular_price = ""
        if price and price != 'NaN' and str(price).strip() not in ['0', '0.0', '']:
            try:
                price_float = float(price)
                if price_float > 0:
                    regular_price = str(price_float)
            except (ValueError, TypeError):
                regular_price = ""
        
        # Базовые данные товара
        product_data = {
            'name': full_name,
            'type': 'simple',
            'description': description,
            'short_description': short_description,
            'sku': sku,
            'manage_stock': False,  # Не управляем складскими остатками
            'in_stock': True,       # Просто указываем что товар в наличии
            'status': 'publish',
            'catalog_visibility': 'visible',
            'featured': False,
            'virtual': False,
            'downloadable': False,
            'categories': [],
            'tags': [],
            'attributes': [],
            'meta_data': []
        }
        
        # Добавляем цену только если она больше 0
        if regular_price:
            product_data['regular_price'] = regular_price
        
        # Добавление категории
        if category:
            category_id = self.get_or_create_category(category)
            if category_id:
                product_data['categories'] = [{'id': category_id}]
                self.log(f"✅ Категория назначена: {category} (ID: {category_id})")
                
        # Добавление изображения
        if image_id:
            product_data['images'] = [{'id': image_id}]
            
            # Добавление бренда как атрибута И как мета-поля
            if brand:
                self.log(f"🏷️  Processing brand: {brand}")
                
                # 1. Создаем атрибут бренда
                brand_attr = self.get_or_create_brand(brand)
                if brand_attr:
                    if 'attributes' not in product_data:
                        product_data['attributes'] = []
                    product_data['attributes'].append(brand_attr)
                    self.log(f"✅ Brand attribute assigned: {brand}")
                
                # 2. Добавляем бренд как мета-поля
                product_data['meta_data'].extend([
                    {"key": "_product_brand", "value": brand},
                    {"key": "brand", "value": brand},
                    {"key": "_brand", "value": brand}
                ])
                self.log(f"✅ Brand meta fields added: {brand}")
                
                if not brand_attr:
                    self.log(f"⚠️  Failed to create brand attribute, but meta fields added")
            
        return product_data

    def format_product_description(self, row):
        """
        Форматирование описания товара с характеристиками
        
        Args:
            row: Строка данных из CSV
            
        Returns:
            str: HTML описание товара
        """
        # Получаем данные
        brand = str(row.get('Бренд', '')).strip()
        name = str(row.get('Название', '')).strip()
        
        if brand:
            brand = brand.capitalize()
        
        # Начинаем с заголовка
        description = f"<h3>{brand} {name}</h3>\n" if brand else f"<h3>{name}</h3>\n"
        
        # Добавляем базовое описание
        if 'Описание' in row and pd.notna(row['Описание']):
            desc_text = str(row['Описание']).strip()
            
            # Переводим русские термины на английский
            if desc_text:
                translations = {
                    'разъем': 'connector',
                    'соединитель': 'connector', 
                    'клемма': 'terminal',
                    'контакт': 'contact',
                    'корпус': 'housing',
                    'блок': 'block',
                    'модуль': 'module'
                }
                
                desc_lower = desc_text.lower()
                for ru_term, en_term in translations.items():
                    if ru_term in desc_lower:
                        desc_text = f"{brand} {en_term}" if brand else en_term
                        break
                else:
                    desc_text = f"{brand} product" if brand else "Electronic product"
            
            description += f"<div class='product-description'><p>{desc_text}</p></div>\n"
        
        # Добавляем характеристики в виде таблицы
        if 'Характеристики' in row and pd.notna(row['Характеристики']):
            characteristics_html = self.parse_characteristics(row['Характеристики'])
            if characteristics_html:
                description += "\n<h4>Technical Specifications:</h4>\n"
                description += characteristics_html
        
        # Добавляем базовую информацию
        basic_info = []
        if brand:
            basic_info.append(f"<strong>Brand:</strong> {brand}")
        if 'Артикул' in row and pd.notna(row['Артикул']):
            basic_info.append(f"<strong>SKU:</strong> {row['Артикул']}")
        
        if basic_info:
            description += "\n<div class='product-info'>\n"
            description += "<br>".join(basic_info)
            description += "\n</div>\n"
        
        return description
        
    def get_or_create_category(self, category_name):
        """
        Получить ID категории или создать новую
        
        Args:
            category_name: Название категории
            
        Returns:
            int: ID категории или None
        """
        try:
            # Поиск существующей категории
            response = self.wcapi.get("products/categories", params={'search': category_name})
            
            if response.status_code == 200:
                categories = response.json()
                for category in categories:
                    if category['name'].lower() == category_name.lower():
                        return category['id']
                        
            # Создание новой категории
            category_data = {
                'name': category_name,
                'slug': category_name.lower().replace(' ', '-').replace('/', '-')
            }
            
            response = self.wcapi.post("products/categories", category_data)
            
            if response.status_code == 201:
                category = response.json()
                self.log(f"Создана категория: {category_name} (ID: {category['id']})")
                return category['id']
            else:
                self.log(f"Ошибка создания категории {category_name}: {response.status_code}")
                return None
                
        except Exception as e:
            self.log(f"Ошибка при работе с категорией {category_name}: {str(e)}")
            return None
            
    def upload_product(self, row, images_folder):
        """
        Загрузка одного товара
        
        Args:
            row: Данные товара
            images_folder: Папка с изображениями
            
        Returns:
            bool: Успешность загрузки
        """
        try:
            product_sku = row.get('Артикул', '')
            product_name = row.get('Название', '')
            brand = row.get('Бренд', '')
            
            self.log(f"Загрузка товара: {product_name} ({product_sku})")
            
            # Поиск и загрузка изображения
            image_id = None
            if images_folder:
                image_path = self.find_product_image(product_sku, images_folder)
                
                if image_path:
                    self.log(f"Найдено изображение: {os.path.basename(image_path)}")
                    media_data = self.upload_image(image_path, product_sku)
                    if media_data:
                        image_id = media_data['id']
                        self.log(f"✅ Изображение загружено (ID: {image_id})")
                    else:
                        self.log(f"❌ Ошибка загрузки изображения")
                else:
                    self.log(f"⚠️  Изображение не найдено для артикула: {product_sku}")
                
            # Создание данных товара
            product_data = self.create_product_data(row, image_id)
            
            # Добавление бренда как атрибута
            if brand:
                brand_attr = self.get_or_create_brand(brand)
                if brand_attr:
                    if 'attributes' not in product_data:
                        product_data['attributes'] = []
                    product_data['attributes'].append(brand_attr)
                    self.log(f"✅ Бренд добавлен: {brand}")
            
            # Загрузка товара
            response = self.wcapi.post("products", product_data)
            
            if response.status_code == 201:
                product = response.json()
                self.log(f"✅ Товар загружен: {product_name} (ID: {product['id']})")
                return True
            else:
                self.log(f"❌ Ошибка загрузки товара {product_name}: {response.status_code}")
                if response.text:
                    self.log(f"Детали ошибки: {response.text}")
                return False
                
        except Exception as e:
            self.log(f"❌ Критическая ошибка при загрузке товара: {str(e)}")
            return False
            
    def upload_products(self, csv_file, images_folder, max_count=None):
        """
        Загрузка товаров из CSV файла
        
        Args:
            csv_file: Путь к CSV файлу
            images_folder: Папка с изображениями
            max_count: Максимальное количество товаров (None для всех)
            
        Returns:
            dict: Результат загрузки
        """
        try:
            self.log("Чтение CSV файла...")
            
            # Чтение CSV с правильной кодировкой
            try:
                df = pd.read_csv(csv_file, encoding='utf-8')
            except UnicodeDecodeError:
                df = pd.read_csv(csv_file, encoding='cp1251')
                
            total_products = len(df)
            self.log(f"Найдено товаров в файле: {total_products}")
            
            # Ограничение количества товаров
            if max_count and max_count < total_products:
                df = df.head(max_count)
                total_products = max_count
                self.log(f"Ограничено до {max_count} товаров")
                
            # Счетчики
            uploaded_count = 0
            error_count = 0
            
            # Обработка каждого товара
            for index, row in df.iterrows():
                if self.stop_requested:
                    self.log("Загрузка остановлена пользователем")
                    break
                    
                current_item = index + 1
                self.update_progress(current_item, total_products, f"Обработка товара {current_item}")
                
                # Загрузка товара
                if self.upload_product(row, images_folder):
                    uploaded_count += 1
                else:
                    error_count += 1
                    
                # Небольшая пауза между запросами
                time.sleep(0.5)
                
            # Результат
            return {
                'success': not self.stop_requested,
                'uploaded': uploaded_count,
                'errors': error_count,
                'total': total_products,
                'message': 'Загрузка завершена' if not self.stop_requested else 'Загрузка прервана'
            }
            
        except Exception as e:
            self.log(f"Критическая ошибка: {str(e)}")
            return {
                'success': False,
                'uploaded': 0,
                'errors': 1,
                'total': 0,
                'message': str(e)
            }
