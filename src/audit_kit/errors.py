"""Exceptions that the CLI maps to exit status 2 (invalid input or refused operation)."""


class AuditKitError(Exception):
    """Base class for expected, user-actionable failures."""


class WorkspaceError(AuditKitError):
    """A workspace path or file operation was refused or failed."""


class OutsideWorkspaceError(WorkspaceError):
    """A path resolves outside the workspace root or passes through a symlink."""


class SeedError(AuditKitError):
    """Seeding was refused or could not be planned."""
