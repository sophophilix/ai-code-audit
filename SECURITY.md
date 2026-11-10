# Security policy

## Report a vulnerability

Don't open a public issue for a security problem. Use GitHub's private
reporting instead: go to the **Security** tab of this repository and select
**Report a vulnerability**.

Include what you found, the commit or version, and the steps to show it.
Don't include real client data, credentials or personal data.

## What's in scope

- The `audit-kit` Python package (`src/audit_kit/`) and `bin/` scripts.
- Anything that lets an audit agent write outside `.audit/`, run the target,
  or reach the network when the kit's rules say it can't (`AGENTS.md`).
- The pinned third-party skills and tools, as the kit uses them
  (`THIRD_PARTY.md`).

## Supported versions

Only the latest release gets fixes. The kit is at 0.x and hasn't yet passed
its own evaluation (`README.md`).
