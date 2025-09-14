# UI models package (Qt models)
# Expose commonly used UI models here for convenient imports.

try:
    from .categories_list_model import CategoriesListModel  # noqa: F401
except Exception:
    # Optional: categories list model may be absent in some minimal builds
    pass

try:
    from .structure_tree_model import StructureTreeModel  # noqa: F401
except Exception:
    # StructureTreeModel exists in this package in the main app, but keep safe import
    pass
