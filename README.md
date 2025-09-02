# Osteen Path — Architecture Overview

## Links domain refactor (async)

- **LinksBusinessLogic (`app/controllers/business/links_business.py`)**
  - Сфокусирован на бизнес‑правилах и сигналах UI (`links_loaded`, `search_results_ready`, `favorites_counted`, `link_updated`, `error_occurred`).
  - Не управляет потоками. Асинхронные операции делегируются в `LinkAsyncController`.
  - Доступ к данным делегируется в `LinksRepositoryAdapter`.
  - `shutdown(timeout)` делегирует `LinkAsyncController.shutdown(timeout_ms)`.

- **LinksRepositoryAdapter (`app/controllers/business/links_repository_adapter.py`)**
  - Инкапсулирует доступ к данным ссылок: чтение, поиск, подсчёты, создание/обновление, пакетные операции.
  - Поверх `Database.links` и/или `LinksService`.

- **LinkAsyncController (`app/controllers/business/link_async_controller.py`)**
  - Управляет задачами: загрузка ссылок по категории, поиск, подсчёт избранного.
  - Инкапсулирует работу с `QThreadPool`/фоном, возвращает результат через переданные колбэки.
  - Имеет `shutdown(timeout_ms)` для корректного ожидания пула потоков.

## Dependency Injection

- Создание и связывание выполняется в `app/controllers/system/window_controllers_setup.py`.
- Явно создаются `LinksRepositoryAdapter` и `LinkAsyncController`, которые передаются в `LinksBusinessLogic`.
- Добавлена защита: адаптер создаётся только если у `db` есть атрибут `links` (важно для тестов с частичными заглушками БД, где ранний `SetupError` ожидается на других шагах проводки).

## Shutdown последовательность

- `AppShutdownController` вызывает остановку бизнес‑/UI‑контроллеров, затем ожидание пулов потоков, затем бэкап.
- Для ссылок вызывается `window.links_business.shutdown()`.

## Тестирование

- Юнит‑тесты без Qt для `LinkAsyncController`: `tests/test_link_async_controller.py`.
- Тесты делегирования и сигналов для `LinksBusinessLogic`: `tests/test_links_business_logic_async_delegation.py`.
- Тест корректного вызова `links_business.shutdown` в `AppShutdownController`: `tests/test_app_shutdown_controller_links_business.py`.
- Полный набор: 208/208 тестов проходит.

## Миграция и контракты

- Сигналы UI остаются прежними; поведение внешнего API `LinksBusinessLogic` не изменилось.
- Новые зависимости внедряются через конструктор `LinksBusinessLogic(db, repository?, async_controller?)`.
- При добавлении новых асинхронных сценариев размещайте их в `LinkAsyncController`, а бизнес‑правила и сигналы — в `LinksBusinessLogic`.
