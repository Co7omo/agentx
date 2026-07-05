"""Compatibility helpers."""

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

__all__ = ["tomllib"]
