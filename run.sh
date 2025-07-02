#!/bin/bash

# WooCommerce Product Uploader - Скрипт запуска для Linux

echo "=============================================="
echo "WooCommerce Product Uploader"
echo "=============================================="
echo ""

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не найден. Пожалуйста, установите Python3"
    exit 1
fi

echo "✓ Python3 найден: $(python3 --version)"

# Переход в директорию скрипта
cd "$(dirname "$0")"

# Проверка зависимостей
echo "Проверка зависимостей..."

if [ ! -f "requirements.txt" ]; then
    echo "❌ Файл requirements.txt не найден"
    exit 1
fi

# Установка зависимостей
echo "Установка зависимостей..."
python3 -m pip install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✓ Зависимости установлены"
else
    echo "❌ Ошибка установки зависимостей"
    exit 1
fi

# Запуск приложения
echo ""
echo "Запуск WooCommerce Product Uploader..."
echo ""

python3 main.py

echo ""
echo "Программа завершена"
