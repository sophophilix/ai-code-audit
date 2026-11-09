"""The workspace state file, .audit/.workspace: one `key: value` per line."""

from __future__ import annotations

from audit_kit.workspace import Workspace

STATE_FILE = ".audit/.workspace"


class State:
    """Read and update a workspace's state file, keeping key order."""

    def __init__(self, ws: Workspace) -> None:
        """Load the state file (missing means empty)."""
        self.ws = ws
        self.values: dict[str, str] = {}
        if ws.is_file(STATE_FILE):
            for line in ws.read_text(STATE_FILE).splitlines():
                key, sep, value = line.partition(": ")
                if sep and key not in self.values:
                    self.values[key] = value

    def get(self, key: str) -> str:
        """Return a value, or an empty string."""
        return self.values.get(key, "")

    def set(self, key: str, value: str) -> None:
        """Set a value and save the file."""
        self.values[key] = value
        self.ws.write_text(
            STATE_FILE, "".join(f"{k}: {v}\n" for k, v in self.values.items())
        )

    def lines(self) -> list[str]:
        """Return the file's lines for display."""
        return [f"{k}: {v}" for k, v in self.values.items()]
