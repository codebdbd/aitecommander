@echo off
REM Script to test the topbar changes

echo Running topbar configuration protocol tests...
pytest tests/test_topbar_config_protocol.py -v

echo.
echo Running topbar layout orchestrator tests...
pytest tests/test_topbar_layout_orchestrator.py -v

echo.
echo Running existing topbar tests...
pytest tests/test_topbar_layout_service.py -v
pytest tests/test_topbar_qt_utils.py -v
pytest tests/test_topbar_visibility_solver.py -v
pytest tests/test_topbar_width_calculator.py -v

echo.
echo Running mypy checks...
mypy app/views/main_components/ui/topbar/

echo.
echo Running ruff checks...
ruff check app/views/main_components/ui/topbar/

echo.
echo All tests completed!
pause
