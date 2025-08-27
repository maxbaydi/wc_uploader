# WooCommerce FIFU Uploader

Загрузчик товаров в WooCommerce с поддержкой плагина FIFU (Featured Image from URL) и загрузкой изображений на SFTP сервер.

## Особенности

- ✅ **FIFU интеграция** - загрузка изображений на SFTP сервер и использование URL в товарах
- ✅ **Потоковая загрузка** - пакетная обработка товаров для высокой производительности  
- ✅ **CSV адаптер** - автоматическое определение полей в различных форматах CSV
- ✅ **Графический интерфейс** - удобный GUI для настройки и мониторинга загрузки
- ✅ **Обработка ошибок** - детальное логирование и восстановление после ошибок

## Требования

- Python 3.8+
- WooCommerce сайт с API доступом
- SFTP сервер для хранения изображений
- Плагин FIFU на WordPress сайте (опционально)

## Установка

1. Клонируйте репозиторий
```bash
git clone <repository-url>
cd woocommerce-uploader
```

2. Создайте виртуальную среду
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# или venv\Scripts\activate  # Windows
```

3. Установите зависимости
```bash
pip install -r requirements.txt
```

## Настройка

1. Отредактируйте файл `gui_settings.json`:
```json
{
  "wc_url": "https://your-site.com",
  "wc_consumer_key": "ck_your_key",
  "wc_consumer_secret": "cs_your_secret",
  "use_batch_upload": true,
  "batch_size": 100
}
```

2. Подготовьте CSV файл с товарами (поддерживаются различные форматы)

3. Подготовьте папку с изображениями (названия файлов должны соответствовать SKU)

## Запуск

### GUI версия (рекомендуется)
```bash
python3 run_fifu.py
```
или используйте готовый скрипт:
```bash
./run_fifu_uploader.sh
```

### Настройка SFTP
В GUI заполните:
- **Хост**: адрес SFTP сервера
- **Порт**: порт SFTP (обычно 22)
- **Пользователь**: имя пользователя
- **Пароль**: пароль
- **Путь**: базовая папка для изображений (например `/images`)

## Поддерживаемые форматы CSV

Автоматически определяются следующие поля:
- **Бренд**: Brand, Производитель, Manufacturer
- **Название**: Name, Наименование, Title  
- **Артикул**: SKU, Код, Article
- **Категория**: Category, Группа, Type
- **Описание**: Description, Desc
- **Характеристики**: Characteristics, Specs, Technical Data
- **Цена**: Price, Цена, Cost
- **Остаток**: Stock, Количество, Qty

## Структура проекта

```
woocommerce-uploader/
├── gui_fifu.py              # Основной GUI
├── woocommerce_fifu_uploader.py  # FIFU загрузчик
├── sftp_uploader.py         # SFTP модуль
├── csv_adapter.py           # CSV адаптер
├── config.py                # Конфигурация
├── gui_settings.json        # Настройки
├── requirements.txt         # Зависимости
├── run_fifu.py             # Скрипт запуска
└── run_fifu_uploader.sh    # Bash скрипт
```

## Устранение неисправностей

### Проблемы с подключением к SFTP
- Проверьте корректность хоста, порта, логина и пароля
- Убедитесь, что SFTP сервер доступен из вашей сети
- Используйте кнопку "Тест соединения" в GUI

### Проблемы с WooCommerce API
- Проверьте URL сайта и API ключи в `gui_settings.json`
- Убедитесь, что WooCommerce REST API включен
- Проверьте права доступа для API ключей

### Проблемы с CSV
- Используйте UTF-8 кодировку для CSV файлов
- Убедитесь, что файл содержит обязательные поля (Name, SKU)
- Проверьте корректность названий колонок

## Лицензия

MIT License 