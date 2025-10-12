"""Тесты для утилит валидации (app/utils/ui/validators.py)."""

from app.utils.ui.validators import (
    validate_url,
    validate_file_path,
    validate_folder_path,
    validate_name,
    validate_icon_path,
    validate_email,
    validate_port,
    sanitize_filename,
)


class TestValidateUrl:
    """Тесты для validate_url()."""
    
    def test_valid_http_url(self):
        """Корректный HTTP URL проходит валидацию."""
        valid, error = validate_url("http://example.com")
        assert valid is True
        assert error is None
    
    def test_valid_https_url(self):
        """Корректный HTTPS URL проходит валидацию."""
        valid, error = validate_url("https://example.com/path?query=1")
        assert valid is True
        assert error is None
    
    def test_empty_url(self):
        """Пустой URL не проходит валидацию."""
        valid, error = validate_url("")
        assert valid is False
        assert "пустым" in error.lower()
    
    def test_url_without_scheme(self):
        """URL без протокола не проходит валидацию."""
        valid, error = validate_url("example.com")
        assert valid is False
        assert "протокол" in error.lower()
    
    def test_url_with_unsupported_scheme(self):
        """URL с неподдерживаемым протоколом не проходит."""
        valid, error = validate_url("telnet://example.com")
        assert valid is False
        assert "неподдерживаемый" in error.lower()
    
    def test_ftp_url(self):
        """FTP URL поддерживается."""
        valid, error = validate_url("ftp://ftp.example.com/file.txt")
        assert valid is True
        assert error is None
    
    def test_file_url(self):
        """File URL поддерживается."""
        valid, error = validate_url("file:///C:/path/to/file.txt")
        assert valid is True
        assert error is None
    
    def test_url_with_whitespace(self):
        """URL с пробелами обрезается и валидируется."""
        valid, error = validate_url("  https://example.com  ")
        assert valid is True


class TestValidateName:
    """Тесты для validate_name()."""
    
    def test_valid_name(self):
        """Корректное имя проходит валидацию."""
        valid, error = validate_name("My Category")
        assert valid is True
        assert error is None
    
    def test_empty_name(self):
        """Пустое имя не проходит."""
        valid, error = validate_name("")
        assert valid is False
        assert "пустым" in error.lower()
    
    def test_whitespace_only_name(self):
        """Имя из пробелов не проходит."""
        valid, error = validate_name("   ")
        assert valid is False
        assert "пустым" in error.lower()
    
    def test_name_too_short(self):
        """Слишком короткое имя не проходит."""
        valid, error = validate_name("AB", min_length=3)
        assert valid is False
        assert "короткое" in error.lower()
    
    def test_name_too_long(self):
        """Слишком длинное имя не проходит."""
        long_name = "A" * 300
        valid, error = validate_name(long_name, max_length=255)
        assert valid is False
        assert "длинное" in error.lower()
    
    def test_name_with_invalid_chars(self):
        """Имя с недопустимыми символами не проходит."""
        invalid_names = [
            "File<Name",
            "File>Name",
            'File"Name',
            "File|Name",
            "File?Name",
            "File*Name",
        ]
        for name in invalid_names:
            valid, error = validate_name(name)
            assert valid is False, f"Name '{name}' should be invalid"
            assert "недопустимые символы" in error.lower()
    
    def test_name_with_safe_special_chars(self):
        """Имя с безопасными спецсимволами проходит."""
        valid, error = validate_name("Category-Name (123)")
        assert valid is True


class TestValidateEmail:
    """Тесты для validate_email()."""
    
    def test_valid_email(self):
        """Корректный email проходит валидацию."""
        valid, error = validate_email("user@example.com")
        assert valid is True
        assert error is None
    
    def test_email_with_plus(self):
        """Email с + проходит."""
        valid, error = validate_email("user+tag@example.com")
        assert valid is True
    
    def test_email_with_subdomain(self):
        """Email с поддоменом проходит."""
        valid, error = validate_email("user@mail.example.com")
        assert valid is True
    
    def test_empty_email(self):
        """Пустой email не проходит."""
        valid, error = validate_email("")
        assert valid is False
        assert "пустым" in error.lower()
    
    def test_email_without_at(self):
        """Email без @ не проходит."""
        valid, error = validate_email("userexample.com")
        assert valid is False
        assert "некорректный" in error.lower()
    
    def test_email_without_domain(self):
        """Email без домена не проходит."""
        valid, error = validate_email("user@")
        assert valid is False


