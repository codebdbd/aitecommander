from PyQt6.QtCore import QCoreApplication

_TR_CONTEXT = "Common"


def tr(text: str) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text)


# lupdate hint for common UI strings
if False:  # pragma: no cover
    QCoreApplication.translate("Common", "Save")
    QCoreApplication.translate("Common", "Cancel")
    QCoreApplication.translate("Common", "Name:")
    QCoreApplication.translate("Common", "Icon")
    QCoreApplication.translate("Common", "Add section")
    QCoreApplication.translate("Common", "Add category")
    QCoreApplication.translate("Common", "Edit section")
    QCoreApplication.translate("Common", "Edit category")
    QCoreApplication.translate("Common", "Restore Database")
    QCoreApplication.translate("Common", "Add link")
    QCoreApplication.translate("Common", "Edit link")
    QCoreApplication.translate("Common", "Import from browser")
    QCoreApplication.translate("Common", "Notes")
    QCoreApplication.translate("Common", "Theme already exists")
    QCoreApplication.translate("Common", "Settings")
    QCoreApplication.translate("Common", "Select Chrome profile")
    QCoreApplication.translate("Common", "Select browser profile")
    QCoreApplication.translate("Common", "Icon Refresh")
    QCoreApplication.translate("Common", "Bad URL Cleanup")
    QCoreApplication.translate("Common", "Delete Bad URLs")
    QCoreApplication.translate("Common", "File search")
    QCoreApplication.translate("Common", "Clear favorites")
    QCoreApplication.translate("Common", "Database restore")
