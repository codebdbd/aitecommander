from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from app.controllers.ui.structure.tree_snapshot_service import TreeSnapshotService
from app.utils.ui.icon.loading_service import IconLoadingService
from app.utils.ui.icon import validation as icon_validation
from app.views.main_components.ui.topbar.toolbar_adapters import (
    _resolve_existing_icon_path_fast,
)
from app.views.windows.dialogs.link_dialog.icon_utils import (
    IconErrorKind,
    get_cached_icon as get_dialog_cached_icon,
    get_cached_icon_with_fallback,
    make_icon_result,
)
from app.utils.ui.icon.loading_policy import (
    get_tiles_icon_loading_policy,
    get_tree_icon_loading_policy,
)
from app.views.models.structure_tree_model import IconLoader, StructureTreeModel, TreeNode


class TestTreeSnapshotIconPathMemo(unittest.TestCase):
    def test_preprocess_resolves_repeated_icon_path_once_per_snapshot(self) -> None:
        service = TreeSnapshotService(manager=None, model=None)
        snapshot = [
            {
                "id": 1,
                "name": "Section",
                "icon_path": "section.png",
                "categories": [
                    {"id": 10, "name": "A", "icon_path": "category.png"},
                    {"id": 11, "name": "B", "icon_path": "category.png"},
                    {"id": 12, "name": "C", "icon_path": "category.png"},
                ],
            }
        ]
        resolved_inputs: list[str] = []

        def _fake_resolve(icon_path: str) -> str:
            resolved_inputs.append(icon_path)
            return f"/resolved/{icon_path}"

        with patch(
            "app.controllers.ui.structure.tree_snapshot_service.resolve_icon_path",
            side_effect=_fake_resolve,
        ):
            processed = service._preprocess_snapshot(snapshot)

        self.assertEqual(["section.png", "category.png"], resolved_inputs)
        self.assertEqual("/resolved/section.png", processed[0]["icon_path"])
        self.assertEqual(
            ["/resolved/category.png"] * 3,
            [item["icon_path"] for item in processed[0]["categories"]],
        )


class TestIconValidationCache(unittest.TestCase):
    def setUp(self) -> None:
        icon_validation._valid_icon_file_cache.clear()

    def tearDown(self) -> None:
        icon_validation._valid_icon_file_cache.clear()

    def test_is_valid_icon_file_caches_successful_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            icon_path = Path(tmp_dir) / "sample.png"
            Image.new("RGBA", (1, 1), (255, 0, 0, 255)).save(icon_path)

            real_open = Image.open
            open_calls = 0

            def _counting_open(*args, **kwargs):
                nonlocal open_calls
                open_calls += 1
                return real_open(*args, **kwargs)

            with patch("app.utils.ui.icon.validation.Image.open", side_effect=_counting_open):
                self.assertTrue(icon_validation.is_valid_icon_file(icon_path))
            self.assertTrue(icon_validation.is_valid_icon_file(icon_path))

            self.assertEqual(1, open_calls)


