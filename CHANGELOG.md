# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Changed
- Simplified structure operations architecture by removing validation and operation strategies.
  - Removed `ValidationStrategy`, `DefaultValidationStrategy`, `StructureOperationStrategy`, `DefaultOperationStrategy`.
  - Inlined validation into `BaseOperations._validate_data()` and upsert execution into `BaseOperations._upsert_and_emit()`.
  - Public API of `BaseOperations` remains: `create_item`, `update_item`, `delete_item` and signal emission via `StructureSignalEmitter`.
- UI Top Panels: enforced strict interface contract for favorites widget
  - `TopPanelsController` now requires `FavoritesPanelWithClear` (must implement `clear_favorites`).
  - Removed fallback behavior in `clear_favorites`.
- TreeManagement optimizations and robustness
  - Uses cached `self.model` instead of repeated `tree.model()` calls.
  - Logs and early-exits when model is missing.
- Window setup hardening
  - `_connect_top_panels_signals` now raises `SetupError` on missing required widgets/controllers instead of silent hasattr/try-except.
- Tests cleanup
  - Added shared stubs/fixtures in `tests/conftest.py` (signals, minimal favorites/recents widgets, links business).
  - Updated tests to use shared fixtures; fixed missing imports; added tests for model cache and setup errors.

### Migration notes
- Derived classes (`CategoryOperations`, `SectionOperations`, `SphereOperations`, `PositioningOperations`) typically require no changes if using `BaseOperations` public methods.
- Tests referencing `DefaultValidationStrategy` should be updated to remove the import and, if needed, mimic validation equivalent to `BaseOperations._validate_data()`.

### Notes
- Signals and logging are unchanged.
- Upsert errors now surface as `StructureOperationError` with operation type "upsert" and item type name.
