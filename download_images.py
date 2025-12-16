import os
import csv
import re
import requests
from urllib.parse import urlparse

IMG_DIR = 'img'
os.makedirs(IMG_DIR, exist_ok=True)

def normalize_filename(s):
    """
    Нормализует имя файла, оставляя только буквы и цифры.
    """
    if not s:
        return "unnamed"

    # Убираем пробелы в начале и конце
    s = s.strip()

    # Оставляем только буквы и цифры, удаляем все остальные символы
    normalized = re.sub(r'[^A-Za-z0-9А-Яа-яЁё]', '', s)

    # Если после очистки ничего не осталось, используем fallback
    if not normalized:
        normalized = "unnamed"

    # Приводим к нижнему регистру
    return normalized.lower()

def get_extension_from_url(url):
    path = urlparse(url).path
    ext = os.path.splitext(path)[1]
    if ext:
        return ext
    return '.jpg'  # по умолчанию

def get_extension_from_response(resp):
    ct = resp.headers.get('Content-Type', '')
    if 'image/' in ct:
        return '.' + ct.split('/')[-1].split(';')[0]
    return '.jpg'

with open('cleaned_product_url.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        img_url = row.get('img_url', '').strip()
        sku = row.get('sku', '').strip()
        if not img_url or not sku:
            continue
        filename = normalize_filename(sku)
        ext = get_extension_from_url(img_url)
        filepath = os.path.join(IMG_DIR, filename + ext)
        # Если файл уже есть — пропускаем
        if os.path.exists(filepath):
            print(f"Пропускаю {filepath} (уже скачан)")
            continue
        try:
            print(f"Скачиваю {img_url} -> {filepath}")
            resp = requests.get(img_url, timeout=20)
            resp.raise_for_status()
            # Проверяем расширение по ответу
            real_ext = get_extension_from_response(resp)
            if real_ext != ext:
                filepath = os.path.join(IMG_DIR, filename + real_ext)
            with open(filepath, 'wb') as out_f:
                out_f.write(resp.content)
        except Exception as e:
            print(f"Ошибка при скачивании {img_url}: {e}") 