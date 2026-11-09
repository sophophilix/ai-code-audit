# ADR 0005: A small Docker sandbox for the few checks that need to run code

> Status: Approved
> Created: 2026-11-07T12:03:16Z
> Last reviewed: 2026-11-07T12:21:51Z
> Next review: Not scheduled

## Review guide

Decision requested: let the kit, never an agent, run four kinds of job inside one
locked-down Docker container, when the tech lead allows it for an engagement. This
relaxes `AGENTS.md` rule 2 for those jobs only, and replaces ADR 0002 D7.

Check these points:

- [ ] The four jobs (D2) are worth it, and nothing else is included.
- [ ] The container limits (D3) are enough for code we don't trust.
- [ ] The approval sits with the tech lead, per engagement (D4).

Respond with one of:

- `approve`
- `approve with follow-up: <action>`
- `request changes: <specific issue>`

## Summary

Some evidence needs code to run: whether the target's tests pass, what knip finds,
whether a claimed bug really fails. Rule 2 forbids running the target, because
install scripts and app code would run with the auditor's credentials, network
routes and agent harness. A container with no network, no host files and no
secrets removes that risk for a few well-defined jobs.

The kit stays small on purpose. A capability is added only if it changes a
finding's verdict or severity, or replaces something a person does by hand.
Integration stubs, booting the whole app, ZAP scans and load tests don't pass that
test yet, so they stay out.

## Decision

### D1. One command, one image

`kit sandbox <job>` builds or reuses one image, pinned by digest, with the Node.js
version from the target's `engines` or `.nvmrc` (the current LTS if neither
says), plus knip and dependency-cruiser at pinned versions. Docker is the only
runtime supported.

### D2. Four jobs

| Job | What runs | Output |
|---|---|---|
| `structure` | knip and dependency-cruiser over the installed copy | `scans/knip.json`, `scans/depcruise.json` |
| `tests` | the target's own test command, with a time limit | `scans/dynamic/tests.txt`: pass, fail, or failed to run, and why |
| `prove <finding>` | a failing test an agent wrote for a Critical or High finding, saved under `.audit/work/` | `scans/dynamic/prove-<id>.txt` |
| `try` | a snippet of at most 20 lines an agent wrote, with no target mounted | stdout and the exit code |

Agents write the test or snippet as a file and the tech lead, or the coordinator
under the policy, starts the job. Agents never get a shell inside the container.

### D3. Container limits

1. **Install:** `npm ci --ignore-scripts` from the target's lockfile, in a container
   whose only network is the package registry. No lockfile, no install, and the
   job records why.
2. **Every other step:** `--network none`, non-root user, `--read-only` with a
   tmpfs for writes, `--cap-drop ALL`, `--security-opt no-new-privileges`, CPU,
   memory and time limits.
3. **What goes in:** a copy of the snapshot (never the workspace itself) and a
   fake `.env` with dummy values for every variable discovery lists. No host home
   directory, Docker socket, SSH agent or real environment variables.
4. **What comes out:** only the output files above, copied back by the kit.

Calls to real integrations fail, because there is no network. That's recorded as a
result, not worked around: "the tests need a live SQL Server" is itself a finding
about the test suite.

### D4. Approval

`.audit/policy.yaml` gains `sandbox: deny | allow`, default `deny`, set by the tech
lead per engagement. The run log records the decision, the image digest and every
job run.

## Consequences

- Unused code and dependency cycles come from knip and dependency-cruiser in the
  sandbox; the kit's own `unused.json` stays for workspaces without Docker.
- A Critical or High finding can carry "proved by a failing test" as evidence.
- Agents can check how the language behaves instead of asserting it.

## Rejected options

- **Integration stubs and booting the full app.** Each engagement needs different
  stubs, Entra ID and Microsoft Graph are hard to fake, and the result is only
  partly realistic. That's a test environment, which the client's team needs and
  the audit should recommend. Add a stub for one integration only when a High
  finding's severity depends on it.
- **ZAP scans and load tests.** Agents write experiment plans for the team, as ADR
  0002 D5 describes.
- **An egress proxy with an allow list.** Not needed while installs run with
  scripts off and every later step has no network.

## Risks and open items

- **Container escapes.** Docker isn't a strong boundary against a kernel exploit.
  The limits in D3 reduce the surface; a VM-based runtime is the next step if a
  client requires it.
- **Registry access during install.** A malicious package can still be downloaded,
  though not run, during install. Its code runs only in the network-less steps.
- **Tool claims to confirm.** The knip and dependency-cruiser output formats and
  flags need checking against the pinned versions before parsing them.
- **Not yet built.**

## Review history

| Reviewed at | Decision | Notes |
|---|---|---|
| 2026-11-07T12:03:16Z | Drafted | From the tech lead's question about testing in isolation and keeping the kit small. |
| 2026-11-07T12:21:51Z | Approved | Approved by the tech lead. |
| 2026-11-07T12:38:31Z | Built | Built in 0.15.0: `kit sandbox` with the four jobs, `sandbox` in policy.yaml, and the image. The base image is pinned by tag, not digest; the built image id is logged per job. Tested with a fake Docker only. |
| 2026-11-07T13:06:30Z | Verified | First run against a real daemon (Docker 29.2.1, colima): all four jobs, the isolation (read-only root, no network, host uid, no host environment) and both timeouts behave as decided. Fixed in the run: `readonly` mount syntax, and the copy and agent files live under the home folder so a VM-based daemon can see them. |