class TestIconLoadingService(unittest.TestCase):
    def test_resolve_path_memoizes_by_input_and_kind(self) -> None:
        service = IconLoadingService()
        with (
            patch(
                "app.utils.ui.icon.loading_service.resolve_icon_path",
                side_effect=lambda value: f"/generic/{value}",
            ) as generic_mock,
            patch(
                "app.utils.ui.icon.loading_service.resolve_category_icon_path",
                side_effect=lambda value: f"/category/{value}",
            ) as category_mock,
        ):
            self.assertEqual("/generic/a.png", service.resolve_path("a.png"))
            self.assertEqual("/generic/a.png", service.resolve_path("a.png"))
            self.assertEqual(
                "/category/a.png",
                service.resolve_path("a.png", category=True),
            )
            self.assertEqual(
                "/category/a.png",
                service.resolve_path("a.png", category=True),
            )

        self.assertEqual(1, generic_mock.call_count)
        self.assertEqual(1, category_mock.call_count)

    def test_get_path_icon_uses_resolved_path_cache(self) -> None:
        service = IconLoadingService()
        fake_icon = QIcon()
        with (
            patch(
                "app.utils.ui.icon.loading_service.resolve_category_icon_path",
                side_effect=lambda value: f"/resolved/{value}",
            ) as resolver_mock,
            patch(
                "app.utils.ui.icon.loading_service.get_cached_category_icon",
                return_value=fake_icon,
            ) as icon_mock,
        ):
            self.assertIs(fake_icon, service.get_path_icon("cat.png", category=True))
            self.assertIs(fake_icon, service.get_path_icon("cat.png", category=True))

        self.assertEqual(1, resolver_mock.call_count)
        self.assertEqual(2, icon_mock.call_count)

    def test_resolve_existing_path_returns_only_real_existing_icon(self) -> None:
        service = IconLoadingService()
        with tempfile.TemporaryDirectory() as tmp_dir:
            user_dir = Path(tmp_dir) / "user"
            ui_dir = Path(tmp_dir) / "ui"
            user_dir.mkdir()
            ui_dir.mkdir()
            icon_file = ui_dir / "ok.png"
            icon_file.write_bytes(b"png")

            with (
                patch(
                    "app.utils.ui.icon.loading_service.icon_path_service.get_user_icons_dir",
                    return_value=user_dir,
                ),
                patch(
                    "app.utils.ui.icon.loading_service.icon_path_service.get_ui_icons_dir",
                    return_value=ui_dir,
                ),
                patch(
                    "app.utils.ui.icon.loading_service.is_valid_icon_file",
                    side_effect=lambda path: str(path) == str(icon_file),
                ),
            ):
                self.assertEqual(
                    str(icon_file),
                    service.resolve_existing_path("ok.png"),
                )
                self.assertEqual("", service.resolve_existing_path("missing.png"))

    def test_resolve_existing_path_memoizes_hits_and_misses(self) -> None:
        service = IconLoadingService()
        with tempfile.TemporaryDirectory() as tmp_dir:
            user_dir = Path(tmp_dir) / "user"
            ui_dir = Path(tmp_dir) / "ui"
            user_dir.mkdir()
            ui_dir.mkdir()
            icon_file = ui_dir / "ok.png"
            icon_file.write_bytes(b"png")

            with (
                patch(
                    "app.utils.ui.icon.loading_service.icon_path_service.get_user_icons_dir",
                    return_value=user_dir,
                ),
                patch(
                    "app.utils.ui.icon.loading_service.icon_path_service.get_ui_icons_dir",
                    return_value=ui_dir,
                ),
                patch(
                    "app.utils.ui.icon.loading_service.is_valid_icon_file",
                    side_effect=lambda path: str(path) == str(icon_file),
                ) as valid_mock,
            ):
                self.assertEqual(str(icon_file), service.resolve_existing_path("ok.png"))
                self.assertEqual(str(icon_file), service.resolve_existing_path("ok.png"))
                self.assertEqual("", service.resolve_existing_path("missing.png"))
                self.assertEqual("", service.resolve_existing_path("missing.png"))

        self.assertEqual(1, valid_mock.call_count)


