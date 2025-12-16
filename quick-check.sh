#!/bin/bash

# Быстрая проверка готовности WooCommerce Uploader AppImage

echo "⚡ Быстрая проверка WooCommerce Uploader"
echo "========================================"

# Быстрые проверки
checks_passed=0
checks_total=0

# 1. AppImage файл
((checks_total++))
if [ -f "WooCommerce-Uploader-x86_64.AppImage" ]; then
    echo "✅ AppImage файл найден"
    ((checks_passed++))
else
    echo "❌ AppImage файл не найден"
fi

# 2. Права на исполнение
((checks_total++))
if [ -x "WooCommerce-Uploader-x86_64.AppImage" ]; then
    echo "✅ Права на исполнение установлены"
    ((checks_passed++))
else
    echo "❌ Нет прав на исполнение"
fi

# 3. Размер файла
((checks_total++))
FILE_SIZE=$(stat -c%s "WooCommerce-Uploader-x86_64.AppImage" 2>/dev/null || stat -f%z "WooCommerce-Uploader-x86_64.AppImage" 2>/dev/null)
if [ "$FILE_SIZE" -gt 50000000 ]; then  # Минимум 50MB для приложения с зависимостями
    FILE_SIZE_MB=$((FILE_SIZE / 1000000))
    echo "✅ Размер файла корректный ($FILE_SIZE_MB MB)"
    ((checks_passed++))
elif [ "$FILE_SIZE" -gt 5000000 ]; then  # Минимум 5MB для базового приложения
    FILE_SIZE_MB=$((FILE_SIZE / 1000000))
    echo "⚠️ Размер файла маловат ($FILE_SIZE_MB MB)"
    ((checks_passed++))
else
    echo "❌ Размер файла слишком мал ($FILE_SIZE байт)"
fi

# 4. Python3
((checks_total++))
if command -v python3 >/dev/null 2>&1; then
    echo "✅ Python3 найден"
    ((checks_passed++))
else
    echo "❌ Python3 не найден"
fi

# 5. tkinter
((checks_total++))
if python3 -c "import tkinter" >/dev/null 2>&1; then
    echo "✅ tkinter найден"
    ((checks_passed++))
else
    echo "❌ tkinter не найден"
fi

# 6. Графическое окружение
((checks_total++))
if [ -n "$DISPLAY" ]; then
    echo "✅ Графическое окружение обнаружено"
    ((checks_passed++))
else
    echo "❌ Графическое окружение не обнаружено"
fi

echo ""
echo "📊 Результат: $checks_passed/$checks_total проверок пройдено"

if [ $checks_passed -eq $checks_total ]; then
    echo ""
    echo "🎉 Все проверки пройдены! AppImage готов к запуску."
    echo ""
    echo "🚀 Для запуска:"
    echo "   ./WooCommerce-Uploader-x86_64.AppImage"
    echo ""
    echo "💡 Если двойной клик не работает:"
    echo "   • Убедитесь, что файл отмечен как исполняемый"
    echo "   • Попробуйте запуск из терминала"
    echo "   • Проверьте логи: ./WooCommerce-Uploader-x86_64.AppImage 2>&1 | tee log.txt"
else
    echo ""
    echo "⚠️ Некоторые проверки не пройдены."
    echo ""
    echo "🔧 Для подробной диагностики:"
    echo "   ./debug-appimage.sh"
    echo ""
    echo "📖 Для решения проблем:"
    echo "   cat AppImage-README.md | grep -A 10 -B 2 'Решение'"
fi

echo ""
echo "========================================"
