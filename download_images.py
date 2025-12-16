import os
import csv
import re
import requests
from urllib.parse import urlparse

IMG_DIR = 'img'
DEFAULT_INPUT = 'cleaned_product_url.csv'


def normalize_filename(s):
    """
    Нормализует имя файла, оставляя только буквы и цифры.
    """
    if not s:
        return "unnamed"

    s = s.strip()
    normalized = re.sub(r'[^A-Za-z0-9А-Яа-яЁё]', '', s)

    if not normalized:
        normalized = "unnamed"

    return normalized.lower()


def get_extension_from_url(url):
    path = urlparse(url).path
    ext = os.path.splitext(path)[1]
    return ext if ext else '.jpg'


def get_extension_from_response(resp):
    ct = resp.headers.get('Content-Type', '')
    if 'image/' in ct:
        return '.' + ct.split('/')[-1].split(';')[0]
    return '.jpg'


def main(input_file: str = DEFAULT_INPUT, output_dir: str = IMG_DIR) -> None:
    os.makedirs(output_dir, exist_ok=True)

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                img_url = row.get('img_url', '').strip()
                sku = row.get('sku', '').strip()
                if not img_url or not sku:
                    continue
                filename = normalize_filename(sku)
                ext = get_extension_from_url(img_url)
                filepath = os.path.join(output_dir, filename + ext)
                if os.path.exists(filepath):
                    print(f"Пропускаю {filepath} (уже скачан)")
                    continue
                try:
                    print(f"Скачиваю {img_url} -> {filepath}")
                    resp = requests.get(img_url, timeout=20)
                    resp.raise_for_status()
                    real_ext = get_extension_from_response(resp)
                    if real_ext != ext:
                        filepath = os.path.join(output_dir, filename + real_ext)
                    with open(filepath, 'wb') as out_f:
                        out_f.write(resp.content)
                except Exception as e:
                    print(f"Ошибка при скачивании {img_url}: {e}")
    except FileNotFoundError:
        print(f"Файл {input_file} не найден, скачивание пропущено.")


if __name__ == "__main__":
    main()