class TestValidatePort:
    """Тесты для validate_port()."""
    
    def test_valid_port(self):
        """Корректный порт проходит."""
        valid, error = validate_port("8080")
        assert valid is True
        assert error is None
    
    def test_port_min_value(self):
        """Минимальный порт (1) проходит."""
        valid, error = validate_port("1")
        assert valid is True
    
    def test_port_max_value(self):
        """Максимальный порт (65535) проходит."""
        valid, error = validate_port("65535")
        assert valid is True
    
    def test_port_zero(self):
        """Порт 0 не проходит."""
        valid, error = validate_port("0")
        assert valid is False
        assert "диапазон" in error.lower()
    
    def test_port_negative(self):
        """Отрицательный порт не проходит."""
        valid, error = validate_port("-1")
        assert valid is False
    
    def test_port_too_large(self):
        """Порт > 65535 не проходит."""
        valid, error = validate_port("70000")
        assert valid is False
        assert "диапазон" in error.lower()
    
    def test_port_not_number(self):
        """Нечисловой порт не проходит."""
        valid, error = validate_port("abc")
        assert valid is False
        assert "числом" in error.lower()
    
    def test_port_with_whitespace(self):
        """Порт с пробелами обрезается."""
        valid, error = validate_port("  8080  ")
        assert valid is True


class TestSanitizeFilename:
    """Тесты для sanitize_filename()."""
    
    def test_clean_filename(self):
        """Чистое имя файла не изменяется."""
        result = sanitize_filename("document.txt")
        assert result == "document.txt"
    
    def test_filename_with_invalid_chars(self):
        """Недопустимые символы заменяются на _."""
        result = sanitize_filename("file:name?.txt")
        assert ":" not in result
        assert "?" not in result
        assert result == "file_name_.txt"
    
    def test_filename_with_multiple_underscores(self):
        """Множественные _ схлопываются в один."""
        result = sanitize_filename("file___name.txt")
        assert result == "file_name.txt"
    
    def test_filename_with_leading_trailing_underscores(self):
        """Начальные/конечные _ удаляются."""
        result = sanitize_filename("_filename_.txt")
        assert result == "filename_.txt"
    
    def test_empty_filename(self):
        """Пустое имя заменяется на 'unnamed'."""
        result = sanitize_filename("")
        assert result == "unnamed"
    
    def test_filename_only_invalid_chars(self):
        """Файл только из недопустимых символов."""
        result = sanitize_filename(":<>?*")
        assert result == "unnamed"


class TestValidateFilePath:
    """Тесты для validate_file_path()."""
    
    def test_valid_path_not_must_exist(self):
        """Корректный путь (без требования существования)."""
        valid, error = validate_file_path("C:\\path\\to\\file.txt", must_exist=False)
        assert valid is True
    
    def test_empty_path(self):
        """Пустой путь не проходит."""
        valid, error = validate_file_path("")
        assert valid is False
        assert "пустым" in error.lower()
    
    def test_existing_file(self, tmp_path):
        """Существующий файл проходит при must_exist=True."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")
        
        valid, error = validate_file_path(str(test_file), must_exist=True)
        assert valid is True
    
    def test_non_existing_file_must_exist(self):
        """Несуществующий файл не проходит при must_exist=True."""
        valid, error = validate_file_path("C:\\nonexistent\\file.txt", must_exist=True)
        assert valid is False
        assert "не найден" in error.lower()
    
    def test_directory_instead_of_file(self, tmp_path):
        """Директория вместо файла не проходит."""
        valid, error = validate_file_path(str(tmp_path), must_exist=True)
        assert valid is False
        assert "папке" in error.lower()


class TestValidateFolderPath:
    """Тесты для validate_folder_path()."""
    
    def test_existing_folder(self, tmp_path):
        """Существующая папка проходит."""
        valid, error = validate_folder_path(str(tmp_path), must_exist=True)
        assert valid is True
    
    def test_non_existing_folder_must_exist(self):
        """Несуществующая папка не проходит при must_exist=True."""
        valid, error = validate_folder_path("C:\\nonexistent", must_exist=True)
        assert valid is False
        assert "не найдена" in error.lower()
    
    def test_file_instead_of_folder(self, tmp_path):
        """Файл вместо папки не проходит."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")
        
        valid, error = validate_folder_path(str(test_file), must_exist=True)
        assert valid is False
        assert "файлу" in error.lower()


class TestValidateIconPath:
    """Тесты для validate_icon_path()."""
    
    def test_empty_path_is_valid(self):
        """Пустой путь валиден (будет иконка по умолчанию)."""
        valid, error = validate_icon_path("")
        assert valid is True
    
    def test_existing_icon_with_valid_format(self, tmp_path):
        """Существующая иконка с валидным форматом."""
        icon_file = tmp_path / "icon.png"
        icon_file.write_bytes(b"fake png data")
        
        valid, error = validate_icon_path(str(icon_file), supported_formats=[".png", ".ico"])
        assert valid is True
    
    def test_icon_with_invalid_format(self, tmp_path):
        """Иконка с неподдерживаемым форматом."""
        icon_file = tmp_path / "icon.txt"
        icon_file.write_text("not an icon")
        
        valid, error = validate_icon_path(str(icon_file), supported_formats=[".png", ".ico"])
        assert valid is False
        assert "неподдерживаемый формат" in error.lower()
    
    def test_non_existing_icon(self):
        """Несуществующая иконка не проходит."""
        valid, error = validate_icon_path("C:\\nonexistent\\icon.png")
        assert valid is False
        assert "не найден" in error.lower()
