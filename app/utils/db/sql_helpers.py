"""SQL query building helpers.

This module provides utilities for constructing SQL queries safely and efficiently.
"""


def build_placeholders(count: int, pattern: str = "?") -> str:
    """Generate SQL placeholders for parameterized queries.

    Args:
        count: Number of placeholders to generate
        pattern: Placeholder pattern (default: "?" for SQLite)

    Returns:
        Comma-separated placeholders string

    Examples:
        >>> build_placeholders(3)
        '?,?,?'
        
        >>> build_placeholders(2, "(?, ?)")
        '(?, ?),(?, ?)'
        
        >>> build_placeholders(0)
        ''

    Notes:
        - Returns empty string for count <= 0
        - Pattern can be any string (e.g., "?" or "(?, ?)" for tuples)
        - Used to comply with SQLite parameter limit (999)
    """
    if count <= 0:
        return ""
    return ",".join([pattern] * count)


def build_in_clause_placeholders(count: int) -> str:
    """Generate placeholders for SQL IN clause.

    Convenience wrapper for build_placeholders with default pattern.

    Args:
        count: Number of values in IN clause

    Returns:
        Comma-separated "?" placeholders

    Example:
        >>> build_in_clause_placeholders(3)
        '?,?,?'
        >>> f"SELECT * FROM table WHERE id IN ({build_in_clause_placeholders(3)})"
        'SELECT * FROM table WHERE id IN (?,?,?)'
    """
    return build_placeholders(count, "?")
