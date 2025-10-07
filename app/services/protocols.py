"""
Protocols for service layer.

✅ NEW FILE: Strict typing of dependencies through Protocol.
"""

from typing import Any, Dict, List, Optional, Protocol


class DatabaseProtocol(Protocol):
    """Protocol for Database with necessary attributes for services.
    
    ✅ FIX: Replaces Any with specific Protocol for type safety.
    """
    
    # Repositories/models
    spheres: Any
    sections: Any
    categories: Any
    links: Any
    
    # Transaction methods
    def transaction(self) -> Any:
        """Transaction context manager."""
        ...
    
    def commit(self) -> None:
        """Commits transaction."""
        ...
    
    def rollback(self) -> None:
        """Rolls back transaction."""
        ...
    
    # Import/export methods
    def get_full_structure(self) -> List[Dict]:
        """Returns full data structure."""
        ...
    
    def export_full_structure(self) -> Dict[str, List]:
        """Exports structure."""
        ...
    
    def export_full_structure_async(
        self, on_finished=None, on_error=None, on_progress=None
    ) -> None:
        """Asynchronous structure export."""
        ...
    
    def import_full_structure(self, data: List[Dict]) -> None:
        """Imports structure."""
        ...
    
    def import_full_structure_async(
        self, data: List[Dict], on_finished=None, on_error=None, on_progress=None
    ) -> None:
        """Asynchronous structure import."""
        ...
    
    def export_section_tree(self, section_id: int) -> Dict[str, Any]:
        """Exports section."""
        ...
    
    def import_section_tree(self, tree: Dict[str, Any]) -> None:
        """Imports section."""
        ...
    
    def export_category_tree(self, category_id: int) -> Dict[str, Any]:
        """Exports category."""
        ...
    
    def import_category_tree(self, tree: Dict[str, Any]) -> None:
        """Imports category."""
        ...
    
    def import_category_trees_bulk(self, trees: List[Dict[str, Any]]) -> None:
        """Imports multiple categories."""
        ...


__all__ = ["DatabaseProtocol"]
