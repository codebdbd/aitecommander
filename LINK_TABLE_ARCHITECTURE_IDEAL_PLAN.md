# Link Table Architecture Ideal Plan

## Goal

Bring the links table to an architecture where adding, changing, or testing a column is centralized, predictable, localized, and covered by regression checks.

## 1. Fix the table contract

- [x] Introduce a single `LinkTableColumn` enum/dataclass instead of scattered numeric indexes.
- [x] Describe each column in one place:
  - id;
  - header source text;
  - header tooltip source text;
  - sort key;
  - editability;
  - minimum width;
  - width policy metadata.
- [x] Remove direct checks such as `if column == 3` from model, view, controllers, and the focused table tests.
- [x] Add role-builder descriptors after model responsibilities are split further.
- [x] Move resize-mode policy fully into descriptors after the Qt view layer is stabilized.

## 2. Separate model and view responsibilities

- [x] Keep `LinksTableModel` responsible for data, roles, and editable values.
- [x] Keep `LinksTableView` / `BaseTable` responsible for visual behavior: widths, delegates, and header interactions.
- [x] Keep column meaning in one registry instead of duplicating it across model, view, and controllers.

## 3. Extract sorting policy

- [x] Extract table sort keys into pure helpers.
- [x] Explicitly define default sort as `order asc`.
- [x] Create a dedicated `LinkSortPolicy` or `LinkTableSortController` for view-level sorting state.
- [x] Explicitly define user sort from header clicks in that controller.
- [x] Separate category reload, search mode, manual reorder, and restored sort state behavior in that controller.

## 4. Strengthen custom order handling

- [x] Extract direct order-edit logic into a pure function, `move_link_position(links, link_id, target_position)`.
- [x] Cover the direct order-edit algorithm with tests:
  - first item to middle;
  - middle item to first;
  - last item to first;
  - out-of-range target;
  - duplicate, empty, or missing positions;
  - 100+ items.
- [x] Let the model call the direct order-edit algorithm and emit the updated order, not own that algorithm detail.
- [x] Extract drag-and-drop row move variants into pure helpers as a separate step.

## 5. Create a full link type descriptor

- [x] Extend the current shared type-label helper into a `LinkTypeDescriptor`.
- [x] Store per type:
  - code: `web`, `file`, `folder`, `program`, `script`, `note`;
  - source label;
  - icon or fallback icon;
  - tooltip address field;
  - validation hints.
- [x] Make import, export, and context menu read link types from the same descriptor.
- [x] Make the dialog and table read type labels/tooltips from the same descriptor.

## 6. Move legacy config compatibility out of the hot path

- [x] Replace runtime fallback logic in `get_links_table_columns()` with one-time config normalization/migration on load.
- [x] Ensure table code always receives the current column schema.

## 7. Stabilize column width behavior

- [x] Introduce a declarative width policy:
  - `group_launch`: fixed;
  - `name`: interactive/stretch candidate;
  - `order`: content/header minimum;
  - `launch`: date minimum;
  - `notes`: stretch;
  - `type`: content/header minimum.
- [x] Add non-GUI tests for width policy where possible.
- Add GUI or screenshot smoke tests for Russian, Ukrainian, and German headers to catch clipping.

## 8. Make i18n reliable

- Investigate why `pylupdate6` fails during `i18n update`.
- Reduce fragile dynamic translation patterns where possible.
- Add CI checks for:
  - `i18n check`;
  - no unfinished or vanished strings;
  - successful `.qm` compilation.

## 9. Fix Qt global-state tests

- Fix `LanguageService has been deleted`.
- Review lifecycle for `QApplication`, translators, and singleton services.
- Make GUI tests independent from execution order.
- Full `pytest` should pass without Qt access violations.
- [x] Stabilize `ExplorerHeaderView` proxy style lifetime by avoiding a stored base-style pointer that caused process aborts at Qt cleanup.
- [x] Stabilize linked table GUI regression tests so they pass together in one process without Qt access violations.

## 10. Define performance and update guarantees

