# app/views/main_components/window_initializer.py


from app.controllers.system.window_controllers_setup import WindowControllersSetup

# Компоненты для рефакторинга
from .window_ui_setup import WindowUISetup


class WindowInitializer:
    """Инициализатор главного окна - извлекает всю логику создания UI из __init__."""

    def __init__(self, main_window, db, settings, theme_ctrl):
        """
        Инициализация компонента.

        Args:
            main_window: Ссылка на главное окно
            db: База данных
            settings: Настройки приложения
            theme_ctrl: Контроллер тем
        """
        self.window = main_window
        self.db = db
        self.settings = settings
        self.theme_ctrl = theme_ctrl

        # Композиция компонентов (пока сохраняем старую логику для обратной совместимости)
        self.ui_setup = WindowUISetup(self)
        self.controllers_setup = WindowControllersSetup(self)

    def initialize_window(self):
        """Выполняет полную инициализацию главного окна."""
        # Блокируем обновления во время инициализации
        self.window.setUpdatesEnabled(False)

        try:
            # Используем новые компоненты (тестируем постепенно)
            self.ui_setup.setup_window_properties()
            self.ui_setup.setup_basic_attributes()
            self.ui_setup.setup_menu()
            self.ui_setup.setup_central_widget()

            # Получаем main_layout из UI компонента для совместимости со старыми методами
            self.main_layout = self.ui_setup.main_layout

            # Используем UI компонент для верхней панели
            self.ui_setup.setup_top_panel()

            # Используем UI компонент для основного содержимого
            self.ui_setup.setup_main_content()

            # Используем UI компонент для нижней панели и статус-бара
            self.ui_setup.setup_bottom_panel()
            self.ui_setup.setup_status_bar()

            # Используем контроллер компонент (должен быть до горячих клавиш)
            self.controllers_setup.setup_controllers()

            # Горячие клавиши после создания контроллеров
            self.ui_setup.setup_shortcuts()
            # Централизованно применяем пользовательский размер шрифта к дереву и таблице
            try:
                if hasattr(self.settings, "get_font_size") and hasattr(self.window, "apply_font_size_to_content"):
                    fs = self.settings.get_font_size()
                    if fs:
                        self.window.apply_font_size_to_content(int(fs))
            except Exception:
                # Не блокируем инициализацию при ошибке применения шрифта
                pass
        finally:
            # Включаем обновления после завершения инициализации
            self.window.setUpdatesEnabled(True)

        # Инициализация сфер выполняется асинхронно
        self.controllers_setup.initialize_spheres()

    # Старые методы _setup_* удалены - функциональность перенесена в WindowUISetup

    # Метод _setup_top_panel удален - функциональность в WindowUISetup.setup_top_panel()

    # Все методы _setup_* удалены - функциональность перенесена в WindowUISetup и WindowControllersSetup
