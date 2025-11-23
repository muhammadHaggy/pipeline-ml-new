import os
from typing import Iterable, List


def _unique(values: Iterable[str]) -> List[str]:
    """Return a list of unique, truthy values while preserving order."""
    seen = set()
    ordered = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _ensure_directory(path: str, label: str) -> str:
    """Create `path` if it does not exist and return the absolute path."""
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"Unable to create {label} directory at '{path}': {exc}") from exc
    return os.path.abspath(path)


_requested_notebooks_root = os.getenv("NOTEBOOKS_ROOT")
_requested_logs_root = os.getenv("LOGS_ROOT", "/logs")

_NOTEBOOK_CANDIDATES = _unique(
    [
        _requested_notebooks_root,
        "/notebooks",
        "/opt/airflow/notebooks",
    ]
)

if not _NOTEBOOK_CANDIDATES:
    _NOTEBOOK_CANDIDATES = ["/notebooks"]

LOGS_ROOT = _ensure_directory(_requested_logs_root, "log")


def get_notebook_path(filename: str) -> str:
    """
    Return the absolute path to `filename`, checking all known notebook roots.
    Raises FileNotFoundError if the notebook cannot be located.
    """
    if not filename:
        raise ValueError("Notebook filename must be provided")

    if os.path.isabs(filename):
        if os.path.exists(filename):
            return filename
        raise FileNotFoundError(
            f"Notebook '{filename}' not found. This is an absolute path, so no fallbacks were checked."
        )

    checked = []
    for root in _NOTEBOOK_CANDIDATES:
        candidate = os.path.join(root, filename)
        checked.append(candidate)
        if os.path.exists(candidate):
            return candidate

    raise FileNotFoundError(
        f"Notebook '{filename}' not found in any configured location. Checked: {', '.join(checked)}"
    )


def get_log_path(filename: str) -> str:
    """
    Return the canonical log path for `filename`. Ensures parent directories exist.
    """
    if not filename:
        raise ValueError("Log filename must be provided")

    if os.path.isabs(filename):
        parent_dir = os.path.dirname(filename)
        if parent_dir:
            _ensure_directory(parent_dir, "log")
        return filename

    parent_dir = LOGS_ROOT
    _ensure_directory(parent_dir, "log")
    return os.path.join(parent_dir, filename)


def get_logs_root() -> str:
    """
    Expose the resolved logs root; primarily useful for dynamic task mapping.
    """
    return LOGS_ROOT