- [x] Keep table loading fast for large categories by switching very large updates to one full model refresh.
- [x] Avoid full table rebuilds when a targeted row update is enough.
- [x] Preserve row data shape during targeted updates so partial payloads do not corrupt the row cache.
- Batch expensive UI operations:
  - [x] layout recalculation via suspended table updates during populate;
  - [x] icon decoration refresh via one targeted `dataChanged` emission;
  - [x] model reset for very large or mass-change populates;
  - [x] sort invalidation via one restore pass after incremental populate.
- Ensure all supported actions remain responsive and timely:
  - [x] category switch;
  - [x] search;
  - [x] add link;
  - [x] edit link;
  - [x] delete link;
  - [x] launch link;
  - [x] group launch checkbox;
  - [x] group launch checkbox persists as a reusable setting, including legacy field normalization and controller dispatch to database update;
  - [x] drag-and-drop reorder;
  - [x] direct order edit;
  - [x] icon enrichment update;
  - [x] language refresh;
  - [x] theme refresh.
- Add performance smoke tests or benchmarks for:
  - [x] initial populate / incremental update path;
  - [x] category switch;
  - [x] row update;
  - [x] reorder;
  - [x] sort by each sortable column.

## 11. Normalize visual style tokens

- [x] Define explicit table style tokens instead of ad hoc per-column styling.
- [x] Use one font size for all body cells.
- [x] Keep header font sizing separate from body font sizing.
- [x] Remove runtime use of mixed body font sizes for `Name`, `Order`, `Launch`, `Notes`, and `Type`.
- [x] Define exactly three text color roles for this table:
  - `table.headerText`: header text, header glyphs, column 0 header icon/glyph, and sort arrow;
  - `table.primaryCellText`: `Name` and `Notes` cell text;
  - `table.secondaryCellText`: `Order`, `Launch`, and `Type` cell text.
- [x] Ensure checkbox indicators and non-text decorations do not accidentally inherit unrelated text colors.
- [x] Keep hover and selection handling separate from body text roles.
- [x] Add style regression checks so theme changes cannot reintroduce inconsistent fonts or colors.
- [x] Recolor the column 0 header icon itself through the header text role instead of relying on the themed icon asset.
- [x] Remove legacy font config keys after config normalization/migration exists.

## 12. Add table regression tests

- [x] Header labels are localized.
- [x] Header tooltips are localized.
- [x] Type labels match the add/edit dialog.
- [x] Type tooltip shows URL/path/resource address.
- [x] Launch tooltip shows full date and time.
- [x] Double-click/edit order does not launch a resource.
- [x] Category switch resets default sort to order.
- [x] Search mode does not break sorting or order behavior.
- [x] Group launch checkbox reads persisted state, survives partial row updates, and dispatches persistent database updates.
- [x] Body cell font size is identical across all table columns.
- [x] Header color uses `table.headerText`.
- [x] `Name` and `Notes` cells use `table.primaryCellText`.
- [x] `Order`, `Launch`, and `Type` cells use `table.secondaryCellText`.
- [x] Large-category populate and targeted row updates stay within accepted timing thresholds.

## 13. Simplify controllers

- [x] Controllers should not know that `notes` is column `4` or `order` is column `2`.
- [x] Replace direct index checks with registry helpers such as:
  - `column_registry.is_notes(column)`;
  - `column_registry.is_order(column)`;
  - `column_registry.is_launch(column)`.
- [x] Keep interaction code resilient to future column changes.

## 14. Final acceptance criteria

- No column magic numbers outside the column registry.
- The table is built from declarative column descriptors.
- The table loads quickly for large categories and updates rows without unnecessary full rebuilds.
- All supported table actions remain responsive and covered by tests or smoke checks.
- Body cell font size is consistent across all columns.
- Table text colors come from the three explicit roles:
  - `table.headerText`;
  - `table.primaryCellText`;
  - `table.secondaryCellText`.
- Full `pytest` is green.
- `i18n update`, `i18n compile`, and `i18n check` are green.
- Visual smoke tests cover header widths in long localized languages.
- Visual/style smoke tests cover cell font and color consistency.
- Adding a new column requires changing one descriptor module and its tests, not a cascade of edits across model, view, and controllers.
