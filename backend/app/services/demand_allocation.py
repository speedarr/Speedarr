"""
Demand-aware allocation helpers (issue #85).

Pure functions and a small stateful tracker used by the decision engine to move
unused bandwidth share from active clients that are not using it to active clients
that are saturating theirs. No engine or config imports: everything here is plain
data in, plain data out, so it can be unit-tested with dicts.
"""
from typing import Dict, List


def split_weights(active: List[str], percents: Dict[str, float]) -> Dict[str, float]:
    """
    Normalised weights for the active clients.

    Configured percents are used only when every active client has one and they
    sum above zero (the existing "all configured or equal" rule); otherwise the
    split is equal. Percents of inactive clients are ignored.
    """
    if not active:
        return {}
    if all(c in percents for c in active):
        raw = {c: float(percents[c]) for c in active}
        total = sum(raw.values())
        if total > 0:
            return {c: v / total for c, v in raw.items()}
    return {c: 1.0 / len(active) for c in active}
