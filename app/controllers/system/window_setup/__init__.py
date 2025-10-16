"""
Main window controller setup modules.
"""
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _resolve_structure_loader(structure_business: Any) -> Callable[[], None]:
    """Create structure loader function from structure_business.
    
    Args:
        structure_business: Structure business logic object
        
    Returns:
        Parameterless function to reload structure
        
    Raises:
        ValueError: If no suitable loading method exists
    """
    # Priority: async > sync
    if hasattr(structure_business, 'load_structure_async') and callable(
        structure_business.load_structure_async
    ):
        logger.debug("Using load_structure_async for structure reload")
        return structure_business.load_structure_async
    
    if hasattr(structure_business, 'load_structure') and callable(
        structure_business.load_structure
    ):
        logger.debug("Using load_structure (sync) for structure reload")
        return structure_business.load_structure
    
    raise ValueError(
        "StructureBusinessLogic must provide load_structure_async or load_structure method"
    )
