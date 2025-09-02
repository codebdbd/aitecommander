from app.controllers.system.app_shutdown_controller import AppShutdownController


class WindowStub:
    def __init__(self):
        class LinksBusinessStub:
            def __init__(self):
                self.shutdown_called = 0

            def shutdown(self):
                self.shutdown_called += 1
        self.links_business = LinksBusinessStub()
        # другие контроллеры могут отсутствовать — код это выдерживает


def test_shutdown_controllers_calls_links_business_shutdown():
    win = WindowStub()
    ctrl = AppShutdownController(win)

    # вызываем приватный метод напрямую, чтобы не трогать потоки и бэкап
    ctrl._shutdown_controllers()

    assert win.links_business.shutdown_called == 1
