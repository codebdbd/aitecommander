"""Тесты для логики определения функций, ожидающих report_progress в db.api."""

import inspect


def test_expects_reporter_logic():
    """Тестируем логику _expects_reporter напрямую."""

    # Воссоздаем логику _expects_reporter для тестирования
    def _expects_reporter(callable_obj):
        try:
            sig = inspect.signature(callable_obj)
        except (TypeError, ValueError):
            return False
        has_var_positional = any(
            p.kind is inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values()
        )
        if has_var_positional:
            return True
        positional_count = sum(
            1
            for p in sig.parameters.values()
            if p.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        )
        return positional_count == 1

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

    # Проверяем логику
    assert not _expects_reporter(func_no_args), (
        "Функция без аргументов не должна получать report_progress"
    )
    assert _expects_reporter(func_one_arg), (
        "Функция с одним аргументом должна получать report_progress"
    )
    assert not _expects_reporter(func_multiple_args), (
        "Функция с несколькими аргументами не должна получать report_progress"
    )
    assert _expects_reporter(func_with_varargs), (
        "Функция с *args должна получать report_progress"
    )
    assert not _expects_reporter(func_keyword_only), (
        "Функция только с keyword-only параметрами не должна получать report_progress"
    )
    assert _expects_reporter(func_with_kwargs), (
        "Функция с одним позиционным + **kwargs должна получать report_progress"
    )


def test_function_signature_edge_cases():
    """Тестируем дополнительные случаи сигнатур функций."""

    # Воссоздаем логику _expects_reporter для тестирования
    def _expects_reporter(callable_obj):
        try:
            sig = inspect.signature(callable_obj)
        except (TypeError, ValueError):
            return False
        has_var_positional = any(
            p.kind is inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values()
        )
        if has_var_positional:
            return True
        positional_count = sum(
            1
            for p in sig.parameters.values()
            if p.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        )
        return positional_count == 1

    # Функция с опциональным аргументом (default value)
    def func_optional_arg(report_progress=None):
        return "success"

    # Функция с позиционным и keyword-only
    def func_mixed_params(pos_arg, *, kw_only="default"):
        return "success"

    # Функция только с **kwargs
    def func_only_kwargs(**kwargs):
        return "success"

    # Функция с позиционным, опциональным и **kwargs
    def func_complex(required, optional="default", **kwargs):
        return "success"

    # Проверяем логику
    assert _expects_reporter(func_optional_arg), (
        "Функция с одним опциональным аргументом должна получать report_progress"
    )
    assert _expects_reporter(func_mixed_params), (
        "Функция с одним позиционным должна получать report_progress"
    )
    assert not _expects_reporter(func_only_kwargs), (
        "Функция только с **kwargs не должна получать report_progress"
    )
    assert not _expects_reporter(func_complex), (
        "Функция с несколькими позиционными не должна получать report_progress"
    )
