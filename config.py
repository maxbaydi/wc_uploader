import json
import os
from pathlib import Path

"""
Динамическая конфигурация для всех модулей проекта.
Настройки читаются из файла ``gui_settings.json`` (лежит в корне проекта).  
Если файл отсутствует или в нём нет некоторых ключей, используются значения по умолчанию.
"""

# Путь к JSON-файлу настроек (лежит в том же каталоге, что и этот скрипт)
ROOT_DIR = Path(__file__).resolve().parent
GUI_SETTINGS_FILE = ROOT_DIR / "gui_settings.json"

DEFAULTS = {
    # WooCommerce
    "wc_url": "http://localhost",
    "wc_consumer_key": "ck_XXXX",
    "wc_consumer_secret": "cs_XXXX",
    "wc_timeout": 30,

    # WordPress (загрузка медиа)
    "wp_username": "admin",
    "wp_app_password": "",
    "wp_email": "",

    # Upload / обработка изображений
    "max_image_size": 10,  # MB
    "image_max_width": 800,
    "image_max_height": 600,
    "image_quality": 85,
    "use_placeholder": False,
    "placeholder_image": "",

    # Поведение загрузчика
    "default_stock": 100,
    "request_delay": 0.5,
    "max_retries": 3,
    "update_existing": True,
    "skip_existing": False,

    # Пакетная загрузка
    "use_batch_upload": True,
    "batch_size": 100,
    "batch_delay": 2.0,
    "update_mode": "all",

    # CSV
    "csv_encoding": "utf-8",
    "csv_fallback_encoding": "cp1251",

    # Логи
    "log_level": "INFO",
    
    # Прокси настройки
    "disable_proxy": True,  # Отключить использование прокси для HTTP запросов
    "proxy_http": None,
    "proxy_https": None,
    "proxy_socks": None,

    # SFTP/SSH
    "sftp_host": "localhost",
    "sftp_port": 22,
    "sftp_username": "",
    "sftp_password": "",
    "sftp_remote_base_path": "/tmp",
    "sftp_web_domain": "localhost",  # Домен для формирования URL изображений
    "sftp_images_base_url": "https://localhost/images",  # Базовый URL для доступа к изображениям
}

# --------------------------------------------------------------------------------------
# Загрузка файла gui_settings.json
# --------------------------------------------------------------------------------------
try:
    with open(GUI_SETTINGS_FILE, "r", encoding="utf-8") as fh:
        _user_cfg = json.load(fh)
except FileNotFoundError:
    _user_cfg = {}

# Объединяем с дефолтами
CFG = {**DEFAULTS, **_user_cfg}

# --------------------------------------------------------------------------------------
# Формируем отдельные секции настроек, которые ожидают другие модули
# --------------------------------------------------------------------------------------
WOOCOMMERCE_CONFIG = {
    "url": CFG["wc_url"],
    "consumer_key": CFG["wc_consumer_key"],
    "consumer_secret": CFG["wc_consumer_secret"],
    "wp_username": CFG["wp_username"],
    "wp_app_password": CFG["wp_app_password"],
    "wp_api": True,  # обязательно для корректного адреса вида /wp-json/wc/v3
    "version": "wc/v3",
    "timeout": CFG["wc_timeout"],
}

WORDPRESS_CONFIG = {
    "url": CFG["wc_url"],  # используем тот же базовый домен
    "username": CFG["wp_username"],
    # Application Password WordPress иногда содержит пробелы – убираем их на всякий случай
    "app_password": str(CFG["wp_app_password"]).replace(" ", ""),
    "email": CFG["wp_email"],
}

# Добавляем wp_email в WOOCOMMERCE_CONFIG для совместимости с GUI
WOOCOMMERCE_CONFIG["wp_email"] = CFG["wp_email"]

SFTP_CONFIG = {
    "host": CFG["sftp_host"],
    "port": CFG["sftp_port"],
    "username": CFG["sftp_username"],
    "password": CFG["sftp_password"],
    "remote_base_path": CFG["sftp_remote_base_path"],
    "web_domain": CFG.get("sftp_web_domain", "localhost"),
}

UPLOAD_CONFIG = {
    "max_image_size": int(CFG["max_image_size"]) * 1024 * 1024,  # переводим МБ → байты
    "image_max_width": CFG["image_max_width"],
    "image_max_height": CFG["image_max_height"],
    "image_quality": CFG["image_quality"],
    "default_stock_quantity": CFG["default_stock"],
    "request_delay": CFG["request_delay"],
    "max_retries": CFG["max_retries"],
    "batch_size": CFG.get("batch_size", 100),  # размер пакета для batch API
    "batch_delay": CFG.get("batch_delay", 2.0),  # задержка между пакетами в секундах
    "use_batch_upload": CFG.get("use_batch_upload", True),  # использовать пакетную загрузку
    "update_mode": CFG.get("update_mode", "all"),  # режим обновления (all, images, descriptions)
    "update_existing": CFG["update_existing"],
    "skip_existing": CFG["skip_existing"],
}

CSV_CONFIG = {
    "encoding": CFG["csv_encoding"],
    "fallback_encoding": CFG["csv_fallback_encoding"],
}

# Конфигурация прокси
PROXY_CONFIG = {
    "disable_proxy": CFG.get("disable_proxy", True),
    "http": CFG.get("proxy_http"),
    "https": CFG.get("proxy_https"),
    "socks": CFG.get("proxy_socks"),
}

# --------------------------------------------------------------------------------------
# Утилитарный доступ
# --------------------------------------------------------------------------------------

def get_setting(key, default=None):
    """Быстрый доступ к произвольному ключу из итоговой конфигурации."""
    return CFG.get(key, default)


def as_dict():
    """Получить полную структуру конфигурации (копию)."""
    return dict(CFG)
