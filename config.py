"""
Конфигурация WooCommerce Uploader
"""

# Настройки WooCommerce API
WOOCOMMERCE_CONFIG = {
    'url': 'https://vendorgroup.org',
    'consumer_key': 'ck_92dc075acec0e78deb003bdefbad707121c7d63a',
    'consumer_secret': 'cs_f7c99eebe651ef0ff3e6d87893719058d6fc4aa6',
    'wp_api': True,
    'version': 'wc/v3',
    'timeout': 30
}

# Настройки WordPress API для загрузки медиа
WORDPRESS_CONFIG = {
    'url': 'https://vendorgroup.org',
    'username': 'vgroup23-',
    'app_password': '9tJI LO1Q 8wsc 7kK2 i0TJ lKXm',
    'email': 'hoxbiz@gmail.com'
}

# Настройки загрузки
UPLOAD_CONFIG = {
    'max_image_size': 10 * 1024 * 1024,  # 10MB
    'supported_image_formats': ['.jpg', '.jpeg', '.png', '.gif', '.webp'],
    'default_stock_quantity': 100,
    'request_delay': 0.5,  # секунд между запросами
    'max_retries': 3
}

# Настройки CSV
CSV_CONFIG = {
    'encoding': 'utf-8',
    'fallback_encoding': 'cp1251',
    'required_columns': ['Бренд', 'Название', 'Артикул', 'Категория', 'Описание', 'Характеристики', 'Цена']
}

# Настройки GUI
GUI_CONFIG = {
    'window_title': 'WooCommerce Product Uploader',
    'window_size': '900x700',
    'min_window_size': (800, 600),
    'theme': 'clam'
}
