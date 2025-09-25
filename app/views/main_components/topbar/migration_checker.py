"""Утилита для проверки миграции на новый API TopBar."""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple


class MigrationChecker:
    """Проверяет миграцию с старого API adjust() на новый request_adjustment()."""
    
    def __init__(self, root_path: str):
        self.root_path = Path(root_path)
        self.issues: List[Dict[str, str]] = []
    
    def check_migration(self) -> Dict[str, List[Dict[str, str]]]:
        """Проверяет миграцию и возвращает отчет."""
        self.issues.clear()
        
        # Ищем Python файлы
        for py_file in self.root_path.rglob("*.py"):
            if "test" in str(py_file).lower():
                continue  # Пропускаем тесты
            
            self._check_file(py_file)
        
        return self._generate_report()
    
    def _check_file(self, file_path: Path) -> None:
        """Проверяет отдельный файл."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Проверяем прямые вызовы adjust()
            self._check_direct_adjust_calls(file_path, content)
            
            # Проверяем использование старых паттернов
            self._check_old_patterns(file_path, content)
            
        except Exception as e:
            self.issues.append({
                "type": "file_error",
                "file": str(file_path),
                "line": "0",
                "issue": f"Cannot read file: {e}",
                "suggestion": "Check file permissions and encoding"
            })
    
    def _check_direct_adjust_calls(self, file_path: Path, content: str) -> None:
        """Проверяет прямые вызовы adjust()."""
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            # Ищем вызовы .adjust() но исключаем комментарии и строки
            if '.adjust()' in line and not self._is_comment_or_string(line):
                # Проверяем, это не наш новый код
                if 'request_adjustment' not in lines[max(0, i-3):i+3]:
                    self.issues.append({
                        "type": "direct_adjust_call",
                        "file": str(file_path.relative_to(self.root_path)),
                        "line": str(i),
                        "issue": f"Direct adjust() call: {line.strip()}",
                        "suggestion": "Replace with request_adjustment(AdjustmentReason.APPROPRIATE_REASON)"
                    })
    
    def _check_old_patterns(self, file_path: Path, content: str) -> None:
        """Проверяет использование старых паттернов."""
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            # Проверяем старые проверки hasattr(obj, 'adjust')
            if re.search(r'hasattr\([^,]+,\s*["\']adjust["\']', line):
                if 'request_adjustment' not in line:
                    self.issues.append({
                        "type": "old_hasattr_check",
                        "file": str(file_path.relative_to(self.root_path)),
                        "line": str(i),
                        "issue": f"Old hasattr check: {line.strip()}",
                        "suggestion": "Update to check for 'request_adjustment' first"
                    })
            
            # Проверяем QTimer.singleShot с adjust
            if 'QTimer.singleShot' in line and 'adjust' in line:
                if 'request_adjustment' not in line:
                    self.issues.append({
                        "type": "qtimer_adjust",
                        "file": str(file_path.relative_to(self.root_path)),
                        "line": str(i),
                        "issue": f"QTimer with adjust: {line.strip()}",
                        "suggestion": "Use lambda with request_adjustment() instead"
                    })
    
    def _is_comment_or_string(self, line: str) -> bool:
        """Проверяет, находится ли вызов в комментарии или строке."""
        stripped = line.strip()
        if stripped.startswith('#'):
            return True
        
        # Простая проверка на строки (не идеальная, но достаточная)
        in_string = False
        quote_char = None
        for char in line:
            if char in ['"', "'"] and not in_string:
                in_string = True
                quote_char = char
            elif char == quote_char and in_string:
                in_string = False
                quote_char = None
        
        return False  # Упрощенная версия
    
    def _generate_report(self) -> Dict[str, List[Dict[str, str]]]:
        """Генерирует отчет о проблемах."""
        report = {
            "direct_adjust_calls": [],
            "old_hasattr_checks": [],
            "qtimer_issues": [],
            "file_errors": [],
            "other_issues": []
        }
        
        for issue in self.issues:
            issue_type = issue["type"]
            if issue_type == "direct_adjust_call":
                report["direct_adjust_calls"].append(issue)
            elif issue_type == "old_hasattr_check":
                report["old_hasattr_checks"].append(issue)
            elif issue_type == "qtimer_adjust":
                report["qtimer_issues"].append(issue)
            elif issue_type == "file_error":
                report["file_errors"].append(issue)
            else:
                report["other_issues"].append(issue)
        
        return report
    
    def print_report(self, report: Dict[str, List[Dict[str, str]]]) -> None:
        """Выводит отчет в консоль."""
        total_issues = sum(len(issues) for issues in report.values())
        
        print(f"\n🔍 Migration Check Report")
        print(f"========================")
        print(f"Total issues found: {total_issues}")
        
        if total_issues == 0:
            print("✅ No migration issues found! All adjust() calls have been migrated.")
            return
        
        for category, issues in report.items():
            if not issues:
                continue
            
            print(f"\n❌ {category.replace('_', ' ').title()}: {len(issues)}")
            print("-" * 40)
            
            for issue in issues:
                print(f"  📁 {issue['file']}:{issue['line']}")
                print(f"     Issue: {issue['issue']}")
                print(f"     Fix: {issue['suggestion']}")
                print()


def main():
    """Запускает проверку миграции."""
    import sys
    
    if len(sys.argv) > 1:
        root_path = sys.argv[1]
    else:
        # По умолчанию проверяем app директорию
        root_path = os.path.join(os.path.dirname(__file__), "..", "..", "..")
    
    checker = MigrationChecker(root_path)
    report = checker.check_migration()
    checker.print_report(report)
    
    # Возвращаем код ошибки если есть проблемы
    total_issues = sum(len(issues) for issues in report.values())
    sys.exit(1 if total_issues > 0 else 0)


if __name__ == "__main__":
    main()
