# hook-app.utils.ui.icon.py
"""PyInstaller hook for app.utils.ui.icon module.

Ensures all required Qt plugins and hidden imports are included in the bundle.
"""

from PyInstaller.utils.hooks import collect_submodules

# Hidden imports required by icon module
hiddenimports = [
    # Qt SVG support (critical for SVG icons)
    'PyQt6.QtSvg',
    'PyQt6.QtSvgWidgets',
    
    # PIL for raster validation
    'PIL.Image',
    'PIL.ImageQt',
    
    # QRC resources (if generated)
    'app.resources.icons_rc',
    
    # All submodules of icon package
    *collect_submodules('app.utils.ui.icon'),
]

# No data files needed if using QRC resources
datas = []
