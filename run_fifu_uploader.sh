#!/bin/bash

echo "========================================"
echo "WooCommerce FIFU Product Uploader"
echo "========================================"
echo ""

# Функция для проверки команды
check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo "❌ Команда '$1' не найдена!"
        echo "   Установите Python 3 для продолжения"
        exit 1
    fi
}

# Функция установки зависимостей
install_dependencies() {
    echo "📦 Установка зависимостей..."
    
    # Проверяем наличие requirements.txt
    if [ -f "requirements.txt" ]; then
        echo "   Использование requirements.txt..."
        if ! pip install -r requirements.txt --quiet; then
            echo "   ❌ Ошибка установки из requirements.txt"
            exit 1
        fi
    else
        echo "   Установка базовых зависимостей..."
        # Список необходимых пакетов
        packages=(
            "woocommerce"
            "pandas" 
            "pillow"
            "requests"
            "paramiko"  # Для SSH/SFTP подключения
        )
        
        for package in "${packages[@]}"; do
            echo "   Установка $package..."
            if ! pip install "$package" --quiet; then
                echo "   ❌ Ошибка установки $package"
                exit 1
            fi
        done
    fi
    
    echo "   ✅ Все зависимости установлены"
}

# Проверяем наличие Python
echo "🔍 Проверка системных требований..."
check_command "python3"
echo "   ✅ Python 3 найден: $(python3 --version)"

# Проверяем наличие pip
check_command "pip"
echo "   ✅ pip найден: $(pip --version | cut -d' ' -f1-2)"

# Проверяем наличие виртуального окружения
if [ ! -f "venv/bin/activate" ]; then
    echo ""
    echo "📁 Виртуальное окружение не найдено"
    echo "🔧 Создание нового виртуального окружения..."
    
    # Создаем виртуальное окружение
    if ! python3 -m venv venv; then
        echo "❌ Ошибка создания виртуального окружения!"
        echo "   Убедитесь что python3-venv установлен:"
        echo "   sudo apt install python3-venv  # Ubuntu/Debian"
        echo "   yum install python3-venv       # CentOS/RHEL"
        exit 1
    fi
    
    echo "   ✅ Виртуальное окружение создано"
    
    # Активируем новое окружение
    echo "🔧 Активация виртуального окружения..."
    source venv/bin/activate
    
    # Обновляем pip
    echo "⬆️  Обновление pip..."
    pip install --upgrade pip --quiet
    
    # Устанавливаем зависимости
    install_dependencies
    
else
    echo "   ✅ Виртуальное окружение найдено"
    
    # Активируем существующее окружение
    echo "🔧 Активация виртуального окружения..."
    source venv/bin/activate
    
    # Проверяем основные зависимости
    echo "🔍 Проверка зависимостей..."
    missing_deps=()
    
    if ! python -c "import woocommerce" 2>/dev/null; then
        missing_deps+=("woocommerce")
    fi
    
    if ! python -c "import pandas" 2>/dev/null; then
        missing_deps+=("pandas")
    fi
    
    if ! python -c "import PIL" 2>/dev/null; then
        missing_deps+=("pillow")
    fi
    
    if ! python -c "import requests" 2>/dev/null; then
        missing_deps+=("requests")
    fi
    
    if ! python -c "import paramiko" 2>/dev/null; then
        missing_deps+=("paramiko")
    fi
    
    if [ ${#missing_deps[@]} -gt 0 ]; then
        echo "   ⚠️  Отсутствуют зависимости: ${missing_deps[*]}"
        echo "📦 Установка недостающих зависимостей..."
        for dep in "${missing_deps[@]}"; do
            echo "   Установка $dep..."
            pip install "$dep" --quiet
        done
    else
        echo "   ✅ Все зависимости установлены"
    fi
fi

# Проверяем наличие основных файлов
if [ ! -f "gui_fifu.py" ]; then
    echo ""
    echo "❌ Файл gui_fifu.py не найден!"
    echo "   Убедитесь что вы находитесь в правильной папке проекта"
    exit 1
fi

if [ ! -f "woocommerce_fifu_uploader.py" ]; then
    echo ""
    echo "❌ Файл woocommerce_fifu_uploader.py не найден!"
    echo "   Убедитесь что вы установили все необходимые скрипты"
    exit 1
fi

# Проверяем наличие конфигурации
if [ ! -f "config.py" ]; then
    echo ""
    echo "⚠️  Файл config.py не найден!"
    echo "   Создайте файл конфигурации с настройками WooCommerce API"
    exit 1
fi

# Запрашиваем CSV файл если не указан в аргументах
CSV_FILE=""
IMAGES_FOLDER=""
MAX_COUNT=""

# Обработка аргументов командной строки
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --csv)
            CSV_FILE="$2"
            shift
            shift
            ;;
        --images)
            IMAGES_FOLDER="$2"
            shift
            shift
            ;;
        --count)
            MAX_COUNT="$2"
            shift
            shift
            ;;
        *)
            echo "⚠️  Неизвестный параметр: $1"
            shift
            ;;
    esac
