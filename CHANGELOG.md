# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Changed
- Simplified structure operations architecture by removing validation and operation strategies.
  - Removed `ValidationStrategy`, `DefaultValidationStrategy`, `StructureOperationStrategy`, `DefaultOperationStrategy`.
  - Inlined validation into `BaseOperations._validate_data()` and upsert execution into `BaseOperations._upsert_and_emit()`.
  - Public API of `BaseOperations` remains: `create_item`, `update_item`, `delete_item` and signal emission via `StructureSignalEmitter`.

### Migration notes
- Derived classes (`CategoryOperations`, `SectionOperations`, `SphereOperations`, `PositioningOperations`) typically require no changes if using `BaseOperations` public methods.
- Tests referencing `DefaultValidationStrategy` should be updated to remove the import and, if needed, mimic validation equivalent to `BaseOperations._validate_data()`.

### Notes
- Signals and logging are unchanged.
- Upsert errors now surface as `StructureOperationError` with operation type "upsert" and item type name.
