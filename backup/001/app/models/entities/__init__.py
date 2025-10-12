"""Domain модели для работы с сущностями БД."""
from .sphere_model import SphereModel
from .section_model import SectionModel
from .category_model import CategoryModel
from .link_model import LinkModel
from .structure_model import StructureModel

__all__ = [
    "SphereModel",
    "SectionModel", 
    "CategoryModel",
    "LinkModel",
    "StructureModel",
]
