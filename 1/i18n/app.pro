# Qt project file for i18n string extraction
# This file helps pylupdate6 find all translatable strings in the project

TEMPLATE = app
TARGET = aite-commander

# Source directories to scan for strings
SOURCES += \
    app/__init__.py \
    app/main.py \
    app/settings.py \
    app/interfaces.py \
    app/config_data/*.py \
    app/controllers/**/*.py \
    app/models/*.py \
    app/resources/**/*.py \
    app/services/*.py \
    app/startup/*.py \
    app/utils/*.py \
    app/views/**/*.py

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
