#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WooCommerce Product Uploader - Console Version
Консольная версия загрузчика товаров для WooCommerce
"""

import os
import sys
import pandas as pd
from pathlib import Path
from woocommerce import API
from PIL import Image
import requests
import base64
import time
from csv_adapter import CSVAdapter
from config import WOOCOMMERCE_CONFIG, WORDPRESS_CONFIG

class ConsoleWooCommerceUploader:
    def __init__(self):
        self.config = WOOCOMMERCE_CONFIG
        self.wp_config = WORDPRESS_CONFIG
        
        self.wcapi = API(
            url=self.config['url'],
            consumer_key=self.config['consumer_key'],
            consumer_secret=self.config['consumer_secret'],
            version=self.config['version'],
            timeout=30
        )
        
        self.csv_adapter = CSVAdapter()
        
        print("🚀 WooCommerce Product Uploader - Console Version")
        print("=" * 50)
    
    def test_connection(self):
        """Тестирование подключения к WooCommerce API"""
        try:
            print("🔍 Тестирование подключения к WooCommerce API...")
            response = self.wcapi.get("products", params={"per_page": 1})
            
            if response.status_code == 200:
                print("✅ Подключение к WooCommerce API успешно!")
                return True
            else:
                print(f"❌ Ошибка подключения: {response.status_code}")
                print(f"Ответ: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Критическая ошибка подключения: {str(e)}")
            return False
    
    def load_csv_file(self, file_path):
        """Загрузка CSV файла"""
        try:
            print(f"📂 Загрузка файла: {file_path}")
            
            # Попробуем разные кодировки
            encodings = ['utf-8', 'cp1251', 'windows-1251', 'iso-8859-1']
            
            for encoding in encodings:
                try:
                    df = pd.read_csv(file_path, encoding=encoding)
                    print(f"✅ Файл загружен успешно (кодировка: {encoding})")
                    print(f"📊 Количество товаров в файле: {len(df)}")
                    return df
                except UnicodeDecodeError:
                    continue
            
            # Если ни одна кодировка не подошла
            raise Exception("Не удалось определить кодировку файла")
                    
        except Exception as e:
            print(f"❌ Ошибка загрузки файла: {str(e)}")
            return None
    
    def show_csv_preview(self, df):
        """Показать предварительный просмотр CSV"""
        print("\n📋 Предварительный просмотр данных:")
        print("-" * 80)
        print("Колонки:", list(df.columns))
        print(f"Первые 3 записи:")
        print(df.head(3).to_string(index=False, max_cols=5))
        print("-" * 80)
    
    def upload_image(self, image_path, product_name):
        """Загрузка изображения через WordPress REST API"""
        try:
            if not os.path.exists(image_path):
                print(f"⚠️  Изображение не найдено: {image_path}")
                return None
            
            print(f"📸 Uploading image: {os.path.basename(image_path)}")
            
            # Оптимизируем изображение
            with Image.open(image_path) as img:
                # Конвертируем в RGB если нужно
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Изменяем размер если нужно
                if img.width > 800 or img.height > 600:
                    img.thumbnail((800, 600), Image.Resampling.LANCZOS)
                
                # Сохраняем оптимизированное изображение во временный файл
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                    img.save(temp_file, format='JPEG', quality=85, optimize=True)
                    temp_path = temp_file.name
            
            try:
                # Читаем оптимизированное изображение
                with open(temp_path, 'rb') as img_file:
                    img_data = img_file.read()
                
                # Формируем имя файла
                filename = f"{product_name}_{os.path.basename(image_path)}"
                
                # URL для загрузки медиа в WordPress
                media_url = f"{self.wp_config['url']}/wp-json/wp/v2/media"
                
                # Подготавливаем данные для загрузки
                files = {
                    'file': (filename, img_data, 'image/jpeg')
                }
                
                # Заголовки
                headers = {
                    'Content-Disposition': f'attachment; filename="{filename}"'
                }
                
                # Авторизация через application password
                from requests.auth import HTTPBasicAuth
                auth = HTTPBasicAuth(self.wp_config['username'], self.wp_config['app_password'])
                
                print(f"🔄 Uploading to: {media_url}")
                print(f"🔑 Using username: {self.wp_config['username']}")
                
                # Загружаем
                response = requests.post(
                    media_url,
                    files=files,
                    headers=headers,
                    auth=auth,
                    timeout=30
                )
                
                if response.status_code in [200, 201]:
                    media_data = response.json()
                    print(f"✅ Image uploaded successfully (ID: {media_data['id']})")
                    return media_data['id']
                else:
                    print(f"⚠️  WordPress upload failed: {response.status_code}")
                    print(f"Response: {response.text}")
                    
                    # Пробуем альтернативный способ через WooCommerce API
                    return self.upload_image_base64(image_path, product_name)
                    
            finally:
                # Удаляем временный файл
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                
        except Exception as e:
            print(f"⚠️  Ошибка загрузки изображения: {str(e)}")
            return self.upload_image_base64(image_path, product_name)
    
    def upload_image_base64(self, image_path, product_name):
        """Альтернативная загрузка изображения через base64"""
        try:
            print(f"🔄 Trying alternative image upload method...")
            
            # Оптимизация изображения
            with Image.open(image_path) as img:
                # Конвертируем в RGB если нужно
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Изменяем размер если нужно
                if img.width > 800 or img.height > 600:
                    img.thumbnail((800, 600), Image.Resampling.LANCZOS)
                
                # Сохраняем оптимизированное изображение в память
                import io
                img_bytes = io.BytesIO()
                img.save(img_bytes, format='JPEG', quality=85, optimize=True)
                img_bytes.seek(0)
                
                # Кодируем в base64
                img_base64 = base64.b64encode(img_bytes.read()).decode('utf-8')
            
            # Загружаем изображение через WooCommerce Media API
            image_data = {
                "name": f"{product_name}.jpg",
                "type": "image/jpeg",
                "src": f"data:image/jpeg;base64,{img_base64}"
            }
            
            response = self.wcapi.post("media", image_data)
            
            if response.status_code in [200, 201]:
                media_data = response.json()
                print(f"✅ Image uploaded via base64 (ID: {media_data['id']})")
                return media_data['id']
            else:
                print(f"⚠️  Base64 upload failed: {response.status_code}")
                print(f"Response: {response.text}")
                return None
                
        except Exception as e:
            print(f"⚠️  Base64 upload error: {str(e)}")
            return None
    
    def get_or_create_brand(self, brand_name):
        """
        Gets or creates a brand via taxonomy and returns its ID.
        Получает или создает бренд через таксономию и возвращает его ID.
        """
        if not brand_name or pd.isna(brand_name) or str(brand_name).strip() == '':
            return None

        brand_name = str(brand_name).strip().capitalize()
        print(f"🔍 Processing brand: '{brand_name}'")

        try:
            # 1. Search for an existing brand
            # The 'product_brand' taxonomy is used by most brand plugins.
            response = self.wcapi.get("products/brands", params={"search": brand_name})
            response.raise_for_status()
            brands = response.json()

            for brand in brands:
                if brand['name'].lower() == brand_name.lower():
                    brand_id = brand['id']
                    print(f"✅ Found brand '{brand_name}' with ID: {brand_id}")
                    return brand_id

            # 2. Create a new brand if not found
            print(f"🔧 Brand '{brand_name}' not found, creating a new one...")
            data = {"name": brand_name}
            response = self.wcapi.post("products/brands", data)
            response.raise_for_status()
            new_brand = response.json()
            brand_id = new_brand['id']
            print(f"✅ Created brand '{brand_name}' with ID: {brand_id}")
            return brand_id

        except Exception as e:
            print(f"❌ Error managing brand '{brand_name}': {e}")
            # Check if it's a 404 error, which might mean the brands endpoint doesn't exist
            if hasattr(e, 'response') and e.response.status_code == 404:
                print("⚠️  The 'products/brands' endpoint was not found. Please ensure a brand plugin is installed and active.")
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
        
        print(f"🔍 Searching image for SKU: {sku} (cleaned: {sku_clean})")
        
        # Перебираем все варианты названий и расширений
        for variant in search_variants:
            for ext in extensions:
                image_path = os.path.join(image_folder, f"{variant}{ext}")
                if os.path.exists(image_path):
                    print(f"✅ Found image: {variant}{ext}")
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
                        print(f"✅ Found image via glob: {os.path.basename(match)}")
                        return match
        except Exception as e:
            print(f"⚠️  Glob search error: {str(e)}")
        
        print(f"❌ No image found for SKU: {sku}")
        return None

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
                print(f"🏷️  Created category: {category_name} (ID: {category['id']})")
                return category['id']
            else:
                print(f"❌ Category creation error {category_name}: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Category error {category_name}: {str(e)}")
            return None
    
    def format_description(self, row):
        """Форматирование описания товара"""
        try:
            # Получаем название товара
            name = row.get('Название', str(row.get('name', 'Product')))
            brand = row.get('Бренд', str(row.get('brand', '')))
            
            # Делаем первую букву бренда заглавной
            if brand:
                brand = brand.capitalize()
            
            description = f"<h3>{brand} {name}</h3>\n" if brand else f"<h3>{name}</h3>\n"
            
            # Если есть поле описание, добавляем его (только на английском)
            if 'Описание' in row and pd.notna(row['Описание']):
                desc_text = str(row['Описание'])
                # Простая проверка - если описание содержит кириллицу, переводим базовые термины
                if any(ord(char) > 127 for char in desc_text):
                    # Заменяем базовые русские термины на английские
                    translations = {
                        'клемма': 'terminal',
                        'соединитель': 'connector', 
                        'разъем': 'connector',
                        'кабель': 'cable',
                        'провод': 'wire',
                        'контакт': 'contact',
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
            
            # Создаем таблицу характеристик из поля "Характеристики"
            if 'Характеристики' in row and pd.notna(row['Характеристики']):
                characteristics_text = str(row['Характеристики'])
                
                description += "<h4>Technical Specifications:</h4>\n"
                description += "<table style='border-collapse: collapse; width: 100%; margin: 10px 0;'>\n"
                
                # Парсим характеристики (разделены символами ||| и |)
                sections = characteristics_text.split('|||')
                
                for section in sections:
                    section = section.strip()
                    if not section:
                        continue
                        
                    if section.startswith('---') and section.endswith('---'):
                        # Это заголовок секции
                        section_title = section.replace('---', '').strip()
                        # Убираем параметры из заголовка, которые идут после |
                        if '|' in section_title:
                            section_title = section_title.split('|')[0].strip()
                        
                        if section_title:
                            description += f"<tr style='border: 1px solid #ddd; background-color: #e8f4f8;'>"
                            description += f"<td colspan='2' style='padding: 12px; font-weight: bold; text-align: center; color: #2c5282;'>{section_title}</td>"
                            description += f"</tr>\n"
                    else:
                        # Это характеристики
                        items = section.split('|')
                        for item in items:
                            item = item.strip()
                            if ':' in item and item:
                                try:
                                    key, value = item.split(':', 1)
                                    key = key.strip()
                                    value = value.strip()
                                    if key and value and not key.startswith('-'):
                                        description += f"<tr style='border: 1px solid #ddd;'>"
                                        description += f"<td style='padding: 8px; background-color: #f9f9f9; font-weight: bold; width: 40%;'>{key}</td>"
                                        description += f"<td style='padding: 8px; width: 60%;'>{value}</td>"
                                        description += f"</tr>\n"
                                except:
                                    continue
                
                description += "</table>\n"
            
            # Добавляем основные характеристики в простом виде
            basic_info = []
            if 'Бренд' in row and pd.notna(row['Бренд']):
                basic_info.append(f"<strong>Brand:</strong> {row['Бренд'].capitalize()}")
            if 'Артикул' in row and pd.notna(row['Артикул']):
                basic_info.append(f"<strong>SKU:</strong> {row['Артикул']}")
            if 'Категория' in row and pd.notna(row['Категория']):
                basic_info.append(f"<strong>Category:</strong> {row['Категория']}")
            
            if basic_info:
                description += "<div class='basic-info' style='margin: 15px 0; padding: 10px; background-color: #f8f9fa; border-radius: 5px;'>\n"
                description += "<br>".join(basic_info)
                description += "</div>\n"
            
            return description
            
        except Exception as e:
            print(f"⚠️  Error formatting description: {str(e)}")
            return f"<p>Product description: {row.get('Название', 'Product')}</p>"
    
    def create_product(self, row, image_folder=None):
        """Создание товара в WooCommerce"""
        try:
            # Получаем данные из правильных полей CSV
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
                "name": full_name,
                "type": "simple",
                "description": self.format_description(row),
                "short_description": name[:100] if name else f"Product {brand}",
                "sku": sku,
                "manage_stock": False,  # Не управляем складскими остатками
                "in_stock": True,       # Просто указываем что товар в наличии
                "status": "publish"
            }
            
            # Добавляем цену только если она больше 0
            if regular_price:
                product_data["regular_price"] = regular_price
            
            # Добавляем категории если есть
            if category:
                print(f"🏷️  Processing category: {category}")
                category_id = self.get_or_create_category(category)
                if category_id:
                    product_data["categories"] = [{"id": category_id}]
                    print(f"✓ Category assigned: {category} (ID: {category_id})")
                else:
                    print(f"⚠️  Failed to create/find category: {category}")
            
            # Добавляем бренд как атрибут И как мета-поле
            if brand:
                print(f"🏷️  Processing brand: {brand}")
                
                # 1. Создаем атрибут бренда
                brand_attr = self.get_or_create_brand(brand)
                if brand_attr:
                    product_data["attributes"] = [brand_attr]
                    print(f"✓ Brand attribute assigned: {brand}")
                
                # 2. Добавляем бренд как мета-поле для лучшей совместимости
                if "meta_data" not in product_data:
                    product_data["meta_data"] = []
                
                product_data["meta_data"].extend([
                    {"key": "_product_brand", "value": brand},
                    {"key": "brand", "value": brand},
                    {"key": "_brand", "value": brand}
                ])
                print(f"✓ Brand meta fields added: {brand}")
                
                if not brand_attr:
                    print(f"⚠️  Failed to create brand attribute, but meta fields added")
            else:
                print(f"⚠️  No brand specified")
            
            # Добавляем изображение если есть папка с изображениями
            if image_folder and os.path.exists(image_folder) and sku:
                image_path = self.find_product_image(sku, image_folder)
                if image_path:
                    print(f"🖼️  Uploading image: {os.path.basename(image_path)}")
                    image_id = self.upload_image(image_path, sku)
                    if image_id:
                        product_data["images"] = [{"id": image_id}]
                        print(f"✅ Image uploaded successfully (ID: {image_id})")
                    else:
                        print(f"❌ Failed to upload image")
                else:
                    print(f"⚠️  No image found for SKU: {sku}")
            
            # Создаем товар
            response = self.wcapi.post("products", product_data)
            
            if response.status_code in [200, 201]:
                product = response.json()
                print(f"✅ Product created: {product['name']} (ID: {product['id']})")
                return True
            else:
                print(f"❌ Product creation error: {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Critical product creation error: {str(e)}")
            return False
    
    def upload_products(self, df, image_folder=None, max_products=None):
        """Загрузка товаров"""
        print(f"\n🚀 Начинаем загрузку товаров...")
        
        total_products = len(df) if max_products is None else min(max_products, len(df))
        successful_uploads = 0
        failed_uploads = 0
        
        print(f"📊 Будет обработано товаров: {total_products}")
        
        if image_folder:
            print(f"🖼️  Папка с изображениями: {image_folder}")
        
        print("-" * 50)
        
        for index, row in df.iterrows():
            if max_products is not None and index >= max_products:
                break
            
            # Получаем информацию о товаре
            brand = str(row.get('Бренд', '')).strip()
            name = str(row.get('Название', '')).strip()
            sku = str(row.get('Артикул', '')).strip()
            full_name = f"{brand} {name}" if brand and name else (name or "Без названия")
            
            print(f"\n📦 Обработка товара {index + 1}/{total_products}")
            print(f"Название: {full_name}")
            print(f"Артикул: {sku or 'Без артикула'}")
            
            if self.create_product(row, image_folder):
                successful_uploads += 1
            else:
                failed_uploads += 1
            
            # Небольшая пауза чтобы не перегружать API
            time.sleep(1)
        
        print("\n" + "=" * 50)
        print("📊 ИТОГИ ЗАГРУЗКИ:")
        print(f"✅ Успешно загружено: {successful_uploads}")
        print(f"❌ Ошибок: {failed_uploads}")
        print(f"📈 Общий процент успеха: {(successful_uploads/total_products)*100:.1f}%")
        print("=" * 50)
    
    def run(self):
        """Основной метод запуска"""
        try:
            # Тест подключения
            if not self.test_connection():
                print("❌ Не удалось подключиться к WooCommerce API")
                return
            
            print("\n" + "=" * 50)
            
            # Запрос файла CSV
            while True:
                csv_file = input("📂 Укажите путь к CSV файлу: ").strip().strip('"').strip("'")
                if os.path.exists(csv_file):
                    break
                print("❌ Файл не найден. Попробуйте еще раз.")
            
            # Загрузка CSV
            df = self.load_csv_file(csv_file)
            if df is None:
                return
            
            # Адаптация данных под стандартный формат
            adapted_df, mapping = self.csv_adapter.adapt_dataframe(df)
            if adapted_df is None:
                print("❌ Не удалось адаптировать данные CSV файла")
                return
            
            # Показать предварительный просмотр адаптированных данных
            self.show_csv_preview(adapted_df)
            
            # Запрос количества товаров
            print(f"\n📊 В файле найдено {len(df)} товаров")
            while True:
                try:
                    choice = input("Сколько товаров загрузить? (все/число): ").strip().lower()
                    if choice in ['все', 'all', '']:
                        max_products = None
                        break
                    else:
                        max_products = int(choice)
                        if max_products > 0:
                            break
                        else:
                            print("❌ Количество должно быть больше 0")
                except ValueError:
                    print("❌ Введите число или 'все'")
            
            # Запрос папки с изображениями
            image_folder = None
            while True:
                img_path = input("🖼️  Укажите путь к папке с изображениями (или Enter для пропуска): ").strip().strip('"').strip("'")
                if not img_path:
                    break
                if os.path.exists(img_path) and os.path.isdir(img_path):
                    image_folder = img_path
                    break
                print("❌ Папка не найдена. Попробуйте еще раз или нажмите Enter для пропуска.")
            
            # Подтверждение загрузки
            print(f"\n📋 НАСТРОЙКИ ЗАГРУЗКИ:")
            print(f"CSV файл: {csv_file}")
            print(f"Количество товаров: {'Все (' + str(len(df)) + ')' if max_products is None else max_products}")
            print(f"Папка с изображениями: {image_folder or 'Не указана'}")
            
            confirm = input("\n❓ Начать загрузку? (y/n): ").strip().lower()
            if confirm not in ['y', 'yes', 'да', 'д']:
                print("❌ Загрузка отменена")
                return
            
            # Запуск загрузки
            self.upload_products(df, image_folder, max_products)
            
        except KeyboardInterrupt:
            print("\n❌ Загрузка прервана пользователем")
        except Exception as e:
            print(f"\n❌ Критическая ошибка программы: {str(e)}")

def main():
    """Главная функция"""
    try:
        uploader = ConsoleWooCommerceUploader()
        uploader.run()
    except Exception as e:
        print(f"❌ Критическая ошибка: {str(e)}")
    
    input("\nНажмите Enter для выхода...")

if __name__ == "__main__":
    main()
