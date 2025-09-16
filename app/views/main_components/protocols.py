# app/views/main_components/protocols.py
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class WindowUISetupProtocol(Protocol):
    """Протокол для UI-строителей панелей, чтобы не использовать Any.

    Минимальные требования к объекту WindowUISetup:
    - атрибут `window`: главное окно или совместимый объект
    - атрибут `main_layout`: основной вертикальный layout центрального содержимого

    Протокол нарочно остаётся узким, чтобы избежать циклических импортов и
    излишней связности. Дополнительные методы/атрибуты, если нужны, можно
    добавлять по мере необходимости.
    """

    window: Any
    main_layout: Any
