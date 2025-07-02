#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Адаптер для различных форматов CSV файлов
"""

class CSVAdapter:
    """
    Адаптер для приведения различных форматов CSV к единому виду
    """
    
    def __init__(self):
        # Возможные варианты названий колонок для каждого поля
        self.field_mappings = {
            'brand': ['Бренд', 'Brand', 'Производитель', 'Manufacturer', 'brand'],
            'name': ['Название', 'Name', 'Наименование', 'Title', 'Product Name', 'name'],
            'sku': ['Артикул', 'SKU', 'Код', 'Code', 'Article', 'sku'],
            'category': ['Категория', 'Category', 'Группа', 'Group', 'Type', 'category'],
            'description': ['Описание', 'Description', 'Desc', 'Short Description', 'description'],
            'characteristics': ['Характеристики', 'Characteristics', 'Specs', 'Technical Data', 'Properties', 'characteristics'],
            'price': ['Цена', 'Price', 'Cost', 'Amount', 'РРЦ', 'price']
        }
    
    def detect_columns(self, df):
        """
        Определяет соответствие колонок в CSV файле нашим полям
        """
        detected_mapping = {}
        available_columns = list(df.columns)
        
        print("🔍 Обнаруженные колонки в CSV:")
        for i, col in enumerate(available_columns):
            print(f"  {i+1}. {col}")
        
        print("\n📋 Автоматическое определение полей:")
        
        for field, possible_names in self.field_mappings.items():
            found_column = None
            
            # Ищем точное совпадение
            for col in available_columns:
                if col in possible_names:
                    found_column = col
                    break
            
            # Если не найдено точное совпадение, ищем частичное
            if not found_column:
                for col in available_columns:
                    for possible_name in possible_names:
                        if possible_name.lower() in col.lower() or col.lower() in possible_name.lower():
                            found_column = col
                            break
                    if found_column:
                        break
            
            if found_column:
                detected_mapping[field] = found_column
                print(f"  ✅ {field} -> '{found_column}'")
            else:
                print(f"  ❓ {field} -> не найдено")
        
        return detected_mapping
    
    def adapt_row(self, row, mapping):
        """
        Адаптирует строку данных к стандартному формату
        """
        adapted_row = {}
        
        # Стандартные поля
        adapted_row['Бренд'] = str(row.get(mapping.get('brand', ''), '')).strip()
        adapted_row['Название'] = str(row.get(mapping.get('name', ''), '')).strip()
        adapted_row['Артикул'] = str(row.get(mapping.get('sku', ''), '')).strip()
        adapted_row['Категория'] = str(row.get(mapping.get('category', ''), '')).strip()
        adapted_row['Описание'] = str(row.get(mapping.get('description', ''), '')).strip()
        adapted_row['Характеристики'] = str(row.get(mapping.get('characteristics', ''), '')).strip()
        adapted_row['Цена'] = str(row.get(mapping.get('price', '0'), '0')).strip()
        
        # Убираем 'nan' значения
        for key, value in adapted_row.items():
            if value.lower() in ['nan', 'none', 'null']:
                adapted_row[key] = ''
        
        return adapted_row
    
    def adapt_dataframe(self, df):
        """
        Адаптирует весь DataFrame к стандартному формату
        """
        print("\n🔄 Адаптация данных...")
        
        # Определяем соответствие колонок
        mapping = self.detect_columns(df)
        
        # Если основные поля не найдены, пытаемся предложить ручную настройку
        required_fields = ['name', 'sku']
        missing_required = [field for field in required_fields if field not in mapping]
        
        if missing_required:
            print(f"\n⚠️  Не удалось автоматически определить обязательные поля: {missing_required}")
            print("Попробуйте переименовать колонки в CSV файле или использовать ручную настройку")
            return None, mapping
        
        # Адаптируем все строки
        adapted_rows = []
        for _, row in df.iterrows():
            adapted_row = self.adapt_row(row, mapping)
            adapted_rows.append(adapted_row)
        
        # Создаем новый DataFrame
        import pandas as pd
        adapted_df = pd.DataFrame(adapted_rows)
        
        print(f"✅ Адаптировано {len(adapted_df)} записей")
        return adapted_df, mapping
    
    def load_and_adapt_csv(self, csv_file_path):
        """
        Загружает CSV файл и адаптирует его к стандартному формату
        
        Args:
            csv_file_path: Путь к CSV файлу
            
        Returns:
            pandas.DataFrame: Адаптированный DataFrame или None в случае ошибки
        """
        import pandas as pd
        
        try:
            # Пробуем загрузить с разными кодировками
            encodings = ['utf-8', 'cp1251', 'iso-8859-1', 'windows-1251']
            df = None
            
            for encoding in encodings:
                try:
                    df = pd.read_csv(csv_file_path, encoding=encoding)
                    print(f"✅ CSV loaded with encoding: {encoding}")
                    break
                except UnicodeDecodeError:
                    continue
                except Exception as e:
                    print(f"⚠️  Error with encoding {encoding}: {str(e)}")
                    continue
            
            if df is None:
                print("❌ Failed to load CSV with any encoding")
                return None
            
            # Адаптируем DataFrame
            result = self.adapt_dataframe(df)
            if isinstance(result, tuple):
                adapted_df, mapping = result
                return adapted_df
            else:
                return result
            
        except Exception as e:
            print(f"❌ Error loading CSV file: {str(e)}")
            return None
