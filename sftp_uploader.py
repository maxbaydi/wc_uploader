#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SFTP Image Uploader
Модуль для загрузки изображений на удаленный SFTP сервер
"""

import os
import paramiko
import time
import shutil
from pathlib import Path
import logging
import requests
import unicodedata
import re

def sftp_path_join(*parts):
    """
    Создает путь для SFTP с прямыми слешами, независимо от операционной системы
    
    Args:
        *parts: Части пути
        
    Returns:
        str: Путь с прямыми слешами
    """
    # Фильтруем пустые части и нормализуем слеши
    filtered_parts = [part.strip('/') for part in parts if part and part.strip('/')]
    
    if not filtered_parts:
        return '/'
    
    # Собираем путь с прямыми слешами
    result = '/' + '/'.join(filtered_parts)
    
    # Убираем двойные слеши
    result = re.sub(r'/+', '/', result)
    
    return result

class SFTPImageUploader:
    def __init__(self, host, port, username, password, remote_base_path='/var/www/mytua.com/images', web_domain=None):
        """
        Инициализация загрузчика SFTP изображений
        
        Args:
            host: Хост SFTP сервера
            port: Порт SFTP сервера
            username: Имя пользователя
            password: Пароль
            remote_base_path: Базовый путь на сервере для загрузки изображений
            web_domain: Домен для формирования URL (если None, будет определен автоматически)
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.remote_base_path = remote_base_path
        
        # Определяем веб-домен для формирования URL
        if web_domain:
            self.web_domain = web_domain
        else:
            # Автоматически определяем домен из remote_base_path
            self.web_domain = self._extract_domain_from_path(remote_base_path)
        
        self.ssh = None
        self.sftp = None
        self.connected = False
        
        self.log_callback = None
        
    def _extract_domain_from_path(self, remote_base_path):
        """
        Извлекает домен из пути на сервере
        
        Args:
            remote_base_path: Путь вида /var/www/domain.com/folder
            
        Returns:
            str: Домен (например, domain.com)
        """
        import re
        # Ищем паттерн /var/www/domain.com или similar
        pattern = r'/var/www/([^/]+)'
        match = re.search(pattern, remote_base_path)
        if match:
            return match.group(1)
        else:
            # Фолбек - используем хост SFTP сервера
            return self.host
            
    def clean_filename(self, filename):
        """
        Очистка имени файла от специальных символов для безопасной загрузки на сервер
        
        Args:
            filename: Исходное имя файла
            
        Returns:
            str: Очищенное имя файла
        """
        if not filename:
            return ""
            
        # Нормализуем Unicode символы
        filename = unicodedata.normalize('NFD', filename)
        
        # Заменяем кириллические символы на латинские аналоги
        cyrillic_to_latin = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
            'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
            'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
            'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
            'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
            'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'E',
            'Ж': 'ZH', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
            'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
            'Ф': 'F', 'Х': 'H', 'Ц': 'TS', 'Ч': 'CH', 'Ш': 'SH', 'Щ': 'SCH',
            'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'YU', 'Я': 'YA'
        }
        
        for cyrillic, latin in cyrillic_to_latin.items():
            filename = filename.replace(cyrillic, latin)
        
        # Заменяем пробелы на подчеркивания
        filename = filename.replace(' ', '_')
        
        # Заменяем запятые на подчеркивания
        filename = filename.replace(',', '_')
        
        # Удаляем все символы, кроме букв, цифр, дефисов, подчеркиваний и точек
        filename = re.sub(r'[^a-zA-Z0-9\-_\.]', '', filename)
        
        # Убираем множественные подчеркивания
        filename = re.sub(r'_+', '_', filename)
        
        # Убираем подчеркивания в начале и конце
        filename = filename.strip('_')
        
        # Если имя файла пустое, возвращаем 'image'
        if not filename:
            filename = 'image'
            
        return filename
        
    def set_log_callback(self, callback):
        """Установить callback для логирования"""
        self.log_callback = callback
        # Теперь можно логировать веб-домен
        self.log(f"🌐 Используемый веб-домен для URL: {self.web_domain}")
        
    def log(self, message):
        """Логирование сообщения"""
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)
    
    def connect(self):
        """
        Подключение к SFTP серверу
        
        Returns:
            bool: Успешность подключения
        """
        try:
            self.log(f"🔌 Подключение к серверу {self.host}:{self.port}...")
            
            # Создаем соединение SSH
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=10
            )
            
            # Открываем SFTP сессию
            self.sftp = self.ssh.open_sftp()
            
            # Проверка соединения
            self.sftp.chdir('.')  # Проверяем текущую директорию
            self.connected = True
            
            self.log(f"✅ Подключение к SFTP серверу установлено")
            
            # Проверяем/создаем базовую директорию для изображений
            self.ensure_remote_directory(self.remote_base_path)
            
            return True
            
        except Exception as e:
            self.log(f"❌ Ошибка подключения к SFTP серверу: {str(e)}")
            self.disconnect()
            return False
            
    def disconnect(self):
        """Отключение от SFTP сервера"""
        try:
            if self.sftp:
                self.sftp.close()
                self.sftp = None
                
            if self.ssh:
                self.ssh.close()
                self.ssh = None
                
            self.connected = False
            self.log("🔌 Отключение от SFTP сервера")
            
        except Exception as e:
            self.log(f"⚠️ Ошибка при отключении от SFTP сервера: {str(e)}")
            
    def ensure_remote_directory(self, remote_path):
        """
        Проверяет наличие директории на сервере, при необходимости создает
        
        Args:
            remote_path: Путь на удаленном сервере
            
        Returns:
            bool: True если директория существует или создана, False в случае ошибки
        """
        if not self.connected or not self.sftp or not self.ssh:
            self.log("❌ Нет активного SFTP-соединения")
            return False
            
        try:
            # Создаем путь к директории поэтапно
            path_parts = remote_path.strip('/').split('/')
            current_path = '/'
            
            self.log(f"🔍 Создание директории поэтапно:")
            self.log(f"   - Исходный путь: {remote_path}")
            self.log(f"   - Части пути: {path_parts}")
            
            for part in path_parts:
                if not part:  # Пропускаем пустые части
                    continue
                    
                current_path = sftp_path_join(current_path, part)
                self.log(f"   - Текущий путь: {current_path}")
                
                try:
                    # Проверяем существование директории
                    self.sftp.stat(current_path)
                except IOError:
                    # Директория не существует, создаем
                    self.log(f"📁 Создание директории: {current_path}")
                    try:
                        # Используем непосредственно SFTP для создания директории
                        self.sftp.mkdir(current_path)
                        self.log(f"✅ Директория создана через SFTP: {current_path}")
                    except IOError as e:
                        self.log(f"⚠️ Ошибка создания через SFTP: {str(e)}, пробуем через SSH")
                        # Если не удалось через SFTP, пробуем через SSH команду
                        stdin, stdout, stderr = self.ssh.exec_command(f"mkdir -p {current_path}")
                        exit_status = stdout.channel.recv_exit_status()
                        
                        if exit_status == 0:
                            self.log(f"✅ Директория создана через SSH: {current_path}")
                        else:
                            error = stderr.read().decode()
                            self.log(f"❌ Ошибка создания директории через SSH: {error}")
                            return False
            
            # Проверяем финальный результат
            try:
                self.sftp.stat(remote_path)
                self.log(f"✅ Директория подтверждена: {remote_path}")
                return True
            except IOError:
                self.log(f"❌ Не удалось подтвердить существование директории: {remote_path}")
                return False
                
        except Exception as e:
            self.log(f"❌ Ошибка при проверке/создании директории: {str(e)}")
            return False
            
    def _generate_image_url(self, remote_directory, filename):
        """
        Формирует URL для доступа к загруженному изображению
        
        Args:
            remote_directory: Относительная директория (например, 'products')
            filename: Имя файла
            
        Returns:
            str: URL для доступа к изображению
        """
        # Определяем путь относительно веб-корня
        web_path = self._get_web_path(remote_directory, filename)
        url = f"https://{self.web_domain}{web_path}"
        return url
        
    def _get_web_path(self, remote_directory, filename):
        """
        Определяет веб-путь к файлу на основе структуры SFTP
        
        Args:
            remote_directory: Относительная директория
            filename: Имя файла
            
        Returns:
            str: Путь для веб-доступа (например, /images/products/file.jpg)
        """
        # Анализируем remote_base_path чтобы понять структуру
        # Например: /var/www/mytua.com/itexport/images -> /itexport/images
        # Или: /var/www/domain.com/images -> /images
        
        import re
        # Ищем все после /var/www/domain.com/
        pattern = rf'/var/www/{re.escape(self.web_domain)}/?(.*)'
        match = re.search(pattern, self.remote_base_path)
        
        if match:
            web_root_path = match.group(1)
            if web_root_path:
                web_path = sftp_path_join('/', web_root_path, remote_directory, filename)
            else:
                web_path = sftp_path_join('/', remote_directory, filename)
        else:
            # Фолбек - используем стандартную структуру
            web_path = sftp_path_join('/', 'images', remote_directory, filename)
        
        return web_path
            
    def file_exists_on_server(self, remote_path):
        """
        Проверка существования файла на сервере
        
        Args:
            remote_path: Полный путь к файлу на сервере
            
        Returns:
            bool: True если файл существует
        """
        try:
            self.sftp.stat(remote_path)
            return True
        except IOError:
            return False
    
    def get_local_file_size(self, local_file_path):
        """
        Получение размера локального файла
        
        Args:
            local_file_path: Путь к локальному файлу
            
        Returns:
            int: Размер файла в байтах или 0
        """
        try:
            return os.path.getsize(local_file_path)
        except OSError:
            return 0
    
    def get_remote_file_size(self, remote_path):
        """
        Получение размера удаленного файла
        
        Args:
            remote_path: Полный путь к файлу на сервере
            
        Returns:
            int: Размер файла в байтах или 0
        """
        try:
            file_stat = self.sftp.stat(remote_path)
            return file_stat.st_size
        except IOError:
            return 0

    def upload_file(self, local_file_path, remote_directory, rename_to=None, force_upload=False):
        """
        Загрузка файла на сервер с проверкой дубликатов
        
        Args:
            local_file_path: Локальный путь к файлу
            remote_directory: Удаленная директория для загрузки (относительно базовой)
            rename_to: Новое имя для файла (None = оставить оригинальное)
            force_upload: Принудительная загрузка (игнорировать проверку дубликатов)
            
        Returns:
            str: URL загруженного изображения или None в случае ошибки
        """
        if not self.connected:
            self.log("❌ Нет активного SFTP-соединения")
            if not self.connect():
                return None
            
        try:
            self.log(f"🔍 Начинаем загрузку файла: {local_file_path}")
            self.log(f"📁 Целевая директория: {remote_directory}")
            self.log(f"🏷️ Переименовать в: {rename_to}")
            
            # Проверяем существование локального файла
            local_file_path = os.path.abspath(local_file_path)
            if not os.path.exists(local_file_path):
                self.log(f"❌ Локальный файл не найден: {local_file_path}")
                return None
            
            local_file_size = os.path.getsize(local_file_path)
            self.log(f"📊 Размер локального файла: {local_file_size} байт")
            
            # Сохраняем исходное имя файла
            original_filename = os.path.basename(local_file_path)
                
            # Формируем полный путь к удаленной директории
            remote_dir_full = sftp_path_join(self.remote_base_path, remote_directory)
            self.log(f"📁 Полный путь к директории на сервере: {remote_dir_full}")
            self.log(f"🔍 Отладочная информация:")
            self.log(f"   - remote_base_path: {self.remote_base_path}")
            self.log(f"   - remote_directory: {remote_directory}")
            self.log(f"   - Результат sftp_path_join: {remote_dir_full}")
            
            # Проверяем/создаем удаленную директорию
            if not self.ensure_remote_directory(remote_dir_full):
                self.log(f"❌ Не удалось создать директорию на сервере: {remote_dir_full}")
                return None
            else:
                self.log(f"✅ Директория на сервере подтверждена: {remote_dir_full}")
                
            # Определяем имя файла
            if rename_to:
                remote_filename = self.clean_filename(rename_to)
            else:
                # Очищаем оригинальное имя файла
                name_without_ext = os.path.splitext(original_filename)[0]
                ext = os.path.splitext(original_filename)[1]
                clean_name = self.clean_filename(name_without_ext)
                remote_filename = clean_name + ext
            
            # Полный путь на удаленном сервере
            remote_path = sftp_path_join(remote_dir_full, remote_filename)
            self.log(f"📍 Полный путь к файлу на сервере: {remote_path}")
            self.log(f"🔍 Отладочная информация для файла:")
            self.log(f"   - remote_dir_full: {remote_dir_full}")
            self.log(f"   - remote_filename: {remote_filename}")
            self.log(f"   - Результат sftp_path_join: {remote_path}")
            
            # Проверяем существование файла на сервере
            file_exists = self.file_exists_on_server(remote_path)
            self.log(f"🔍 Файл существует на сервере: {file_exists}")
            self.log(f"🔍 Проверяем путь: {remote_path}")
            
            # Определяем, нужно ли перезаписывать файл
            should_overwrite = False
            if file_exists:
                if force_upload:
                    self.log("🔄 Принудительная перезапись файла включена.")
                    should_overwrite = True
                else:
                    # Сравниваем размеры, чтобы определить, нужна ли перезапись
                    local_size = self.get_local_file_size(local_file_path)
                    remote_size = self.get_remote_file_size(remote_path)
                    
                    if local_size != remote_size:
                        self.log(f"⚠️ Размеры файлов отличаются (локальный: {local_size}, удаленный: {remote_size}). Файл будет перезаписан.")
                        should_overwrite = True
                    else:
                        # Файл идентичен, пропускаем загрузку
                        self.log(f"⏭️ Файл уже существует на сервере и имеет тот же размер. Пропускаем.")
                        image_url = self._generate_image_url(remote_directory, remote_filename)
                        return image_url
            else:
                # Если файла не существует, его нужно создать
                should_overwrite = True

            # Если файл существует и его нужно перезаписать, сначала удаляем его
            if file_exists and should_overwrite:
                try:
                    self.log(f"🗑️ Удаляем старую версию файла: {remote_path}")
                    self.sftp.remove(remote_path)
                    self.log(f"✅ Старая версия файла удалена.")
                except IOError as e:
                    self.log(f"⚠️ Не удалось удалить старый файл (возможно, это не критично): {e}")

            # Загружаем файл, если это необходимо
            if should_overwrite:
                self.log(f"📤 Загрузка файла: {remote_filename} -> {remote_path}")
            
                # Проверяем, что у нас есть активная SFTP сессия
                if not self.sftp:
                    self.log(f"❌ Нет активной SFTP сессии, пытаемся переподключиться")
                    if not self.connect():
                        return None
                
                try:
                    self.log(f"🔄 Начинаем загрузку файла через SFTP...")
                    self.log(f"   - Локальный файл для загрузки: {local_file_path}")
                    self.log(f"   - Удаленный путь: {remote_path}")
                    
                    # Пробуем загрузить файл
                    self.sftp.put(local_file_path, remote_path)
                    self.log(f"✅ Файл успешно передан через SFTP")
                    
                    # Устанавливаем права доступа 644 (rw-r--r--)
                    self.sftp.chmod(remote_path, 0o644)
                    self.log(f"✅ Права доступа установлены: 644")
                    
                    # Проверяем, что файл действительно загружен
                    file_stat = self.sftp.stat(remote_path)
                    if file_stat.st_size == 0:
                        self.log(f"⚠️ Предупреждение: загруженный файл имеет нулевой размер")
                    
                    self.log(f"✅ Файл загружен успешно (размер: {file_stat.st_size} байт)")
                    
                except Exception as e:
                    self.log(f"❌ Ошибка при загрузке файла через SFTP: {str(e)}")
                    return None
            
            # Формируем URL для доступа к файлу
            image_url = self._generate_image_url(remote_directory, remote_filename)
            self.log(f"✅ URL изображения: {image_url}")
            
            return image_url
            
        except Exception as e:
            self.log(f"❌ Ошибка при загрузке файла: {str(e)}")
            # При ошибке пытаемся переподключиться для следующей операции
            self.disconnect()
            return None
            
    def upload_directory(self, local_directory, remote_directory=None):
        """
        Загрузка всей директории на сервер
        
        Args:
            local_directory: Локальная директория с файлами
            remote_directory: Удаленная директория (None = использовать имя локальной директории)
            
        Returns:
            dict: Словарь {имя_файла: url_изображения}
        """
        if not os.path.isdir(local_directory):
            self.log(f"❌ Указанная директория не существует: {local_directory}")
            return {}
            
        # Если удаленная директория не указана, используем имя локальной директории
        if remote_directory is None:
            remote_directory = os.path.basename(os.path.normpath(local_directory))
            
        self.log(f"📁 Начинаем загрузку директории: {local_directory} -> {remote_directory}")
        
        if not self.connected:
            if not self.connect():
                return {}
                
        results = {}
        total_files = 0
        uploaded_files = 0
        
        # Собираем все файлы для загрузки
        files_to_upload = []
        for root, _, files in os.walk(local_directory):
            for filename in files:
                # Пропускаем скрытые файлы и файлы без расширения
                if filename.startswith('.') or '.' not in filename:
                    continue
                
                # Проверяем расширение файла (только изображения)
                ext = os.path.splitext(filename)[1].lower()
                if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                    continue
                    
                local_file_path = os.path.join(root, filename)
                # Относительный путь для сохранения структуры каталогов
                rel_path = os.path.relpath(root, local_directory)
                rel_remote_dir = remote_directory
                
                if rel_path != '.':
                    # Если не в корневой директории, добавляем подпуть
                    rel_remote_dir = sftp_path_join(remote_directory, rel_path)
                    
                files_to_upload.append((local_file_path, rel_remote_dir, filename))
                total_files += 1
        
        # Загружаем все файлы
        for idx, (local_file_path, rel_remote_dir, filename) in enumerate(files_to_upload, 1):
            self.log(f"[{idx}/{total_files}] Загрузка {filename}")
            url = self.upload_file(local_file_path, rel_remote_dir)
            
            if url:
                results[filename] = url
                uploaded_files += 1
                
        self.log(f"📊 Загрузка директории завершена: {uploaded_files}/{total_files} файлов загружено")
        return results

# Пример использования
if __name__ == "__main__":
    # Конфигурация
    config = {
        'host': 'bf6baca11842.vps.myjino.ru',
        'port': 49181,
        'username': 'root',
        'password': 'dKX-wGM-RYw-jDH',
        'remote_base_path': '/var/www/mytua.com/images'
    }
    
    uploader = SFTPImageUploader(**config)
    
    # Пример загрузки одного файла
    if uploader.connect():
        # Загрузка одного файла
        url = uploader.upload_file('example.jpg', 'products')
        print(f"Загруженный файл: {url}")
        
        # Загрузка всей директории
        results = uploader.upload_directory('images/products')
        print(f"Загружено файлов: {len(results)}")
        
        uploader.disconnect()