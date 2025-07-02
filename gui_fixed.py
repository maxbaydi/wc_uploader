#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WooCommerce Product Uploader - Simple GUI
Простой графический интерфейс для загрузчика товаров
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import threading
import time
from console_uploader import ConsoleWooCommerceUploader


class SimpleUploaderGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("WooCommerce Product Uploader")
        self.root.geometry("800x600")
        self.root.minsize(700, 500)
        
        # Переменные
        self.csv_file_path = tk.StringVar()
        self.images_folder_path = tk.StringVar()
        self.products_count = tk.StringVar(value="all")
        self.custom_count = tk.IntVar(value=10)
        
        self.uploader = None
        self.is_uploading = False
        
        self.setup_ui()
        
    def setup_ui(self):
        # Заголовок
        header_frame = tk.Frame(self.root, bg='#2c3e50', height=80)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)
        
        title_label = tk.Label(
            header_frame, 
            text="WooCommerce Product Uploader", 
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
        
        # Вкладка процесса
        self.setup_progress_tab(notebook)
        
    def setup_settings_tab(self, notebook):
        """Настройка вкладки с настройками"""
        settings_frame = ttk.Frame(notebook)
        notebook.add(settings_frame, text="Settings")
        
        # Файлы
        files_frame = ttk.LabelFrame(settings_frame, text="Files", padding=10)
        files_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # CSV файл
        csv_frame = tk.Frame(files_frame)
        csv_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(csv_frame, text="CSV file:", width=15, anchor='w').pack(side=tk.LEFT)
        csv_entry = tk.Entry(csv_frame, textvariable=self.csv_file_path)
        csv_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        tk.Button(csv_frame, text="Browse", command=self.browse_csv_file).pack(side=tk.RIGHT)
        
        # Папка с изображениями
        images_frame = tk.Frame(files_frame)
        images_frame.pack(fill=tk.X)
        
        tk.Label(images_frame, text="Images folder:", width=15, anchor='w').pack(side=tk.LEFT)
        images_entry = tk.Entry(images_frame, textvariable=self.images_folder_path)
        images_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        tk.Button(images_frame, text="Browse", command=self.browse_images_folder).pack(side=tk.RIGHT)
        
        # Количество товаров
        count_frame = ttk.LabelFrame(settings_frame, text="Upload Settings", padding=10)
        count_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(count_frame, text="Number of products:").pack(anchor='w')
        
        radio_frame = tk.Frame(count_frame)
        radio_frame.pack(fill=tk.X, pady=5)
        
        tk.Radiobutton(
            radio_frame, 
            text="All products from file", 
            variable=self.products_count, 
            value="all"
        ).pack(side=tk.LEFT)
        
        tk.Radiobutton(
            radio_frame, 
            text="Custom:", 
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
        
        # Кнопки
        buttons_frame = tk.Frame(settings_frame)
        buttons_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.start_button = tk.Button(
            buttons_frame, 
            text="Start Upload", 
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
            text="Stop", 
            command=self.stop_upload,
            bg='#e74c3c',
            fg='white',
            font=("Arial", 11, "bold"),
            padx=20,
            pady=5,
            state=tk.DISABLED
        )
        self.stop_button.pack(side=tk.LEFT)
        
    def setup_progress_tab(self, notebook):
        """Настройка вкладки с прогрессом"""
        progress_frame = ttk.Frame(notebook)
        notebook.add(progress_frame, text="Progress")
        
        # Прогресс бар
        progress_container = tk.Frame(progress_frame)
        progress_container.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(progress_container, text="Upload Progress:", font=("Arial", 11, "bold")).pack(anchor='w')
        
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
            text="Ready to upload",
            font=("Arial", 10)
        )
        self.status_label.pack(anchor='w')
        
        # Лог
        log_container = tk.Frame(progress_frame)
        log_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        tk.Label(log_container, text="Upload Log:", font=("Arial", 11, "bold")).pack(anchor='w')
        
        self.log_text = scrolledtext.ScrolledText(
            log_container, 
            height=15, 
            wrap=tk.WORD,
            bg='#2c3e50',
            fg='#ecf0f1',
            font=("Consolas", 9)
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Кнопка очистки лога
        tk.Button(
            log_container, 
            text="Clear Log", 
            command=self.clear_log
        ).pack(anchor='w', pady=5)
        
        # Начальное сообщение
        self.log_message("=== WooCommerce Product Uploader ===")
        self.log_message("Select CSV file and images folder to start")
        
    def browse_csv_file(self):
        filename = filedialog.askopenfilename(
            title="Select CSV file",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if filename:
            self.csv_file_path.set(filename)
            self.log_message(f"✓ Selected CSV file: {os.path.basename(filename)}")
            
    def browse_images_folder(self):
        folder = filedialog.askdirectory(title="Select images folder")
        if folder:
            self.images_folder_path.set(folder)
            # Подсчет изображений
            try:
                image_count = len([f for f in os.listdir(folder) 
                                 if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))])
                self.log_message(f"✓ Selected images folder: {os.path.basename(folder)}")
                self.log_message(f"  Found {image_count} images")
            except:
                self.log_message(f"✓ Selected images folder: {os.path.basename(folder)}")
            
    def log_message(self, message):
        """Добавить сообщение в лог"""
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
        
    def clear_log(self):
        """Очистить лог"""
        self.log_text.delete(1.0, tk.END)
        self.log_message("=== Log cleared ===")
        
    def update_progress(self, current, total, message=""):
        """Обновить прогресс"""
        if total > 0:
            progress = (current / total) * 100
            self.progress_var.set(progress)
            
        status_text = f"Processed: {current} of {total}"
        if message:
            status_text += f" - {message}"
        self.status_label.config(text=status_text)
        self.root.update_idletasks()
        
    def start_upload(self):
        """Начать загрузку"""
        if self.is_uploading:
            return
            
        # Проверка входных данных
        if not self.csv_file_path.get():
            messagebox.showerror("Error", "Please select CSV file")
            return
            
        if not os.path.exists(self.csv_file_path.get()):
            messagebox.showerror("Error", "CSV file not found")
            return
            
        # Определение количества товаров
        count = None
        if self.products_count.get() == "custom":
            count = self.custom_count.get()
            
        # Изменение состояния кнопок
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.is_uploading = True
        
        # Сброс прогресса
        self.progress_var.set(0)
        self.status_label.config(text="Initializing...")
        
        # Запуск в отдельном потоке
        self.upload_thread = threading.Thread(
            target=self.upload_worker,
            args=(self.csv_file_path.get(), self.images_folder_path.get(), count),
            daemon=True
        )
        self.upload_thread.start()
        
    def stop_upload(self):
        """Остановить загрузку"""
        if self.uploader:
            self.uploader.stop_upload()
        self.log_message("⚠ Stop signal received...")
        
    def upload_worker(self, csv_file, images_folder, count):
        """Рабочая функция загрузки"""
        try:
            self.log_message("")
            self.log_message("=" * 50)
            self.log_message("🚀 STARTING UPLOAD")
            self.log_message("=" * 50)
            
            # Создание загрузчика
            self.uploader = ConsoleWooCommerceUploader()
            
            # Настройка callback'ов через monkey patching
            original_log = self.uploader.log
            def log_wrapper(message):
                self.log_message(message)
                
            self.uploader.log = log_wrapper
            
            # Загрузка CSV
            df = self.uploader.load_csv_file(csv_file)
            if df is None:
                return
                
            # Адаптация данных
            adapted_df, mapping = self.uploader.csv_adapter.adapt_dataframe(df)
            if adapted_df is None:
                self.log_message("❌ Failed to adapt CSV data")
                return
            
            total_products = len(adapted_df) if count is None else min(count, len(adapted_df))
            
            # Загрузка товаров
            successful_uploads = 0
            failed_uploads = 0
            
            for index, row in adapted_df.iterrows():
                if count is not None and index >= count:
                    break
                    
                if not self.is_uploading:  # Проверка на остановку
                    break
                
                # Обновление прогресса
                current = index + 1
                self.update_progress(current, total_products, f"Processing product {current}")
                
                # Получаем информацию о товаре
                brand = str(row.get('Бренд', '')).strip()
                name = str(row.get('Название', '')).strip()
                sku = str(row.get('Артикул', '')).strip()
                full_name = f"{brand} {name}" if brand and name else (name or "No name")
                
                self.log_message(f"\n📦 Processing product {current}/{total_products}")
                self.log_message(f"Name: {full_name}")
                self.log_message(f"SKU: {sku or 'No SKU'}")
                
                if self.uploader.create_product(row, images_folder):
                    successful_uploads += 1
                else:
                    failed_uploads += 1
                
                # Пауза между запросами
                time.sleep(1)
            
            # Итоги
            self.log_message("\n" + "=" * 50)
            self.log_message("📊 UPLOAD RESULTS:")
            self.log_message(f"✅ Successfully uploaded: {successful_uploads}")
            self.log_message(f"❌ Errors: {failed_uploads}")
            self.log_message(f"📈 Success rate: {(successful_uploads/total_products)*100:.1f}%")
            self.log_message("=" * 50)
            
            if self.is_uploading:  # Если не было остановки
                messagebox.showinfo("Success", f"Upload completed!\n\nUploaded: {successful_uploads} products\nErrors: {failed_uploads}")
            
        except Exception as e:
            self.log_message(f"\n💥 CRITICAL ERROR: {str(e)}")
            messagebox.showerror("Error", f"Critical error occurred:\n{str(e)}")
        finally:
            # Возвращение состояния кнопок
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.status_label.config(text="Ready to upload")
            self.is_uploading = False
            
    def run(self):
        """Запуск приложения"""
        self.root.mainloop()


if __name__ == "__main__":
    app = SimpleUploaderGUI()
    app.run()
