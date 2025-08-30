#!/usr/bin/env python3
"""Простой тест для проверки исправления логики _expects_reporter."""

import inspect
import sys
import os

# Добавляем путь к проекту
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _expects_reporter(callable_obj):
    """Воссоздаем исправленную логику _expects_reporter."""
    try:
        sig = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return False
    has_var_positional = any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values())
    if has_var_positional:
        return True
    positional_count = sum(
        1
        for p in sig.parameters.values()
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    )
    return positional_count == 1


def test_all_cases():
    """Тестируем все случаи использования функций."""
    
    # Функция без аргументов
    def func_no_args():
        return "success"
    
    # Функция с одним аргументом
    def func_one_arg(report_progress):
        return "success"
    
    # Функция с несколькими аргументами
    def func_multiple_args(uid, data):
        return "success"
    
    # Функция с *args
    def func_with_varargs(*args):
        return "success"
    
    # Функция только с keyword-only параметрами
    def func_keyword_only(*, param="default"):
        return "success"
    
    # Функция с одним позиционным + **kwargs
    def func_with_kwargs(report_progress, **kwargs):
        return "success"
    
    # Функция с опциональным аргументом
    def func_optional_arg(report_progress=None):
        return "success"
    
    # Функция с несколькими позиционными (один обязательный, один опциональный)
    def func_mixed_params(required, optional="default"):
        return "success"
    
    # Тесты
    tests = [
        (func_no_args, False, "Функция без аргументов НЕ должна получать report_progress"),
        (func_one_arg, True, "Функция с одним аргументом ДОЛЖНА получать report_progress"),
        (func_multiple_args, False, "Функция с несколькими аргументами НЕ должна получать report_progress"),
        (func_with_varargs, True, "Функция с *args ДОЛЖНА получать report_progress"),
        (func_keyword_only, False, "Функция только с keyword-only НЕ должна получать report_progress"),
        (func_with_kwargs, True, "Функция с одним позиционным + **kwargs ДОЛЖНА получать report_progress"),
        (func_optional_arg, True, "Функция с одним опциональным аргументом ДОЛЖНА получать report_progress"),
        (func_mixed_params, False, "Функция с несколькими позиционными НЕ должна получать report_progress"),
    ]
    
    print("Тестирование логики _expects_reporter:")
    print("=" * 60)
    
    all_passed = True
    for func, expected, description in tests:
        result = _expects_reporter(func)
        status = "✓ PASS" if result == expected else "✗ FAIL"
        print(f"{status} | {description}")
        if result != expected:
            print(f"      Ожидалось: {expected}, получено: {result}")
            all_passed = False
    
    print("=" * 60)
    if all_passed:
        print("✓ Все тесты прошли успешно!")
    else:
        print("✗ Некоторые тесты не прошли!")
    assert all_passed


if __name__ == "__main__":
    success = test_all_cases()
    sys.exit(0 if success else 1)
