@echo off
chcp 65001 >nul
echo 🚀 WooCommerce Uploader - Финальная сборка exe
echo ================================================
echo.

REM Проверяем наличие Python
py --version >nul 2>&1
if errorlevel 1 (
    echo ❌ ОШИБКА: Python не найден!
    echo Установите Python 3.8+ с сайта python.org
    pause
    exit /b 1
)

echo ✅ Python найден
echo.

REM Устанавливаем зависимости если нужно
echo 📦 Проверяем зависимости...
py -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo Устанавливаем PyInstaller...
    py -m pip install pyinstaller
)

py -c "import pandas" >nul 2>&1
if errorlevel 1 (
    echo Устанавливаем pandas...
    py -m pip install --only-binary=all pandas
)

py -c "import numpy" >nul 2>&1
if errorlevel 1 (
    echo Устанавливаем numpy...
    py -m pip install --only-binary=all numpy
)

py -c "import PIL" >nul 2>&1
if errorlevel 1 (
    echo Устанавливаем Pillow...
    py -m pip install --only-binary=all pillow
)

echo ✅ Все зависимости установлены
echo.

REM Очищаем предыдущие сборки
echo 🧹 Очищаем предыдущие сборки...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist *.spec del *.spec

echo.

REM Запускаем сборку с полным набором файлов
echo 🔨 Начинаем финальную сборку...
py -m PyInstaller ^
    --onefile ^
    --windowed ^
    --add-data "gui_settings.json;." ^
    --add-data "gui_settings_huatech.json;." ^
    --add-data "gui_settings_itexport.json;." ^
    --name "WooCommerce-Uploader" ^
    gui_fifu.py

if errorlevel 1 (
    echo ❌ ОШИБКА: Сборка не удалась!
    echo Проверьте логи выше
    pause
    exit /b 1
)

echo.
echo ✅ Сборка завершена успешно!
echo 📁 Exe файл создан в папке dist/

REM Проверяем размер файла
if exist "dist\WooCommerce-Uploader.exe" (
    for %%A in ("dist\WooCommerce-Uploader.exe") do (
        set /a size=%%~zA/1024/1024
        echo 📊 Размер exe файла: !size! МБ
    )
)

echo.
echo 🎉 Готово! Exe файл готов к распространению
echo 💡 Файл: dist\WooCommerce-Uploader.exe
echo 📋 Включенные файлы настроек:
echo    - gui_settings.json
echo    - gui_settings_huatech.json  
echo    - gui_settings_itexport.json
pause
