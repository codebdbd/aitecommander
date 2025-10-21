from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
I18N_DIR = BASE_DIR / "i18n"

LANG_FILES = {
    "ru": "app_ru.ts",
    "uk": "app_uk.ts",
    "fr": "app_fr.ts",
    "es": "app_es.ts",
    "de": "app_de.ts",
}


TRANSLATIONS: dict[str, dict[str, str]] = {
    " (Alt+{n})": {
        "ru": "\u00A0(Alt+{n})",
        "uk": "\u00A0(Alt+{n})",
        "fr": "\u00A0(Alt+{n})",
        "es": "\u00A0(Alt+{n})",
        "de": "\u00A0(Alt+{n})",
    },
    "&Actions": {
        "fr": "&Actions",
        "es": "&Acciones",
        "de": "&Aktionen",
    },
    "&Data": {
        "fr": "&Donn\u00e9es",
        "es": "&Datos",
        "de": "&Daten",
    },
    "&File": {
        "fr": "&Fichier",
        "es": "&Archivo",
        "de": "&Datei",
    },
    "&Help": {
        "fr": "&Aide",
        "es": "A&yuda",
        "de": "&Hilfe",
    },
    "&Redo": {
        "fr": "&R\u00e9tablir",
        "es": "Re&hacer",
        "de": "&Wiederholen",
    },
    "&Search": {
        "fr": "&Recherche",
        "es": "&Buscar",
        "de": "&Suchen",
    },
    "&Themes": {
        "fr": "&Th\u00e8mes",
        "es": "&Temas",
        "de": "&Designs",
    },
    "&Undo": {
        "fr": "&Annuler",
        "es": "&Deshacer",
        "de": "&R\u00fcckg\u00e4ngig",
    },
    "(no email)": {
        "fr": "(pas d'e-mail)",
        "es": "(sin correo)",
        "de": "(keine E-Mail)",
    },
    "A category with the same name already exists in the selected section.": {
        "ru": "\u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f \u0441 \u0442\u0430\u043a\u0438\u043c \u0438\u043c\u0435\u043d\u0435\u043c \u0443\u0436\u0435 \u0441\u0443\u0449\u0435\u0441\u0442\u0432\u0443\u0435\u0442 \u0432 \u0432\u044b\u0431\u0440\u0430\u043d\u043d\u043e\u043c \u0440\u0430\u0437\u0434\u0435\u043b\u0435.",
        "uk": "\u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0456\u044f \u0437 \u0442\u0430\u043a\u043e\u044e \u043d\u0430\u0437\u0432\u043e\u044e \u0432\u0436\u0435 \u0456\u0441\u043d\u0443\u0454 \u0443 \u043e\u0431\u0440\u0430\u043d\u043e\u043c\u0443 \u0440\u043e\u0437\u0434\u0456\u043b\u0456.",
        "fr": "Une cat\u00e9gorie portant le m\u00eame nom existe d\u00e9j\u00e0 dans la section s\u00e9lectionn\u00e9e.",
        "es": "Ya existe una categor\u00eda con el mismo nombre en la secci\u00f3n seleccionada.",
        "de": "In dem ausgew\u00e4hlten Abschnitt existiert bereits eine Kategorie mit diesem Namen.",
    },
    "About": {
        "ru": "\u041e \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0438",
        "uk": "\u041f\u0440\u043e \u043f\u0440\u043e\u0433\u0440\u0430\u043c\u0443",
        "fr": "\u00c0 propos",
        "es": "Acerca de",
        "de": "\u00dcber",
    },
    "Add": {
        "fr": "Ajouter",
        "es": "Agregar",
        "de": "Hinzuf\u00fcgen",
    },
    "Add all": {
        "fr": "Tout ajouter",
        "es": "Agregar todo",
        "de": "Alle hinzuf\u00fcgen",
    },
    "Add as link": {
        "uk": "\u0414\u043e\u0434\u0430\u0442\u0438 \u044f\u043a \u043f\u043e\u0441\u0438\u043b\u0430\u043d\u043d\u044f",
        "fr": "Ajouter comme lien",
        "es": "Agregar como enlace",
        "de": "Als Link hinzuf\u00fcgen",
    },
    "Add category": {
        "ru": "\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u043a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044e",
        "uk": "\u0414\u043e\u0434\u0430\u0442\u0438 \u043a\u0430\u0442\u0435\u0433\u043e\u0440\u0456\u044e",
        "fr": "Ajouter une cat\u00e9gorie",
        "es": "Agregar categor\u00eda",
        "de": "Kategorie hinzuf\u00fcgen",
    },
    "Add link": {
        "ru": "\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0441\u0441\u044b\u043b\u043a\u0443",
        "uk": "\u0414\u043e\u0434\u0430\u0442\u0438 \u043f\u043e\u0441\u0438\u043b\u0430\u043d\u043d\u044f",
        "fr": "Ajouter un lien",
        "es": "Agregar enlace",
        "de": "Link hinzuf\u00fcgen",
    },
    "Add section": {
        "ru": "\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0440\u0430\u0437\u0434\u0435\u043b",
        "uk": "\u0414\u043e\u0434\u0430\u0442\u0438 \u0440\u043e\u0437\u0434\u0456\u043b",
        "fr": "Ajouter une section",
        "es": "Agregar secci\u00f3n",
        "de": "Abschnitt hinzuf\u00fcgen",
    },
    "Add to favorites": {
        "ru": "\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0432 \u0438\u0437\u0431\u0440\u0430\u043d\u043d\u043e\u0435",
        "uk": "\u0414\u043e\u0434\u0430\u0442\u0438 \u0434\u043e \u0432\u0438\u0431\u0440\u0430\u043d\u043e\u0433\u043e",
        "fr": "Ajouter aux favoris",
        "es": "Agregar a favoritos",
        "de": "Zu Favoriten hinzuf\u00fcgen",
    },
    "Advanced file search": {
        "uk": "\u0420\u043e\u0437\u0448\u0438\u0440\u0435\u043d\u0438\u0439 \u043f\u043e\u0448\u0443\u043a \u0444\u0430\u0439\u043b\u0456\u0432",
        "fr": "Recherche de fichiers avanc\u00e9e",
        "es": "B\u00fasqueda avanzada de archivos",
        "de": "Erweiterte Dateisuche",
    },
    "Aite Commander": {
        "ru": "\u00abAite Commander\u00bb",
        "uk": "\u00abAite Commander\u00bb",
        "fr": "Aite Commander",
        "es": "Aite Commander",
        "de": "Aite Commander",
    },
    "Application": {
        "fr": "Application",
        "es": "Aplicaci\u00f3n",
        "de": "Anwendung",
    },
    "Arguments:": {
        "fr": "Arguments\u00a0:",
        "es": "Argumentos:",
        "de": "Argumente:",
    },
    "Backup selection required": {
        "ru": "\u041d\u0435\u043e\u0431\u0445\u043e\u0434\u0438\u043c\u043e \u0432\u044b\u0431\u0440\u0430\u0442\u044c \u0440\u0435\u0437\u0435\u0440\u0432\u043d\u0443\u044e \u043a\u043e\u043f\u0438\u044e",
        "uk": "\u041f\u043e\u0442\u0440\u0456\u0431\u043d\u043e \u0432\u0438\u0431\u0440\u0430\u0442\u0438 \u0440\u0435\u0437\u0435\u0440\u0432\u043d\u0443 \u043a\u043e\u043f\u0456\u044e",
        "fr": "S\u00e9lection d'une sauvegarde requise",
        "es": "Es necesario seleccionar una copia de seguridad",
        "de": "Bitte eine Sicherung ausw\u00e4hlen",
    },
    "Browse": {
        "uk": "\u041e\u0433\u043b\u044f\u043d\u0443\u0442\u0438",
        "fr": "Parcourir",
        "es": "Examinar",
        "de": "Durchsuchen",
    },
    "Browsers:": {
        "fr": "Navigateurs\u00a0:",
        "es": "Navegadores:",
        "de": "Browser:",
    },
    "Case sensitive": {
        "uk": "\u0417 \u0443\u0440\u0430\u0445\u0443\u0432\u0430\u043d\u043d\u044f\u043c \u0440\u0435\u0433\u0456\u0441\u0442\u0440\u0443",
        "fr": "Respecter la casse",
        "es": "Distinguir may\u00fasculas/min\u00fasculas",
        "de": "Gro\u00df-/Kleinschreibung beachten",
    },
    "Categories: %1": {
        "fr": "Cat\u00e9gories\u00a0: %1",
        "es": "Categor\u00edas: %1",
        "de": "Kategorien: %1",
    },
    "Category deleted": {
        "fr": "Cat\u00e9gorie supprim\u00e9e",
        "es": "Categor\u00eda eliminada",
        "de": "Kategorie gel\u00f6scht",
    },
    "Category duplicate": {
        "fr": "Cat\u00e9gorie en double",
        "es": "Categor\u00eda duplicada",
        "de": "Kategorie doppelt",
    },
    "Category not found.": {
        "fr": "Cat\u00e9gorie introuvable.",
        "es": "Categor\u00eda no encontrada.",
        "de": "Kategorie nicht gefunden.",
    },
    "Category unavailable": {
        "fr": "Cat\u00e9gorie indisponible",
        "es": "Categor\u00eda no disponible",
        "de": "Kategorie nicht verf\u00fcgbar",
    },
    "Check database connection and try again.": {
        "fr": "V\u00e9rifiez la connexion \u00e0 la base de donn\u00e9es, puis r\u00e9essayez.",
        "es": "Verifique la conexi\u00f3n con la base de datos y vuelva a intentarlo.",
        "de": "\u00dcberpr\u00fcfen Sie die Datenbankverbindung und versuchen Sie es erneut.",
    },
    "Check the database connection and try again.": {
        "ru": "\u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435 \u043a \u0431\u0430\u0437\u0435 \u0434\u0430\u043d\u043d\u044b\u0445 \u0438 \u043f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0435\u0449\u0435 \u0440\u0430\u0437.",
        "uk": "\u041f\u0435\u0440\u0435\u0432\u0456\u0440\u0442\u0435 \u043f\u0456\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u043d\u044f \u0434\u043e \u0431\u0430\u0437\u0438 \u0434\u0430\u043d\u0438\u0445 \u0456 \u0441\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0449\u0435 \u0440\u0430\u0437.",
        "es": "Compruebe la conexi\u00f3n con la base de datos y vuelva a intentarlo.",
        "de": "\u00dcberpr\u00fcfen Sie die Datenbankverbindung und versuchen Sie es erneut.",
    },
    "Choose a Chrome profile:": {
        "fr": "Choisissez un profil Chrome\u00a0:",
        "es": "Elija un perfil de Chrome:",
        "de": "Chrome-Profil ausw\u00e4hlen:",
    },
    "Choose a section from the dropdown, then click 'Import'.": {
        "fr": "Choisissez une section dans la liste d\u00e9roulante, puis cliquez sur \u00ab\u00a0Importer\u00a0\u00bb.",
        "es": "Elija una secci\u00f3n en la lista desplegable y luego haga clic en \"Importar\".",
        "de": "W\u00e4hlen Sie einen Abschnitt aus der Liste und klicken Sie anschlie\u00dfend auf \"Importieren\".",
    },
    "Choose a section from the list and press \"Save\".": {
        "fr": "Choisissez une section dans la liste et cliquez sur \u00ab\u00a0Enregistrer\u00a0\u00bb.",
        "es": "Elija una secci\u00f3n de la lista y pulse \"Guardar\".",
        "de": "W\u00e4hlen Sie einen Abschnitt aus der Liste und klicken Sie auf \"Speichern\".",
    },
    "Choose another image file (.png, .ico, .jpg, .svg) and try again.": {
        "fr": "Choisissez un autre fichier image (.png, .ico, .jpg, .svg) puis r\u00e9essayez.",
        "es": "Elija otro archivo de imagen (.png, .ico, .jpg, .svg) y vuelva a intentarlo.",
        "de": "W\u00e4hlen Sie eine andere Bilddatei (.png, .ico, .jpg, .svg) und versuchen Sie es erneut.",
    },
    "Chrome profiles not found": {
        "fr": "Profils Chrome introuvables",
        "es": "No se encontraron perfiles de Chrome",
        "de": "Keine Chrome-Profile gefunden",
    },
    "Clear favorites": {
        "ru": "\u041e\u0447\u0438\u0441\u0442\u0438\u0442\u044c \u0438\u0437\u0431\u0440\u0430\u043d\u043d\u043e\u0435",
        "uk": "\u041e\u0447\u0438\u0441\u0442\u0438\u0442\u0438 \u043e\u0431\u0440\u0430\u043d\u0435",
        "fr": "Effacer les favoris",
        "es": "Vaciar favoritos",
        "de": "Favoriten leeren",
    },
    "Clear selection": {
        "fr": "Effacer la s\u00e9lection",
        "es": "Borrar selecci\u00f3n",
        "de": "Auswahl aufheben",
    },
    "Close": {
        "ru": "\u0417\u0430\u043a\u0440\u044b\u0442\u044c",
        "uk": "\u0417\u0430\u043a\u0440\u0438\u0442\u0438",
        "fr": "Fermer",
        "es": "Cerrar",
        "de": "Schlie\u00dfen",
    },
    "Configuration error": {
        "fr": "Erreur de configuration",
        "es": "Error de configuraci\u00f3n",
        "de": "Konfigurationsfehler",
    },
    "Configuration parameter for icons is missing or empty.": {
        "fr": "Le param\u00e8tre de configuration des ic\u00f4nes est manquant ou vide.",
        "es": "El par\u00e1metro de configuraci\u00f3n de los \u00edconos falta o est\u00e1 vac\u00edo.",
        "de": "Der Konfigurationsparameter f\u00fcr Symbole fehlt oder ist leer.",
    },
    "Confirmation": {
        "fr": "Confirmation",
        "es": "Confirmaci\u00f3n",
        "de": "Best\u00e4tigung",
    },
    "Confirmation error": {
        "fr": "Erreur de confirmation",
        "es": "Error de confirmaci\u00f3n",
        "de": "Best\u00e4tigungsfehler",
    },
    "Connect database": {
        "fr": "Connecter la base de donn\u00e9es",
        "es": "Conectar base de datos",
        "de": "Datenbank verbinden",
    },
    "Content:": {
        "uk": "\u0412\u043c\u0456\u0441\u0442:",
        "fr": "Contenu\u00a0:",
        "es": "Contenido:",
        "de": "Inhalt:",
    },
    "Copy": {
        "fr": "Copier",
        "es": "Copiar",
        "de": "Kopieren",
    },
    "Copy as email message": {
        "fr": "Copier comme message e-mail",
        "es": "Copiar como mensaje de correo",
        "de": "Als E-Mail-Nachricht kopieren",
    },
    "Count completed": {
        "fr": "Comptage termin\u00e9",
        "es": "Conteo completado",
        "de": "Z\u00e4hlung abgeschlossen",
    },
    "Count error": {
        "fr": "Erreur de comptage",
        "es": "Error al contar",
        "de": "Z\u00e4hlfehler",
    },
    "Counting objects for section {section_id}\u2026": {
        "fr": "Comptage des objets pour la section {section_id}\u2026",
        "es": "Contando objetos para la secci\u00f3n {section_id}\u2026",
        "de": "Objekte f\u00fcr Abschnitt {section_id} werden gez\u00e4hlt\u2026",
    },
    "Cut": {
        "fr": "Couper",
        "es": "Cortar",
        "de": "Ausschneiden",
    },
    "Dark": {
        "ru": "\u0422\u0451\u043c\u043d\u0430\u044f",
        "uk": "\u0422\u0435\u043c\u043d\u0430",
        "fr": "Sombre",
        "es": "Oscuro",
        "de": "Dunkel",
    },
    "Database error during move": {
        "fr": "Erreur de base de donn\u00e9es lors du d\u00e9placement",
        "es": "Error de base de datos durante el movimiento",
        "de": "Datenbankfehler beim Verschieben",
    },
    "Database initialization error": {
        "ru": "\u041e\u0448\u0438\u0431\u043a\u0430 \u0438\u043d\u0438\u0446\u0438\u0430\u043b\u0438\u0437\u0430\u0446\u0438\u0438 \u0431\u0430\u0437\u044b \u0434\u0430\u043d\u043d\u044b\u0445",
        "uk": "\u041f\u043e\u043c\u0438\u043b\u043a\u0430 \u0456\u043d\u0456\u0446\u0456\u0430\u043b\u0456\u0437\u0430\u0446\u0456\u0457 \u0431\u0430\u0437\u0438 \u0434\u0430\u043d\u0438\u0445",
        "fr": "Erreur d'initialisation de la base de donn\u00e9es",
        "es": "Error de inicializaci\u00f3n de la base de datos",
        "de": "Fehler bei der Initialisierung der Datenbank",
    },
    "Database initialization\u2026": {
        "ru": "\u0418\u043d\u0438\u0446\u0438\u0430\u043b\u0438\u0437\u0430\u0446\u0438\u044f \u0431\u0430\u0437\u044b \u0434\u0430\u043d\u043d\u044b\u0445\u2026",
        "uk": "\u0406\u043d\u0456\u0446\u0456\u0430\u043b\u0456\u0437\u0430\u0446\u0456\u044f \u0431\u0430\u0437\u0438 \u0434\u0430\u043d\u0438\u0445\u2026",
        "fr": "Initialisation de la base de donn\u00e9es\u2026",
        "es": "Inicializando base de datos\u2026",
        "de": "Datenbankinitialisierung\u2026",
    },
    "Database ready": {
        "ru": "\u0411\u0430\u0437\u0430 \u0434\u0430\u043d\u043d\u044b\u0445 \u0433\u043e\u0442\u043e\u0432\u0430",
        "uk": "\u0411\u0430\u0437\u0430 \u0434\u0430\u043d\u0438\u0445 \u0433\u043e\u0442\u043e\u0432\u0430",
        "fr": "Base de donn\u00e9es pr\u00eate",
        "es": "Base de datos lista",
        "de": "Datenbank bereit",
    },
    "Database: connected": {
        "fr": "Base de donn\u00e9es\u00a0: connect\u00e9e",
        "es": "Base de datos: conectada",
        "de": "Datenbank: verbunden",
    },
    "Database: disconnected": {
        "fr": "Base de donn\u00e9es\u00a0: d\u00e9connect\u00e9e",
        "es": "Base de datos: desconectada",
        "de": "Datenbank: getrennt",
    },
    "Default icon not found.": {
        "fr": "Ic\u00f4ne par d\u00e9faut introuvable.",
        "es": "No se encontr\u00f3 el \u00edcono predeterminado.",
        "de": "Standardsymbol nicht gefunden.",
    },
    "Delete category": {
        "fr": "Supprimer la cat\u00e9gorie",
        "es": "Eliminar categor\u00eda",
        "de": "Kategorie l\u00f6schen",
    },
    "Delete section": {
        "fr": "Supprimer la section",
        "es": "Eliminar secci\u00f3n",
        "de": "Abschnitt l\u00f6schen",
    },
    "Delete selected": {
        "fr": "Supprimer la s\u00e9lection",
        "es": "Eliminar seleccionados",
        "de": "Auswahl l\u00f6schen",
    },
    "Deleting category\u2026": {
        "fr": "Suppression de la cat\u00e9gorie\u2026",
        "es": "Eliminando categor\u00eda\u2026",
        "de": "Kategorie wird gel\u00f6scht\u2026",
    },
    "Deselect all": {
        "fr": "Tout d\u00e9s\u00e9lectionner",
        "es": "Deseleccionar todo",
        "de": "Alle abw\u00e4hlen",
    },
    "Edit category": {
        "fr": "Modifier la cat\u00e9gorie",
        "es": "Editar categor\u00eda",
        "de": "Kategorie bearbeiten",
    },
    "Edit link": {
        "ru": "\u0418\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u0441\u0441\u044b\u043b\u043a\u0443",
        "uk": "\u0417\u043c\u0456\u043d\u0438\u0442\u0438 \u043f\u043e\u0441\u0438\u043b\u0430\u043d\u043d\u044f",
        "fr": "Modifier le lien",
        "es": "Editar enlace",
        "de": "Link bearbeiten",
    },
    "Edit section": {
        "fr": "Modifier la section",
        "es": "Editar secci\u00f3n",
        "de": "Abschnitt bearbeiten",
    },
    "Email": {
        "fr": "E-mail",
        "es": "Correo electr\u00f3nico",
        "de": "E-Mail",
    },
    "Enable undo/redo support or initialize undo_stack in the main window.": {
        "fr": "Activez la prise en charge Annuler/R\u00e9tablir ou initialisez undo_stack dans la fen\u00eatre principale.",
        "es": "Habilite la funci\u00f3n de deshacer/rehacer o inicialice undo_stack en la ventana principal.",
        "de": "Aktivieren Sie die Undo/Redo-Unterst\u00fctzung oder initialisieren Sie den undo_stack im Hauptfenster.",
    },
    "Error": {
        "fr": "Erreur",
        "es": "Error",
        "de": "Fehler",
    },
    "Error loading sections": {
        "fr": "Erreur de chargement des sections",
        "es": "Error al cargar las secciones",
        "de": "Fehler beim Laden der Abschnitte",
    },
    "Error: {details}": {
        "ru": "\u041e\u0448\u0438\u0431\u043a\u0430: {details}",
        "uk": "\u041f\u043e\u043c\u0438\u043b\u043a\u0430: {details}",
        "fr": "Erreur : {details}",
        "es": "Error: {details}",
        "de": "Fehler: {details}",
    },
    "Error: {error}": {
        "fr": "Erreur : {error}",
        "es": "Error: {error}",
        "de": "Fehler: {error}",
    },
    "Exit": {
        "fr": "Quitter",
        "es": "Salir",
        "de": "Beenden",
    },
    "Expected file: {path}": {
        "fr": "Fichier attendu : {path}",
        "es": "Archivo esperado: {path}",
        "de": "Erwartete Datei: {path}",
    },
    "Export completed": {
        "fr": "Export termin\u00e9",
        "es": "Exportaci\u00f3n completada",
        "de": "Export abgeschlossen",
    },
    "Export icons": {
        "fr": "Exporter les ic\u00f4nes",
        "es": "Exportar iconos",
        "de": "Symbole exportieren",
    },
    "Facebook": {
        "ru": "\u0424\u0435\u0439\u0441\u0431\u0443\u043a",
        "uk": "Facebook",
        "fr": "Facebook",
        "es": "Facebook",
        "de": "Facebook",
    },
    "Failed to confirm section selection.": {
        "fr": "Impossible de confirmer la s\u00e9lection de la section.",
        "es": "No se pudo confirmar la selecci\u00f3n de la secci\u00f3n.",
        "de": "Abschnittsauswahl konnte nicht best\u00e4tigt werden.",
    },
    "Failed to count items: {error}": {
        "fr": "\u00c9chec du comptage des \u00e9l\u00e9ments : {error}",
        "es": "No se pudieron contar los elementos: {error}",
        "de": "Elemente konnten nicht gez\u00e4hlt werden: {error}",
    },
    "Failed to delete category: {error}": {
        "fr": "Impossible de supprimer la cat\u00e9gorie : {error}",
        "es": "No se pudo eliminar la categor\u00eda: {error}",
        "de": "Kategorie konnte nicht gel\u00f6scht werden: {error}",
    },
    "Failed to fetch link information.": {
        "fr": "Impossible de r\u00e9cup\u00e9rer les informations du lien.",
        "es": "No se pudo obtener la informaci\u00f3n del enlace.",
        "de": "Linkinformationen konnten nicht abgerufen werden.",
    },
    "Failed to list database backups: {error}": {
        "ru": "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u0441\u043f\u0438\u0441\u043e\u043a \u0440\u0435\u0437\u0435\u0440\u0432\u043d\u044b\u0445 \u043a\u043e\u043f\u0438\u0439 \u0431\u0430\u0437\u044b \u0434\u0430\u043d\u043d\u044b\u0445: {error}",
        "uk": "\u041d\u0435 \u0432\u0434\u0430\u043b\u043e\u0441\u044f \u043e\u0442\u0440\u0438\u043c\u0430\u0442\u0438 \u0441\u043f\u0438\u0441\u043e\u043a \u0440\u0435\u0437\u0435\u0440\u0432\u043d\u0438\u0445 \u043a\u043e\u043f\u0456\u0439 \u0431\u0430\u0437\u0438 \u0434\u0430\u043d\u0438\u0445: {error}",
        "fr": "Impossible d\u2019\u00e9num\u00e9rer les sauvegardes de la base : {error}",
        "es": "No se pudo enumerar las copias de seguridad de la base de datos: {error}",
        "de": "Auflistung der Datenbanksicherungen fehlgeschlagen: {error}",
    },
    "Failed to load file:\n{0}": {
        "ru": "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u0444\u0430\u0439\u043b:\n{0}",
        "uk": "\u041d\u0435 \u0432\u0434\u0430\u043b\u043e\u0441\u044f \u0437\u0430\u0432\u0430\u043d\u0442\u0430\u0436\u0438\u0442\u0438 \u0444\u0430\u0439\u043b:\n{0}",
        "fr": "Impossible de charger le fichier :\n{0}",
        "es": "No se pudo cargar el archivo:\n{0}",
        "de": "Datei konnte nicht geladen werden:\n{0}",
    },
    "Failed to load profiles": {
        "fr": "Impossible de charger les profils",
        "es": "No se pudieron cargar los perfiles",
        "de": "Profile konnten nicht geladen werden",
    },
    "Failed to load sections.": {
        "ru": "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u0440\u0430\u0437\u0434\u0435\u043b\u044b.",
        "uk": "\u041d\u0435 \u0432\u0434\u0430\u043b\u043e\u0441\u044f \u0437\u0430\u0432\u0430\u043d\u0442\u0430\u0436\u0438\u0442\u0438 \u0440\u043e\u0437\u0434\u0456\u043b\u0438.",
        "fr": "Impossible de charger les sections.",
        "es": "No se pudieron cargar las secciones.",
        "de": "Abschnitte konnten nicht geladen werden.",
    },
    "Failed to load spheres": {
        "ru": "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u0441\u0444\u0435\u0440\u044b",
        "uk": "\u041d\u0435 \u0432\u0434\u0430\u043b\u043e\u0441\u044f \u0437\u0430\u0432\u0430\u043d\u0442\u0430\u0436\u0438\u0442\u0438 \u0441\u0444\u0435\u0440\u0438",
        "fr": "Impossible de charger les sph\u00e8res",
        "es": "No se pudieron cargar las esferas",
        "de": "Sph\u00e4ren konnten nicht geladen werden",
    },
    "Failed to open file in explorer: {error}": {
        "uk": "\u041d\u0435 \u0432\u0434\u0430\u043b\u043e\u0441\u044f \u0432\u0456\u0434\u043a\u0440\u0438\u0442\u0438 \u0444\u0430\u0439\u043b \u0443 \u043f\u0440\u043e\u0432\u0456\u0434\u043d\u0438\u043a\u0443: {error}",
        "fr": "Impossible d\u2019ouvrir le fichier dans l\u2019explorateur : {error}",
        "es": "No se pudo abrir el archivo en el explorador: {error}",
        "de": "Datei konnte im Explorer nicht ge\u00f6ffnet werden: {error}",
    },
    "Failed to save file:\n{0}": {
        "ru": "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0444\u0430\u0439\u043b:\n{0}",
        "uk": "\u041d\u0435 \u0432\u0434\u0430\u043b\u043e\u0441\u044f \u0437\u0431\u0435\u0440\u0435\u0433\u0442\u0438 \u0444\u0430\u0439\u043b:\n{0}",
        "fr": "Impossible d\u2019enregistrer le fichier :\n{0}",
        "es": "No se pudo guardar el archivo:\n{0}",
        "de": "Datei konnte nicht gespeichert werden:\n{0}",
    },
    "Failed to start deletion task: {error}": {
        "fr": "Impossible de lancer la suppression : {error}",
        "es": "No se pudo iniciar la tarea de eliminaci\u00f3n: {error}",
        "de": "L\u00f6schvorgang konnte nicht gestartet werden: {error}",
    },
    "Failed to start loading": {
        "fr": "Impossible de lancer le chargement",
        "es": "No se pudo iniciar la carga",
        "de": "Ladevorgang konnte nicht gestartet werden",
    },
    "Failed to update item positions.": {
        "fr": "Impossible de mettre \u00e0 jour la position des \u00e9l\u00e9ments.",
        "es": "No se pudo actualizar la posici\u00f3n de los elementos.",
        "de": "Elementpositionen konnten nicht aktualisiert werden.",
    },
    "File contains invalid JSON:\n{0}": {
        "ru": "\u0424\u0430\u0439\u043b \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u0442 \u043d\u0435\u043a\u043e\u0440\u0440\u0435\u043a\u0442\u043d\u044b\u0439 JSON:\n{0}",
        "uk": "\u0424\u0430\u0439\u043b \u043c\u0456\u0441\u0442\u0438\u0442\u044c \u043d\u0435\u043a\u043e\u0440\u0435\u043a\u0442\u043d\u0438\u0439 JSON:\n{0}",
        "fr": "Le fichier contient un JSON invalide :\n{0}",
        "es": "El archivo contiene un JSON no v\u00e1lido:\n{0}",
        "de": "Datei enth\u00e4lt ung\u00fcltiges JSON:\n{0}",
    },
    "File not found: {path}": {
        "uk": "\u0424\u0430\u0439\u043b \u043d\u0435 \u0437\u043d\u0430\u0439\u0434\u0435\u043d\u043e: {path}",
        "fr": "Fichier introuvable : {path}",
        "es": "Archivo no encontrado: {path}",
        "de": "Datei nicht gefunden: {path}",
    },
    "Format error": {
        "fr": "Erreur de format",
        "es": "Error de formato",
        "de": "Formatfehler",
    },
    "General": {
        "fr": "G\u00e9n\u00e9ral",
        "es": "General",
        "de": "Allgemein",
    },
    "Hidden files": {
        "uk": "\u041f\u0440\u0438\u0445\u043e\u0432\u0430\u043d\u0456 \u0444\u0430\u0439\u043b\u0438",
        "fr": "Fichiers cach\u00e9s",
        "es": "Archivos ocultos",
        "de": "Verborgene Dateien",
    },
    "History is unavailable. Move between sections canceled.": {
        "fr": "Historique indisponible. D\u00e9placement entre sections annul\u00e9.",
        "es": "Historial no disponible. Movimiento entre secciones cancelado.",
        "de": "Verlauf nicht verf\u00fcgbar. Verschieben zwischen Abschnitten abgebrochen.",
    },
    "ID {id}": {
        "ru": "\u0418\u0434\u0435\u043d\u0442\u0438\u0444\u0438\u043a\u0430\u0442\u043e\u0440 {id}",
        "uk": "\u0406\u0434\u0435\u043d\u0442\u0438\u0444\u0456\u043a\u0430\u0442\u043e\u0440 {id}",
        "fr": "ID {id}",
        "es": "ID {id}",
        "de": "ID {id}",
    },
    "Icon configuration is invalid.": {
        "fr": "La configuration de l\u2019ic\u00f4ne est invalide.",
        "es": "La configuraci\u00f3n del icono es inv\u00e1lida.",
        "de": "Symbolkonfiguration ist ung\u00fcltig.",
    },
    "Icon issue": {
        "fr": "Probl\u00e8me d’ic\u00f4ne",
        "es": "Problema con el icono",
        "de": "Symbolproblem",
    },
    "Icon selection error": {
        "fr": "Erreur de s\u00e9lection d’ic\u00f4ne",
        "es": "Error al seleccionar el icono",
        "de": "Fehler bei der Symbolauswahl",
    },
    "Icons directory is not set. Specify the path in the application settings or config.": {
        "fr": "Le dossier des ic\u00f4nes n’est pas d\u00e9fini. Indiquez le chemin dans les param\u00e8tres ou la configuration.",
        "es": "No se ha establecido el directorio de iconos. Especifique la ruta en la configuraci\u00f3n de la aplicaci\u00f3n.",
        "de": "Das Symbolverzeichnis ist nicht festgelegt. Geben Sie den Pfad in den Einstellungen oder der Konfiguration an.",
    },
    "Import confirmation": {
        "fr": "Confirmation d’import",
        "es": "Confirmaci\u00f3n de importaci\u00f3n",
        "de": "Importbest\u00e4tigung",
    },
    "Import from browser": {
        "fr": "Importer depuis le navigateur",
        "es": "Importar desde el navegador",
        "de": "Aus dem Browser importieren",
    },
    "Import icons": {
        "fr": "Importer des ic\u00f4nes",
        "es": "Importar iconos",
        "de": "Symbole importieren",
    },
    "Import structure from file:\n{0}\n\n\u26a0\ufe0f WARNING: Current structure will be completely replaced!\n\nIt is recommended to create a backup before importing.": {
        "ru": "\u0418\u043c\u043f\u043e\u0440\u0442 \u0441\u0442\u0440\u0443\u043a\u0442\u0443\u0440\u044b \u0438\u0437 \u0444\u0430\u0439\u043b\u0430:\n{0}\n\n\u26a0\ufe0f \u0412\u041d\u0418\u041c\u0410\u041d\u0418\u0415: \u0442\u0435\u043a\u0443\u0449\u0430\u044f \u0441\u0442\u0440\u0443\u043a\u0442\u0443\u0440\u0430 \u0431\u0443\u0434\u0435\u0442 \u043f\u043e\u043b\u043d\u043e\u0441\u0442\u044c\u044e \u0437\u0430\u043c\u0435\u043d\u0435\u043d\u0430!\n\n\u0420\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0443\u0435\u0442\u0441\u044f \u0441\u043e\u0437\u0434\u0430\u0442\u044c \u0440\u0435\u0437\u0435\u0440\u0432\u043d\u0443\u044e \u043a\u043e\u043f\u0438\u044e \u043f\u0435\u0440\u0435\u0434 \u0438\u043c\u043f\u043e\u0440\u0442\u043e\u043c.",
        "uk": "\u0406\u043c\u043f\u043e\u0440\u0442 \u0441\u0442\u0440\u0443\u043a\u0442\u0443\u0440\u0438 \u0437 \u0444\u0430\u0439\u043b\u0443:\n{0}\n\n\u26a0\ufe0f \u041f\u041e\u041f\u0415\u0420\u0415\u0414\u0416\u0415\u041d\u041d\u042f: \u043f\u043e\u0442\u043e\u0447\u043d\u0430 \u0441\u0442\u0440\u0443\u043a\u0442\u0443\u0440\u0430 \u0431\u0443\u0434\u0435 \u043f\u043e\u0432\u043d\u0456\u0441\u0442\u044e \u0437\u0430\u043c\u0456\u043d\u0435\u043d\u0430!\n\n\u0420\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0443\u0454\u043c\u043e \u0441\u0442\u0432\u043e\u0440\u0438\u0442\u0438 \u0440\u0435\u0437\u0435\u0440\u0432\u043d\u0443 \u043a\u043e\u043f\u0456\u044e \u043f\u0435\u0440\u0435\u0434 \u0456\u043c\u043f\u043e\u0440\u0442\u043e\u043c.",
        "fr": "Importer la structure depuis le fichier :\n{0}\n\n\u26a0\ufe0f AVERTISSEMENT : la structure actuelle sera totalement remplac\u00e9e !\n\nIl est recommand\u00e9 de cr\u00e9er une sauvegarde avant l’import.",
        "es": "Importar estructura desde el archivo:\n{0}\n\n\u26a0\ufe0f ADVERTENCIA: ¡La estructura actual se reemplazar\u00e1 por completo!\n\nSe recomienda crear una copia de seguridad antes de importar.",
        "de": "Struktur aus Datei importieren:\n{0}\n\n\u26a0\ufe0f WARNUNG: Die aktuelle Struktur wird vollst\u00e4ndig ersetzt!\n\nEs wird empfohlen, vor dem Import eine Sicherung anzulegen.",
    },
    "Information": {
        "fr": "Information",
        "es": "Informaci\u00f3n",
        "de": "Information",
    },
    "Invalid input": {
        "fr": "Entr\u00e9e invalide",
        "es": "Entrada no v\u00e1lida",
        "de": "Ung\u00fcltige Eingabe",
    },
    "Invalid link ID": {
        "ru": "\u041d\u0435\u0434\u043e\u043f\u0443\u0441\u0442\u0438\u043c\u044b\u0439 \u0438\u0434\u0435\u043d\u0442\u0438\u0444\u0438\u043a\u0430\u0442\u043e\u0440 \u0441\u0441\u044b\u043b\u043a\u0438",
        "uk": "\u041d\u0435\u0434\u0456\u0439\u0441\u043d\u0438\u0439 \u0456\u0434\u0435\u043d\u0442\u0438\u0444\u0456\u043a\u0430\u0442\u043e\u0440 \u043f\u043e\u0441\u0438\u043b\u0430\u043d\u043d\u044f",
        "fr": "Identifiant de lien invalide",
        "es": "ID de enlace no v\u00e1lido",
        "de": "Ung\u00fcltige Link-ID",
    },
    "Invalid link data for toggle_favorite": {
        "fr": "Donn\u00e9es de lien invalides pour toggle_favorite",
        "es": "Datos de enlace no v\u00e1lidos para toggle_favorite",
        "de": "Ung\u00fcltige Linkdaten f\u00fcr toggle_favorite",
    },
    "Invalid regular expression for content: {error}": {
        "uk": "Некоректний регулярний вираз для вмісту: {error}",
        "fr": "Expression rationnelle invalide pour le contenu : {error}",
        "es": "Expresión regular no válida para el contenido: {error}",
        "de": "Ung\u00fcltiger regul\u00e4rer Ausdruck f\u00fcr Inhalt: {error}",
    },
    "Invalid regular expression for name: {error}": {
        "uk": "Некоректний регулярний вираз для назви: {error}",
        "fr": "Expression rationnelle invalide pour le nom : {error}",
        "es": "Expresión regular no válida para el nombre: {error}",
        "de": "Ung\u00fcltiger regul\u00e4rer Ausdruck f\u00fcr Namen: {error}",
    },
    "Light": {
        "ru": "\u0421\u0432\u0435\u0442\u043b\u0430\u044f",
        "uk": "\u0421\u0432\u0456\u0442\u043b\u0430",
        "fr": "Clair",
        "es": "Claro",
        "de": "Hell",
    },
    "Link not found": {
        "fr": "Lien introuvable",
        "es": "Enlace no encontrado",
        "de": "Link nicht gefunden",
    },
    "Link processing error": {
        "fr": "Erreur de traitement du lien",
        "es": "Error al procesar el enlace",
        "de": "Fehler bei der Linkverarbeitung",
    },
    "LinkedIn": {
        "ru": "\u041b\u0438\u043d\u043a\u0435\u0434\u0438\u043d",
        "uk": "LinkedIn",
        "fr": "LinkedIn",
        "es": "LinkedIn",
        "de": "LinkedIn",
    },
    "Links: %1": {
        "fr": "Liens\u00a0: %1",
        "es": "Enlaces: %1",
        "de": "Links: %1",
    },
    "Loading profiles\u2026": {
        "fr": "Chargement des profils\u2026",
        "es": "Cargando perfiles\u2026",
        "de": "Profile werden geladen\u2026",
    },
    "Loading\u2026": {
        "ru": "\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430\u2026",
        "uk": "\u0417\u0430\u0432\u0430\u043d\u0442\u0430\u0436\u0435\u043d\u043d\u044f\u2026",
        "fr": "Chargement\u2026",
        "es": "Cargando\u2026",
        "de": "Wird geladen\u2026",
    },
    "Modified:": {
        "uk": "\u0417\u043c\u0456\u043d\u0435\u043d\u043e:",
        "fr": "Modifi\u00e9\u00a0:",
        "es": "Modificado:",
        "de": "Ge\u00e4ndert:",
    },
    "Name (regex):": {
        "uk": "\u041d\u0430\u0437\u0432\u0430 (regex):",
        "fr": "Nom (regex)\u00a0:",
        "es": "Nombre (regex):",
        "de": "Name (Regex):",
    },
    "Name cannot be empty.": {
        "fr": "Le nom ne peut pas \u00eatre vide.",
        "es": "El nombre no puede estar vac\u00edo.",
        "de": "Der Name darf nicht leer sein.",
    },
    "Name:": {
        "uk": "\u041d\u0430\u0437\u0432\u0430:",
        "fr": "Nom\u00a0:",
        "es": "Nombre:",
        "de": "Name:",
    },
    "No backup selected.": {
        "ru": "\u0420\u0435\u0437\u0435\u0440\u0432\u043d\u0430\u044f \u043a\u043e\u043f\u0438\u044f \u043d\u0435 \u0432\u044b\u0431\u0440\u0430\u043d\u0430.",
        "uk": "\u0420\u0435\u0437\u0435\u0440\u0432\u043d\u0443 \u043a\u043e\u043f\u0456\u044e \u043d\u0435 \u0432\u0438\u0431\u0440\u0430\u043d\u043e.",
        "fr": "Aucune sauvegarde s\u00e9lectionn\u00e9e.",
        "es": "No se ha seleccionado ninguna copia de seguridad.",
        "de": "Keine Sicherung ausgew\u00e4hlt.",
    },
    "No data": {
        "fr": "Aucune donn\u00e9e",
        "es": "Sin datos",
        "de": "Keine Daten",
    },
    "No profiles found": {
        "fr": "Aucun profil trouv\u00e9",
        "es": "No se encontraron perfiles",
        "de": "Keine Profile gefunden",
    },
    "No section selected for import.": {
        "fr": "Aucune section s\u00e9lectionn\u00e9e pour l\u2019import.",
        "es": "No se seleccion\u00f3 ninguna secci\u00f3n para importar.",
        "de": "Kein Abschnitt zum Import ausgew\u00e4hlt.",
    },
    "No spheres found": {
        "fr": "Aucune sph\u00e8re trouv\u00e9e",
        "es": "No se encontraron esferas",
        "de": "Keine Sph\u00e4ren gefunden",
    },
    "Notes": {
        "fr": "Notes",
        "es": "Notas",
        "de": "Notizen",
    },
    "Notes:": {
        "uk": "\u041f\u0440\u0438\u043c\u0456\u0442\u043a\u0438:",
        "fr": "Notes\u00a0:",
        "es": "Notas:",
        "de": "Notizen:",
    },
    "Open": {
        "fr": "Ouvrir",
        "es": "Abrir",
        "de": "\u00d6ffnen",
    },
    "Open in file explorer": {
        "uk": "\u0412\u0456\u0434\u043a\u0440\u0438\u0442\u0438 \u0443 \u043f\u0440\u043e\u0432\u0456\u0434\u043d\u0438\u043a\u0443",
        "fr": "Ouvrir dans l\u2019explorateur",
        "es": "Abrir en el explorador de archivos",
        "de": "Im Datei-Explorer \u00f6ffnen",
    },
    "Paste": {
        "fr": "Coller",
        "es": "Pegar",
        "de": "Einf\u00fcgen",
    },
    "Path: ": {
        "fr": "Chemin\u00a0: ",
        "es": "Ruta: ",
        "de": "Pfad: ",
    },
    "Pattern:": {
        "uk": "\u0428\u0430\u0431\u043b\u043e\u043d:",
        "fr": "Motif\u00a0:",
        "es": "Patr\u00f3n:",
        "de": "Muster:",
    },
    "Pinterest": {
        "ru": "\u041f\u0438\u043d\u0442\u0435\u0440\u0435\u0441\u0442",
        "uk": "Pinterest",
        "fr": "Pinterest",
        "es": "Pinterest",
        "de": "Pinterest",
    },
    "Please provide a name for the entity.": {
        "fr": "Veuillez indiquer un nom pour l’entit\u00e9.",
        "es": "Indique un nombre para la entidad.",
        "de": "Bitte geben Sie einen Namen f\u00fcr das Objekt an.",
    },
    "Position changes were not saved.": {
        "fr": "Les modifications de position n’ont pas \u00e9t\u00e9 enregistr\u00e9es.",
        "es": "Los cambios de posici\u00f3n no se guardaron.",
        "de": "Positions\u00e4nderungen wurden nicht gespeichert.",
    },
    "Profile: {email}": {
        "fr": "Profil : {email}",
        "es": "Perfil: {email}",
        "de": "Profil: {email}",
    },
    "Profiles: {first}, {second}": {
        "fr": "Profils : {first}, {second}",
        "es": "Perfiles: {first}, {second}",
        "de": "Profile: {first}, {second}",
    },
    "Profiles: {first}, {second} and {rest} more": {
        "fr": "Profils : {first}, {second} et {rest} autres",
        "es": "Perfiles: {first}, {second} y {rest} m\u00e1s",
        "de": "Profile: {first}, {second} und {rest} weitere",
    },
    "Quickly apply an extension mask": {
        "uk": "\u0428\u0432\u0438\u0434\u043a\u043e \u0437\u0430\u0441\u0442\u043e\u0441\u0443\u0432\u0430\u0442\u0438 \u043c\u0430\u0441\u043a\u0443 \u0440\u043e\u0437\u0448\u0438\u0440\u0435\u043d\u044c",
        "fr": "Appliquer rapidement un masque d’extension",
        "es": "Aplicar r\u00e1pidamente una m\u00e1scara de extensi\u00f3n",
        "de": "Dateierweiterungsmaske schnell anwenden",
    },
    "Read-only": {
        "uk": "\u041b\u0438\u0448\u0435 \u0447\u0438\u0442\u0430\u043d\u043d\u044f",
        "fr": "Lecture seule",
        "es": "Solo lectura",
        "de": "Schreibgesch\u00fctzt",
    },
    "Ready": {
        "fr": "Pr\u00eat",
        "es": "Listo",
        "de": "Bereit",
    },
    "Ready to search": {
        "uk": "\u0413\u043e\u0442\u043e\u0432\u043e \u0434\u043e \u043f\u043e\u0448\u0443\u043a\u0443",
        "fr": "Pr\u00eat pour la recherche",
        "es": "Listo para buscar",
        "de": "Bereit zum Suchen",
    },
    "Refresh": {
        "fr": "Actualiser",
        "es": "Actualizar",
        "de": "Aktualisieren",
    },
    "Refresh profiles": {
        "fr": "Actualiser les profils",
        "es": "Actualizar perfiles",
        "de": "Profile aktualisieren",
    },
    "Regex": {
        "fr": "Regex",
        "es": "Regex",
        "de": "Regex",
    },
    "Remove from favorites": {
        "fr": "Retirer des favoris",
        "es": "Quitar de favoritos",
        "de": "Aus Favoriten entfernen",
    },
    "Rename the category or choose another section.": {
        "fr": "Renommez la cat\u00e9gorie ou choisissez une autre section.",
        "es": "Renombre la categor\u00eda o elija otra secci\u00f3n.",
        "de": "Benennen Sie die Kategorie um oder w\u00e4hlen Sie einen anderen Abschnitt.",
    },
    "Restore database": {
        "fr": "Restaurer la base de donn\u00e9es",
        "es": "Restaurar base de datos",
        "de": "Datenbank wiederherstellen",
    },
    "Save database": {
        "fr": "Enregistrer la base de donn\u00e9es",
        "es": "Guardar base de datos",
        "de": "Datenbank speichern",
    },
    "Save error": {
        "fr": "Erreur d'enregistrement",
        "es": "Error de guardado",
        "de": "Speicherfehler",
    },
    "Script": {
        "fr": "Script",
        "es": "Script",
        "de": "Skript",
    },
    "Search": {
        "uk": "Пошук",
        "fr": "Rechercher",
        "es": "Buscar",
        "de": "Suchen",
    },
    "Search by name/email…": {
        "fr": "Rechercher par nom/e-mail…",
        "es": "Buscar por nombre/correo…",
        "de": "Nach Name/E-Mail suchen…",
    },
    "Search error": {
        "uk": "Помилка пошуку",
        "fr": "Erreur de recherche",
        "es": "Error de búsqueda",
        "de": "Suchfehler",
    },
    "Search files": {
        "fr": "Rechercher des fichiers",
        "es": "Buscar archivos",
        "de": "Dateien suchen",
    },
    "Search finished. Files found: {count}": {
        "uk": "Пошук завершено. Знайдено файлів: {count}",
        "fr": "Recherche terminée. Fichiers trouvés : {count}",
        "es": "Búsqueda finalizada. Archivos encontrados: {count}",
        "de": "Suche abgeschlossen. Gefundene Dateien: {count}",
    },
    "Search location:": {
        "uk": "Область пошуку:",
        "fr": "Emplacement :",
        "es": "Ubicación:",
        "de": "Suchbereich:",
    },
    "Searching…": {
        "uk": "Пошук…",
        "fr": "Recherche…",
        "es": "Buscando…",
        "de": "Suche läuft…",
    },
    "Section named \"{name}\" already exists in the selected sphere": {
        "fr": "Une section nommée « {name} » existe déjà dans la sphère sélectionnée",
        "es": "Ya existe una sección llamada \"{name}\" en la esfera seleccionada",
        "de": "Ein Abschnitt namens „{name}“ existiert bereits in der ausgewählten Sphäre",
    },
    "Section not found": {
        "fr": "Section introuvable",
        "es": "Sección no encontrada",
        "de": "Abschnitt nicht gefunden",
    },
    "Section not selected.": {
        "fr": "Aucune section sélectionnée.",
        "es": "No se seleccionó ninguna sección.",
        "de": "Kein Abschnitt ausgewählt.",
    },
    "Section selection required": {
        "ru": "Требуется выбрать раздел",
        "uk": "Потрібно вибрати розділ",
        "fr": "Sélection d’une section requise",
        "es": "Se requiere seleccionar una sección",
        "de": "Abschnittsauswahl erforderlich",
    },
    "Section:": {
        "ru": "Раздел:",
        "uk": "Розділ:",
        "fr": "Section :",
        "es": "Sección:",
        "de": "Abschnitt:",
    },
    "Sections load error": {
        "fr": "Erreur de chargement des sections",
        "es": "Error al cargar las secciones",
        "de": "Fehler beim Laden der Abschnitte",
    },
    "Select Chrome profile": {
        "fr": "Sélectionner un profil Chrome",
        "es": "Seleccionar perfil de Chrome",
        "de": "Chrome-Profil auswählen",
    },
    "Select a file from the list and click 'Restore'. If the list is empty, verify the backup directory.": {
        "ru": "Выберите файл из списка и нажмите «Восстановить». Если список пуст, проверьте каталог резервных копий.",
        "uk": "Виберіть файл зі списку й натисніть «Відновити». Якщо список порожній, перевірте каталог резервних копій.",
        "fr": "Sélectionnez un fichier dans la liste et cliquez sur « Restaurer ». Si la liste est vide, vérifiez le dossier de sauvegarde.",
        "es": "Seleccione un archivo de la lista y haga clic en «Restaurar». Si la lista está vacía, verifique el directorio de copias de seguridad.",
        "de": "Wählen Sie eine Datei aus der Liste und klicken Sie auf „Wiederherstellen“. Ist die Liste leer, prüfen Sie das Sicherungsverzeichnis.",
    },
    "Select a sphere first": {
        "fr": "Sélectionnez d’abord une sphère",
        "es": "Seleccione primero una esfera",
        "de": "Wählen Sie zuerst eine Sphäre aus",
    },
    "Select all": {
        "fr": "Tout sélectionner",
        "es": "Seleccionar todo",
        "de": "Alles auswählen",
    },
    "Select browser profile": {
        "fr": "Sélectionner un profil navigateur",
        "es": "Seleccionar perfil de navegador",
        "de": "Browser-Profil auswählen",
    },
    "Select folder for search": {
        "uk": "Виберіть теку для пошуку",
        "fr": "Sélectionnez un dossier à parcourir",
        "es": "Seleccione la carpeta para la búsqueda",
        "de": "Ordner für die Suche auswählen",
    },
    "Select where to import links:": {
        "fr": "Choisissez où importer les liens :",
        "es": "Seleccione dónde importar los enlaces:",
        "de": "Ziel für den Linkimport auswählen:",
    },
    "Share": {
        "fr": "Partager",
        "es": "Compartir",
        "de": "Teilen",
    },
    "Size (KB):": {
        "uk": "Розмір (КБ):",
        "fr": "Taille (Ko) :",
        "es": "Tamaño (KB):",
        "de": "Größe (KB):",
    },
    "Sort categories": {
        "fr": "Trier les catégories",
        "es": "Ordenar categorías",
        "de": "Kategorien sortieren",
    },
    "Specify a folder to search.": {
        "uk": "Вкажіть теку для пошуку.",
        "fr": "Indiquez un dossier à parcourir.",
        "es": "Especifique una carpeta para la búsqueda.",
        "de": "Geben Sie einen Ordner für die Suche an.",
    },
    "Stop": {
        "uk": "Зупинити",
        "fr": "Arrêter",
        "es": "Detener",
        "de": "Stopp",
    },
    "Telegram": {
        "ru": "\u0422\u0435\u043b\u0435\u0433\u0440\u0430\u043c",
        "uk": "Telegram",
        "fr": "Telegram",
        "es": "Telegram",
        "de": "Telegram",
    },
    "The button will be shown without an icon. Provide a valid icons path in settings.": {
        "fr": "Le bouton sera affiché sans icône. Indiquez un chemin valide dans les paramètres.",
        "es": "El botón se mostrará sin icono. Proporcione una ruta válida en la configuración.",
        "de": "Der Button wird ohne Symbol angezeigt. Legen Sie in den Einstellungen einen gültigen Symbolpfad fest.",
    },
    "The category might have been deleted. ID: %1": {
        "ru": "Категория могла быть удалена. ID: %1",
        "uk": "Категорію, можливо, видалено. ID: %1",
        "fr": "La catégorie a peut-être été supprimée. ID : %1",
        "es": "La categoría puede haber sido eliminada. ID: %1",
        "de": "Die Kategorie wurde möglicherweise gelöscht. ID: %1",
    },
    "The folder does not exist: {path}": {
        "uk": "Теки не існує: {path}",
        "fr": "Le dossier n’existe pas : {path}",
        "es": "La carpeta no existe: {path}",
        "de": "Der Ordner existiert nicht: {path}",
    },
    "The section may have been removed. Refresh sections and select another.": {
        "fr": "La section a peut-être été supprimée. Actualisez la liste et choisissez-en une autre.",
        "es": "Es posible que la sección se haya eliminado. Actualice las secciones y seleccione otra.",
        "de": "Der Abschnitt wurde möglicherweise entfernt. Aktualisieren Sie die Liste und wählen Sie einen anderen.",
    },
    "The selected section is unavailable.": {
        "fr": "La section sélectionnée est indisponible.",
        "es": "La sección seleccionada no está disponible.",
        "de": "Der ausgewählte Abschnitt ist nicht verfügbar.",
    },
    "The selected sphere has no sections": {
        "fr": "La sphère sélectionnée ne contient aucune section",
        "es": "La esfera seleccionada no tiene secciones",
        "de": "Die ausgewählte Sphäre enthält keine Abschnitte",
    },
    "The specified path is not a folder: {path}": {
        "uk": "Зазначений шлях не є текою: {path}",
        "fr": "Le chemin indiqué n’est pas un dossier : {path}",
        "es": "La ruta especificada no es una carpeta: {path}",
        "de": "Der angegebene Pfad ist kein Ordner: {path}",
    },
    "Try selecting the section again or refresh the sections list.": {
        "fr": "Sélectionnez la section à nouveau ou actualisez la liste.",
        "es": "Seleccione la sección nuevamente o actualice la lista.",
        "de": "Wählen Sie den Abschnitt erneut oder aktualisieren Sie die Liste.",
    },
    "Unable to set selected icon.": {
        "fr": "Impossible d’appliquer l’icône sélectionnée.",
        "es": "No se pudo establecer el icono seleccionado.",
        "de": "Ausgewähltes Symbol konnte nicht gesetzt werden.",
    },
    "Undo history is unavailable. Batch move canceled.": {
        "fr": "Historique indisponible. Déplacement groupé annulé.",
        "es": "El historial no está disponible. Movimiento por lotes cancelado.",
        "de": "Verlauf nicht verfügbar. Stapelverschiebung abgebrochen.",
    },
    "Undo history is unavailable. Move canceled.": {
        "fr": "Historique indisponible. Déplacement annulé.",
        "es": "El historial no está disponible. Movimiento cancelado.",
        "de": "Verlauf nicht verfügbar. Verschiebung abgebrochen.",
    },
    "Undo history unavailable": {
        "fr": "Historique indisponible",
        "es": "Historial no disponible",
        "de": "Verlauf nicht verfügbar",
    },
    "Unexpected error: {error}": {
        "uk": "Неочікувана помилка: {error}",
        "fr": "Erreur inattendue : {error}",
        "es": "Error inesperado: {error}",
        "de": "Unerwarteter Fehler: {error}",
    },
    "Unnamed": {
        "fr": "Sans nom",
        "es": "Sin nombre",
        "de": "Ohne Namen",
    },
    "Verify the path/URL is valid and the resource is reachable.": {
        "fr": "Vérifiez que le chemin ou l’URL est valide et que la ressource est accessible.",
        "es": "Verifique que la ruta o URL sea válida y que el recurso sea accesible.",
        "de": "Stellen Sie sicher, dass Pfad/URL gültig sind und die Ressource erreichbar ist.",
    },
    "Via Gmail": {
        "fr": "Via Gmail",
        "es": "Vía Gmail",
        "de": "Über Gmail",
    },
    "Via default client (mailto)": {
        "fr": "Via le client par défaut (mailto)",
        "es": "Por el cliente predeterminado (mailto)",
        "de": "Über Standardclient (mailto)",
    },
    "Viber": {
        "ru": "\u0412\u0430\u0439\u0431\u0435\u0440",
        "uk": "Viber",
        "fr": "Viber",
        "es": "Viber",
        "de": "Viber",
    },
    "Warning": {
        "fr": "Avertissement",
        "es": "Advertencia",
        "de": "Warnung",
    },
    "WhatsApp": {
        "ru": "\u0412\u0430\u0442\u0441\u0430\u043f",
        "uk": "WhatsApp",
        "fr": "WhatsApp",
        "es": "WhatsApp",
        "de": "WhatsApp",
    },
    "X (Twitter)": {
        "ru": "X (\u0422\u0432\u0438\u0442\u0442\u0435\u0440)",
        "uk": "X (Twitter)",
        "fr": "X (Twitter)",
        "es": "X (Twitter)",
        "de": "X (Twitter)",
    },
    "category": {
        "fr": "catégorie",
        "es": "categoría",
        "de": "Kategorie",
    },
    "entity": {
        "fr": "entité",
        "es": "entidad",
        "de": "Objekt",
    },
    "from": {
        "uk": "від",
        "fr": "de",
        "es": "desde",
        "de": "von",
    },
    "section": {
        "fr": "section",
        "es": "sección",
        "de": "Abschnitt",
    },
    "to": {
        "uk": "до",
        "fr": "à",
        "es": "hasta",
        "de": "bis",
    },
    "{backup_name} ({size} MB)": {
        "fr": "{backup_name} ({size} Mo)",
        "es": "{backup_name} ({size} MB)",
        "de": "{backup_name} ({size} MB)",
    },
    "{backup_name} - {timestamp} ({size} MB)": {
        "es": "{backup_name} - {timestamp} ({size} MB)",
        "de": "{backup_name} - {timestamp} ({size} MB)",
    },
    "{operation} ({current}/{total})…": {
        "ru": "{operation} ({current} из {total})…",
        "uk": "{operation} ({current} із {total})…",
        "fr": "{operation} ({current}/{total})…",
        "es": "{operation} ({current}/{total})…",
        "de": "{operation} ({current}/{total})…",
    },
    "{percentage}% ({current}/{total})": {
        "ru": "{percentage}% ({current} из {total})",
        "uk": "{percentage}% ({current} із {total})",
        "fr": "{percentage}% ({current}/{total})",
        "es": "{percentage}% ({current}/{total})",
        "de": "{percentage}% ({current}/{total})",
    },
    "{profile} ({browser})": {
        "ru": "\u041f\u0440\u043e\u0444\u0438\u043b\u044c {profile} ({browser})",
        "uk": "\u041f\u0440\u043e\u0444\u0456\u043b\u044c {profile} ({browser})",
        "fr": "{profile} ({browser})",
        "es": "{profile} ({browser})",
        "de": "{profile} ({browser})",
    },
    "\u2705 Operation completed successfully": {
        "uk": "\u2705 \u041e\u043f\u0435\u0440\u0430\u0446\u0456\u044e \u0443\u0441\u043f\u0456\u0448\u043d\u043e \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u043e",
        "fr": "\u2705 Op\u00e9ration termin\u00e9e avec succ\u00e8s",
        "es": "\u2705 Operaci\u00f3n completada con \u00e9xito",
        "de": "\u2705 Vorgang erfolgreich abgeschlossen",
    },
    "\u274c Error: {error}": {
        "es": "\u274c Error: {error}",
        "fr": "\u274c Erreur : {error}",
        "de": "\u274c Fehler: {error}",
     }
}


def apply_translations() -> None:
    for lang_code, filename in LANG_FILES.items():
        path = I18N_DIR / filename
        tree = ET.parse(path)
        root = tree.getroot()
        updated = 0

        for context in root.findall("context"):
            for message in context.findall("message"):
                source = message.findtext("source") or ""
                translation_elem = message.find("translation")
                if not source or translation_elem is None:
                    continue

                new_text = TRANSLATIONS.get(source, {}).get(lang_code)
                if not new_text:
                    continue

                current_text = translation_elem.text or ""
                if current_text == new_text and translation_elem.get("type") is None:
                    continue

                translation_elem.text = new_text
                translation_elem.attrib.pop("type", None)
                updated += 1

        if updated:
            tree.write(path, encoding="utf-8")
            print(f"{filename}: updated {updated} entries")
        else:
            print(f"{filename}: no changes")


if __name__ == "__main__":
    apply_translations()