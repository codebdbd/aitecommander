# Resource file for i18n
# This file is generated and should not be edited manually

from PyQt6.QtCore import QResource

# Register resource data (empty for now)
_resource_data = b""

def qInitResources():
    """Initialize Qt resources."""
    QResource.registerResourceData(_resource_data)

def qCleanupResources():
    """Cleanup Qt resources."""
    QResource.unregisterResourceData(_resource_data)
