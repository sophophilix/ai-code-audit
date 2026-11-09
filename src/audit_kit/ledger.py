"""The file review's pass ledger and unit status (ADR 0007 D8).

`passes.jsonl` gets one line per attempt: turns, tokens by type, cost and
seconds as Claude Code reported them. `status.tsv` holds each unit's latest
status, which the coordinator reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast, get_args

from pydantic import BaseModel, ConfigDict, Field

from audit_kit.brief import WORK
from audit_kit.workspace import Workspace

STATUS = WORK / "status.tsv"
PASSES = WORK / "passes.jsonl"
STATUS_HEADER = "unit\tstatus\tpass\ttokens\tupdated_utc\n"
UnitStatus = Literal[
    "pending", "running", "done", "reused", "interrupted", "gate-failed"
]
Outcome = Literal["ok", "checks failed", "error", "rate limited"]


class PassRow(BaseModel):
    """One attempt at one unit's pass."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: str
    unit: str
    label: str
    model: str
    attempt: int = Field(ge=1)
    outcome: Outcome
    started_utc: str
    turns: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_read_tokens: int = Field(ge=0)
    cache_write_tokens: int = Field(ge=0)
    cost_usd: float | None
    seconds: float = Field(ge=0)
    session_id: str
    problems: list[str] = Field(default_factory=list)


def append(ws: Workspace, row: PassRow) -> None:
    """Add one attempt to the ledger."""
    ws.append_text(PASSES, row.model_dump_json() + "\n")


def read(ws: Workspace) -> list[PassRow]:
    """Return every attempt in the ledger, in the order they ran.

    Raises:
        pydantic.ValidationError: If a line isn't a ledger row.
    """
    if not ws.is_file(PASSES):
        return []
    text = ws.read_text(PASSES, limit=200_000_000)
    return [PassRow.model_validate_json(line) for line in text.splitlines() if line]


@dataclass(frozen=True)
class StatusRow:
    """One unit's latest status."""

    unit: str
    status: UnitStatus
    label: str
    tokens: int
    updated_utc: str

    def line(self) -> str:
        """Render as one status.tsv line."""
        return f"{self.unit}\t{self.status}\t{self.label}\t{self.tokens}\t{self.updated_utc}\n"


def read_status(ws: Workspace) -> dict[str, StatusRow]:
    """Return status.tsv by unit id; empty if it hasn't been written.

    A row with a status the kit doesn't write is left out, so the unit is
    treated as not yet reviewed.
    """
    if not ws.is_file(STATUS):
        return {}
    rows: dict[str, StatusRow] = {}
    for line in ws.read_text(STATUS).splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) >= 5 and cols[1] in get_args(UnitStatus):
            tokens = int(cols[3]) if cols[3].isdigit() else 0
            status = cast(UnitStatus, cols[1])
            rows[cols[0]] = StatusRow(cols[0], status, cols[2], tokens, cols[4])
    return rows


def write_status(ws: Workspace, rows: dict[str, StatusRow]) -> None:
    """Rewrite status.tsv, in unit order."""
    ws.write_text(STATUS, STATUS_HEADER + "".join(rows[k].line() for k in sorted(rows)))
