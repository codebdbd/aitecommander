# Qt project file for i18n string extraction
# This file helps pylupdate6 find all translatable strings in the project

TEMPLATE = app
TARGET = aite-commander

# Source directories to scan for strings (recursive search)
PYTHON_SOURCES = $$files(app, *.py, true)
UI_SOURCES = $$files(app, *.ui, true)
QML_SOURCES = $$files(app, *.qml, true)

SOURCES += $$PYTHON_SOURCES $$UI_SOURCES $$QML_SOURCES

# Translation files
TRANSLATIONS += \
    i18n/app_en.ts \
    i18n/app_uk.ts \
    i18n/app_ru.ts \
    i18n/app_fr.ts \
    i18n/app_es.ts \
    i18n/app_de.ts

# Codecs for different languages
CODECFORTR = UTF-8
CODECFORSRC = UTF-8
