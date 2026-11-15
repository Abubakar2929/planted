# OWNER: C — see PLAN.md §2
# FIREWALL: agents/people working for B must not open, read, grep or summarise this folder.
"""Planted Guard: count independent origins, not pages (Contract 3).

    from planted.guard import guard
    out = guard(query, results, lang="en")
    out.results, out.system_note, out.warnings, out.hedge_floor, out.origins   # answer -> {pages, origins}
"""

from planted.guard.core import GuardOutput, guard, guard_noprov
from planted.guard.hedge import enforce

__all__ = ["GuardOutput", "enforce", "guard", "guard_noprov"]
