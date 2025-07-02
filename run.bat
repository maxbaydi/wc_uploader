@echo off
title WooCommerce Product Uploader

echo ==============================================
echo WooCommerce Product Uploader
echo ==============================================
echo.

REM Проверка Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден. Установите Python с python.org
    pause
    exit /b 1
)

echo ✓ Python найден
echo.

REM Переход в директорию скрипта
cd /d "%~dp0"

REM Установка зависимостей
echo Установка зависимостей...
python -m pip install -r requirements.txt

if errorlevel 1 (
    echo ❌ Ошибка установки зависимостей
    pause
    exit /b 1
)

echo ✓ Зависимости установлены
echo.

REM Запуск приложения
echo Запуск WooCommerce Product Uploader...
echo.

python main.py

echo.
echo Программа завершена
pause
