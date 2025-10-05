@echo off
REM Simple script to update translations using new pylupdate6 syntax

echo ========================================
echo  Updating Translation Files
echo ========================================
echo.

cd /d "%~dp0"

echo Collecting source files...

REM Build list of all source files
set SOURCES=^
..\app\views\windows\main_window.py ^
..\app\views\windows\dialogs\base_dialog.py ^
..\app\views\windows\dialogs\entity_dialogs.py ^
..\app\views\windows\dialogs\async_operation_dialog.py ^
..\app\views\windows\dialogs\browser_profile_dialog.py ^
..\app\views\windows\dialogs\database_dialogs.py ^
..\app\views\windows\dialogs\import_browser_dialog.py ^
..\app\views\windows\dialogs\restore_db_dialog.py ^
..\app\views\windows\dialogs\file_search_dialog\file_search_dialog.py ^
..\app\views\windows\dialogs\link_dialog\link_dialog.py ^
..\app\views\windows\dialogs\link_dialog\link_dialog_ui.py ^
..\app\views\windows\dialogs\link_dialog\link_dialog_handlers.py ^
..\app\views\widgets\base\base_widgets.py ^
..\app\views\widgets\custom_widgets.py ^
..\app\views\widgets\language_selector.py ^
..\app\views\widgets\status_bar.py ^
..\app\views\widgets\link\base_table.py ^
..\app\views\widgets\link\links_model.py ^
..\app\views\widgets\link\item_builders.py ^
..\app\views\widgets\tree_components\move_operations_handler.py ^
..\app\controllers\ui\action_controller.py ^
..\app\controllers\ui\menu_controller.py ^
..\app\controllers\ui\theme_controller.py ^
..\app\controllers\ui\dialogs\dialog_manager.py ^
..\app\controllers\ui\dialogs\database_controller.py ^
..\app\controllers\ui\dialogs\link_dialog_controller.py ^
..\app\controllers\ui\undo\commands.py ^
..\app\controllers\ui\undo\commands_links.py ^
..\app\controllers\ui\undo\commands_structure.py

echo.
echo Updating app_en.ts...
pylupdate6 --verbose --ts app_en.ts %SOURCES%

echo.
echo Updating app_uk.ts...
pylupdate6 --verbose --ts app_uk.ts %SOURCES%

echo.
echo ========================================
echo Translation files updated!
echo ========================================
echo.
echo Next steps:
echo 1. Edit translations in Qt Linguist:
echo    linguist app_en.ts
echo    linguist app_uk.ts
echo.
echo 2. Compile translations:
echo    compile_translations.bat
echo.
pause
