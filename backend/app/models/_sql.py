from collections.abc import Iterable


def sql_in(column: str, values: Iterable[str]) -> str:
    """Build a CHECK-constraint expression: column IN ('a', 'b', ...)."""
    quoted = ", ".join("'" + v.replace("'", "''") + "'" for v in values)
    return f"{column} IN ({quoted})"
