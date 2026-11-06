"""Privacy budget ledger: the epsilon of every release adds up for the people in all of them.

One line per release, kept by the data controller next to the private outputs (never published). A cap stops a
release that would take a receiver's running total above what the scenario allows.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


class BudgetExceededError(ValueError):
    """The release would spend more privacy budget than allowed."""


def receiver_of(key_domain: str) -> str:
    """'HEALTH-S2/public/2026-W45' -> 'HEALTH-S2/public': the last part names the release, the rest the receiver."""
    return key_domain.rsplit("/", 1)[0]


@dataclass(frozen=True)
class LedgerEntry:
    release_id: str
    key_domain: str
    epsilon: float
    created_at: str


@dataclass(frozen=True)
class EpsilonLedger:
    path: Path
    cap: float | None = None  # most epsilon one receiver may receive in total; None = record only

    def entries(self) -> list[LedgerEntry]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [LedgerEntry(**json.loads(line)) for line in lines if line.strip()]

    def spent(self, receiver: str) -> float:
        """Total epsilon released so far to one receiver, e.g. 'HEALTH-S2/public' (all its key domains)."""
        return sum(e.epsilon for e in self.entries() if receiver_of(e.key_domain) == receiver)

    def record(self, release_id: str, key_domain: str, epsilon: float, created: datetime) -> float:
        """Add a release and return the new running total for its receiver; refuse it if it breaks the cap."""
        receiver = receiver_of(key_domain)
        total = self.spent(receiver) + epsilon
        if self.cap is not None and total > self.cap + 1e-9:
            raise BudgetExceededError(
                f"{receiver}: this release (epsilon {epsilon:g}) brings the total to {total:g}, "
                f"above the cap {self.cap:g}"
            )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entry = LedgerEntry(release_id, key_domain, epsilon, created.isoformat())
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.__dict__) + "\n")
        return total
