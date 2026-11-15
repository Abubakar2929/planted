# OWNER: A — see PLAN.md §2
"""Planted: measure and fix poisoned search results in AI search agents.

    from planted import guard, apply_defense, MockEngine, make_episode_id

``guard`` is imported eagerly: ``planted.guard`` is also a subpackage, and importing a subpackage
binds the module over a lazily resolved name. The other exports are resolved lazily (PEP 562), so
``import planted`` stays cheap (the engine pulls in litellm). A stub raises NotImplementedError only
when called.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__version__ = "0.1.0"

try:
    from planted.guard import guard
except ImportError as _e:  # pragma: no cover - keep `import planted` working
    _guard_error = _e

    def guard(query, results, lang="en"):
        raise NotImplementedError(f"planted.guard could not be imported: {_guard_error}")

_EXPORTS = {
    "apply_defense": "planted.baselines",
    "MockEngine": "planted.engine",
    "make_episode_id": "planted.engine",
}
__all__ = ["__version__", "guard", *_EXPORTS]


def __getattr__(name: str) -> Any:
    if name in _EXPORTS:
        value = getattr(import_module(_EXPORTS[name]), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module 'planted' has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORTS))
