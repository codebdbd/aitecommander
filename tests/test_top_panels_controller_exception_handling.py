import unittest
from unittest.mock import Mock, patch

from PyQt6.QtWidgets import QApplication

from app.controllers.ui.top_panels_controller import TopPanelsController


class DummyFavWidget:
    def __init__(self):
        self.items = None

    def set_favorites(self, items):
        self.items = items

    # Новый контракт контроллера — set_data(items)
    def set_data(self, items):
        self.set_favorites(items)

    def clear_favorites(self):
        self.items = []


class DummyRecentsWidget:
    def __init__(self):
        self.items = None

    def set_recent_links(self, items):
        self.items = items

    # Новый контракт контроллера — set_data(items)
    def set_data(self, items):
        self.set_recent_links(items)


class DummyRecentsWidgetWithLimit(DummyRecentsWidget):
    def __init__(self, limit):
        super().__init__()
        self._limit = limit

    def get_limit(self):
        return self._limit


class TestTopPanelsControllerExceptionHandling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def test_refresh_favorites_business_error_logged_and_not_raised(self):
        fav = DummyFavWidget()
        rec = DummyRecentsWidget()
        links_business = Mock()
        links_business.get_favorite_links.side_effect = RuntimeError("boom")

        ctrl = TopPanelsController(
            Mock(),
            fav_widget=fav,
            recent_links_widget=rec,
            links_business=links_business,
        )

        with patch(
            "app.controllers.ui.top_panels_controller.logger.exception"
        ) as mock_exc:
            ctrl.refresh_favorites()
            mock_exc.assert_called_once()

    def test_refresh_recent_business_error_logged_and_not_raised(self):
        fav = DummyFavWidget()
        rec = DummyRecentsWidget()
        links_business = Mock()
        links_business.get_recent_links.side_effect = RuntimeError("boom")

        ctrl = TopPanelsController(
            Mock(),
            fav_widget=fav,
            recent_links_widget=rec,
            links_business=links_business,
        )

        with patch(
            "app.controllers.ui.top_panels_controller.logger.exception"
        ) as mock_exc:
            ctrl.refresh_recent()
            mock_exc.assert_called_once()

    def test_refresh_recent_widget_update_error_logged_and_not_raised(self):
        fav = DummyFavWidget()
        rec = DummyRecentsWidget()

        def failing_set(items):
            raise RuntimeError("widget fail")

        rec.set_recent_links = failing_set

        links_business = Mock()
        links_business.get_recent_links.return_value = [1, 2, 3]

        ctrl = TopPanelsController(
            Mock(),
            fav_widget=fav,
            recent_links_widget=rec,
            links_business=links_business,
        )

        with patch(
            "app.controllers.ui.top_panels_controller.logger.exception"
        ) as mock_exc:
            ctrl.refresh_recent()
            mock_exc.assert_called_once()

    def test_request_recents_refresh_unexpected_error_is_raised(self):
        fav = DummyFavWidget()
        rec = DummyRecentsWidget()
        ctrl = TopPanelsController(
            Mock(), fav_widget=fav, recent_links_widget=rec, links_business=Mock()
        )

        with patch.object(
            ctrl._recent_refresh_timer, "start", side_effect=RuntimeError("timer fail")
        ):
            with patch(
                "app.controllers.ui.top_panels_controller.logger.exception"
            ) as mock_exc:
                with self.assertRaises(RuntimeError):
                    ctrl.request_recents_refresh(10)
                mock_exc.assert_called_once()


if __name__ == "__main__":
    unittest.main()
