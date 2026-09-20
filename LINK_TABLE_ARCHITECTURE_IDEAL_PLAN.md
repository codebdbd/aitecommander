# Link Table Architecture Ideal Plan

## Goal

Bring the links table to an architecture where adding, changing, or testing a column is centralized, predictable, localized, and covered by regression checks.

## 1. Fix the table contract

- Introduce a single `LinkTableColumn` enum/dataclass instead of scattered numeric indexes.
- Describe each column in one place:
  - id;
  - header source text;
  - header tooltip source text;
  - role builder;
  - sort key;
  - editability;
  - minimum width;
  - resize mode.
- Remove direct checks such as `if column == 3` from model, view, and controllers.

## 2. Separate model and view responsibilities

- Keep `LinksTableModel` responsible for data, roles, and editable values.
- Keep `LinksTableView` / `BaseTable` responsible for visual behavior: widths, delegates, and header interactions.
- Keep column meaning in one registry instead of duplicating it across model, view, and controllers.

## 3. Extract sorting policy

- Create a `LinkSortPolicy` or `LinkTableSortController`.
- Explicitly define default sort as `order asc`.
- Explicitly define user sort from header clicks.
- Separate category reload, search mode, manual reorder, and restored sort state behavior.

## 4. Strengthen custom order handling

- Extract reorder logic into a pure function, for example `move_link_position(links, link_id, target_position)`.
- Cover the algorithm with tests:
  - first item to middle;
  - middle item to first;
  - last item to first;
  - out-of-range target;
  - duplicate, empty, or missing positions;
  - 100+ items.
- Let the model call the algorithm and emit the updated order, not own the algorithm details.

## 5. Create a full link type descriptor

- Extend the current shared type-label helper into a `LinkTypeDescriptor`.
- Store per type:
  - code: `web`, `file`, `folder`, `program`, `script`;
  - source label;
  - icon or fallback icon;
  - tooltip address field;
  - validation hints.
- Make the dialog, table, import, export, and context menu read link types from the same descriptor.

## 6. Move legacy config compatibility out of the hot path

- Replace runtime fallback logic in `get_links_table_columns()` with one-time config normalization/migration on load.
- Ensure table code always receives the current column schema.

## 7. Stabilize column width behavior

- Introduce a declarative width policy:
  - `group_launch`: fixed;
  - `name`: interactive/stretch candidate;
  - `order`: content/header minimum;
  - `launch`: date minimum;
  - `notes`: stretch;
  - `type`: content/header minimum.
- Add non-GUI tests for width policy where possible.
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

## 10. Add table regression tests

- Header labels are localized.
- Header tooltips are localized.
- Type labels match the add/edit dialog.
- Type tooltip shows URL/path/resource address.
- Launch tooltip shows full date and time.
- Double-click/edit order does not launch a resource.
- Category switch resets default sort to order.
- Search mode does not break sorting or order behavior.

## 11. Simplify controllers

- Controllers should not know that `notes` is column `4` or `order` is column `2`.
- Replace direct index checks with registry helpers such as:
  - `column_registry.is_notes(column)`;
  - `column_registry.is_order(column)`;
  - `column_registry.is_launch(column)`.
- Keep interaction code resilient to future column changes.

## 12. Final acceptance criteria

- No column magic numbers outside the column registry.
- The table is built from declarative column descriptors.
- Full `pytest` is green.
- `i18n update`, `i18n compile`, and `i18n check` are green.
- Visual smoke tests cover header widths in long localized languages.
- Adding a new column requires changing one descriptor module and its tests, not a cascade of edits across model, view, and controllers.
