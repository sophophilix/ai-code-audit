"""The engagement policy, .audit/policy.yaml: per-client rules on top of the fixed ones.

Safety rules (read-only, never run the target, evidence) are not configurable.
This file holds what does vary by client, starting with network lookups, so the
kit has the capability and each engagement decides whether to use it.
"""

from __future__ import annotations

from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from audit_kit.errors import AuditKitError
from audit_kit.workspace import Workspace

POLICY_PATH = ".audit/policy.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Network(_Strict):
    """Which outbound requests the kit itself may make."""

    metadata_lookups: Literal["deny", "allow"] = "deny"


class Policy(_Strict):
    """The whole of .audit/policy.yaml. A missing file means every default (deny)."""

    version: Literal[1] = 1
    network: Network = Network()
    # ADR 0005: whether `kit sandbox` may run the target's code in a container.
    sandbox: Literal["deny", "allow"] = "deny"


def load_policy(ws: Workspace) -> Policy:
    """Read the workspace's policy; a missing file gives the defaults.

    Raises:
        AuditKitError: If the file isn't valid YAML or doesn't match the model.
    """
    if not ws.is_file(POLICY_PATH):
        return Policy()
    try:
        raw = yaml.safe_load(ws.read_text(POLICY_PATH)) or {}
        return Policy.model_validate(raw)
    except yaml.YAMLError as exc:
        raise AuditKitError(f"{POLICY_PATH}: invalid YAML ({exc})") from exc
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or "(top level)"
        raise AuditKitError(f"{POLICY_PATH}: {where}: {first['msg']}") from exc
