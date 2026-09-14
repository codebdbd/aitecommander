from __future__ import annotations

import tomllib
from pathlib import Path


def test_wheel_includes_i18n_package() -> None:
    pyproject_path = Path(__file__).resolve().parent.parent / 'pyproject.toml'
    assert pyproject_path.is_file(), 'pyproject.toml not found'

    with pyproject_path.open('rb') as f:
        data = tomllib.load(f)

    wheel_packages = data.get('tool', {}).get('hatch', {}).get('build', {}).get('targets', {}).get('wheel', {}).get('packages', [])
    assert 'app' in wheel_packages, 'app package missing from wheel configuration'
    assert 'i18n' in wheel_packages, 'i18n package missing from wheel configuration (AUD-028)'


def test_ruff_configuration_present() -> None:
    pyproject_path = Path(__file__).resolve().parent.parent / 'pyproject.toml'
    assert pyproject_path.is_file(), 'pyproject.toml not found'

    with pyproject_path.open('rb') as f:
        data = tomllib.load(f)

    ruff_config = data.get('tool', {}).get('ruff', {})
    assert ruff_config.get('target-version') == 'py312', 'Ruff target-version should be py312'

    lint_config = ruff_config.get('lint', {})
    select_rules = lint_config.get('select', [])
    assert 'E' in select_rules, 'Ruff should select pycodestyle (E)'
    assert 'F' in select_rules, 'Ruff should select pyflakes (F)'
    assert 'I' in select_rules, 'Ruff should select isort (I)'

    ignore_rules = lint_config.get('ignore', [])
    assert 'BLE001' in ignore_rules, 'Ruff should ignore BLE001 for Qt GUI app (AUD-041)'

