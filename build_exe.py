#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Скрипт для сборки WooCommerce Uploader в exe файл
Использует PyInstaller для создания автономного исполняемого файла
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def install_pyinstaller():
    """Устанавливает PyInstaller если не установлен"""
    try:
        import PyInstaller
        print("✅ PyInstaller уже установлен")
    except ImportError:
        print("📦 Устанавливаем PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("✅ PyInstaller установлен")

def create_spec_file():
    """Создает spec файл для PyInstaller"""
    spec_content = '''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['gui_fifu.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('gui_settings.json', '.'),
        ('gui_settings_huatech.json', '.'),
        ('gui_settings_itexport.json', '.'),
        ('config.py', '.'),
        ('*.py', '.'),
    ],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'tkinter.scrolledtext',
        'pandas',
        'numpy',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'paramiko',
        'woocommerce',
        'requests',
        'json',
        'threading',
        'queue',
        'datetime',
        'os',
        'sys',
        'pathlib',
        'ttkbootstrap',
        'tkinter_tooltip',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='WooCommerce-Uploader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
'''
    
    with open('WooCommerce-Uploader.spec', 'w', encoding='utf-8') as f:
        f.write(spec_content)
    
    print("✅ Создан spec файл: WooCommerce-Uploader.spec")

def build_exe():
    """Собирает exe файл"""
    print("🔨 Начинаем сборку exe файла...")
    
    # Очищаем предыдущие сборки
    if os.path.exists('build'):
        shutil.rmtree('build')
    if os.path.exists('dist'):
        shutil.rmtree('dist')
    
    # Запускаем PyInstaller
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        "WooCommerce-Uploader.spec"
    ]
    
    print(f"🚀 Выполняем команду: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    
    if result.returncode == 0:
        print("✅ Сборка завершена успешно!")
        print(f"📁 Exe файл создан в: {os.path.abspath('dist')}")
        
        # Проверяем размер файла
        exe_path = os.path.join('dist', 'WooCommerce-Uploader.exe')
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"📊 Размер exe файла: {size_mb:.1f} МБ")
    else:
        print("❌ Ошибка при сборке:")
        print(result.stderr)
        return False
    
    return True

def create_installer_script():
    """Создает bat файл для установки зависимостей"""
    bat_content = '''@echo off
echo Установка зависимостей для WooCommerce Uploader...
echo.

REM Проверяем наличие Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ОШИБКА: Python не найден! Установите Python 3.8+ с сайта python.org
    pause
    exit /b 1
)

echo Python найден. Устанавливаем зависимости...

REM Устанавливаем зависимости
pip install -r requirements.txt

if errorlevel 1 (
    echo ОШИБКА: Не удалось установить зависимости!
    pause
    exit /b 1
)

echo.
echo ✅ Зависимости установлены успешно!
echo Теперь можно запустить WooCommerce-Uploader.exe
pause
'''
    
    with open('install_dependencies.bat', 'w', encoding='utf-8') as f:
        f.write(bat_content)
    
    print("✅ Создан bat файл для установки зависимостей: install_dependencies.bat")

def create_readme_exe():
    """Создает README для exe версии"""
    readme_content = '''# WooCommerce Uploader - Exe версия

## 🚀 Запуск

1. Запустите файл `WooCommerce-Uploader.exe`
2. При первом запуске может потребоваться время для инициализации

## ⚙️ Настройка

### Первый запуск
1. Откройте настройки в программе
2. Укажите данные вашего WooCommerce сайта:
   - URL сайта
   - Consumer Key
   - Consumer Secret
3. Настройте SFTP параметры для загрузки изображений
4. Сохраните настройки

### Файлы настроек
Программа использует следующие файлы настроек:
- `gui_settings.json` - основные настройки
- `gui_settings_huatech.json` - настройки для Huatech
- `gui_settings_itexport.json` - настройки для ITExport

## 📋 Требования

- Windows 7/8/10/11
- Интернет соединение
- WooCommerce сайт с API доступом
- SFTP сервер (опционально)

## 🔧 Устранение неисправностей

### Программа не запускается
1. Убедитесь, что у вас Windows 7 или новее
2. Проверьте, что антивирус не блокирует программу
3. Запустите от имени администратора

### Ошибки подключения
1. Проверьте интернет соединение
2. Убедитесь в корректности настроек WooCommerce
3. Проверьте доступность SFTP сервера

### Проблемы с изображениями
1. Убедитесь в корректности SFTP настроек
2. Проверьте права доступа на SFTP сервере
3. Убедитесь в доступности веб-сервера

## 📞 Поддержка

При возникновении проблем:
1. Проверьте логи в папке с программой
2. Убедитесь в корректности всех настроек
3. Обратитесь к разработчику с описанием проблемы

## 📄 Лицензия

MIT License
'''
    
    with open('README-EXE.md', 'w', encoding='utf-8') as f:
        f.write(readme_content)
    
    print("✅ Создан README для exe версии: README-EXE.md")

def main():
    """Основная функция"""
    print("🚀 WooCommerce Uploader - Сборка exe файла")
    print("=" * 50)
    
    try:
        # Устанавливаем PyInstaller
        install_pyinstaller()
        
        # Создаем spec файл
        create_spec_file()
        
        # Собираем exe
        if build_exe():
            # Создаем дополнительные файлы
            create_installer_script()
            create_readme_exe()
            
            print("\n🎉 Сборка завершена успешно!")
            print("📁 Файлы созданы в папке dist/")
            print("📋 Дополнительные файлы:")
            print("   - install_dependencies.bat")
            print("   - README-EXE.md")
            print("\n💡 Для распространения скопируйте папку dist/")
        else:
            print("❌ Сборка не удалась!")
            return 1
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
