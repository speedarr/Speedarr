"""
Demand-aware allocation helpers (issue #85).

Pure functions and a small stateful tracker used by the decision engine to move
unused bandwidth share from active clients that are not using it to active clients
that are saturating theirs. No engine or config imports: everything here is plain
data in, plain data out, so it can be unit-tested with dicts.
"""
from enum import Enum
from typing import Dict, Iterable, List, Optional


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


# Tunables (issue #85). Measured on the homelab 2026-09-15: reported speed lags a limit
# change by one 5 s poll and qBittorrent overshoots up to 4.4x while ramping, so two polls
# are needed before trusting "saturated"; a SLACK client sits at 1/1.5 = 0.67 of its limit,
# under the 0.9 line even with qBittorrent's +-20% steady-state noise.
DEMAND_SATURATION_RATIO = 0.9       # speed / last emitted limit at or above this = "wants more"
DEMAND_POLLS_TO_SATURATED = 2       # consecutive polls at or above the ratio
DEMAND_POLLS_TO_SLACK = 3           # consecutive polls below the ratio
DEMAND_HEADROOM_MULTIPLIER = 1.5    # a SLACK client's limit is its usage times this


class DemandState(str, Enum):
    UNKNOWN = "unknown"      # no evidence yet (fresh, errored, inactive, no last limit)
    SATURATED = "saturated"  # filling its limit: wants more
    SLACK = "slack"          # leaving share unused: can lend it


class _Entry:
    __slots__ = ("state", "up", "down")

    def __init__(self):
        self.state = DemandState.UNKNOWN
        self.up = 0
        self.down = 0


class DemandTracker:
    """
    Per-client saturation classifier for one direction (download or upload).

    Feed it every *active* client each poll with the speed it reported and the limit
    the engine last emitted for it. Counters give hysteresis: it takes
    DEMAND_POLLS_TO_SATURATED polls at or above the ratio to become SATURATED and
    DEMAND_POLLS_TO_SLACK below it to become SLACK; a crossing resets the other counter.
    """

    def __init__(self):
        self._entries: Dict[str, _Entry] = {}

    def state(self, client_id: str) -> DemandState:
        entry = self._entries.get(client_id)
        return entry.state if entry else DemandState.UNKNOWN

    def states(self) -> Dict[str, DemandState]:
        return {cid: e.state for cid, e in self._entries.items()}

    def observe(self, client_id: str, speed: float, last_limit: Optional[float]) -> DemandState:
        if last_limit is None or last_limit <= 0:
            self.reset(client_id)
            return DemandState.UNKNOWN
        entry = self._entries.setdefault(client_id, _Entry())
        if speed / last_limit >= DEMAND_SATURATION_RATIO:
            entry.up += 1
            entry.down = 0
            if entry.up >= DEMAND_POLLS_TO_SATURATED:
                entry.state = DemandState.SATURATED
        else:
            entry.down += 1
            entry.up = 0
            if entry.down >= DEMAND_POLLS_TO_SLACK:
                entry.state = DemandState.SLACK
        return entry.state

    def reset(self, client_id: str) -> None:
        self._entries[client_id] = _Entry()

    def prune(self, current_ids: Iterable[str]) -> None:
        keep = set(current_ids)
        self._entries = {cid: e for cid, e in self._entries.items() if cid in keep}


def apply_demand(
    target: Dict[str, float],
    states: Dict[str, DemandState],
    speeds: Dict[str, float],
    percents: Dict[str, float],
    safety_net_amount: float,
    enabled: bool,
) -> Dict[str, float]:
    """
    Move unused share from SLACK clients to SATURATED clients.

    target: the split from _target_split (every client, inactive ones included).
    states/speeds: only the active clients (inactive and errored clients are absent).

    Rules (spec section 3):
    - Off, or no SATURATED client: return the target untouched.
    - Each SLACK client keeps usage * DEMAND_HEADROOM_MULTIPLIER, clamped to
      [safety_net_amount, its target]; the difference to its target is freed.
    - SATURATED clients receive their target plus the freed total, weighted by their
      configured percents when all of them have one, else equally.
    - UNKNOWN clients, and clients absent from states, keep their target.
    The sum is preserved by construction.
    """
    result = dict(target)
    if not enabled:
        return result
    saturated = [c for c, s in states.items() if s == DemandState.SATURATED and c in target]
    if not saturated:
        return result

    freed = 0.0
    for client_id, state in states.items():
        if state != DemandState.SLACK or client_id not in target:
            continue
        share = target[client_id]
        wanted = speeds.get(client_id, 0.0) * DEMAND_HEADROOM_MULTIPLIER
        new_limit = min(max(wanted, safety_net_amount), share)
        freed += share - new_limit
        result[client_id] = new_limit

    weights = split_weights(saturated, percents)
    for client_id in saturated:
        result[client_id] = target[client_id] + freed * weights[client_id]
    return result
