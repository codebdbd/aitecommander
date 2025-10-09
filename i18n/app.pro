# Qt Linguist project file for Aite Commander
# Auto-generated list of source files for translation extraction

# Main window
SOURCES = ../app/views/windows/main_window.py

# Dialogs
SOURCES += ../app/views/windows/dialogs/base_dialog.py \
           ../app/views/windows/dialogs/entity_dialogs.py \
           ../app/views/windows/dialogs/async_operation_dialog.py \
           ../app/views/windows/dialogs/browser_profile_dialog.py \
           ../app/views/windows/dialogs/database_dialogs.py \
           ../app/views/windows/dialogs/import_browser_dialog.py \
           ../app/views/windows/dialogs/restore_db_dialog.py \
           ../app/views/windows/dialogs/file_search_dialog/file_search_dialog.py \
           ../app/views/windows/dialogs/link_dialog/link_dialog.py \
           ../app/views/windows/dialogs/link_dialog/link_dialog_ui.py \
           ../app/views/windows/dialogs/link_dialog/link_dialog_handlers.py \
           ../app/views/windows/dialogs/link_dialog/handlers_mixins/file_dialog_mixin.py \
           ../app/views/windows/dialogs/link_dialog/handlers_mixins/validation_mixin.py

# Widgets - Base
SOURCES += ../app/views/widgets/base/base_widgets.py \
           ../app/views/widgets/base/base_panel_widgets.py \
           ../app/views/widgets/custom_widgets.py \
           ../app/views/widgets/language_selector.py \
           ../app/views/widgets/status_bar.py

# Widgets - Link table
SOURCES += ../app/views/widgets/link/base_table.py \
           ../app/views/widgets/link/links_model.py \
           ../app/views/widgets/link/item_builders.py \
           ../app/views/widgets/link/data_management.py \
           ../app/views/widgets/link/row_operations.py \
           ../app/views/widgets/link/population_manager.py

# Widgets - Panels
SOURCES += ../app/views/widgets/panels/favorites_panel_widget.py \
           ../app/views/widgets/panels/quick_add_panel_widget.py \
           ../app/views/widgets/panels/recent_panel_widget.py

# Widgets - Tiles
SOURCES += ../app/views/widgets/tiles/widget.py \
           ../app/views/widgets/tiles/delegate.py \
           ../app/views/widgets/tiles/list_view.py

# Widgets - Tree components
SOURCES += ../app/views/widgets/tree_components/move_operations_handler.py

# UI Controllers
SOURCES += ../app/controllers/ui/action_controller.py \
           ../app/controllers/ui/menu_controller.py \
           ../app/controllers/ui/theme_controller.py \
           ../app/controllers/ui/top_panels_controller.py \
           ../app/controllers/ui/window_facade.py

# UI Controllers - Dialogs
SOURCES += ../app/controllers/ui/dialogs/dialog_manager.py \
           ../app/controllers/ui/dialogs/database_controller.py \
           ../app/controllers/ui/dialogs/data_import_export_controller.py \
           ../app/controllers/ui/dialogs/link_dialog_controller.py \
           ../app/controllers/ui/dialogs/link_operations_controller.py \
           ../app/controllers/ui/dialogs/system_dialog_controller.py

# UI Controllers - Links
SOURCES += ../app/controllers/ui/links/controller.py \
           ../app/controllers/ui/links/handlers.py \
           ../app/controllers/ui/links/clipboard.py \
           ../app/controllers/ui/links/link_operations.py \
           ../app/controllers/ui/links/table_controller.py

# Startup - Application initialization and argument parsing
SOURCES += ../app/startup/argument_parser.py \
           ../app/controllers/ui/structure/tree_management.py \
           ../app/controllers/ui/structure/item_dialogs_service.py \
           ../app/controllers/ui/structure/item_deletion_service.py \
           ../app/controllers/ui/dialogs/data_import_export_controller.py \


# Models - Workers (async operations with user messages)
SOURCES += ../app/models/workers/README.md \
           ../app/controllers/ui/undo/commands_links.py \
           ../app/controllers/ui/undo/commands_structure.py

# Utils - Menu builders (ensure menu texts are extracted)
SOURCES += ../app/utils/ui/menu_builders/menu_actions.py \
           ../app/utils/ui/menu_builders/main_menu_builder.py \
           ../app/utils/ui/menu_builders/links_menu_builder.py \
           ../app/utils/ui/menu_builders/structure_menu_builder.py \
           ../app/utils/ui/menu_builders/category_menu_builder.py

# Views - Main components initialization (window initializer with user messages)
SOURCES += ../app/views/main_components/initialization/window_initializer.py \
           ../app/views/main_components/ui/bottom_panel_setup.py \
           ../app/views/main_components/ui/topbar/panel_visibility_manager.py

# Utils - UI validators (translate validation messages)
SOURCES += ../app/utils/ui/validators.py

# Services - Share functionality and other services with user messages
SOURCES += ../app/services/share_service.py
           ../app/utils/links/parser/cache.py \
           ../app/utils/links/parser/constants.py \
           ../app/utils/links/parser/domain.py \
           ../app/utils/links/parser/favicon_cache.py \
           ../app/utils/links/parser/fetcher.py \
           ../app/utils/links/parser/http_client.py \
           ../app/utils/links/parser/icon_candidates.py \
           ../app/utils/links/parser/icon_downloader.py \
           ../app/utils/links/parser/js_renderer.py \
           ../app/utils/links/parser/svg_convert.py \
           ../app/utils/links/parser/title_parser.py

# Translation files
TRANSLATIONS = app_en.ts \
               app_ru.ts \
               app_uk.ts \
               app_de.ts \
               app_es.ts \
               app_fr.ts

# Encoding settings
CODECFORTR = UTF-8
CODECFORSRC = UTF-8
