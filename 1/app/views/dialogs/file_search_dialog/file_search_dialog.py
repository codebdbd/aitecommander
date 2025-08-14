import datetime
import fnmatch
import os
import platform
import re
import stat
import subprocess
import time

from PyQt6.QtCore import QDate, QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.utils.ui.dialog_manager import DialogMixin
from app.utils.system.os_ops import open_file as os_open_file
from app.utils.system.os_ops import reveal_in_folder as os_reveal_in_folder


# Базовый класс диалога (если нет, создаем простую версию)
class BaseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)

from .search_signals import SearchSignals
from .common import matches_criteria as _matches_common, check_file_content as _check_content_common
from .search_worker import FileSearchWorker as ExternalFileSearchWorker


class FileSearchDialog(BaseDialog, DialogMixin):
    """
    Диалог для расширенного поиска файлов с фильтрами:
    - Маска (fnmatch)
    - Регулярные выражения по имени
    - Размер файла (минимум/максимум, КБ)
    - Дата модификации (от/до)
    - Атрибуты (скрытые, только для чтения)
    - Поиск по содержимому (текст или regex, с учётом регистра)
    """
    files_selected = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Расширенный поиск файлов")
        self.resize(900, 700)
        
        # Переменные для контроля поиска
        self.search_worker = None
        self.is_searching = False
        
        self._setup_ui()
        self._setup_defaults()
        
        # ThreadPool для фонового поиска
        self.threadpool = QThreadPool()
        
    def _setup_ui(self):
        """Настройка пользовательского интерфейса"""
        layout = QVBoxLayout(self)
        
        # --- Панель основных фильтров ---
        top_layout = QHBoxLayout()
        
        # Выбор папки
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(QLabel("Место поиска:"))
        self.root_le = QLineEdit(os.path.expanduser("~"))
        self.root_le.setMinimumWidth(200)
        browse_btn = QPushButton("Обзор")
        browse_btn.clicked.connect(self._choose_root)
        folder_layout.addWidget(self.root_le)
        folder_layout.addWidget(browse_btn)
        
        # Маска и имя файла на отдельной строке, сначала имя, потом маска
        name_mask_layout = QHBoxLayout()
        name_mask_layout.addWidget(QLabel("Имя (Regex):"))
        from PyQt6.QtWidgets import QSizePolicy
        self.regex_le = QLineEdit()
        self.regex_le.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        name_mask_layout.addWidget(self.regex_le)
        name_mask_layout.setStretch(name_mask_layout.count()-1, 1)
        name_mask_layout.addWidget(QLabel("Маска:"))
        self.pattern_le = QLineEdit("*.*")
        self.pattern_le.setMaximumWidth(100)
        name_mask_layout.addWidget(self.pattern_le)

        # --- Выпадающий список популярных расширений ---
        from PyQt6.QtWidgets import QComboBox
        self.pattern_combo = QComboBox()
        self.pattern_combo.setEditable(False)
        common_patterns = [
            "*.cdr", "*.psd", "*.ai", "*.indd", "*.pdf", "*.doc", "*.docx", "*.xls", "*.xlsx", "*.ppt", "*.pptx", "*.odt", "*.ods", "*.odp", "*.txt", "*.md", "*.jpg", "*.jpeg", "*.png", "*.gif", "*.tiff", "*.svg", "*.webp", "*.ico", "*.raw", "*.nef", "*.dng", "*.mp3", "*.wav", "*.flac", "*.ogg", "*.mp4", "*.avi", "*.mkv", "*.mov", "*.webm", "*.mpeg", "*.fb2", "*.zip", "*.rar", "*.7z", "*.torrent"
        ]
        self.pattern_combo.addItems(common_patterns)
        # Подогнать ширину по содержимому
        font_metrics = self.pattern_combo.fontMetrics()
        max_width = max(font_metrics.horizontalAdvance(ext) for ext in common_patterns)
        self.pattern_combo.setFixedWidth(max_width + 36)  # +36 для стрелки и отступов
        self.pattern_combo.setToolTip("Быстрый выбор маски по расширению")
        self.pattern_combo.setCurrentIndex(-1)
        def set_pattern_from_combo(idx):
            if idx >= 0:
                self.pattern_le.setText(self.pattern_combo.itemText(idx))
        self.pattern_combo.currentIndexChanged.connect(set_pattern_from_combo)
        name_mask_layout.addWidget(self.pattern_combo)
        
        # Содержимое и чекбоксы сразу после маски
        name_mask_layout.addWidget(QLabel("Содержимое:"))
        self.content_le = QLineEdit()
        self.content_le.setMinimumWidth(200)
        self.content_regex_cb = QCheckBox("Regex")
        self.case_cb = QCheckBox("Учёт регистра")
        name_mask_layout.addWidget(self.content_le)
        self.search_btn = QPushButton("Поиск")
        self.search_btn.clicked.connect(self._start_search)
        self.stop_btn = QPushButton("Стоп")
        self.stop_btn.clicked.connect(self._stop_search)
        self.stop_btn.setEnabled(False)
        name_mask_layout.addWidget(self.search_btn)
        name_mask_layout.addWidget(self.stop_btn)
        name_mask_layout.addStretch()

        # Первая строка: путь
        layout.addLayout(folder_layout)
        # Вторая строка: имя, маска, содержимое, кнопки
        layout.addLayout(name_mask_layout)

        
        # --- Фильтры размера и даты ---
        filter_row1 = QHBoxLayout()
        
        # Размер файла
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Размер (КБ):"))
        from PyQt6.QtGui import QIntValidator
        self.size_min_le = QLineEdit()
        self.size_min_le.setValidator(QIntValidator(0, 999999))
        self.size_min_le.setPlaceholderText("от")
        self.size_min_le.setMaximumWidth(60)
        size_layout.addWidget(self.size_min_le)
        size_layout.addWidget(QLabel("-"))
        self.size_max_le = QLineEdit()
        self.size_max_le.setValidator(QIntValidator(0, 999999))
        self.size_max_le.setPlaceholderText("до")
        self.size_max_le.setMaximumWidth(60)
        size_layout.addWidget(self.size_max_le)
        
        # Дата модификации
        date_layout = QHBoxLayout()
        date_layout.addWidget(QLabel("Дата изм.:"))
        self.date_from_de = QDateEdit()
        self.date_from_de.setCalendarPopup(True)
        self.date_from_de.setDate(QDate.currentDate().addYears(-1))
        
        self.date_to_de = QDateEdit()
        self.date_to_de.setCalendarPopup(True)
        self.date_to_de.setDate(QDate.currentDate())
        
        date_layout.addWidget(self.date_from_de)
        date_layout.addWidget(self.date_to_de)
        
        filter_row1.addLayout(size_layout)
        filter_row1.addLayout(date_layout)
        # Чекбоксы после даты
        self.hidden_cb = QCheckBox("Скрытые")
        self.readonly_cb = QCheckBox("Только для чтения")
        self.content_regex_cb = QCheckBox("Regex")
        self.case_cb = QCheckBox("Учёт регистра")
        filter_row1.addWidget(self.hidden_cb)
        filter_row1.addWidget(self.readonly_cb)
        filter_row1.addWidget(self.content_regex_cb)
        filter_row1.addWidget(self.case_cb)
        filter_row1.addStretch()
        
        # --- Прогресс бар ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)  # Неопределенный прогресс
        
        # --- Таблица результатов ---
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Имя", "Путь", "Размер (КБ)", "Изменён", "Содержит"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        
        # Настройка размеров колонок
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)  # Имя
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)      # Путь
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Размер
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Дата
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Содержит
        
        # Двойной клик для открытия в проводнике
        self.table.doubleClicked.connect(self._on_double_click)
        
        # --- Статус ---
        self.status_label = QLabel("Готов к поиску")
        
        # --- Кнопки действий ---
        btns_layout = QHBoxLayout()

        self.add_link_btn = QPushButton("Добавить как ссылку")
        self.add_link_btn.setEnabled(False)
        self.add_link_btn.clicked.connect(self._on_add_link)
        
        self.open_folder_btn = QPushButton("Открыть в проводнике")
        self.open_folder_btn.setEnabled(False)
        self.open_folder_btn.clicked.connect(self._on_open_folder)
        
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.reject)
        
        btns_layout.addWidget(self.status_label)
        btns_layout.addStretch()
        btns_layout.addWidget(self.add_link_btn)
        btns_layout.addWidget(self.open_folder_btn)
        btns_layout.addWidget(close_btn)
        
        # Сборка основного layout
        layout.addLayout(top_layout)
        layout.addLayout(filter_row1)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.table)
        layout.addLayout(btns_layout)
        
        # Подключение сигналов для обновления кнопок
        self.table.itemSelectionChanged.connect(self._update_buttons)

    def _update_buttons(self):
        """Обновление состояния кнопок в зависимости от выбора"""
        has_selection = bool(self.table.selectionModel().selectedRows())
        self.add_link_btn.setEnabled(has_selection)
        self.open_folder_btn.setEnabled(has_selection)

    def _get_full_file_path(self, row):
        """Получение полного пути к файлу из указанной строки таблицы"""
        filename = self.table.item(row, 0).text()  # Имя файла
        folder_path = self.table.item(row, 1).text()  # Путь к папке
        
        # Объединяем путь к папке и имя файла
        full_path = os.path.join(folder_path, filename)
        
        # Нормализуем путь
        full_path = os.path.normpath(full_path)
        
        return full_path

    def _on_add_link(self):
        """Добавить выбранный файл как ссылку"""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        file_path = self._get_full_file_path(selected_rows[0].row())
        main_window = self.parent() if hasattr(self.parent(), 'show_link_dialog') else (self.parent().parent() if self.parent() else None)
        if main_window and hasattr(main_window, 'show_link_dialog'):
            # Открываем LinkDialog с уже заполненным путем
            from app.views.dialogs.link_dialog.link_dialog import LinkDialog

            # Используем link_operations вместо прямого обращения к БД
            if hasattr(main_window, 'link_operations'):
                main_window.link_operations.show_link_dialog(link={"type": "file", "url": file_path}, category_id=getattr(main_window, 'current_category_id', None))
            else:
                # Fallback: создаем диалог через метод MainWindow
                main_window.show_link_dialog(link={"type": "file", "url": file_path}, category_id=getattr(main_window, 'current_category_id', None))
            return  # Выходим, так как link_operations сам обработает диалог

    def _on_open_folder(self):
        """Открыть папку с выбранным файлом в проводнике"""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        file_path = self._get_full_file_path(selected_rows[0].row())
        self._open_file_in_explorer(file_path)

    def _open_file_in_explorer(self, file_path):
        """Открыть файл в проводнике с выделением"""
        try:
            print(f"Открываю в проводнике: {file_path}")
            
            # Нормализуем путь
            file_path = os.path.normpath(file_path)
            
            if not os.path.exists(file_path):
                # ЦЕНТРАЛИЗОВАНО: Использует DialogManager вместо прямого QMessageBox
                self.show_warning(f"Файл не найден: {file_path}")
                return
            
            system = platform.system()
            
            if system == "Windows":
                # Windows: используем explorer с параметром /select
                # Экранируем путь для корректной работы с пробелами
                subprocess.run(['explorer', '/select,', file_path], shell=False)
            elif system == "Darwin":  # macOS
                # macOS: используем open с параметром -R (reveal)
                subprocess.run(['open', '-R', file_path], check=True)
            elif system == "Linux":
                # Linux: пробуем различные файловые менеджеры
                try:
                    # Пробуем nautilus (GNOME)
                    subprocess.run(['nautilus', '--select', file_path], check=True)
                except (subprocess.CalledProcessError, FileNotFoundError):
                    try:
                        # Пробуем dolphin (KDE)
                        subprocess.run(['dolphin', '--select', file_path], check=True)
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        try:
                            # Пробуем thunar (XFCE)
                            subprocess.run(['thunar', os.path.dirname(file_path)], check=True)
                        except (subprocess.CalledProcessError, FileNotFoundError):
                            try:
                                # Пробуем pcmanfm (LXDE)
                                subprocess.run(['pcmanfm', os.path.dirname(file_path)], check=True)
                            except (subprocess.CalledProcessError, FileNotFoundError):
                                # Если ничего не сработало, открываем папку
                                folder_path = os.path.dirname(file_path)
                                subprocess.run(['xdg-open', folder_path], check=True)
            else:
                # Для других систем открываем папку
                folder_path = os.path.dirname(file_path)
                subprocess.run(['xdg-open', folder_path], check=True)
                
        except subprocess.CalledProcessError as e:
            # ЦЕНТРАЛИЗОВАНО: Использует DialogManager вместо прямого QMessageBox
            self.show_warning(f"Не удалось открыть файл в проводнике: {str(e)}")
        except Exception as e:
            # ЦЕНТРАЛИЗОВАНО: Использует DialogManager вместо прямого QMessageBox
            self.show_warning(f"Произошла ошибка: {str(e)}")
                    
    def _setup_defaults(self):
        """Настройка значений по умолчанию"""
        self.size_min_le.clear()
        self.size_max_le.clear()
        
    def _choose_root(self):
        """Выбор корневой папки для поиска"""
        current_path = self.root_le.text().strip()
        if not current_path or not os.path.exists(current_path):
            current_path = os.path.expanduser("~")
            
        path = QFileDialog.getExistingDirectory(
            self, "Выбрать папку для поиска", current_path
        )
        if path:
            self.root_le.setText(path)
            
    def _validate_inputs(self):
        """Валидация пользовательских данных"""
        root_path = self.root_le.text().strip()
        if not root_path:
            # ЦЕНТРАЛИЗОВАНО: Использует DialogManager вместо прямого QMessageBox
            self.show_warning("Укажите папку для поиска")
            return False
            
        if not os.path.exists(root_path):
            # ЦЕНТРАЛИЗОВАНО: Использует DialogManager вместо прямого QMessageBox
            self.show_warning(f"Папка не существует: {root_path}")
            return False
            
        if not os.path.isdir(root_path):
            # ЦЕНТРАЛИЗОВАНО: Использует DialogManager вместо прямого QMessageBox
            self.show_warning(f"Указанный путь не является папкой: {root_path}")
            return False
            
        # Проверка регулярного выражения
        regex_pattern = self.regex_le.text().strip()
        if regex_pattern:
            try:
                re.compile(regex_pattern)
            except re.error as e:
                # ЦЕНТРАЛИЗОВАНО: Использует DialogManager вместо прямого QMessageBox
                self.show_warning(f"Неверное регулярное выражение для имени: {e}")
                return False
                
        # Проверка регулярного выражения для содержимого
        content_pattern = self.content_le.text().strip()
        if content_pattern and self.content_regex_cb.isChecked():
            try:
                flags = 0 if self.case_cb.isChecked() else re.IGNORECASE
                re.compile(content_pattern, flags)
            except re.error as e:
                # ЦЕНТРАЛИЗОВАНО: Использует DialogManager вместо прямого QMessageBox
                self.show_warning(f"Неверное регулярное выражение для содержимого: {e}")
                return False
                
        return True
        
    def _start_search(self):
        """Запуск поиска файлов"""
        if not self._validate_inputs():
            return
            
        if self.is_searching:
            return
            
        # Очистка предыдущих результатов
        self.table.setRowCount(0)
        
        # Переключение UI в режим поиска
        self.is_searching = True
        self.search_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.status_label.setText("Поиск...")
        
        # Создание конфигурации поиска
        config = self._create_search_config()
        
        # Создание и запуск worker'а
        self.search_worker = FileSearchWorker(config)
        self.search_worker.signals.result_found.connect(self._add_result)
        self.search_worker.signals.search_finished.connect(self._on_search_finished)
        self.search_worker.signals.error_occurred.connect(self._on_search_error)
        
        self.threadpool.start(self.search_worker)
        
    def _stop_search(self):
        """Остановка поиска"""
        if self.search_worker:
            self.search_worker.stop()
        self._on_search_finished()
        
    def _create_search_config(self):
        """Создание конфигурации поиска"""
        return {
            'root': self.root_le.text().strip(),
            'pattern': self.pattern_le.text().strip() or "*.*",
            'regex_name': self.regex_le.text().strip(),
            'size_min': int(self.size_min_le.text()) if self.size_min_le.text() else None,
            'size_max': int(self.size_max_le.text()) if self.size_max_le.text() else None,
            'date_from': self.date_from_de.date().toPyDate(),
            'date_to': self.date_to_de.date().toPyDate(),
            'hidden': self.hidden_cb.isChecked(),
            'readonly': self.readonly_cb.isChecked(),
            'content': self.content_le.text().strip(),
            'content_regex': self.content_regex_cb.isChecked(),
            'case_sensitive': self.case_cb.isChecked(),
        }
        
    def _add_result(self, file_path: str):
        """Добавление результата поиска в таблицу"""
        try:
            file_stat = os.stat(file_path)
            size_kb = file_stat.st_size // 1024
            mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(file_stat.st_mtime))
            
            # Проверяем, есть ли поиск по содержимому
            has_content = "✓" if self.content_le.text().strip() else ""
            
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # Заполняем ячейки
            filename = os.path.basename(file_path)
            folder_path = os.path.dirname(file_path)
            
            self.table.setItem(row, 0, QTableWidgetItem(filename))
            self.table.setItem(row, 1, QTableWidgetItem(folder_path))
            self.table.setItem(row, 2, QTableWidgetItem(str(size_kb)))
            self.table.setItem(row, 3, QTableWidgetItem(mtime))
            self.table.setItem(row, 4, QTableWidgetItem(has_content))
            
            # Обновляем статус
            self.status_label.setText(f"Найдено файлов: {self.table.rowCount()}")
            
        except OSError as e:
            print(f"Ошибка при получении информации о файле {file_path}: {e}")
            
    def _on_search_finished(self):
        """Обработка завершения поиска"""
        self.is_searching = False
        self.search_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        
        count = self.table.rowCount()
        self.status_label.setText(f"Поиск завершен. Найдено файлов: {count}")
        
        self._update_buttons()
        
    def _on_search_error(self, error_msg: str):
        """Обработка ошибки поиска"""
        self._on_search_finished()
        # ЦЕНТРАЛИЗОВАНО: Использует DialogManager вместо прямого QMessageBox
        self.show_error(error_msg, "Ошибка поиска")
        
    def _on_double_click(self, index):
        """Обработка двойного клика по таблице - открытие в проводнике"""
        if index.isValid():
            file_path = self._get_full_file_path(index.row())
            self._open_file_in_explorer(file_path)


class FileSearchWorker(ExternalFileSearchWorker):
    """DEPRECATED shim: используйте search_worker.FileSearchWorker.
    Оставлено для обратной совместимости и минимизации изменений.
    """
    pass