class TestStructureTreeModelIconDedup(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_start_icon_loading_deduplicates_same_path(self) -> None:
        model = StructureTreeModel()
        node_a = TreeNode(type="category", id=1, name="A")
        node_b = TreeNode(type="category", id=2, name="B")

        started = []

        with patch.object(model._thread_pool, "start", side_effect=lambda loader: started.append(loader)):
            model._start_icon_loading(node_a, "shared.png")
            model._start_icon_loading(node_b, "shared.png")

        self.assertEqual(1, len(started))
        self.assertEqual([node_a, node_b], model._icon_waiters_by_path["shared.png"])
        self.assertIn("shared.png", model._active_icon_tasks)

        model._on_icon_loaded("shared.png", QIcon())

        self.assertNotIn("shared.png", model._icon_waiters_by_path)
        self.assertNotIn("shared.png", model._active_icon_tasks)


class TestIconLoader(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_run_resolves_path_before_gui_materialization(self) -> None:
        loaded = []
        fake_icon = QIcon()

        loader = IconLoader("raw.png", on_loaded=lambda path, icon: loaded.append((path, icon)))

        with (
            patch(
                "app.views.models.structure_tree_model.icon_loading_service.resolve_path",
                return_value="/resolved/raw.png",
            ) as resolve_mock,
            patch(
                "app.views.models.structure_tree_model.icon_loading_service.get_path_icon",
                return_value=fake_icon,
            ) as icon_mock,
        ):
            loader.run()
            self._app.processEvents()

        resolve_mock.assert_called_once_with("raw.png")
        icon_mock.assert_called_once_with("/resolved/raw.png")
        self.assertEqual([("raw.png", fake_icon)], loaded)


class TestTopBarIconResolution(unittest.TestCase):
    def test_fast_resolver_delegates_to_loading_service(self) -> None:
        with patch(
            "app.views.main_components.ui.topbar.toolbar_adapters.icon_loading_service.resolve_existing_path",
            return_value="/resolved/icon.png",
        ) as resolver_mock:
            self.assertEqual("/resolved/icon.png", _resolve_existing_icon_path_fast("icon.png"))

        resolver_mock.assert_called_once_with("icon.png")


class TestLinkDialogIconUtils(unittest.TestCase):
    def test_make_icon_result_uses_loading_service(self) -> None:
        fake_icon = unittest.mock.Mock(spec=QIcon)
        fake_icon.isNull.return_value = False
        with (
            patch(
                "app.views.windows.dialogs.link_dialog.icon_utils.icon_loading_service.resolve_existing_path",
                return_value="/resolved/dialog.png",
            ) as resolve_mock,
            patch(
                "app.views.windows.dialogs.link_dialog.icon_utils.icon_loading_service.get_path_icon",
                return_value=fake_icon,
            ) as icon_mock,
        ):
            result = make_icon_result("dialog.png")

        self.assertTrue(result.success)
        self.assertEqual(Path("/resolved/dialog.png"), result.resolved_path)
        self.assertIs(fake_icon, result.icon)
        resolve_mock.assert_called_once_with("dialog.png")
        icon_mock.assert_called_once_with("/resolved/dialog.png")

    def test_make_icon_result_returns_not_found_for_missing_icon(self) -> None:
        with patch(
            "app.views.windows.dialogs.link_dialog.icon_utils.icon_loading_service.resolve_existing_path",
            return_value="",
        ):
            result = make_icon_result("missing.png")

        self.assertFalse(result.success)
        self.assertEqual(IconErrorKind.NOT_FOUND, result.error_kind)

    def test_get_cached_icon_returns_none_for_empty_icon(self) -> None:
        with patch(
            "app.views.windows.dialogs.link_dialog.icon_utils.make_icon",
            return_value=QIcon(),
        ):
            self.assertIsNone(get_dialog_cached_icon("x.png"))

    def test_get_cached_icon_with_fallback_uses_section_default(self) -> None:
        fake_icon = unittest.mock.Mock(spec=QIcon)
        fake_icon.isNull.return_value = False
        with (
            patch(
                "app.views.windows.dialogs.link_dialog.icon_utils.resolve_section_icon_path",
                return_value="/resolved/section.png",
            ) as resolve_mock,
            patch(
                "app.views.windows.dialogs.link_dialog.icon_utils.icon_loading_service.get_path_icon",
                return_value=fake_icon,
            ) as icon_mock,
        ):
            icon = get_cached_icon_with_fallback("deleted-custom.png", "section")

        self.assertIs(fake_icon, icon)
        resolve_mock.assert_called_once_with("deleted-custom.png")
        icon_mock.assert_called_once_with("/resolved/section.png")


class TestIconLoadingPolicy(unittest.TestCase):
    def test_tree_policy_fast_switch_uses_sections_first_and_deferred_categories(self) -> None:
        with (
            patch(
                "app.utils.ui.icon.loading_policy.get_tree_sections_first_render",
                return_value=True,
            ),
            patch(
                "app.utils.ui.icon.loading_policy.get_tree_section_icon_prewarm_limit",
                return_value=5,
            ),
        ):
            policy = get_tree_icon_loading_policy(snapshot_mode="fast_switch")

        self.assertTrue(policy.sections_first_render)
        self.assertEqual(5, policy.section_sync_limit)
        self.assertTrue(policy.defer_category_loads)

    def test_tree_policy_full_restore_disables_sections_first_and_deferred_categories(self) -> None:
        with patch(
            "app.utils.ui.icon.loading_policy.get_tree_section_icon_prewarm_limit",
            return_value=7,
        ):
            policy = get_tree_icon_loading_policy(snapshot_mode="full_restore")

        self.assertFalse(policy.sections_first_render)
        self.assertEqual(7, policy.section_sync_limit)
        self.assertFalse(policy.defer_category_loads)

    def test_tiles_policy_reads_runtime_values(self) -> None:
        fake_ui = unittest.mock.Mock()
        fake_ui.get.side_effect = lambda key, default=None: {
            "ui.tiles_lazy_icons": False,
            "ui.tiles_icon_prefetch_count": 30,
            "ui.tiles_icon_sync_prefetch_cap": 12,
            "ui.tiles_icon_batch_size": 48,
        }.get(key, default)
        fake_app_config = unittest.mock.Mock()
        fake_app_config.ui = fake_ui

        with patch(
            "app.utils.ui.icon.loading_policy.get_runtime_app_config",
            return_value=fake_app_config,
        ):
            policy = get_tiles_icon_loading_policy()

        self.assertFalse(policy.lazy)
        self.assertEqual(12, policy.sync_prefetch_count)
        self.assertEqual(48, policy.batch_size)


if __name__ == "__main__":
    unittest.main()
