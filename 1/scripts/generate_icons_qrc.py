#!/usr/bin/env python3
"""Генерация icons.qrc из директории ui_icons для упаковки приложения.

Сканирует app/resources/ui_icons/ и создаёт .qrc файл для компиляции в Python ресурсы.

Usage:
    python scripts/generate_icons_qrc.py
    pyrcc6 app/resources/icons.qrc -o app/resources/icons_rc.py
"""

from __future__ import annotations

import sys
from pathlib import Path


def generate_qrc(icons_dir: Path, output_file: Path) -> None:
    """Генерирует .qrc файл из директории с иконками.
    
    Args:
        icons_dir: Путь к директории ui_icons (содержит light/, dark/ и т.д.)
        output_file: Путь к выходному .qrc файлу
    """
    if not icons_dir.exists():
        print(f"ERROR: Icons directory not found: {icons_dir}", file=sys.stderr)
        sys.exit(1)
    
    qrc_lines = [
        '<!DOCTYPE RCC>',
        '<RCC version="1.0">',
        '    <qresource prefix="/icons">',
    ]
    
    # Собираем все иконки по темам
    icon_count = 0
    for theme_dir in sorted(icons_dir.iterdir()):
        if not theme_dir.is_dir():
            continue
        
        theme_name = theme_dir.name
        print(f"Processing theme: {theme_name}")
        
        # Все файлы в теме
        for icon_file in sorted(theme_dir.iterdir()):
            if icon_file.is_file() and icon_file.suffix.lower() in (
                '.svg', '.png', '.jpg', '.jpeg', '.ico', '.bmp', '.gif'
            ):
                # Алиас: light/add.svg
                alias = f"{theme_name}/{icon_file.name}"
                # Относительный путь от корня проекта
                rel_path = icon_file.relative_to(icons_dir.parent)
                
                qrc_lines.append(f'        <file alias="{alias}">{rel_path}</file>')
                icon_count += 1
    
    qrc_lines.extend([
        '    </qresource>',
        '</RCC>',
        ''  # trailing newline
    ])
    
    # Записываем файл
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text('\n'.join(qrc_lines), encoding='utf-8')
    
    print(f"\n✓ Generated {output_file}")
    print(f"✓ Total icons: {icon_count}")
    print(f"\nNext step:")
    print(f"  pyrcc6 {output_file} -o {output_file.with_suffix('.py').parent / 'icons_rc.py'}")


def main() -> None:
    """Entry point."""
    # Определяем пути относительно корня проекта
    project_root = Path(__file__).parent.parent
    icons_dir = project_root / "app" / "resources" / "ui_icons"
    output_file = project_root / "app" / "resources" / "icons.qrc"
    
    print(f"Project root: {project_root}")
    print(f"Icons dir: {icons_dir}")
    print(f"Output: {output_file}\n")
    
    generate_qrc(icons_dir, output_file)


if __name__ == "__main__":
    main()
