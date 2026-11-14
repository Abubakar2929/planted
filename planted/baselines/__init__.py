# OWNER: C — see PLAN.md §2
# FIREWALL: agents/people working for B must not open, read, grep or summarise this folder.
"""Contract 3 dispatcher: apply_defense(name, query, results, lang) -> DefenseOut."""

from __future__ import annotations

from contracts.schemas import DefenseName, DefenseOut

DEFENSES: tuple[DefenseName, ...] = ("none", "prompt", "pagevote", "guard", "guard_noprov")


def apply_defense(name: str, query: str, results: list[dict], lang: str) -> DefenseOut:
    """Dispatch on defense name.

    TODO (C, PLAN.md §8): implement "prompt", "pagevote", "guard" (= planted.guard.guard)
    and "guard_noprov" (Guard without provenance edges).
    """
    if name == "none":
        return DefenseOut(results=results, system_note=None, warnings=[], hedge_floor=None)
    if name in DEFENSES:
        raise NotImplementedError(f"defense {name!r} not implemented yet")
    raise ValueError(f"unknown defense {name!r}; expected one of {DEFENSES}")


def enforce(answer: str, hedge_floor: str | None, lang: str) -> str:
    """TODO (C, PLAN.md §8): delegate to planted.guard.hedge.enforce."""
    raise NotImplementedError
