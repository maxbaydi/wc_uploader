@echo off
chcp 65001 >nul
echo 🚀 WooCommerce Uploader - Сборка exe файла
echo ================================================
echo.

REM Проверяем наличие Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ ОШИБКА: Python не найден!
    echo Установите Python 3.8+ с сайта python.org
    pause
    exit /b 1
)

echo ✅ Python найден
echo.

REM Устанавливаем PyInstaller если нужно
echo 📦 Проверяем PyInstaller...
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo Устанавливаем PyInstaller...
    pip install pyinstaller
    if errorlevel 1 (
        echo ❌ ОШИБКА: Не удалось установить PyInstaller!
        pause
        exit /b 1
    )
) else (
    echo ✅ PyInstaller уже установлен
)

echo.

REM Очищаем предыдущие сборки
echo 🧹 Очищаем предыдущие сборки...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist *.spec del *.spec

echo.

REM Запускаем сборку
echo 🔨 Начинаем сборку...
python -m PyInstaller --clean --noconfirm --onefile --windowed --name "WooCommerce-Uploader" gui_fifu.py

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
echo 🎉 Готово! Exe файл находится в папке dist/
echo 💡 Для распространения скопируйте файл WooCommerce-Uploader.exe
pause