done

# Если CSV файл не указан, запрашиваем его
if [ -z "$CSV_FILE" ]; then
    read -p "📄 Введите путь к CSV файлу с товарами: " CSV_FILE
    if [ -z "$CSV_FILE" ]; then
        echo "❌ Файл не указан, выход."
        exit 1
    fi
fi

# Если папка с изображениями не указана, запрашиваем её
if [ -z "$IMAGES_FOLDER" ]; then
    read -p "📁 Введите путь к папке с изображениями: " IMAGES_FOLDER
    if [ -z "$IMAGES_FOLDER" ]; then
        echo "❌ Папка не указана, выход."
        exit 1
    fi
fi

# Проверка наличия файлов и папок
if [ ! -f "$CSV_FILE" ]; then
    echo "❌ CSV файл не найден: $CSV_FILE"
    exit 1
fi

if [ ! -d "$IMAGES_FOLDER" ]; then
    echo "❌ Папка с изображениями не найдена: $IMAGES_FOLDER"
    exit 1
fi

# Опционально запрашиваем количество товаров
if [ -z "$MAX_COUNT" ]; then
    read -p "🔢 Введите максимальное количество товаров для загрузки (пусто = все): " MAX_COUNT
fi

# Запрашиваем режим загрузки
read -p "📦 Использовать пакетную загрузку? (y/n, по умолчанию: y): " USE_BATCH
USE_BATCH=${USE_BATCH:-y}

# Размер пакета
BATCH_SIZE=100
if [[ "$USE_BATCH" == "y" || "$USE_BATCH" == "Y" ]]; then
    read -p "📊 Введите размер пакета (по умолчанию: 100): " BATCH_INPUT
    if [ ! -z "$BATCH_INPUT" ]; then
        BATCH_SIZE=$BATCH_INPUT
    fi
fi

# Режим обновления
read -p "⚙️ Режим обновления (all/images/description/missing, по умолчанию: all): " UPDATE_MODE
UPDATE_MODE=${UPDATE_MODE:-all}

# Пропуск существующих товаров
read -p "⏭️ Пропускать существующие товары? (y/n, по умолчанию: y): " SKIP_EXISTING
SKIP_EXISTING=${SKIP_EXISTING:-y}

echo ""
echo "🚀 Запуск GUI загрузчика FIFU..."
echo "   Python: $(which python)"
echo "   Версия: $(python --version)"
echo ""

# Запускаем GUI загрузчик
python run_fifu.py

# Сохраняем код выхода
exit_code=$?

echo ""
echo "========================================"
if [ $exit_code -eq 0 ]; then
    echo "✅ Скрипт завершен успешно!"
else
    echo "❌ Скрипт завершился с ошибкой (код: $exit_code)"
fi
echo "Нажмите Enter для выхода..."
read 