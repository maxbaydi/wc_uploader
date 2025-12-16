#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WooCommerce ExtraURL Uploader - GUI
Графический интерфейс для загрузчика товаров с поддержкой плагина ExtraURL и загрузкой изображений на SFTP
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import threading
import json
import queue
from datetime import datetime
from woocommerce_fifu_uploader import WooCommerceFIFUUploader
from config import WOOCOMMERCE_CONFIG, SFTP_CONFIG
import pandas as pd
from csv_adapter import CSVAdapter
from image_downloader import ImageDownloader
from ai_description_generator import AIDescriptionGenerator

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gui_settings.json')
DEFAULT_DIALOG_DIR = os.path.expanduser("~")
CSV_FILETYPES = [("CSV файлы", "*.csv"), ("Все файлы", "*.*")]
IMAGE_FILETYPES = [
    ("Изображения", "*.jpg *.jpeg *.png *.gif *.webp"),
    ("JPEG", "*.jpg *.jpeg"),
    ("PNG", "*.png"),
    ("GIF", "*.gif"),
    ("WebP", "*.webp"),
    ("Все файлы", "*.*")
]


class ScrollableFrame(ttk.Frame):
    """Фрейм с вертикальной прокруткой"""
    
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        
        # Создаем canvas и scrollbar
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        # Настраиваем прокрутку
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        # Создаем окно в canvas
        self.canvas_frame = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        # Привязываем прокрутку
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # Размещаем элементы
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        # Включаем глобальные бинды колесика с проверкой принадлежности виджетов
        self._bind_mousewheel()

        # Обновляем размер canvas при изменении размера фрейма
        self.bind("<Configure>", self._on_frame_configure)
        
    def _on_frame_configure(self, event):
        """Обновляет ширину canvas при изменении размера фрейма"""
        canvas_width = event.width - self.scrollbar.winfo_reqwidth()
        self.canvas.configure(width=canvas_width)
        self.canvas.itemconfig(self.canvas_frame, width=canvas_width)
        # Подгоняем высоту содержимого под доступную область, чтобы оно могло растягиваться
        self.canvas.itemconfig(self.canvas_frame, height=event.height)
        
    def _bind_mousewheel(self, _event=None):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self.canvas.bind_all("<Button-4>", self._on_mousewheel, add="+")
        self.canvas.bind_all("<Button-5>", self._on_mousewheel, add="+")

    def _is_descendant(self, widget):
        while widget:
            if widget is self:
                return True
            widget = widget.master
        return False

    def _on_mousewheel(self, event):
        """Обработка прокрутки колесом мыши"""
        delta = 0
        if event.delta:
            delta = int(-event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1)
        elif event.num in (4, 5):
            delta = -1 if event.num == 4 else 1

        if not delta:
            return

        target = self.winfo_containing(event.x_root, event.y_root)

        # Если колесо над вложенным текстовым виджетом — прокручиваем его, а не весь canvas
        if target and self._is_descendant(target):
            if hasattr(target, "yview_scroll"):
                target.yview_scroll(delta, "units")
                return "break"

            # Если событие на дочернем виджете, но без собственной прокрутки — прокручиваем canvas
            if self._has_vertical_overflow():
                self.canvas.yview_scroll(delta, "units")
                return "break"

        # Если колесо крутится вне дочерних или в пустой зоне — скроллим только при переполнении
        if self._has_vertical_overflow():
            self.canvas.yview_scroll(delta, "units")
            return "break"

    def _has_vertical_overflow(self) -> bool:
        """Проверяет, превышает ли содержимое видимую область canvas по высоте."""
        bbox = self.canvas.bbox("all")
        if not bbox:
            return False
        _, y1, _, y2 = bbox
        content_height = y2 - y1
        view_height = self.canvas.winfo_height()
        return content_height > view_height + 2  # небольшой запас


class UploaderGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("WooCommerce Uploader")
        self.root.geometry("900x500")
        self.root.minsize(800, 600)
        self.root.maxsize(1200, 1100)  # Максимальный размер окна
        
        # Переменные для файлов и папок
        self.csv_file_path = tk.StringVar()
        self.images_folder_path = tk.StringVar()
        self.products_count = tk.StringVar(value="all")
        self.custom_count = tk.IntVar(value=10)
        
        # Переменные для SSH (читаем из конфига)
        self.ssh_host = tk.StringVar(value=SFTP_CONFIG.get('host', 'localhost'))
        self.ssh_port = tk.IntVar(value=SFTP_CONFIG.get('port', 22))
        self.ssh_username = tk.StringVar(value=SFTP_CONFIG.get('username', ''))
        self.ssh_password = tk.StringVar(value=SFTP_CONFIG.get('password', ''))
        self.ssh_remote_path = tk.StringVar(value=SFTP_CONFIG.get('remote_base_path', '/tmp'))
        self.ssh_web_domain = tk.StringVar(value=SFTP_CONFIG.get('web_domain', 'localhost'))
        
        # Переменные для WooCommerce (читаем из конфига)
        self.wc_url = tk.StringVar(value=WOOCOMMERCE_CONFIG.get('url', 'http://localhost'))
        self.wc_consumer_key = tk.StringVar(value=WOOCOMMERCE_CONFIG.get('consumer_key', ''))
        self.wc_consumer_secret = tk.StringVar(value=WOOCOMMERCE_CONFIG.get('consumer_secret', ''))
        self.wc_timeout = tk.IntVar(value=WOOCOMMERCE_CONFIG.get('timeout', 30))
        self.wp_username = tk.StringVar(value=WOOCOMMERCE_CONFIG.get('wp_username', ''))
        self.wp_app_password = tk.StringVar(value=WOOCOMMERCE_CONFIG.get('wp_app_password', ''))
        self.wp_email = tk.StringVar(value=WOOCOMMERCE_CONFIG.get('wp_email', ''))
        
        # Переменная для использования SFTP
        self.use_fifu = tk.BooleanVar(value=True)
        
        # Переменная для использования заглушки
        self.use_placeholder = tk.BooleanVar(value=False)
        self.placeholder_image_path = tk.StringVar()
        
        # Переменная для включения/отключения маркетингового текста
        self.use_marketing_text = tk.BooleanVar(value=False)
        
        # Переменные для режима работы с существующими товарами
        self.existing_mode = tk.StringVar(value="update")  # "skip" или "update"
        
        self.uploader = None
        self.is_uploading = False
        
        # Переменные для скачивания изображений
        self.download_csv_files = []  # Список выбранных CSV файлов
        self.download_csv_files_display = tk.StringVar(value="Файлы не выбраны")
        self.download_output_folder = tk.StringVar(value="img")
        self.enable_image_conversion = tk.BooleanVar(value=False)
        self.download_url_column = tk.StringVar(value="img_url")
        self.download_sku_column = tk.StringVar(value="sku")
        self.download_max_workers = tk.IntVar(value=4)
        
        # Загрузчик изображений
        self.image_downloader = None
        self.is_downloading = False
        self._download_stop_flag = False

        # Переменные для обработки изображений
        self.process_source_folder = tk.StringVar(value="")
        self.process_output_folder = tk.StringVar(value="img_result")
        self.process_max_workers = tk.IntVar(value=4)

        # Обработчик изображений
        self.image_processor = None
        self.is_processing_images = False
        self._process_stop_flag = False
        
        # Переменные для AI генерации описаний
        self.ai_csv_file_path = tk.StringVar()
        self.ai_api_key = tk.StringVar()
        self.ai_api_url = tk.StringVar(value="https://api.vsegpt.ru/v1/chat/completions")
        self.ai_model = tk.StringVar(value="gpt-3.5-turbo")
        self.ai_temperature = tk.DoubleVar(value=0.7)
        self.ai_language = tk.StringVar(value="русский")
        self.ai_max_description_length = tk.IntVar(value=300)
        self.ai_batch_size = tk.IntVar(value=5)
        self.ai_delay_between_batches = tk.DoubleVar(value=1.0)
        self.ai_name_column = tk.StringVar(value="product_name")
        self.ai_translate_names = tk.BooleanVar(value=True)
        
        # Настройки retry
        self.ai_max_retries = tk.IntVar(value=3)
        self.ai_retry_delay = tk.DoubleVar(value=2.0)
        self.ai_timeout = tk.IntVar(value=120)
        
        # AI генератор
        self.ai_generator = None
        self.is_generating = False
        self._ai_stop_flag = False
        
        # Переменные для выбора столбцов
        self.column_vars = {}  # field_name -> tk.BooleanVar()
        self.column_frame = None  # контейнер для чекбоксов
        
        self.ui_queue = queue.Queue()
        
        self.setup_ui()
        self.process_ui_queue()
        
        # Автоматически загружаем настройки при запуске
        self.load_settings_on_startup()

    def _get_initial_dir(self):
        """Возвращает начальный каталог для диалогов выбора файлов/папок."""
        return DEFAULT_DIALOG_DIR

    def _load_settings_file(self):
        """Читает файл настроек GUI или возвращает пустой словарь."""
        if not os.path.exists(SETTINGS_FILE):
            return {}
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_settings_file(self, settings: dict):
        """Сохраняет переданные настройки в файл."""
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)

    def _update_settings(self, updates: dict):
        """Обновляет файл настроек переданными значениями."""
        settings = self._load_settings_file()
        settings.update(updates)
        self._save_settings_file(settings)

    def _apply_settings(self, settings: dict, mapping: dict):
        """Проставляет значения в tkinter-переменные, если ключи присутствуют."""
        for key, var in mapping.items():
            if key in settings:
                var.set(settings[key])

    def _get_ssh_config(self):
        """Формирует конфиг SFTP из текущих полей формы."""
        return {
            'host': self.ssh_host.get(),
            'port': self.ssh_port.get(),
            'username': self.ssh_username.get(),
            'password': self.ssh_password.get(),
            'remote_base_path': self.ssh_remote_path.get(),
            'web_domain': self.ssh_web_domain.get()
        }

    def _get_dummy_ssh_config(self):
        """Возвращает заглушку SFTP для режима без SFTP."""
        return {
            'host': 'localhost',
            'port': 22,
            'username': 'dummy',
            'password': 'dummy',
            'remote_base_path': '/tmp',
            'web_domain': 'localhost'
        }

    def _create_uploader(self):
        """Создает и настраивает загрузчик WooCommerce с актуальными параметрами."""
        ssh_config = self._get_ssh_config() if self.use_fifu.get() else self._get_dummy_ssh_config()
        uploader = WooCommerceFIFUUploader(
            wc_url=self.wc_url.get(),
            wc_consumer_key=self.wc_consumer_key.get(),
            wc_consumer_secret=self.wc_consumer_secret.get(),
            ssh_config=ssh_config,
            wp_username=self.wp_username.get(),
            wp_app_password=self.wp_app_password.get()
        )
        uploader.set_progress_callback(self.update_progress)
        uploader.set_log_callback(self.log_message)
        return uploader

    def _read_csv_preview(self, filename: str, nrows: int = 5):
        """Читает небольшую часть CSV с автоматическим выбором кодировки."""
        try:
            return pd.read_csv(filename, nrows=nrows, encoding='utf-8', on_bad_lines='skip')
        except UnicodeDecodeError:
            return pd.read_csv(filename, nrows=nrows, encoding='cp1251', on_bad_lines='skip')
        except Exception as e:
            self.log_message(f"⚠ Не удалось прочитать CSV для предпросмотра: {e}")
            return None
        
    def setup_ui(self):
        # Заголовок
        header_frame = tk.Frame(self.root, bg='#2c3e50', height=80)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)
        
        title_label = tk.Label(
            header_frame, 
            text="WooCommerce Uploader", 
            font=("Arial", 16, "bold"),
            fg='white',
            bg='#2c3e50'
        )
        title_label.pack(pady=20)
        
        # Основной контейнер
        main_frame = tk.Frame(self.root, bg='#ecf0f1')
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Создание notebook для вкладок
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Вкладка настроек
        self.setup_settings_tab(notebook)
        
        # Вкладка WooCommerce настроек
        self.setup_wc_tab(notebook)
        
        # Вкладка SSH настроек
        self.setup_ssh_tab(notebook)
        
        # Вкладка скачивания изображений
        self.setup_download_tab(notebook)
        
        # Вкладка генерации AI описаний
        self.setup_ai_description_tab(notebook)

        # Вкладка обработки изображений
        self.setup_image_processing_tab(notebook)

        # Вкладка процесса
        self.setup_progress_tab(notebook)
        
    def setup_settings_tab(self, notebook):
        """Настройка вкладки с основными настройками"""
        # Создаем прокручиваемый фрейм
        scrollable_tab = ScrollableFrame(notebook)
        notebook.add(scrollable_tab, text="Основные настройки")
        settings_frame = scrollable_tab.scrollable_frame
        
        # Файлы
        files_frame = ttk.LabelFrame(settings_frame, text="Файлы", padding=10)
        files_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # CSV файл
        csv_frame = tk.Frame(files_frame)
        csv_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(csv_frame, text="CSV файл:", width=15, anchor='w').pack(side=tk.LEFT)
        csv_entry = tk.Entry(csv_frame, textvariable=self.csv_file_path)
        csv_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        tk.Button(csv_frame, text="Обзор", command=self.browse_csv_file).pack(side=tk.RIGHT)
        
        # Папка с изображениями
        images_frame = tk.Frame(files_frame)
        images_frame.pack(fill=tk.X)
        
        tk.Label(images_frame, text="Папка изображений:", width=15, anchor='w').pack(side=tk.LEFT)
        images_entry = tk.Entry(images_frame, textvariable=self.images_folder_path)
        images_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        tk.Button(images_frame, text="Обзор", command=self.browse_images_folder).pack(side=tk.RIGHT)
        
        # Режим загрузки изображений
        mode_frame = ttk.LabelFrame(settings_frame, text="Режим загрузки изображений", padding=10)
        mode_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Checkbutton(
            mode_frame, 
            text="Использовать плагин ExtraURL и загрузку на удалённый сервер (рекомендуется)", 
            variable=self.use_fifu,
            onvalue=True,
            offvalue=False
        ).pack(anchor='w', pady=(0, 5))
        
        description_label = tk.Label(
            mode_frame, 
            text="При включенной опции изображения загружаются на SFTP сервер и используются\nпо ссылке через плагин ExtraURL. При выключенной - загружаются напрямую в WordPress.",
            justify=tk.LEFT,
            wraplength=600
        )
        description_label.pack(anchor='w')
        
        # Изображение-заглушка
        placeholder_check = tk.Checkbutton(
            mode_frame,
            text="Использовать заглушку для товаров без изображений",
            variable=self.use_placeholder,
            onvalue=True,
            offvalue=False,
            command=self.toggle_placeholder_controls
        )
        placeholder_check.pack(anchor='w', pady=(10, 0))
        
        # Фрейм для выбора заглушки
        self.placeholder_frame = tk.Frame(mode_frame)
        self.placeholder_frame.pack(fill=tk.X, pady=(5, 5), padx=(20, 0))
        
        # Элементы управления для выбора заглушки
        tk.Label(self.placeholder_frame, text="Изображение-заглушка:").pack(side=tk.LEFT)
        placeholder_entry = tk.Entry(self.placeholder_frame, textvariable=self.placeholder_image_path)
        placeholder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        tk.Button(self.placeholder_frame, text="Выбрать", command=self.browse_placeholder_image).pack(side=tk.RIGHT)
        
        # Описание заглушки
        placeholder_label = tk.Label(
            mode_frame,
            text="При включении этой опции товары без изображений будут использовать выбранное изображение-заглушку.\nЗаглушка загружается один раз и кэшируется для использования со всеми товарами без изображений.",
            justify=tk.LEFT,
            wraplength=600,
            fg='#666666'
        )
        placeholder_label.pack(anchor='w')
        
        # Маркетинговый текст
        tk.Checkbutton(
            mode_frame,
            text="Добавлять маркетинговый текст в описание товаров",
            variable=self.use_marketing_text,
            onvalue=True,
            offvalue=False
        ).pack(anchor='w', pady=(10, 0))
        
        marketing_label = tk.Label(
            mode_frame,
            text="При включении к описанию товаров будет добавлен маркетинговый текст с информацией о компании.\nОтключите эту опцию, если не хотите добавлять маркетинговый текст.",
            justify=tk.LEFT,
            wraplength=600,
            fg='#666666'
        )
        marketing_label.pack(anchor='w')
        
        # Режим работы с существующими товарами
        existing_frame = ttk.LabelFrame(settings_frame, text="Режим работы с существующими товарами", padding=10)
        existing_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Radiobutton(
            existing_frame,
            text="Пропускать существующие (быстро - пропускает товары найденные в кэше)",
            variable=self.existing_mode,
            value="skip",
            justify=tk.LEFT,
            wraplength=700
        ).pack(anchor='w', pady=(0, 5))
        
        tk.Radiobutton(
            existing_frame,
            text="Обновлять существующие (пакетное обновление через REST API batch)",
            variable=self.existing_mode,
            value="update",
            justify=tk.LEFT,
            wraplength=700
        ).pack(anchor='w')
        
        # Количество товаров
        count_frame = ttk.LabelFrame(settings_frame, text="Настройки загрузки", padding=10)
        count_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(count_frame, text="Количество товаров:").pack(anchor='w')
        
        radio_frame = tk.Frame(count_frame)
        radio_frame.pack(fill=tk.X, pady=5)
        
        tk.Radiobutton(
            radio_frame, 
            text="Все товары из файла", 
            variable=self.products_count, 
            value="all"
        ).pack(side=tk.LEFT)
        
        tk.Radiobutton(
            radio_frame, 
            text="Указать количество:", 
            variable=self.products_count, 
            value="custom"
        ).pack(side=tk.LEFT, padx=(20, 5))
        
        tk.Spinbox(
            radio_frame, 
            from_=1, 
            to=1000, 
            width=8, 
            textvariable=self.custom_count
        ).pack(side=tk.LEFT)
        
        # Контейнер для динамических чекбоксов столбцов
        self.column_frame = ttk.LabelFrame(settings_frame, text="Выберите столбцы для загрузки", padding=10)
        self.column_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,10))
        
        # Кнопки
        buttons_frame = tk.Frame(settings_frame)
        buttons_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.start_button = tk.Button(
            buttons_frame, 
            text="Начать загрузку", 
            command=self.start_upload,
            bg='#27ae60',
            fg='white',
            font=("Arial", 11, "bold"),
            padx=20,
            pady=5
        )
        self.start_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.stop_button = tk.Button(
            buttons_frame, 
            text="Остановить", 
            command=self.stop_upload,
            bg='#e74c3c',
            fg='white',
            font=("Arial", 11, "bold"),
            padx=20,
            pady=5,
            state=tk.DISABLED
        )
        self.stop_button.pack(side=tk.LEFT)
        
    def setup_wc_tab(self, notebook):
        """Настройка вкладки с WooCommerce настройками"""
        # Создаем прокручиваемый фрейм
        scrollable_tab = ScrollableFrame(notebook)
        notebook.add(scrollable_tab, text="WooCommerce настройки")
        wc_frame = scrollable_tab.scrollable_frame
        
        # WooCommerce настройки
        wc_settings_frame = ttk.LabelFrame(wc_frame, text="Настройки WooCommerce", padding=10)
        wc_settings_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # URL магазина
        url_frame = tk.Frame(wc_settings_frame)
        url_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(url_frame, text="URL магазина:", width=20, anchor='w').pack(side=tk.LEFT)
        tk.Entry(url_frame, textvariable=self.wc_url).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Consumer Key
        key_frame = tk.Frame(wc_settings_frame)
        key_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(key_frame, text="Consumer Key:", width=20, anchor='w').pack(side=tk.LEFT)
        tk.Entry(key_frame, textvariable=self.wc_consumer_key).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Consumer Secret
        secret_frame = tk.Frame(wc_settings_frame)
        secret_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(secret_frame, text="Consumer Secret:", width=20, anchor='w').pack(side=tk.LEFT)
        secret_entry = tk.Entry(secret_frame, textvariable=self.wc_consumer_secret, show="*")
        secret_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Timeout
        timeout_frame = tk.Frame(wc_settings_frame)
        timeout_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(timeout_frame, text="Timeout (сек):", width=20, anchor='w').pack(side=tk.LEFT)
        tk.Entry(timeout_frame, textvariable=self.wc_timeout).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # WordPress настройки
        wp_settings_frame = ttk.LabelFrame(wc_frame, text="Настройки WordPress (для загрузки изображений)", padding=10)
        wp_settings_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Username
        wp_username_frame = tk.Frame(wp_settings_frame)
        wp_username_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(wp_username_frame, text="Пользователь WP:", width=20, anchor='w').pack(side=tk.LEFT)
        tk.Entry(wp_username_frame, textvariable=self.wp_username).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # App Password
        wp_password_frame = tk.Frame(wp_settings_frame)
        wp_password_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(wp_password_frame, text="App Password:", width=20, anchor='w').pack(side=tk.LEFT)
        wp_password_entry = tk.Entry(wp_password_frame, textvariable=self.wp_app_password, show="*")
        wp_password_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Email
        wp_email_frame = tk.Frame(wp_settings_frame)
        wp_email_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(wp_email_frame, text="Email:", width=20, anchor='w').pack(side=tk.LEFT)
        tk.Entry(wp_email_frame, textvariable=self.wp_email).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Кнопки для работы с конфигурацией
        config_frame = tk.Frame(wc_frame)
        config_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Button(
            config_frame,
            text="Проверить подключение к WooCommerce",
            command=self.test_wc_connection
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        tk.Button(
            config_frame,
            text="Сохранить в gui_settings.json",
            command=self.save_wc_config
        ).pack(side=tk.LEFT)
        
        tk.Button(
            config_frame,
            text="Перезагрузить из gui_settings.json",
            command=self.load_wc_config
        ).pack(side=tk.LEFT, padx=10)
        
        # Описание
        info_frame = ttk.LabelFrame(wc_frame, text="Информация", padding=10)
        info_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        info_text = """
Для работы с WooCommerce требуется:

1. URL вашего сайта с WooCommerce (например: https://mystore.com)
2. Consumer Key и Consumer Secret из настроек WooCommerce API
3. Пользователь WordPress с правами администратора
4. App Password для этого пользователя (создается в профиле пользователя)

Настройки WooCommerce загружаются из файла gui_settings.json при запуске.
Используйте кнопки для сохранения изменений в файл настроек или их перезагрузки.

Consumer Key и Consumer Secret можно получить в админпанели WooCommerce:
WooCommerce → Настройки → Продвинутые → REST API → Добавить ключ
        """
        
        tk.Label(
            info_frame,
            text=info_text,
            justify=tk.LEFT,
            wraplength=750,
            anchor='w'
        ).pack(fill=tk.BOTH, expand=True)
        
    def setup_ssh_tab(self, notebook):
        """Настройка вкладки с SSH настройками"""
        # Создаем прокручиваемый фрейм
        scrollable_tab = ScrollableFrame(notebook)
        notebook.add(scrollable_tab, text="SFTP настройки")
        ssh_frame = scrollable_tab.scrollable_frame
        
        # SSH настройки
        ssh_settings_frame = ttk.LabelFrame(ssh_frame, text="Настройки SFTP сервера", padding=10)
        ssh_settings_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Хост
        host_frame = tk.Frame(ssh_settings_frame)
        host_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(host_frame, text="Хост:", width=15, anchor='w').pack(side=tk.LEFT)
        tk.Entry(host_frame, textvariable=self.ssh_host).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Порт
        port_frame = tk.Frame(ssh_settings_frame)
        port_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(port_frame, text="Порт:", width=15, anchor='w').pack(side=tk.LEFT)
        tk.Entry(port_frame, textvariable=self.ssh_port).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Пользователь
        username_frame = tk.Frame(ssh_settings_frame)
        username_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(username_frame, text="Пользователь:", width=15, anchor='w').pack(side=tk.LEFT)
        tk.Entry(username_frame, textvariable=self.ssh_username).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Пароль
        password_frame = tk.Frame(ssh_settings_frame)
        password_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(password_frame, text="Пароль:", width=15, anchor='w').pack(side=tk.LEFT)
        password_entry = tk.Entry(password_frame, textvariable=self.ssh_password, show="*")
        password_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Путь на сервере
        path_frame = tk.Frame(ssh_settings_frame)
        path_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(path_frame, text="Путь на сервере:", width=15, anchor='w').pack(side=tk.LEFT)
        tk.Entry(path_frame, textvariable=self.ssh_remote_path).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Веб-домен
        domain_frame = tk.Frame(ssh_settings_frame)
        domain_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(domain_frame, text="Веб-домен:", width=15, anchor='w').pack(side=tk.LEFT)
        tk.Entry(domain_frame, textvariable=self.ssh_web_domain).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Кнопки для работы с конфигурацией
        config_frame = tk.Frame(ssh_frame)
        config_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Button(
            config_frame,
            text="Проверить соединение",
            command=self.test_ssh_connection
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        tk.Button(
            config_frame,
            text="Сохранить в gui_settings.json",
            command=self.save_ssh_config
        ).pack(side=tk.LEFT)
        
        tk.Button(
            config_frame,
            text="Перезагрузить из gui_settings.json",
            command=self.load_ssh_config
        ).pack(side=tk.LEFT, padx=10)
        
        # Описание
        info_frame = ttk.LabelFrame(ssh_frame, text="Информация", padding=10)
        info_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        info_text = """
Для работы с внешними изображениями через ExtraURL требуется:

1. Настроенный SFTP сервер для загрузки изображений
2. Доступность изображений по HTTP/HTTPS (веб-сервер на том же хосте)  
3. Установленный плагин ExtraURL на сайте WooCommerce

Настройки SFTP загружаются из файла gui_settings.json при запуске.
Используйте кнопки для сохранения изменений в файл настроек или их перезагрузки.

Текущие настройки загрузят изображения в указанную папку на сервере,
и будут использовать URL вида: http://hostname/images/...
        """
        
        tk.Label(
            info_frame,
            text=info_text,
            justify=tk.LEFT,
            wraplength=750,
            anchor='w'
        ).pack(fill=tk.BOTH, expand=True)
    
    def setup_download_tab(self, notebook):
        """Настройка вкладки скачивания изображений"""
        # Создаем прокручиваемый фрейм
        scrollable_tab = ScrollableFrame(notebook)
        notebook.add(scrollable_tab, text="Скачивание изображений")
        download_frame = scrollable_tab.scrollable_frame
        
        # Настройки файлов
        files_frame = ttk.LabelFrame(download_frame, text="Файлы и папки", padding=10)
        files_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # CSV файлы с URL и SKU
        csv_frame = tk.Frame(files_frame)
        csv_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(csv_frame, text="CSV файлы с URL:", width=20, anchor='w').pack(side=tk.LEFT)
        csv_entry = tk.Entry(csv_frame, textvariable=self.download_csv_files_display, state='readonly')
        csv_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        
        # Кнопки для работы с файлами
        csv_buttons_frame = tk.Frame(csv_frame)
        csv_buttons_frame.pack(side=tk.RIGHT)
        
        tk.Button(csv_buttons_frame, text="Выбрать файлы", command=self.browse_download_csv_multiple).pack(side=tk.LEFT, padx=(0, 2))
        tk.Button(csv_buttons_frame, text="Очистить", command=self.clear_download_csv_files).pack(side=tk.LEFT)
        
        # Папка для сохранения
        output_frame = tk.Frame(files_frame)
        output_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(output_frame, text="Базовая папка:", width=20, anchor='w').pack(side=tk.LEFT)
        output_entry = tk.Entry(output_frame, textvariable=self.download_output_folder)
        output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        tk.Button(output_frame, text="Выбрать", command=self.browse_download_output_folder).pack(side=tk.RIGHT)
        
        # Описание логики папок
        folder_info = tk.Label(
            files_frame,
            text="💡 При выборе одного файла используется указанная папка.\n"
                 "При выборе нескольких файлов для каждого создается отдельная папка: базовая_папка_имя_файла",
            justify=tk.LEFT,
            fg='#666666',
            font=("Arial", 9)
        )
        folder_info.pack(anchor='w')
        
        # Настройки колонок CSV
        columns_frame = ttk.LabelFrame(download_frame, text="Настройки CSV", padding=10)
        columns_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Колонка с URL
        url_column_frame = tk.Frame(columns_frame)
        url_column_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(url_column_frame, text="Колонка с URL:", width=20, anchor='w').pack(side=tk.LEFT)
        tk.Entry(url_column_frame, textvariable=self.download_url_column).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Колонка с SKU/артикулом
        sku_column_frame = tk.Frame(columns_frame)
        sku_column_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(sku_column_frame, text="Колонка с SKU/артикулом:", width=20, anchor='w').pack(side=tk.LEFT)
        tk.Entry(sku_column_frame, textvariable=self.download_sku_column).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Настройки обработки
        processing_frame = ttk.LabelFrame(download_frame, text="Настройки обработки", padding=10)
        processing_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Чекбокс для преобразования изображений
        convert_checkbox = tk.Checkbutton(
            processing_frame,
            text="Включить преобразование изображений в унифицированный формат (2560x1440)",
            variable=self.enable_image_conversion,
            onvalue=True,
            offvalue=False
        )
        convert_checkbox.pack(anchor='w', pady=(0, 5))
        
        # Описание преобразования
        convert_description = tk.Label(
            processing_frame,
            text="При включении этой опции скачанные изображения будут автоматически преобразованы\\n"
                 "в унифицированный формат: размещены по центру белого холста 2560x1440.\\n"
                 "Качество и четкость изображений будут улучшены при необходимости.",
            justify=tk.LEFT,
            wraplength=600,
            fg='#666666'
        )
        convert_description.pack(anchor='w', pady=(0, 10))
        
        # Количество потоков
        threads_frame = tk.Frame(processing_frame)
        threads_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(threads_frame, text="Потоков скачивания:", width=20, anchor='w').pack(side=tk.LEFT)
        tk.Spinbox(
            threads_frame,
            from_=1,
            to=10,
            width=8,
            textvariable=self.download_max_workers
        ).pack(side=tk.LEFT)
        
        # Кнопки управления
        buttons_frame = tk.Frame(download_frame)
        buttons_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.download_start_button = tk.Button(
            buttons_frame,
            text="Начать скачивание",
            command=self.start_image_download,
            bg='#27ae60',
            fg='white',
            font=("Arial", 11, "bold"),
            padx=20,
            pady=5
        )
        self.download_start_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.download_stop_button = tk.Button(
            buttons_frame,
            text="Остановить",
            command=self.stop_image_download,
            bg='#e74c3c',
            fg='white',
            font=("Arial", 11, "bold"),
            padx=20,
            pady=5,
            state=tk.DISABLED
        )
        self.download_stop_button.pack(side=tk.LEFT)
        
        # Информация
        info_frame = ttk.LabelFrame(download_frame, text="Информация", padding=10)
        info_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        info_text = """
Модуль массового скачивания изображений:

📁 МНОЖЕСТВЕННЫЕ ФАЙЛЫ:
• Выберите один или несколько CSV файлов с URL и SKU
• При выборе одного файла - используется указанная папка
• При выборе нескольких - для каждого создается папка: базовая_имя_файла

📋 НАСТРОЙКА:
1. Нажмите "Выбрать файлы" для выбора CSV файлов
2. Укажите базовую папку сохранения
3. Настройте названия колонок (определяются автоматически)
4. Включите преобразование изображений при необходимости

🔄 ПРЕОБРАЗОВАНИЕ ИЗОБРАЖЕНИЙ:
• Строгая нормализация имен файлов (только буквы и цифры)
• Анализ качества и умное масштабирование
• Размещение по центру белого холста 2560x1440
• Поддержка кириллицы в именах файлов

📊 СТАТИСТИКА:
Подробная статистика по каждому файлу и общие итоги

Поддерживаемые форматы: JPG, PNG, WebP, BMP, TIFF
        """
        
        tk.Label(
            info_frame,
            text=info_text,
            justify=tk.LEFT,
            wraplength=750,
            anchor='w'
        ).pack(fill=tk.BOTH, expand=True)
        
    def setup_progress_tab(self, notebook):
        """Настройка вкладки с прогрессом"""
        # Создаем прокручиваемый фрейм
        scrollable_tab = ScrollableFrame(notebook)
        notebook.add(scrollable_tab, text="Процесс")
        progress_frame = scrollable_tab.scrollable_frame
        
        # Прогресс бар
        progress_container = tk.Frame(progress_frame)
        progress_container.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(progress_container, text="Прогресс загрузки:", font=("Arial", 11, "bold")).pack(anchor='w')
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            progress_container, 
            variable=self.progress_var, 
            mode='determinate'
        )
        self.progress_bar.pack(fill=tk.X, pady=5)
        
        # Статус
        self.status_label = tk.Label(
            progress_container, 
            text="Готов к загрузке",
            font=("Arial", 10)
        )
        self.status_label.pack(anchor='w')
        
        # Лог
        log_container = tk.Frame(progress_frame)
        log_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        tk.Label(log_container, text="Журнал загрузки:", font=("Arial", 11, "bold")).pack(anchor='w')

        log_body = tk.Frame(log_container)
        log_body.pack(fill=tk.BOTH, expand=True, pady=5)
        log_body.rowconfigure(0, weight=1)
        log_body.columnconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(
            log_body, 
            height=15, 
            wrap=tk.WORD,
            bg='#2c3e50',
            fg='#ecf0f1',
            font=("Consolas", 9)
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        
        # Настраиваем теги для цветного лога
        self.log_text.tag_config('SUCCESS', foreground='#27ae60', font=("Consolas", 9, "bold"))
        self.log_text.tag_config('ERROR', foreground='#e74c3c', font=("Consolas", 9, "bold"))
        self.log_text.tag_config('WARNING', foreground='#f39c12')
        self.log_text.tag_config('INFO', foreground='#ecf0f1')
        self.log_text.tag_config('HEADER', foreground='#3498db', font=("Consolas", 9, "bold"))
        self.log_text.tag_config('TIMESTAMP', foreground='#95a5a6')
        self.log_text.tag_config('DEBUG', foreground='cyan')

        # Делаем лог по умолчанию только для чтения
        self.log_text.configure(state='disabled')
        
        # Кнопки управления логом
        log_buttons_frame = tk.Frame(log_container)
        log_buttons_frame.pack(fill=tk.X, pady=5)

        tk.Button(
            log_buttons_frame, 
            text="Очистить лог", 
            command=self.clear_log
        ).pack(side=tk.LEFT, anchor='w')

        tk.Button(
            log_buttons_frame,
            text="Сохранить лог",
            command=self.save_log
        ).pack(side=tk.LEFT, anchor='w', padx=5)

        # Начальное сообщение
        self.log_message("=== WooCommerce ExtraURL Uploader ===")
        
        # Инициализация состояния элементов управления
        self.initialize_gui_state()
        self.log_message("Выберите CSV файл и папку с изображениями для начала работы")
        
    def browse_csv_file(self):
        filename = filedialog.askopenfilename(
            title="Выберите CSV файл",
            initialdir=self._get_initial_dir(),
            filetypes=CSV_FILETYPES
        )
        if filename:
            self.csv_file_path.set(filename)
            self.log_message(f"✓ Выбран CSV файл: {os.path.basename(filename)}")
            
            # Автоматически определяем колонки и строим чекбоксы
            df_preview = self._read_csv_preview(filename, nrows=1)
            if df_preview is None:
                return

            # Очищаем предыдущие чекбоксы
            for widget in self.column_frame.winfo_children():
                widget.destroy()

            self.column_vars.clear()

            tk.Label(self.column_frame, text="Выберите столбцы для загрузки в WooCommerce:").pack(anchor='w')

            for field in df_preview.columns:
                var = tk.BooleanVar(value=True)
                self.column_vars[field] = var
                chk = tk.Checkbutton(self.column_frame, text=field, variable=var)
                chk.pack(anchor='w')

            self.column_frame.update_idletasks()
            
    def initialize_gui_state(self):
        """Инициализация начального состояния элементов управления"""
        # Скрываем элементы управления заглушкой при старте, если она не включена
        if not self.use_placeholder.get():
            self.placeholder_frame.pack_forget()
    
    def browse_images_folder(self):
        folder = filedialog.askdirectory(
            title="Выберите папку с изображениями",
            initialdir=self._get_initial_dir()
        )
        if folder:
            self.images_folder_path.set(folder)
            # Подсчет изображений
            try:
                image_count = len([f for f in os.listdir(folder) 
                                 if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))])
                self.log_message(f"✓ Выбрана папка с изображениями: {os.path.basename(folder)}")
                self.log_message(f"  Найдено {image_count} изображений")
            except:
                self.log_message(f"✓ Выбрана папка с изображениями: {os.path.basename(folder)}")
                
    def toggle_placeholder_controls(self):
        """Включение/отключение элементов управления заглушкой"""
        if self.use_placeholder.get():
            self.placeholder_frame.pack(fill=tk.X, pady=(5, 5), padx=(20, 0))
        else:
            self.placeholder_frame.pack_forget()
    
    def browse_placeholder_image(self):
        """Выбор изображения-заглушки"""
        image_path = filedialog.askopenfilename(
            title="Выберите изображение-заглушку", 
            filetypes=IMAGE_FILETYPES
        )
        
        if image_path:
            self.placeholder_image_path.set(image_path)
            
            # Показываем информацию о выбранном изображении
            try:
                file_size = os.path.getsize(image_path) / (1024 * 1024)  # в МБ
                self.log_message(f"✓ Выбрано изображение-заглушка: {os.path.basename(image_path)} ({file_size:.2f} МБ)")
            except Exception as e:
                self.log_message(f"❌ Ошибка при получении информации о заглушке: {str(e)}")
                
    def test_ssh_connection(self):
        """Тестирование соединения с SSH сервером"""
        try:
            # Создаем временный объект SFTP загрузчика для проверки
            from sftp_uploader import SFTPImageUploader
            
            ssh_config = self._get_ssh_config()
            
            uploader = SFTPImageUploader(**ssh_config)
            uploader.set_log_callback(self.log_message)
            
            self.log_message("\n=== Тестирование SFTP соединения ===")
            
            # Пробуем подключиться
            if uploader.connect():
                self.log_message("✅ Соединение с SFTP сервером установлено успешно")
                self.log_message(f"✅ Базовая директория {ssh_config['remote_base_path']} проверена/создана")
                
                # Отключаемся
                uploader.disconnect()
                messagebox.showinfo("Подключение успешно", "Соединение с SFTP сервером установлено успешно")
            else:
                self.log_message("❌ Не удалось подключиться к SFTP серверу")
                messagebox.showerror("Ошибка подключения", "Не удалось установить соединение с SFTP сервером")
        except Exception as e:
            self.log_message(f"❌ Ошибка при подключении к SFTP серверу: {str(e)}")
            messagebox.showerror("Ошибка", f"Произошла ошибка при подключении:\n{str(e)}")
            
    def save_ssh_config(self):
        """Сохранение конфигурации SFTP в gui_settings.json"""
        try:
            self._update_settings({
                'sftp_host': self.ssh_host.get(),
                'sftp_port': self.ssh_port.get(),
                'sftp_username': self.ssh_username.get(),
                'sftp_password': self.ssh_password.get(),
                'sftp_remote_base_path': self.ssh_remote_path.get(),
                'sftp_web_domain': self.ssh_web_domain.get()
            })
                    
            self.log_message(f"✅ Настройки SFTP сохранены в gui_settings.json")
            messagebox.showinfo("Сохранено", "Настройки SFTP успешно сохранены в gui_settings.json")
                
        except Exception as e:
            self.log_message(f"❌ Ошибка при сохранении настроек: {str(e)}")
            messagebox.showerror("Ошибка", f"Не удалось сохранить настройки:\n{str(e)}")
            
    def load_ssh_config(self):
        """Перезагрузка конфигурации SFTP из gui_settings.json"""
        try:
            if not os.path.exists(SETTINGS_FILE):
                messagebox.showwarning("Внимание", "Файл gui_settings.json не найден")
                return
                
            settings = self._load_settings_file()
            self._apply_settings(settings, {
                'sftp_host': self.ssh_host,
                'sftp_port': self.ssh_port,
                'sftp_username': self.ssh_username,
                'sftp_password': self.ssh_password,
                'sftp_remote_base_path': self.ssh_remote_path,
                'sftp_web_domain': self.ssh_web_domain
            })
                    
            self.log_message(f"✅ Настройки SFTP перезагружены из gui_settings.json")
            messagebox.showinfo("Загружено", "Настройки SFTP успешно перезагружены из gui_settings.json")
                
        except Exception as e:
            self.log_message(f"❌ Ошибка при загрузке настроек: {str(e)}")
            messagebox.showerror("Ошибка", f"Не удалось загрузить настройки:\n{str(e)}")
            
    def test_wc_connection(self):
        """Тестирование подключения к WooCommerce"""
        try:
            from woocommerce import API
            
            wc_config = {
                'url': self.wc_url.get(),
                'consumer_key': self.wc_consumer_key.get(),
                'consumer_secret': self.wc_consumer_secret.get(),
                'wp_api': True,
                'version': 'wc/v3',
                'timeout': self.wc_timeout.get()
            }
            
            self.log_message("\n=== Тестирование подключения к WooCommerce ===")
            
            # Создаем API клиент
            wcapi = API(**wc_config)
            
            # Пробуем выполнить простой запрос
            response = wcapi.get("system_status")
            
            if response.status_code == 200:
                self.log_message("✅ Подключение к WooCommerce API установлено успешно")
                data = response.json()
                if 'environment' in data:
                    env = data['environment']
                    self.log_message(f"✅ WooCommerce версия: {env.get('version', 'неизвестна')}")
                    self.log_message(f"✅ WordPress версия: {env.get('wp_version', 'неизвестна')}")
                messagebox.showinfo("Подключение успешно", "Подключение к WooCommerce API установлено успешно")
            else:
                self.log_message(f"❌ Ошибка подключения: HTTP {response.status_code}")
                messagebox.showerror("Ошибка подключения", f"Не удалось подключиться к WooCommerce API\nHTTP код: {response.status_code}")
                
        except Exception as e:
            self.log_message(f"❌ Ошибка при подключении к WooCommerce: {str(e)}")
            messagebox.showerror("Ошибка", f"Произошла ошибка при подключении:\n{str(e)}")
            
    def save_wc_config(self):
        """Сохранение конфигурации WooCommerce в gui_settings.json"""
        try:
            self._update_settings({
                'wc_url': self.wc_url.get(),
                'wc_consumer_key': self.wc_consumer_key.get(),
                'wc_consumer_secret': self.wc_consumer_secret.get(),
                'wc_timeout': self.wc_timeout.get(),
                'wp_username': self.wp_username.get(),
                'wp_app_password': self.wp_app_password.get(),
                'wp_email': self.wp_email.get()
            })
                    
            self.log_message(f"✅ Настройки WooCommerce сохранены в gui_settings.json")
            messagebox.showinfo("Сохранено", "Настройки WooCommerce успешно сохранены в gui_settings.json")
                
        except Exception as e:
            self.log_message(f"❌ Ошибка при сохранении настроек: {str(e)}")
            messagebox.showerror("Ошибка", f"Не удалось сохранить настройки:\n{str(e)}")
            
    def load_wc_config(self):
        """Перезагрузка конфигурации WooCommerce из gui_settings.json"""
        try:
            if not os.path.exists(SETTINGS_FILE):
                messagebox.showwarning("Внимание", "Файл gui_settings.json не найден")
                return
                
            settings = self._load_settings_file()
            self._apply_settings(settings, {
                'wc_url': self.wc_url,
                'wc_consumer_key': self.wc_consumer_key,
                'wc_consumer_secret': self.wc_consumer_secret,
                'wc_timeout': self.wc_timeout,
                'wp_username': self.wp_username,
                'wp_app_password': self.wp_app_password,
                'wp_email': self.wp_email
            })
                    
            self.log_message(f"✅ Настройки WooCommerce перезагружены из gui_settings.json")
            messagebox.showinfo("Загружено", "Настройки WooCommerce успешно перезагружены из gui_settings.json")
                
        except Exception as e:
            self.log_message(f"❌ Ошибка при загрузке настроек: {str(e)}")
            messagebox.showerror("Ошибка", f"Не удалось загрузить настройки:\n{str(e)}")
            
    def process_ui_queue(self):
        """Обрабатывает все сообщения из очереди в основном потоке GUI."""
        try:
            while True:
                msg_type, data = self.ui_queue.get_nowait()

                if msg_type == 'log':
                    self._log_to_widget(data)
                elif msg_type == 'progress':
                    current, total, message = data
                    self._update_progress_widget(current, total, message)
                elif msg_type == 'finish':
                    self._finish_upload_ui(data)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_ui_queue)

    def _show_message_async(self, kind: str, title: str, text: str):
        def _show():
            if kind == "info":
                messagebox.showinfo(title, text)
            elif kind == "warning":
                messagebox.showwarning(title, text)
            else:
                messagebox.showerror(title, text)

        self.root.after(0, _show)

    def _log_to_widget(self, message):
        """Вставляет отформатированное сообщение в виджет лога. Должен выполняться в основном потоке."""
        # Проверяем, находится ли скроллбар в самом низу перед добавлением текста
        scroll_pos = self.log_text.yview()[1]
        autoscroll = scroll_pos >= 1.0
        
        self.log_text.configure(state='normal')
        
        # Определяем тег на основе содержимого
        l_msg = str(message).lower()
        tag = 'INFO'
        if l_msg.startswith("✅") or "успешно" in l_msg or "success" in l_msg:
            tag = 'SUCCESS'
        elif l_msg.startswith("❌") or "ошибка" in l_msg or "error" in l_msg or "критическая" in l_msg:
            tag = 'ERROR'
        elif l_msg.startswith("⚠️") or "предупреждение" in l_msg or "warning" in l_msg:
            tag = 'WARNING'
        elif l_msg.startswith("===") or l_msg.startswith("🚀") or l_msg.startswith("📊"):
            tag = 'HEADER'
        elif l_msg.startswith(("🔌", "🔧", "📦", "📡", "🔄", "🔍", "🖼️")):
            tag = 'DEBUG'

        timestamp = datetime.now().strftime('%H:%M:%S')
        self.log_text.insert(tk.END, f"[{timestamp}] ", ('TIMESTAMP',))
        self.log_text.insert(tk.END, f"{message}\n", (tag,))
        
        # Прокручиваем вниз только если скроллбар уже был внизу
        if autoscroll:
            self.log_text.see(tk.END)
            
        self.log_text.configure(state='disabled')
        
    def _update_progress_widget(self, current, total, message=""):
        """Обновляет прогресс-бар и метку статуса. Должен выполняться в основном потоке."""
        if total > 0:
            progress = (current / total) * 100
            self.progress_var.set(progress)
        
        status_text = f"Обработано: {current} из {total}"
        if message:
            status_text += f" - {message}"
        self.status_label.config(text=status_text)

    def _finish_upload_ui(self, result):
        """Завершает работу интерфейса после окончания загрузки. Должен выполняться в основном потоке."""
        if result:
            if result.get('success', False):
                messagebox.showinfo("Успех", f"Загрузка завершена!\n\nЗагружено товаров: {result.get('uploaded', 0)}\nОшибок: {result.get('errors', 0)}")
            else:
                messagebox.showerror("Ошибка", result.get('message', 'Произошла неизвестная ошибка при загрузке.'))

        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.status_label.config(text="Готов к загрузке")
        self.is_uploading = False
        self.uploader = None
        
    def log_message(self, message):
        """Помещает сообщение в очередь для логирования из любого потока."""
        self.ui_queue.put(('log', message))
        
    def clear_log(self):
        """Очищает виджет лога."""
        self.log_text.configure(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state='disabled')
        self.log_message("=== Лог очищен ===")

    def save_log(self):
        """Сохраняет содержимое виджета лога в текстовый файл."""
        log_content = self.log_text.get(1.0, tk.END)
        if not log_content.strip():
            messagebox.showinfo("Информация", "Лог пуст, нечего сохранять.")
            return

        try:
            filename = filedialog.asksaveasfilename(
                title="Сохранить лог как...",
                filetypes=[("Text files", "*.txt"), ("Log files", "*.log"), ("All files", "*.*")],
                defaultextension=".txt",
                initialfile=f"woocommerce-uploader-log-{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
            )
            
            if filename:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(log_content)
                self.log_message(f"✅ Лог успешно сохранен в файл: {os.path.basename(filename)}")
                messagebox.showinfo("Сохранено", "Лог был успешно сохранен.")
        except Exception as e:
            self.log_message(f"❌ Ошибка при сохранении лога: {str(e)}")
            messagebox.showerror("Ошибка", f"Не удалось сохранить лог:\n{str(e)}")
        
    def update_progress(self, current, total, message=""):
        """Помещает обновление прогресса в очередь из любого потока."""
        self.ui_queue.put(('progress', (current, total, message)))
        
    def start_upload(self):
        """Запуск процесса загрузки в отдельном потоке"""
        
        # Проверки перед запуском
        if self.is_uploading:
            messagebox.showwarning("Внимание", "Загрузка уже идет.")
            return
            
        csv_file = self.csv_file_path.get()
        if not csv_file:
            messagebox.showerror("Ошибка", "Не выбран CSV файл.")
            return
            
        images_folder = self.images_folder_path.get()
        if not images_folder:
            messagebox.showerror("Ошибка", "Не выбрана папка с изображениями.")
            return

        self.is_uploading = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.clear_log()
        self.log_message(f"▶️ Запуск загрузки...")
        self.uploader = self._create_uploader()
        
        count = self.custom_count.get() if self.products_count.get() == "custom" else None
        selected_fields = [field for field, var in self.column_vars.items() if var.get()]
        use_placeholder = self.use_placeholder.get()
        placeholder_image = self.placeholder_image_path.get() if use_placeholder else None

        # Запуск в отдельном потоке
        upload_thread = threading.Thread(
            target=self.upload_worker,
            args=(csv_file, images_folder, count, selected_fields, use_placeholder, placeholder_image),
            daemon=True
        )
        upload_thread.start()
        
    def stop_upload(self):
        """Остановить загрузку"""
        if self.uploader:
            self.uploader.stop_upload()
        self.log_message("⚠ Получен сигнал остановки...")
        
    def upload_worker(self, csv_file, images_folder, count, selected_fields, use_placeholder=False, placeholder_image=None):
        """Рабочая функция загрузки, выполняется в отдельном потоке."""
        result = None
        try:
            self.log_message("")
            self.log_message("=" * 50)
            self.log_message("🚀 НАЧАЛО ЗАГРУЗКИ")
            self.log_message("=" * 50)
            
            # Настройка callback'ов. Теперь они просто кладут данные в очередь.
            log_wrapper = self.log_message
            
            use_fifu = self.use_fifu.get()
            if use_fifu:
                self.log_message("📡 Режим: ExtraURL с загрузкой на SFTP")
            else:
                self.log_message("🔄 Режим: Только загрузка в WooCommerce (без SFTP)")

            if self.uploader is None:
                self.uploader = self._create_uploader()

            # Настраиваем callbacks (актуализируем при каждом запуске)
            self.uploader.set_log_callback(log_wrapper)
            self.uploader.set_progress_callback(self.update_progress)

            # Определяем режим работы с существующими товарами
            skip_existing = self.existing_mode.get() == "skip"
            
            self.log_message(f"🔧 Режим работы с существующими: {'Пропуск' if skip_existing else 'Обновление'}")
            
            # Log placeholder status
            if use_placeholder and placeholder_image:
                self.log_message(f"🖼️ Режим заглушки: Включен, файл: {os.path.basename(placeholder_image)}")
            elif use_placeholder:
                self.log_message(f"⚠️ Режим заглушки: Включен, но файл не выбран - заглушка не будет использоваться")
                use_placeholder = False
            else:
                self.log_message(f"ℹ️ Режим заглушки: Отключен")
            
            # Используем стандартную загрузку ExtraURL с выбранным режимом
            result = self.uploader.upload_products(
                csv_file, 
                images_folder, 
                max_count=count, 
                selected_fields=selected_fields,
                skip_existing=skip_existing,
                update_mode='all',  # Всегда используем полное обновление
                use_marketing_text=self.use_marketing_text.get(),
                use_placeholder=use_placeholder,
                placeholder_image=placeholder_image
            )

            # Итоговые сообщения
            self.log_message("\n" + "=" * 50)
            self.log_message("📊 РЕЗУЛЬТАТЫ ЗАГРУЗКИ:")
            self.log_message(f"✅ Успешно загружено: {result['uploaded']}")
            if 'new' in result and 'updated' in result:
                self.log_message(f"🆕 Новых товаров: {result['new']}")
                self.log_message(f"♻️ Обновлено товаров: {result['updated']}")
            if 'skipped' in result:
                self.log_message(f"⏭️ Пропущено товаров: {result['skipped']}")
            self.log_message(f"❌ Ошибки: {result['errors']}")
            if result['total'] > 0:
                self.log_message(f"📈 Успешность: {(result['uploaded']/result['total']*100):.1f}%")
            self.log_message("=" * 50)
            
        except Exception as e:
            # Формируем результат с ошибкой
            self.log_message(f"\n💥 КРИТИЧЕСКАЯ ОШИБКА: {str(e)}")
            result = {
                'success': False,
                'message': f"Произошла критическая ошибка:\n{str(e)}"
            }
        finally:
            # Помещаем финализацию UI в очередь
            self.ui_queue.put(('finish', result))
    
    def browse_download_csv_multiple(self):
        """Выбор нескольких CSV файлов для скачивания изображений"""
        filenames = filedialog.askopenfilenames(
            title="Выберите CSV файлы с URL изображений",
            initialdir=self._get_initial_dir(),
            filetypes=CSV_FILETYPES
        )
        if filenames:
            self.download_csv_files = list(filenames)
            
            # Обновляем отображение
            if len(filenames) == 1:
                display_text = f"1 файл: {os.path.basename(filenames[0])}"
            else:
                display_text = f"{len(filenames)} файлов: {', '.join([os.path.basename(f) for f in filenames[:3]])}"
                if len(filenames) > 3:
                    display_text += f" и ещё {len(filenames) - 3}..."
            
            self.download_csv_files_display.set(display_text)
            self.log_message(f"✓ Выбрано {len(filenames)} CSV файлов для скачивания")
            
            # Автоматически определяем колонки из первого файла
            first_file = filenames[0]
            df_preview = self._read_csv_preview(first_file, nrows=5)
            if df_preview is not None:
                columns = list(df_preview.columns)
                self.log_message(f"📋 Найденные колонки в первом файле: {', '.join(columns)}")
                
                # Пытаемся найти подходящие колонки автоматически
                url_candidates = [col for col in columns if any(word in col.lower() for word in ['url', 'image', 'img', 'link', 'photo'])]
                sku_candidates = [col for col in columns if any(word in col.lower() for word in ['sku', 'article', 'артикул', 'code', 'id'])]
                
                if url_candidates:
                    self.download_url_column.set(url_candidates[0])
                    self.log_message(f"🎯 Автоматически выбрана колонка URL: {url_candidates[0]}")
                    
                if sku_candidates:
                    self.download_sku_column.set(sku_candidates[0])
                    self.log_message(f"🎯 Автоматически выбрана колонка SKU: {sku_candidates[0]}")
    
    def clear_download_csv_files(self):
        """Очищает список выбранных CSV файлов"""
        self.download_csv_files = []
        self.download_csv_files_display.set("Файлы не выбраны")
        self.log_message("🗑️ Список CSV файлов очищен")
    
    def browse_download_output_folder(self):
        """Выбор папки для сохранения скачанных изображений"""
        folder = filedialog.askdirectory(
            title="Выберите папку для сохранения изображений",
            initialdir=self._get_initial_dir()
        )
        if folder:
            self.download_output_folder.set(folder)
            self.log_message(f"✓ Выбрана папка для сохранения: {os.path.basename(folder)}")
    
    def start_image_download(self):
        """Запуск процесса скачивания изображений"""
        if self.is_downloading:
            messagebox.showwarning("Внимание", "Скачивание уже идет.")
            return
            
        if not self.download_csv_files:
            messagebox.showerror("Ошибка", "Не выбраны CSV файлы.")
            return
        
        # Проверяем существование всех файлов
        missing_files = [f for f in self.download_csv_files if not os.path.exists(f)]
        if missing_files:
            messagebox.showerror("Ошибка", f"Не найдены файлы:\n" + "\n".join([os.path.basename(f) for f in missing_files]))
            return
        
        output_folder = self.download_output_folder.get()
        if not output_folder:
            messagebox.showerror("Ошибка", "Не указана базовая папка для сохранения.")
            return
        
        url_column = self.download_url_column.get().strip()
        sku_column = self.download_sku_column.get().strip()
        
        if not url_column or not sku_column:
            messagebox.showerror("Ошибка", "Не указаны названия колонок URL и SKU.")
            return
        
        self.is_downloading = True
        self.download_start_button.config(state=tk.DISABLED)
        self.download_stop_button.config(state=tk.NORMAL)
        
        self.log_message("🚀 Запуск скачивания изображений...")
        self.log_message(f"📁 Будет обработано {len(self.download_csv_files)} файлов")
        
        # Запуск в отдельном потоке
        download_thread = threading.Thread(
            target=self.download_worker_multiple,
            args=(self.download_csv_files, output_folder, url_column, sku_column),
            daemon=True
        )
        download_thread.start()
    
    def stop_image_download(self):
        """Остановка скачивания изображений"""
        self._download_stop_flag = True
        if self.image_downloader:
            self.image_downloader.stop_download()
            self.log_message("⚠ Получен сигнал остановки скачивания...")
    
    def download_worker(self, csv_file: str, output_folder: str, url_column: str, sku_column: str):
        """Рабочий процесс скачивания изображений"""
        try:
            # Создаем загрузчик изображений
            self.image_downloader = ImageDownloader(output_folder)
            self.image_downloader.set_log_callback(self.log_message)
            self.image_downloader.set_progress_callback(self.update_progress)
            
            # Запускаем скачивание
            stats = self.image_downloader.download_images_from_csv(
                csv_file=csv_file,
                convert_enabled=self.enable_image_conversion.get(),
                url_column=url_column,
                sku_column=sku_column,
                max_workers=self.download_max_workers.get()
            )
            
            # Показываем результаты
            success_rate = (stats['downloaded'] / stats['total'] * 100) if stats['total'] > 0 else 0
            
            if stats['errors'] == 0:
                self._show_message_async(
                    "info",
                    "Скачивание завершено",
                    f"Скачивание завершено успешно!\n\n"
                    f"Всего записей: {stats['total']}\n"
                    f"Скачано: {stats['downloaded']}\n"
                    f"Преобразовано: {stats['converted']}\n"
                    f"Пропущено: {stats['skipped']}\n"
                    f"Успешность: {success_rate:.1f}%"
                )
            else:
                self._show_message_async(
                    "warning",
                    "Скачивание завершено с ошибками",
                    f"Скачивание завершено!\n\n"
                    f"Всего записей: {stats['total']}\n"
                    f"Скачано: {stats['downloaded']}\n"
                    f"Преобразовано: {stats['converted']}\n"
                    f"Пропущено: {stats['skipped']}\n"
                    f"Ошибки: {stats['errors']}\n"
                    f"Успешность: {success_rate:.1f}%"
                )
            
        except Exception as e:
            self.log_message(f"💥 КРИТИЧЕСКАЯ ОШИБКА при скачивании: {str(e)}")
            self._show_message_async("error", "Критическая ошибка", f"Произошла критическая ошибка:\n{str(e)}")
        finally:
            # Восстанавливаем состояние кнопок
            self.is_downloading = False
            self.download_start_button.config(state=tk.NORMAL)
            self.download_stop_button.config(state=tk.DISABLED)
            self.image_downloader = None
    
    def download_worker_multiple(self, csv_files: list, base_output_folder: str, url_column: str, sku_column: str):
        """Рабочий процесс скачивания изображений из нескольких CSV файлов"""
        try:
            total_stats = {
                'total': 0,
                'downloaded': 0,
                'converted': 0,
                'errors': 0,
                'skipped': 0,
                'files_processed': 0
            }
            
            self.log_message("=" * 50)
            self.log_message("🚀 НАЧАЛО МАССОВОГО СКАЧИВАНИЯ ИЗОБРАЖЕНИЙ")
            self.log_message("=" * 50)
            
            # Сбрасываем флаг остановки
            self._download_stop_flag = False
            
            # Обрабатываем каждый CSV файл
            for file_index, csv_file in enumerate(csv_files, 1):
                if self._download_stop_flag:
                    break
                    
                filename_without_ext = os.path.splitext(os.path.basename(csv_file))[0]
                
                # Определяем папку для сохранения
                if len(csv_files) == 1:
                    # Если только один файл, используем базовую папку
                    output_folder = base_output_folder
                else:
                    # Если несколько файлов, создаем отдельную папку для каждого
                    output_folder = f"{base_output_folder}_{filename_without_ext}"
                
                self.log_message(f"\n📂 [{file_index}/{len(csv_files)}] Обработка файла: {os.path.basename(csv_file)}")
                self.log_message(f"📁 Папка сохранения: {output_folder}")
                
                # Создаем загрузчик для текущего файла
                self.image_downloader = ImageDownloader(output_folder)
                self.image_downloader.set_log_callback(self.log_message)
                self.image_downloader.set_progress_callback(
                    lambda current, total, message, fi=file_index: 
                    self.update_progress(current, total, f"[{fi}/{len(csv_files)}] {message}")
                )
                
                # Скачиваем изображения из текущего файла
                file_stats = self.image_downloader.download_images_from_csv(
                    csv_file=csv_file,
                    convert_enabled=self.enable_image_conversion.get(),
                    url_column=url_column,
                    sku_column=sku_column,
                    max_workers=self.download_max_workers.get()
                )
                
                # Обновляем общую статистику
                total_stats['total'] += file_stats['total']
                total_stats['downloaded'] += file_stats['downloaded']
                total_stats['converted'] += file_stats['converted']
                total_stats['errors'] += file_stats['errors']
                total_stats['skipped'] += file_stats['skipped']
                total_stats['files_processed'] += 1
                
                if self._download_stop_flag:
                    self.log_message("⚠️ Процесс остановлен пользователем")
                    break
            
            # Итоговая статистика
            self.log_message("\n" + "=" * 50)
            self.log_message("📊 ИТОГОВЫЕ РЕЗУЛЬТАТЫ МАССОВОГО СКАЧИВАНИЯ")
            self.log_message("=" * 50)
            self.log_message(f"Обработано файлов: {total_stats['files_processed']}/{len(csv_files)}")
            self.log_message(f"Всего записей: {total_stats['total']}")
            self.log_message(f"Скачано: {total_stats['downloaded']}")
            self.log_message(f"Преобразовано: {total_stats['converted']}")
            self.log_message(f"Пропущено: {total_stats['skipped']}")
            self.log_message(f"Ошибки: {total_stats['errors']}")
            
            # Показываем результаты
            success_rate = (total_stats['downloaded'] / total_stats['total'] * 100) if total_stats['total'] > 0 else 0
            
            if total_stats['errors'] == 0:
                self._show_message_async(
                    "info",
                    "Массовое скачивание завершено",
                    f"Скачивание завершено успешно!\n\n"
                    f"Обработано файлов: {total_stats['files_processed']}/{len(csv_files)}\n"
                    f"Всего записей: {total_stats['total']}\n"
                    f"Скачано: {total_stats['downloaded']}\n"
                    f"Преобразовано: {total_stats['converted']}\n"
                    f"Пропущено: {total_stats['skipped']}\n"
                    f"Успешность: {success_rate:.1f}%"
                )
            else:
                self._show_message_async(
                    "warning",
                    "Массовое скачивание завершено с ошибками",
                    f"Скачивание завершено!\n\n"
                    f"Обработано файлов: {total_stats['files_processed']}/{len(csv_files)}\n"
                    f"Всего записей: {total_stats['total']}\n"
                    f"Скачано: {total_stats['downloaded']}\n"
                    f"Преобразовано: {total_stats['converted']}\n"
                    f"Пропущено: {total_stats['skipped']}\n"
                    f"Ошибки: {total_stats['errors']}\n"
                    f"Успешность: {success_rate:.1f}%"
                )
            
        except Exception as e:
            self.log_message(f"💥 КРИТИЧЕСКАЯ ОШИБКА при массовом скачивании: {str(e)}")
            self._show_message_async("error", "Критическая ошибка", f"Произошла критическая ошибка:\n{str(e)}")
        finally:
            # Восстанавливаем состояние кнопок
            self.is_downloading = False
            self.download_start_button.config(state=tk.NORMAL)
            self.download_stop_button.config(state=tk.DISABLED)
            self.image_downloader = None
    
    def setup_ai_description_tab(self, notebook):
        """Настройка вкладки генерации AI описаний"""
        # Создаем прокручиваемый фрейм
        scrollable_tab = ScrollableFrame(notebook)
        notebook.add(scrollable_tab, text="Генерация описаний")
        ai_frame = scrollable_tab.scrollable_frame
        
        # Настройки файлов
        files_frame = ttk.LabelFrame(ai_frame, text="Файлы", padding=10)
        files_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # CSV файл
        csv_frame = tk.Frame(files_frame)
        csv_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(csv_frame, text="CSV файл:", width=20, anchor='w').pack(side=tk.LEFT)
        csv_entry = tk.Entry(csv_frame, textvariable=self.ai_csv_file_path)
        csv_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        tk.Button(csv_frame, text="Обзор", command=self.browse_ai_csv_file).pack(side=tk.RIGHT)
        
        # Колонка с названиями товаров
        name_column_frame = tk.Frame(files_frame)
        name_column_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(name_column_frame, text="Колонка названий:", width=20, anchor='w').pack(side=tk.LEFT)
        tk.Entry(name_column_frame, textvariable=self.ai_name_column).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Настройки API
        api_frame = ttk.LabelFrame(ai_frame, text="Настройки AI API", padding=10)
        api_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # API ключ
        api_key_frame = tk.Frame(api_frame)
        api_key_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(api_key_frame, text="API ключ:", width=20, anchor='w').pack(side=tk.LEFT)
        api_key_entry = tk.Entry(api_key_frame, textvariable=self.ai_api_key, show="*")
        api_key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # API URL
        api_url_frame = tk.Frame(api_frame)
        api_url_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(api_url_frame, text="API URL:", width=20, anchor='w').pack(side=tk.LEFT)
        tk.Entry(api_url_frame, textvariable=self.ai_api_url).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Модель
        model_frame = tk.Frame(api_frame)
        model_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(model_frame, text="Модель:", width=20, anchor='w').pack(side=tk.LEFT)
        model_entry = tk.Entry(model_frame, textvariable=self.ai_model)
        model_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Температура
        temperature_frame = tk.Frame(api_frame)
        temperature_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(temperature_frame, text="Температура:", width=20, anchor='w').pack(side=tk.LEFT)
        tk.Scale(
            temperature_frame,
            from_=0.0,
            to=1.0,
            resolution=0.1,
            orient=tk.HORIZONTAL,
            variable=self.ai_temperature
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Настройки генерации
        generation_frame = ttk.LabelFrame(ai_frame, text="Настройки генерации", padding=10)
        generation_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Язык
        language_frame = tk.Frame(generation_frame)
        language_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(language_frame, text="Язык описаний:", width=20, anchor='w').pack(side=tk.LEFT)
        language_combo = ttk.Combobox(
            language_frame,
            textvariable=self.ai_language,
            values=["русский", "english", "español", "français", "deutsch"],
            state="readonly"
        )
        language_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Переводить названия товаров
        translate_names_frame = tk.Frame(generation_frame)
        translate_names_frame.pack(fill=tk.X, pady=(0, 5))
        
        translate_names_checkbox = tk.Checkbutton(
            translate_names_frame,
            text="Переводить названия товаров на язык описаний",
            variable=self.ai_translate_names,
            onvalue=True,
            offvalue=False
        )
        translate_names_checkbox.pack(anchor='w')
        
        # Описание опции
        translate_desc = tk.Label(
            translate_names_frame,
            text="При включении названия товаров будут переведены на язык описаний (например, с русского на английский)",
            justify=tk.LEFT,
            wraplength=600,
            fg='#666666',
            font=("Arial", 8)
        )
        translate_desc.pack(anchor='w', pady=(2, 0))
        
        # Максимальная длина описания
        max_length_frame = tk.Frame(generation_frame)
        max_length_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(max_length_frame, text="Макс. длина:", width=20, anchor='w').pack(side=tk.LEFT)
        tk.Spinbox(
            max_length_frame,
            from_=100,
            to=1000,
            width=8,
            textvariable=self.ai_max_description_length
        ).pack(side=tk.LEFT)
        tk.Label(max_length_frame, text="символов").pack(side=tk.LEFT, padx=(5, 0))
        
        # Размер пакета
        batch_size_frame = tk.Frame(generation_frame)
        batch_size_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(batch_size_frame, text="Размер пакета:", width=20, anchor='w').pack(side=tk.LEFT)
        tk.Spinbox(
            batch_size_frame,
            from_=1,
            to=20,
            width=8,
            textvariable=self.ai_batch_size
        ).pack(side=tk.LEFT)
        tk.Label(batch_size_frame, text="товаров").pack(side=tk.LEFT, padx=(5, 0))
        
        # Задержка между пакетами
        delay_frame = tk.Frame(generation_frame)
        delay_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(delay_frame, text="Задержка:", width=20, anchor='w').pack(side=tk.LEFT)
        tk.Scale(
            delay_frame,
            from_=0.0,
            to=10.0,
            resolution=0.5,
            orient=tk.HORIZONTAL,
            variable=self.ai_delay_between_batches
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(delay_frame, text="сек.").pack(side=tk.RIGHT)
        
        # --- Настройки отказоустойчивости (Retry) ---
        retry_section = tk.LabelFrame(ai_frame, text="🔄 Отказоустойчивость", font=("Arial", 10, "bold"))
        retry_section.pack(fill=tk.X, padx=10, pady=(10, 0))
        
        retry_frame = tk.Frame(retry_section)
        retry_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Максимальное количество повторных попыток
        max_retries_frame = tk.Frame(retry_frame)
        max_retries_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(max_retries_frame, text="Попыток при ошибке:", width=20, anchor='w').pack(side=tk.LEFT)
        tk.Spinbox(
            max_retries_frame,
            from_=1,
            to=10,
            width=8,
            textvariable=self.ai_max_retries
        ).pack(side=tk.LEFT)
        tk.Label(max_retries_frame, text="раз").pack(side=tk.LEFT, padx=(5, 0))
        
        # Начальная задержка retry
        retry_delay_frame = tk.Frame(retry_frame)
        retry_delay_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(retry_delay_frame, text="Задержка retry:", width=20, anchor='w').pack(side=tk.LEFT)
        tk.Scale(
            retry_delay_frame,
            from_=0.5,
            to=10.0,
            resolution=0.5,
            orient=tk.HORIZONTAL,
            variable=self.ai_retry_delay
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(retry_delay_frame, text="сек.").pack(side=tk.RIGHT)
        
        # Таймаут запроса
        timeout_frame = tk.Frame(retry_frame)
        timeout_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(timeout_frame, text="Таймаут запроса:", width=20, anchor='w').pack(side=tk.LEFT)
        tk.Spinbox(
            timeout_frame,
            from_=30,
            to=300,
            increment=30,
            width=8,
            textvariable=self.ai_timeout
        ).pack(side=tk.LEFT)
        tk.Label(timeout_frame, text="сек.").pack(side=tk.LEFT, padx=(5, 0))
        
        # Кнопки управления
        buttons_frame = tk.Frame(ai_frame)
        buttons_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.ai_start_button = tk.Button(
            buttons_frame,
            text="Начать генерацию",
            command=self.start_ai_generation,
            bg='#27ae60',
            fg='white',
            font=("Arial", 11, "bold"),
            padx=20,
            pady=5
        )
        self.ai_start_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.ai_stop_button = tk.Button(
            buttons_frame,
            text="Остановить",
            command=self.stop_ai_generation,
            bg='#e74c3c',
            fg='white',
            font=("Arial", 11, "bold"),
            padx=20,
            pady=5,
            state=tk.DISABLED
        )
        self.ai_stop_button.pack(side=tk.LEFT)
        
        # Кнопки для настроек
        settings_buttons_frame = tk.Frame(buttons_frame)
        settings_buttons_frame.pack(side=tk.RIGHT)
        
        tk.Button(
            settings_buttons_frame,
            text="Загрузить настройки",
            command=self.load_ai_settings
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        tk.Button(
            settings_buttons_frame,
            text="Сохранить настройки",
            command=self.save_ai_settings
        ).pack(side=tk.LEFT)
        
        # Информация
        info_frame = ttk.LabelFrame(ai_frame, text="Информация", padding=10)
        info_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        info_text = """
🤖 ГЕНЕРАЦИЯ AI ОПИСАНИЙ:

📋 ПРИНЦИП РАБОТЫ:
• Выберите CSV файл с названиями товаров
• Укажите колонку с названиями товаров
• Настройте параметры AI API (ключ, модель, температура)
• Выберите язык описаний и максимальную длину

🔧 НАСТРОЙКИ API:
• API ключ - ваш ключ доступа к vsegpt
• URL - endpoint API (по умолчанию vsegpt)
• Модель - используемая AI модель (gpt-3.5-turbo рекомендуется)
• Температура - креативность ответов (0.0-1.0)

⚡ ПАКЕТНАЯ ОБРАБОТКА:
• Товары обрабатываются пакетами для экономии запросов
• Размер пакета - количество товаров в одном запросе
• Задержка между пакетами - пауза между запросами

🔄 ОТКАЗОУСТОЙЧИВОСТЬ:
• Автоматические повторные попытки при ошибках
• Экспоненциальная задержка между повторами
• Увеличенный таймаут для стабильности
• Восстановление неполных JSON ответов

📝 РЕЗУЛЬТАТ:
• Создается/обновляется колонка 'description' в CSV файле
• Описания генерируются на указанном языке
• Максимальная длина описаний ограничена
• Подробная статистика включая retry данные

💡 РЕКОМЕНДАЦИИ:
• Используйте размер пакета 3-7 товаров для лучших результатов
• Установите задержку 1-2 секунды между пакетами
• Настройте 3-5 повторных попыток для надежности
• Увеличьте таймаут до 120+ секунд для крупных пакетов
• Проверьте правильность названия колонки
• Сохраните резервную копию CSV перед генерацией
        """
        
        tk.Label(
            info_frame,
            text=info_text,
            justify=tk.LEFT,
            wraplength=750,
            anchor='nw'
        ).pack(fill=tk.BOTH, expand=True)
    
    def browse_ai_csv_file(self):
        """Выбор CSV файла для генерации описаний"""
        filename = filedialog.askopenfilename(
            title="Выберите CSV файл для генерации описаний",
            initialdir=self._get_initial_dir(),
            filetypes=CSV_FILETYPES
        )
        if filename:
            self.ai_csv_file_path.set(filename)
            self.log_message(f"✓ Выбран CSV файл для AI генерации: {os.path.basename(filename)}")
            
            # Автоматически определяем колонки
            df_preview = self._read_csv_preview(filename, nrows=5)
            if df_preview is not None:
                columns = list(df_preview.columns)
                self.log_message(f"📋 Найденные колонки: {', '.join(columns)}")
                
                # Пытаемся найти подходящие колонки автоматически
                name_candidates = [col for col in columns if any(word in col.lower() 
                                 for word in ['name', 'title', 'название', 'наименование', 'товар', 'product'])]
                
                if name_candidates:
                    self.ai_name_column.set(name_candidates[0])
                    self.log_message(f"🎯 Автоматически выбрана колонка названий: {name_candidates[0]}")
    
    def load_ai_settings(self):
        """Загрузка настроек AI из gui_settings.json"""
        try:
            if not os.path.exists(SETTINGS_FILE):
                messagebox.showwarning("Внимание", "Файл gui_settings.json не найден")
                return
            
            settings = self._load_settings_file()
            self._apply_settings(settings, {
                'ai_api_key': self.ai_api_key,
                'ai_api_url': self.ai_api_url,
                'ai_model': self.ai_model,
                'ai_temperature': self.ai_temperature,
                'ai_language': self.ai_language,
                'ai_max_description_length': self.ai_max_description_length,
                'ai_batch_size': self.ai_batch_size,
                'ai_delay_between_batches': self.ai_delay_between_batches,
                'ai_translate_names': self.ai_translate_names,
                'ai_max_retries': self.ai_max_retries,
                'ai_retry_delay': self.ai_retry_delay,
                'ai_timeout': self.ai_timeout
            })
                
            self.log_message(f"✅ Настройки AI перезагружены из gui_settings.json")
            messagebox.showinfo("Загружено", "Настройки AI успешно перезагружены из gui_settings.json")
                
        except Exception as e:
            self.log_message(f"❌ Ошибка при загрузке настроек AI: {str(e)}")
            messagebox.showerror("Ошибка", f"Не удалось загрузить настройки:\n{str(e)}")
    
    def save_ai_settings(self):
        """Сохранение настроек AI в gui_settings.json"""
        try:
            self._update_settings({
                'ai_api_key': self.ai_api_key.get(),
                'ai_api_url': self.ai_api_url.get(),
                'ai_model': self.ai_model.get(),
                'ai_temperature': self.ai_temperature.get(),
                'ai_language': self.ai_language.get(),
                'ai_max_description_length': self.ai_max_description_length.get(),
                'ai_batch_size': self.ai_batch_size.get(),
                'ai_delay_between_batches': self.ai_delay_between_batches.get(),
                'ai_translate_names': self.ai_translate_names.get(),
                'ai_max_retries': self.ai_max_retries.get(),
                'ai_retry_delay': self.ai_retry_delay.get(),
                'ai_timeout': self.ai_timeout.get()
            })
                
            self.log_message(f"✅ Настройки AI сохранены в gui_settings.json")
            messagebox.showinfo("Сохранено", "Настройки AI успешно сохранены в gui_settings.json")
                
        except Exception as e:
            self.log_message(f"❌ Ошибка при сохранении настроек AI: {str(e)}")
            messagebox.showerror("Ошибка", f"Не удалось сохранить настройки:\n{str(e)}")
    
    def start_ai_generation(self):
        """Запуск генерации AI описаний"""
        if self.is_generating:
            messagebox.showwarning("Внимание", "Генерация уже идет.")
            return
            
        csv_file = self.ai_csv_file_path.get()
        if not csv_file:
            messagebox.showerror("Ошибка", "Не выбран CSV файл.")
            return
            
        if not os.path.exists(csv_file):
            messagebox.showerror("Ошибка", "Выбранный CSV файл не существует.")
            return
        
        api_key = self.ai_api_key.get().strip()
        if not api_key:
            messagebox.showerror("Ошибка", "Не указан API ключ.")
            return
        
        api_url = self.ai_api_url.get().strip()
        if not api_url:
            messagebox.showerror("Ошибка", "Не указан API URL.")
            return
        
        name_column = self.ai_name_column.get().strip()
        if not name_column:
            messagebox.showerror("Ошибка", "Не указана колонка с названиями товаров.")
            return
        
        self.is_generating = True
        self.ai_start_button.config(state=tk.DISABLED)
        self.ai_stop_button.config(state=tk.NORMAL)
        
        self.log_message("🤖 Запуск генерации AI описаний...")
        
        # Запуск в отдельном потоке
        generation_thread = threading.Thread(
            target=self.ai_generation_worker,
            args=(csv_file, api_key, api_url, name_column),
            daemon=True
        )
        generation_thread.start()
    
    def stop_ai_generation(self):
        """Остановка генерации AI описаний"""
        self._ai_stop_flag = True
        if self.ai_generator:
            self.ai_generator.stop_generation()
            self.log_message("⚠ Получен сигнал остановки генерации AI...")
    
    def ai_generation_worker(self, csv_file: str, api_key: str, api_url: str, name_column: str):
        """Рабочий процесс генерации AI описаний"""
        try:
            # Сбрасываем флаг остановки
            self._ai_stop_flag = False
            
            # Создаем AI генератор с настройками retry
            self.ai_generator = AIDescriptionGenerator(
                api_key=api_key,
                api_url=api_url,
                model=self.ai_model.get(),
                temperature=self.ai_temperature.get(),
                max_retries=self.ai_max_retries.get(),
                retry_delay=self.ai_retry_delay.get(),
                timeout=self.ai_timeout.get()
            )
            
            self.ai_generator.set_log_callback(self.log_message)
            self.ai_generator.set_progress_callback(self.update_progress)
            
            # Запускаем генерацию
            stats = self.ai_generator.generate_descriptions_from_csv(
                csv_file=csv_file,
                name_column=name_column,
                language=self.ai_language.get(),
                max_length=self.ai_max_description_length.get(),
                batch_size=self.ai_batch_size.get(),
                delay_between_batches=self.ai_delay_between_batches.get(),
                translate_names=self.ai_translate_names.get()
            )
            
            # Показываем результаты
            success_rate = (stats['generated'] / stats['total'] * 100) if stats['total'] > 0 else 0
            
            if stats['errors'] == 0:
                self._show_message_async(
                    "info",
                    "Генерация завершена",
                    f"Генерация описаний завершена успешно!\n\n"
                    f"Всего товаров: {stats['total']}\n"
                    f"Сгенерировано описаний: {stats['generated']}\n"
                    f"Обработано пакетов: {stats['batches']}\n"
                    f"Пропущено: {stats['skipped']}\n"
                    f"Успешность: {success_rate:.1f}%"
                )
            else:
                self._show_message_async(
                    "warning",
                    "Генерация завершена с ошибками",
                    f"Генерация описаний завершена!\n\n"
                    f"Всего товаров: {stats['total']}\n"
                    f"Сгенерировано описаний: {stats['generated']}\n"
                    f"Обработано пакетов: {stats['batches']}\n"
                    f"Пропущено: {stats['skipped']}\n"
                    f"Ошибки: {stats['errors']}\n"
                    f"Успешность: {success_rate:.1f}%"
                )
            
        except Exception as e:
            self.log_message(f"💥 КРИТИЧЕСКАЯ ОШИБКА при генерации AI: {str(e)}")
            self._show_message_async("error", "Критическая ошибка", f"Произошла критическая ошибка:\n{str(e)}")
        finally:
            # Восстанавливаем состояние кнопок
            self.is_generating = False
            self.ai_start_button.config(state=tk.NORMAL)
            self.ai_stop_button.config(state=tk.DISABLED)
            self.ai_generator = None
    
    def load_settings_on_startup(self):
        """Автоматическая загрузка настроек при запуске приложения"""
        try:
            if not os.path.exists(SETTINGS_FILE):
                self.log_message("📋 Файл gui_settings.json не найден - используются настройки по умолчанию")
                return

            self.log_message("🔧 Автоматическая загрузка настроек при запуске...")
            settings = self._load_settings_file()

            loaded_settings = []

            if any(k in settings for k in ['sftp_host', 'sftp_port', 'sftp_username', 'sftp_password', 'sftp_remote_base_path', 'sftp_web_domain']):
                self._apply_settings(settings, {
                    'sftp_host': self.ssh_host,
                    'sftp_port': self.ssh_port,
                    'sftp_username': self.ssh_username,
                    'sftp_password': self.ssh_password,
                    'sftp_remote_base_path': self.ssh_remote_path,
                    'sftp_web_domain': self.ssh_web_domain
                })
                loaded_settings.append("SFTP")

            if any(k in settings for k in ['wc_url', 'wc_consumer_key', 'wc_consumer_secret', 'wc_timeout', 'wp_username', 'wp_app_password', 'wp_email']):
                self._apply_settings(settings, {
                    'wc_url': self.wc_url,
                    'wc_consumer_key': self.wc_consumer_key,
                    'wc_consumer_secret': self.wc_consumer_secret,
                    'wc_timeout': self.wc_timeout,
                    'wp_username': self.wp_username,
                    'wp_app_password': self.wp_app_password,
                    'wp_email': self.wp_email
                })
                loaded_settings.append("WooCommerce")

            if any(k in settings for k in [
                'ai_api_key', 'ai_api_url', 'ai_model', 'ai_temperature', 'ai_language',
                'ai_max_description_length', 'ai_batch_size', 'ai_delay_between_batches',
                'ai_translate_names', 'ai_max_retries', 'ai_retry_delay', 'ai_timeout'
            ]):
                self._apply_settings(settings, {
                    'ai_api_key': self.ai_api_key,
                    'ai_api_url': self.ai_api_url,
                    'ai_model': self.ai_model,
                    'ai_temperature': self.ai_temperature,
                    'ai_language': self.ai_language,
                    'ai_max_description_length': self.ai_max_description_length,
                    'ai_batch_size': self.ai_batch_size,
                    'ai_delay_between_batches': self.ai_delay_between_batches,
                    'ai_translate_names': self.ai_translate_names,
                    'ai_max_retries': self.ai_max_retries,
                    'ai_retry_delay': self.ai_retry_delay,
                    'ai_timeout': self.ai_timeout
                })
                loaded_settings.append("AI")

            if loaded_settings:
                settings_str = ", ".join(loaded_settings)
                self.log_message(f"✅ Настройки загружены: {settings_str}")
            else:
                self.log_message("⚠️ Файл настроек найден, но настройки не загружены")
                
        except Exception as e:
            self.log_message(f"❌ Ошибка при загрузке настроек: {str(e)}")

    def setup_image_processing_tab(self, notebook):
        """Настройка вкладки обработки изображений"""
        # Создаем прокручиваемый фрейм
        scrollable_tab = ScrollableFrame(notebook)
        notebook.add(scrollable_tab, text="Обработка изображений")
        process_frame = scrollable_tab.scrollable_frame

        # Настройки папок
        folders_frame = ttk.LabelFrame(process_frame, text="Папки", padding=10)
        folders_frame.pack(fill=tk.X, padx=10, pady=10)

        # Исходная папка
        source_frame = tk.Frame(folders_frame)
        source_frame.pack(fill=tk.X, pady=(0, 5))

        tk.Label(source_frame, text="Исходная папка:", width=20, anchor='w').pack(side=tk.LEFT)
        source_entry = tk.Entry(source_frame, textvariable=self.process_source_folder)
        source_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        tk.Button(source_frame, text="Выбрать", command=self.browse_process_source_folder).pack(side=tk.RIGHT)

        # Папка для результатов
        output_frame = tk.Frame(folders_frame)
        output_frame.pack(fill=tk.X, pady=(0, 10))

        tk.Label(output_frame, text="Папка результатов:", width=20, anchor='w').pack(side=tk.LEFT)
        output_entry = tk.Entry(output_frame, textvariable=self.process_output_folder)
        output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        tk.Button(output_frame, text="Выбрать", command=self.browse_process_output_folder).pack(side=tk.RIGHT)

        # Настройки обработки
        processing_frame = ttk.LabelFrame(process_frame, text="Настройки обработки", padding=10)
        processing_frame.pack(fill=tk.X, padx=10, pady=10)

        # Количество потоков
        threads_frame = tk.Frame(processing_frame)
        threads_frame.pack(fill=tk.X, pady=(0, 5))

        tk.Label(threads_frame, text="Количество потоков:", width=20, anchor='w').pack(side=tk.LEFT)
        tk.Spinbox(
            threads_frame,
            from_=1,
            to=10,
            width=8,
            textvariable=self.process_max_workers
        ).pack(side=tk.LEFT)

        # Кнопки управления
        buttons_frame = tk.Frame(process_frame)
        buttons_frame.pack(fill=tk.X, padx=10, pady=10)

        self.process_start_button = tk.Button(
            buttons_frame,
            text="Начать обработку",
            command=self.start_image_processing,
            bg='#27ae60',
            fg='white',
            font=("Arial", 11, "bold"),
            padx=20,
            pady=5
        )
        self.process_start_button.pack(side=tk.LEFT, padx=(0, 10))

        self.process_stop_button = tk.Button(
            buttons_frame,
            text="Остановить",
            command=self.stop_image_processing,
            bg='#e74c3c',
            fg='white',
            font=("Arial", 11, "bold"),
            padx=20,
            pady=5,
            state=tk.DISABLED
        )
        self.process_stop_button.pack(side=tk.LEFT)

        # Информация
        info_frame = ttk.LabelFrame(process_frame, text="Информация", padding=10)
        info_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        info_text = """
🖼️ ОБРАБОТКА ИЗОБРАЖЕНИЙ:

🎯 ФУНКЦИОНАЛЬНОСТЬ:
• Преобразование изображений в унифицированный формат 2560x1440
• Анализ качества и умное масштабирование
• Размещение изображений по центру белого холста
• Поддержка множественных форматов (JPG, PNG, WebP, BMP, TIFF)

📁 РАБОТА С ПАПКАМИ:
• Выберите исходную папку с изображениями для обработки
• Укажите папку для сохранения результатов
• Обрабатываются все поддерживаемые форматы в исходной папке

⚡ ПАРАЛЛЕЛЬНАЯ ОБРАБОТКА:
• Настройте количество потоков для ускорения обработки
• Рекомендуется 2-4 потока в зависимости от мощности ПК
• Подробная статистика обработки для каждого файла

📊 РЕЗУЛЬТАТЫ:
• Подробный лог обработки с информацией о каждом изображении
• Статистика по качеству, размерам и масштабированию
• Сохранение результатов в указанную папку
• Поддержка кириллицы в именах файлов

🔧 ТЕХНИЧЕСКИЕ ДЕТАЛИ:
• Автоматическое определение оптимального масштаба
• Повышение резкости при необходимости
• Сохранение в формате JPEG с качеством 100%
• Центрирование изображений на белом фоне
        """

        tk.Label(
            info_frame,
            text=info_text,
            justify=tk.LEFT,
            wraplength=750,
            anchor='nw'
        ).pack(fill=tk.BOTH, expand=True)

    def browse_process_source_folder(self):
        """Выбор исходной папки для обработки изображений"""
        folder = filedialog.askdirectory(
            title="Выберите папку с изображениями для обработки",
            initialdir=self._get_initial_dir()
        )
        if folder:
            self.process_source_folder.set(folder)
            self.log_message(f"✓ Выбрана исходная папка: {os.path.basename(folder)}")

    def browse_process_output_folder(self):
        """Выбор папки для сохранения обработанных изображений"""
        folder = filedialog.askdirectory(
            title="Выберите папку для сохранения результатов",
            initialdir=self._get_initial_dir()
        )
        if folder:
            self.process_output_folder.set(folder)
            self.log_message(f"✓ Выбрана папка результатов: {os.path.basename(folder)}")

    def start_image_processing(self):
        """Запуск обработки изображений"""
        if self.is_processing_images:
            messagebox.showwarning("Внимание", "Обработка уже идет.")
            return

        source_folder = self.process_source_folder.get()
        if not source_folder:
            messagebox.showerror("Ошибка", "Не выбрана исходная папка.")
            return

        if not os.path.exists(source_folder):
            messagebox.showerror("Ошибка", "Выбранная папка не существует.")
            return

        output_folder = self.process_output_folder.get()
        if not output_folder:
            messagebox.showerror("Ошибка", "Не указана папка для результатов.")
            return

        self.is_processing_images = True
        self.process_start_button.config(state=tk.DISABLED)
        self.process_stop_button.config(state=tk.NORMAL)

        self.log_message("🖼️ Запуск обработки изображений...")

        # Запуск в отдельном потоке
        processing_thread = threading.Thread(
            target=self.image_processing_worker,
            args=(source_folder, output_folder),
            daemon=True
        )
        processing_thread.start()

    def stop_image_processing(self):
        """Остановка обработки изображений"""
        self._process_stop_flag = True
        if self.image_processor:
            self.log_message("⚠ Получен сигнал остановки обработки изображений...")

    def image_processing_worker(self, source_folder: str, output_folder: str):
        """Рабочий процесс обработки изображений"""
        try:
            # Сбрасываем флаг остановки
            self._process_stop_flag = False

            # Импортируем и создаем обработчик изображений
            from image_converter import ImageConverter

            self.log_message("🔧 Инициализация обработчика изображений...")
            self.image_processor = ImageConverter(source_folder, output_folder, log_callback=self.log_message)

            # Запускаем обработку
            self.log_message("=" * 50)
            self.log_message("🚀 НАЧАЛО ОБРАБОТКИ ИЗОБРАЖЕНИЙ")
            self.log_message("=" * 50)

            # Проверяем, не остановлена ли обработка
            if self._process_stop_flag:
                self.log_message("⚠️ Обработка остановлена пользователем")
                return

            # Запускаем обработку
            self.image_processor.convert_images(max_workers=self.process_max_workers.get())

            # Сообщаем о завершении
            self.log_message("\n" + "=" * 50)
            self.log_message("✅ ОБРАБОТКА ИЗОБРАЖЕНИЙ ЗАВЕРШЕНА")
            self.log_message("=" * 50)

            self._show_message_async(
                "info",
                "Обработка завершена",
                f"Обработка изображений завершена!\n\nРезультаты сохранены в: {output_folder}"
            )

        except Exception as e:
            self.log_message(f"💥 КРИТИЧЕСКАЯ ОШИБКА при обработке изображений: {str(e)}")
            self._show_message_async("error", "Критическая ошибка", f"Произошла критическая ошибка:\n{str(e)}")
        finally:
            # Восстанавливаем состояние кнопок
            self.is_processing_images = False
            self.process_start_button.config(state=tk.NORMAL)
            self.process_stop_button.config(state=tk.DISABLED)
            self.image_processor = None

    def run(self):
        """Запуск приложения"""
        self.root.mainloop()


if __name__ == "__main__":
    app = UploaderGUI()
    app.run() 